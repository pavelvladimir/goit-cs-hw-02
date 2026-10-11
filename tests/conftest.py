import os
from collections.abc import Generator
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from conf.settings import Settings

# Import the app with isolated, non-secret test settings. Tests never read the
# developer's database credentials or open a connection to the real database.
with (
    patch.dict(Settings.model_config, {"env_file": None}),
    patch.dict(
        os.environ,
        {
            "DB_HOST": "test-db.invalid",
            "DB_PORT": "5432",
            "DB_CONNECT_TIMEOUT": "3",
            "SHUTDOWN_GRACE_SECONDS": "20",
            "DB_NAME": "test_db",
            "DB_USER": "test_app",
            "DB_PASSWORD": "unit-test-only",
            "DB_PASSWORD_FILE": "",
            "LOG_LEVEL": "INFO",
        },
    ),
):
    from conf.db import get_db
    from main import app, application


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--integration",
        action="store_true",
        help="Run integration tests using disposable Percona Compose projects.",
    )


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    # Bash has its own Linux image and isolated pytest configuration.
    if collection_path.name == "bash":
        return True
    if collection_path.name == "integration" and not config.getoption("--integration"):
        return True
    return None


@pytest.fixture
def db_session() -> MagicMock:
    session = MagicMock(spec=Session)
    session.execute.return_value.fetchone.return_value = (1,)
    return session


@pytest.fixture
def client(db_session: MagicMock) -> Generator[TestClient]:
    def override_db() -> Generator[Session]:
        yield cast(Session, db_session)

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(application) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
