"""Stop PID 1 while a real HTTP request holds a PostgreSQL connection."""

import json
import subprocess
import time
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import httpx2
import pytest
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.pool import NullPool

from tests.integration.stack import ROOT, ComposeStack

pytestmark = pytest.mark.integration
LOCK_KEY = 731942
STOP_BUDGET = 20


@pytest.fixture
def shutdown_stack() -> Generator[ComposeStack]:
    with TemporaryDirectory(prefix="hw02-shutdown-") as temporary:
        directory = Path(temporary)
        stack = ComposeStack.create(directory)
        override = directory / "shutdown.compose.yaml"
        # JSON is valid YAML; serialize host paths without manual quoting.
        override.write_text(
            json.dumps(
                {
                    "services": {
                        "app": {
                            "command": ["/app/shutdown_probe.py"],
                            "environment": {"SHUTDOWN_PROBE_LOCK": str(LOCK_KEY)},
                            "volumes": [
                                {
                                    "type": "bind",
                                    "source": str(
                                        ROOT / "tests/integration/shutdown_probe.py"
                                    ),
                                    "target": "/app/shutdown_probe.py",
                                    "read_only": True,
                                }
                            ],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        stack.command.extend(["-f", str(override)])
        try:
            stack.run(
                "up", "--build", "-d", "--wait", "--wait-timeout", "90", timeout=600
            )
            yield stack
        finally:
            stack.cleanup()


def docker_output(stack: ComposeStack, *arguments: str) -> str:
    result = subprocess.run(
        ["docker", *arguments],
        env=stack.environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, stack.redact(result.stderr)
    return result.stdout.strip()


def wait_for_blocked_request(admin: Connection, username: str) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        blocked = admin.execute(
            text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE usename = :username AND state = 'active' "
                "AND pg_backend_pid() = ANY(pg_blocking_pids(pid))"
            ),
            {"username": username},
        ).scalar_one()
        if blocked == 1:
            return
        time.sleep(0.05)
    pytest.fail("The HTTP request never waited for the test's database lock")


def test_sigterm_drains_request_closes_pool_and_exits_without_sigkill(
    shutdown_stack: ComposeStack,
) -> None:
    stack = shutdown_stack
    assert stack.project.startswith("hw02-test-")
    container_id = stack.run("ps", "--quiet", "app")
    assert container_id
    base_url = f"http://127.0.0.1:{stack.port('app', 8000)}"
    request_id = str(uuid4())
    admin_engine = create_engine(
        stack.url(admin=True),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={"connect_timeout": 3},
    )
    try:
        with (
            admin_engine.connect() as admin,
            ThreadPoolExecutor(max_workers=2) as workers,
        ):
            admin.execute(text("SELECT pg_advisory_lock(:key)"), {"key": LOCK_KEY})

            def request() -> httpx2.Response:
                with httpx2.Client(
                    base_url=base_url, timeout=30, trust_env=False
                ) as client:
                    return client.get(
                        "/healthchecker",
                        headers={"X-Request-ID": request_id, "X-Shutdown-Probe": "1"},
                    )

            pending_request = workers.submit(request)
            try:
                wait_for_blocked_request(admin, stack.username)
                assert not pending_request.done()
                since = datetime.now(UTC).isoformat()
                started = time.monotonic()
                # No --timeout override: exercise the real stop_grace_period.
                stopping = workers.submit(stack.run, "stop", "app", timeout=35)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    output = stack.run("logs", "--no-color", "--no-log-prefix", "app")
                    records = [json.loads(line) for line in output.splitlines()]
                    if any(
                        record["message"].startswith("Waiting for connections to close")
                        for record in records
                    ):
                        break
                    time.sleep(0.05)
                else:
                    pytest.fail("Uvicorn did not begin draining the active request")
                assert not pending_request.done(), "The locked request finished early"
                assert not stopping.done(), "The server exited with an active request"
            finally:
                admin.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY}
                )

            response = pending_request.result(timeout=10)
            assert response.status_code == 200
            assert response.json() == {"message": "Welcome to FastAPI!"}
            assert response.headers["x-request-id"] == request_id
            stopping.result(timeout=STOP_BUDGET + 5)
            elapsed = time.monotonic() - started
            assert elapsed < STOP_BUDGET, f"Shutdown took {elapsed:.3f}s"
            assert (
                admin.execute(
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE usename = :username"
                    ),
                    {"username": stack.username},
                ).scalar_one()
                == 0
            )
    finally:
        admin_engine.dispose()

    inspection = json.loads(
        docker_output(
            stack,
            "inspect",
            "--format",
            '{"state":{{json .State}},"stop_signal":{{json .Config.StopSignal}},'
            '"stop_timeout":{{json .Config.StopTimeout}},'
            '"path":{{json .Path}},"args":{{json .Args}}}',
            container_id,
        )
    )
    assert inspection["stop_signal"] == "SIGTERM"
    assert inspection["stop_timeout"] == STOP_BUDGET
    assert inspection["path"] == "/app/.venv/bin/python3"
    assert inspection["args"] == ["/app/shutdown_probe.py"]
    state = inspection["state"]
    assert state["Status"] == "exited"
    assert state["Pid"] == 0
    assert state["OOMKilled"] is False
    assert state["Error"] == ""
    # Uvicorn re-raises SIGTERM after cleanup. PID 1 can ignore its restored
    # default handler (exit 0); other runtimes may report 128 + SIGTERM (143).
    assert state["ExitCode"] in (0, 143)

    events = [
        json.loads(line)
        for line in docker_output(
            stack,
            "events",
            "--since",
            since,
            "--until",
            datetime.now(UTC).isoformat(),
            "--filter",
            f"container={container_id}",
            "--format",
            "{{json .}}",
        ).splitlines()
    ]
    signals = [
        event["Actor"]["Attributes"]["signal"]
        for event in events
        if event["Action"] == "kill"
    ]
    assert signals in (["15"], ["SIGTERM"]), signals
    deaths = [event for event in events if event["Action"] == "die"]
    assert len(deaths) == 1
    assert int(deaths[0]["Actor"]["Attributes"]["exitCode"]) == state["ExitCode"]

    output = stack.run("logs", "--no-color", "--no-log-prefix", "app")
    records = [json.loads(line) for line in output.splitlines()]
    messages = [record["message"] for record in records]
    assert "Started server process [1]" in messages
    access = [record for record in records if record.get("request_id") == request_id]
    assert len(access) == 1
    assert access[0]["logger"] == "app.access"
    assert access[0]["message"] == "request_completed"
    assert access[0]["status"] == 200
    assert records.index(access[0]) > messages.index("Shutting down")
    assert records.index(access[0]) < messages.index("Database connection pool closed")
    assert (
        messages.index("Database connection pool closed")
        < messages.index("Observed database connections are closed")
        < messages.index("Application shutdown complete.")
        < messages.index("Finished server process [1]")
    )
    assert all(record["level"] not in {"ERROR", "CRITICAL"} for record in records)
    for password in (stack.password, stack.admin_password):
        assert password.get_secret_value() not in output
