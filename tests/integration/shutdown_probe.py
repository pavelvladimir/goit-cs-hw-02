"""Test-only bootstrap, bind-mounted into a disposable application container."""

import logging
import os
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from typing import Protocol

from fastapi import FastAPI, Request
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from conf.db import engine, get_db
from conf.server import main as run_server
from main import app


class ObservedConnection(Protocol):
    @property
    def closed(self) -> int: ...


def main() -> None:
    observed_connections: list[ObservedConnection] = []
    lock_key = int(os.environ["SHUTDOWN_PROBE_LOCK"])

    def remember_connection(connection: ObservedConnection, record: object) -> None:
        observed_connections.append(connection)

    event.listen(engine, "connect", remember_connection)

    def delayed_db(request: Request) -> Generator[Session]:
        # Retain the production session lifecycle and /healthchecker handler.
        # Only the marked test request waits; Docker's healthcheck stays normal.
        with contextmanager(get_db)() as session:
            if request.headers.get("X-Shutdown-Probe") == "1":
                session.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key}
                )
            yield session

    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def verify_closed(application: FastAPI) -> AsyncGenerator[None]:
        async with original_lifespan(application):
            yield
        # Check actual psycopg2 handles while PID 1 is still alive. Merely
        # checking pg_stat_activity after exit would also pass after SIGKILL.
        assert observed_connections, "The test must open a real DB connection"
        assert all(connection.closed for connection in observed_connections)
        logging.getLogger("shutdown.probe").info(
            "Observed database connections are closed"
        )

    app.dependency_overrides[get_db] = delayed_db
    app.router.lifespan_context = verify_closed
    # Same production launcher, Uvicorn options and middleware; no subprocess.
    run_server()


if __name__ == "__main__":
    main()
