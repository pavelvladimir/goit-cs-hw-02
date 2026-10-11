"""Stop only the disposable Percona and recover without restarting the API."""

import json
import time
from textwrap import dedent
from uuid import uuid4

import httpx2
import pytest

from tests.integration.stack import ComposeStack

pytestmark = pytest.mark.integration


def app_process_identity(stack: ComposeStack) -> tuple[str, str]:
    container_id = stack.run("ps", "--quiet", "app")
    assert container_id
    started_at_ticks = stack.run(
        "exec",
        "-T",
        "app",
        "/app/.venv/bin/python3",
        "-c",
        dedent("""
            from pathlib import Path

            assert 'conf.server' in Path('/proc/1/cmdline').read_text().split(chr(0))
            # Field 22 is process start time; PID 1 alone survives a restart.
            fields = Path('/proc/1/stat').read_text().rsplit(')', 1)[1].split()
            print(fields[19])
        """),
    )
    assert started_at_ticks.isdecimal()
    return container_id, started_at_ticks


def test_database_outage_and_recovery_without_app_restart(
    stack: ComposeStack,
    http_client: httpx2.Client,
) -> None:
    # Check the effective libpq option on a real connection inside the image,
    # not just a Settings value or a mock of create_engine. Print no credentials.
    timeout = stack.run(
        "exec",
        "-T",
        "app",
        "/app/.venv/bin/python3",
        "-c",
        dedent("""
            from conf.db import engine

            with engine.connect() as connection:
                driver = connection.connection.driver_connection
                print(driver.get_dsn_parameters()['connect_timeout'])
        """),
    )
    assert int(timeout) == stack.connect_timeout
    # Warm the application's own pool so the outage also invalidates old sockets.
    healthy = http_client.get("/healthchecker")
    assert healthy.status_code == 200
    assert healthy.json() == {"message": "Welcome to FastAPI!"}
    identity = app_process_identity(stack)
    budget = stack.connect_timeout + 2.0
    failed_requests: list[str] = []

    # Every command carries the fixture's random -p project and temporary env.
    # Always restore the DB, even if the HTTP, latency or log assertion fails.
    assert stack.project.startswith("hw02-test-")
    try:
        stack.run("stop", "--timeout", "5", "db")
        assert stack.run("ps", "--status", "exited", "--quiet", "db")
        for _ in range(2):
            request_id = str(uuid4())
            failed_requests.append(request_id)
            started = time.monotonic()
            response = http_client.get(
                "/healthchecker",
                headers={"X-Request-ID": request_id},
                timeout=budget,
            )
            elapsed = time.monotonic() - started
            assert elapsed < budget, f"DB failure response took {elapsed:.3f}s"
            assert response.status_code == 500
            assert response.json() == {"detail": "Error connecting to the database"}
            assert response.headers["x-request-id"] == request_id
        assert app_process_identity(stack) == identity
        assert http_client.get("/docs", timeout=budget).status_code == 200

        # The response can arrive just before middleware emits the access log.
        deadline = time.monotonic() + 3
        while True:
            output = stack.run("logs", "--no-color", "--no-log-prefix", "app")
            records = [json.loads(line) for line in output.splitlines()]
            access_ids = {
                record.get("request_id")
                for record in records
                if record["logger"] == "app.access"
            }
            if set(failed_requests) <= access_ids or time.monotonic() >= deadline:
                break
            time.sleep(0.05)
        for request_id in failed_requests:
            related = [
                record for record in records if record.get("request_id") == request_id
            ]
            assert len(related) == 2
            error, access = related
            assert error["logger"] == "main"
            assert error["level"] == "ERROR"
            assert error["message"] == "Database health check failed"
            assert error["exception"]["type"] == "OperationalError"
            assert error["exception"]["frames"]
            assert (
                access.items()
                >= {
                    "logger": "app.access",
                    "level": "ERROR",
                    "message": "request_completed",
                    "method": "GET",
                    "path": "/healthchecker",
                    "status": 500,
                }.items()
            )
            assert 0 <= access["duration_ms"] < budget * 1000
        for password in (stack.password, stack.admin_password):
            assert password.get_secret_value() not in output
    finally:
        stack.run("start", "--wait", "--wait-timeout", "60", "db", timeout=90)

    # The very first request after DB readiness must recover; no API restart,
    # pool.dispose() or client-side retry can conceal a stale-connection error.
    for _ in range(3):
        recovered = http_client.get("/healthchecker", timeout=budget)
        assert recovered.status_code == 200
        assert recovered.json() == healthy.json()
    assert app_process_identity(stack) == identity
