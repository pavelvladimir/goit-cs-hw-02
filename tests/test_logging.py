import asyncio
import io
import json
import logging
import sys
import weakref
from collections.abc import Generator
from datetime import datetime
from unittest.mock import MagicMock, patch
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.exc import OperationalError
from starlette.types import Message, Receive, Scope, Send

from conf.logging import JsonFormatter, configure_logging, request_id_context
from conf.middleware import RequestLoggingMiddleware
from conf.server import main as run_server
from conf.settings import Settings


@pytest.fixture
def log_output() -> Generator[io.StringIO]:
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JsonFormatter("unit-test-only"))
    root = logging.getLogger()
    old_level = root.level
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)
    try:
        yield output
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)
        handler.close()


@pytest.fixture
def isolated_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for key, value in {
        "DB_HOST": "test-db.invalid",
        "DB_PORT": "5432",
        "DB_CONNECT_TIMEOUT": "3",
        "SHUTDOWN_GRACE_SECONDS": "20",
        "DB_NAME": "test_db",
        "DB_USER": "test_app",
        "DB_PASSWORD": "unit-test-only",
        "DB_PASSWORD_FILE": "",
        "LOG_LEVEL": "INFO",
    }.items():
        monkeypatch.setenv(key, value)
    # dictConfig closes registered handlers. Give it an isolated registry so
    # exercising real configuration does not close pytest's capture handlers.
    root = logging.RootLogger(logging.WARNING)
    monkeypatch.setattr(logging, "root", root)
    monkeypatch.setattr(logging.Logger, "root", root)
    monkeypatch.setattr(logging.Logger, "manager", logging.Manager(root))
    monkeypatch.setattr(logging, "_handlers", weakref.WeakValueDictionary())
    monkeypatch.setattr(logging, "_handlerList", [])


def test_shared_configuration_filters_and_does_not_duplicate(
    isolated_logging: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("DEBUG", "unit-test-only")
    for name in ("main", "uvicorn.error", "sqlalchemy.engine"):
        logging.getLogger(name).warning("probe")
    logging.getLogger("main").debug("debug allowed")
    logging.getLogger("sqlalchemy.engine").info("SELECT sensitive_data")
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [record["logger"] for record in records] == [
        "main",
        "uvicorn.error",
        "sqlalchemy.engine",
        "main",
    ]
    assert all(record["message"] != "SELECT sensitive_data" for record in records)

    configure_logging("ERROR")
    logging.getLogger("uvicorn.error").info("filtered")
    logging.getLogger("main").error("visible")
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(records) == 1
    assert records[0]["message"] == "visible"


def test_formatter_redacts_password_and_omits_exception_payloads() -> None:
    secret = 'private@:/?#\\" secret'
    formatter = JsonFormatter(secret)
    try:
        raise OperationalError(
            "SELECT secret_column",
            {"token": "secret-token"},
            RuntimeError("sensitive original error"),
        )
    except OperationalError:
        record = logging.LogRecord(
            "main",
            logging.ERROR,
            __file__,
            1,
            "Failure\npassword=%s url=%s",
            (secret, quote(secret, safe="")),
            sys.exc_info(),
        )
    record.authorization = "Bearer secret-token"
    record.stack_info = "private source and local variables"
    line = formatter.format(record)
    payload = json.loads(line)
    assert len(line.splitlines()) == 1
    assert payload["message"] == "Failure\npassword=[REDACTED] url=[REDACTED]"
    offset = datetime.fromisoformat(payload["timestamp"]).utcoffset()
    assert offset is not None and offset.total_seconds() == 0
    assert payload["exception"]["type"] == "OperationalError"
    assert payload["exception"]["frames"][-1]["function"] == (
        "test_formatter_redacts_password_and_omits_exception_payloads"
    )
    for value in (
        secret,
        "secret-token",
        "secret_column",
        "sensitive original error",
        "private source",
        "authorization",
    ):
        assert value not in line


@pytest.mark.parametrize("secret", ['private@:/?#\\" секрет', '"', "\\", "200"])
def test_formatter_redacts_nested_strings_without_changing_json_structure(
    secret: str,
) -> None:
    encoded = json.dumps(secret, ensure_ascii=False)[1:-1]
    ascii_encoded = json.dumps(secret, ensure_ascii=True)[1:-1]

    def crash() -> None:
        raise RuntimeError("exception text must remain omitted")

    crash.__code__ = crash.__code__.replace(
        co_filename=f"/private/{encoded}/handler.py", co_name=f"handle_{secret}"
    )
    with pytest.raises(RuntimeError) as caught:
        crash()
    error = caught.value
    record = logging.LogRecord(
        f"logger.{secret}",
        logging.ERROR,
        __file__,
        1,
        "Encoded password=%s",
        (ascii_encoded,),
        (type(error), error, error.__traceback__),
    )
    record.path = f"/private/{quote(secret, safe='')}/"
    record.status = 200
    record.duration_ms = 12.5
    record.invalid_settings = [{"field": f"db_{secret}", "type": "value_error"}]

    line = JsonFormatter(secret).format(record)
    payload = json.loads(line)
    assert len(line.splitlines()) == 1
    assert payload["logger"] == "logger.[REDACTED]"
    assert payload["message"] == "Encoded password=[REDACTED]"
    assert payload["path"] == "/private/[REDACTED]/"
    assert payload["status"] == 200
    assert payload["duration_ms"] == 12.5
    assert payload["invalid_settings"] == [
        {"field": "db_[REDACTED]", "type": "value_error"}
    ]
    assert payload["exception"]["type"] == "RuntimeError"
    assert payload["exception"]["frames"][-1] == {
        "file": "/private/[REDACTED]/handler.py",
        "line": crash.__code__.co_firstlineno + 1,
        "function": "handle_[REDACTED]",
    }
    assert "exception text must remain omitted" not in line
    # Other handlers receive the original record and its nested values.
    assert record.__dict__["path"] == f"/private/{quote(secret, safe='')}/"
    assert record.__dict__["invalid_settings"][0]["field"] == f"db_{secret}"


@pytest.mark.parametrize("supplied", [None, "invalid", "x" * 36, str(uuid4())])
def test_request_id_and_access_log(
    client: TestClient,
    log_output: io.StringIO,
    supplied: str | None,
) -> None:
    response = client.get(
        "/healthchecker?token=private-query",
        headers={
            "Authorization": "Bearer private-header",
            **({"X-Request-ID": supplied} if supplied is not None else {}),
        },
    )
    request_id = response.headers["x-request-id"]
    assert str(UUID(request_id)) == request_id
    if supplied is not None and supplied != "invalid" and supplied != "x" * 36:
        assert request_id == supplied
    records = [json.loads(line) for line in log_output.getvalue().splitlines()]
    access = [record for record in records if record["logger"] == "app.access"]
    assert len(access) == 1
    assert (
        access[0].items()
        >= {
            "request_id": request_id,
            "method": "GET",
            "path": "/healthchecker",
            "status": 200,
            "level": "INFO",
            "message": "request_completed",
        }.items()
    )
    assert access[0]["duration_ms"] >= 0
    # Only our access records are relevant: the test-client logger logs URLs.
    assert "private-query" not in json.dumps(access)
    assert "private-header" not in json.dumps(access)
    assert request_id_context.get() is None


def test_database_error_has_correlated_trace_once(
    client: TestClient,
    db_session: MagicMock,
    log_output: io.StringIO,
) -> None:
    db_session.execute.side_effect = OperationalError(
        "SELECT secret_column", {"token": "secret-token"}, RuntimeError("private-error")
    )
    response = client.get("/healthchecker")
    records = [json.loads(line) for line in log_output.getvalue().splitlines()]
    related = [
        record
        for record in records
        if record.get("request_id") == response.headers["x-request-id"]
    ]
    assert len(related) == 2
    assert all(record["level"] == "ERROR" for record in related)
    assert sum("exception" in record for record in related) == 1
    assert "private-error" not in log_output.getvalue()
    assert "secret-token" not in log_output.getvalue()
    assert "secret_column" not in log_output.getvalue()


def test_unmatched_path_and_body_are_not_logged(
    client: TestClient,
    log_output: io.StringIO,
) -> None:
    response = client.post("/private-path", content="private-body")
    records = [json.loads(line) for line in log_output.getvalue().splitlines()]
    access = next(record for record in records if record["logger"] == "app.access")
    assert access["path"] == "<unmatched>"
    assert access["status"] == response.status_code == 404
    assert access["level"] == "WARNING"
    assert "private-" not in json.dumps(access)


def test_unhandled_error_keeps_id_for_uvicorn_and_500_response(
    log_output: io.StringIO,
) -> None:
    app = FastAPI()

    @app.get("/crash")
    def crash() -> None:
        raise RuntimeError("private-error")

    request_id = str(uuid4())
    with TestClient(RequestLoggingMiddleware(app)) as client:
        with pytest.raises(RuntimeError) as caught:
            client.get("/crash", headers={"X-Request-ID": request_id})
        # Uvicorn logs the propagated error outside the request context.
        error = caught.value
        logging.getLogger("uvicorn.error").error(
            "Exception in ASGI application",
            exc_info=(type(error), error, error.__traceback__),
        )
    records = [json.loads(line) for line in log_output.getvalue().splitlines()]
    related = [record for record in records if record.get("request_id") == request_id]
    assert len(related) == 2
    assert related[0]["status"] == 500
    assert related[0]["message"] == "request_completed"
    assert "exception" in related[1]
    assert "private-error" not in log_output.getvalue()
    assert request_id_context.get() is None
    with TestClient(
        RequestLoggingMiddleware(app), raise_server_exceptions=False
    ) as client:
        response = client.get("/crash", headers={"X-Request-ID": request_id})
        assert response.status_code == 500
        assert response.headers["x-request-id"] == request_id


def test_concurrent_requests_keep_independent_context(log_output: io.StringIO) -> None:
    app = FastAPI()

    @app.get("/items/{item}")
    async def item(item: str) -> dict[str, str | None]:
        await asyncio.sleep(0)
        return {"request_id": request_id_context.get()}

    async def exercise() -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=RequestLoggingMiddleware(app)),
            base_url="http://test",
        ) as client:
            ids = [str(uuid4()), str(uuid4())]
            responses = await asyncio.gather(
                *(
                    client.get("/items/private-value", headers={"X-Request-ID": value})
                    for value in ids
                )
            )
            assert [response.json()["request_id"] for response in responses] == ids
            assert request_id_context.get() is None

    asyncio.run(exercise())
    records = [json.loads(line) for line in log_output.getvalue().splitlines()]
    access = [record for record in records if record["logger"] == "app.access"]
    assert len({record["request_id"] for record in access}) == 2
    assert all(record["path"] == "/items/{item}" for record in access)


def test_interrupted_response_is_recorded_and_error_propagates(
    log_output: io.StringIO,
) -> None:
    async def broken_stream(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"part", "more_body": True})
        raise RuntimeError("stream interrupted")

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        pass

    async def exercise() -> None:
        with pytest.raises(RuntimeError, match="stream interrupted"):
            await RequestLoggingMiddleware(broken_stream)(
                {"type": "http", "headers": [], "method": "GET"}, receive, send
            )
        assert request_id_context.get() is None

    asyncio.run(exercise())
    records = [json.loads(line) for line in log_output.getvalue().splitlines()]
    record = next(record for record in records if record["logger"] == "app.access")
    assert record["message"] == "request_incomplete"
    assert record["status"] == 200
    assert record["level"] == "ERROR"


def test_launcher_uses_shared_logging_and_one_access_logger(
    isolated_logging: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(
        db_host="db",
        db_name="test",
        db_user="test_app",
        db_password=SecretStr("unit-test-only"),
        db_password_file=None,
        log_level="WARNING",
        shutdown_grace_seconds=30,
    )
    monkeypatch.setenv("PORT", "8123")
    with (
        patch("conf.server.Settings", return_value=settings),
        patch("conf.server.uvicorn.run") as run,
    ):
        run_server()
    run.assert_called_once_with(
        "main:application",
        host="0.0.0.0",
        port=8123,
        log_config=None,
        access_log=False,
        lifespan="on",
        timeout_graceful_shutdown=25,
    )
    logging.getLogger("uvicorn.error").info("filtered")
    logging.getLogger("main").warning("visible")
    assert len(capsys.readouterr().out.splitlines()) == 1


def test_invalid_configuration_exits_with_safe_json(
    isolated_logging: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "private-invalid-input")
    with pytest.raises(SystemExit) as caught:
        run_server()
    assert caught.value.code == 1
    output = capsys.readouterr().out
    record = json.loads(output)
    assert {"field": "log_level", "type": "literal_error"} in record["invalid_settings"]
    assert "private-invalid-input" not in output
