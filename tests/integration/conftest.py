from collections.abc import Generator
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx2
import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from tests.integration.stack import ComposeStack


@pytest.fixture(scope="session")
def stack(request: pytest.FixtureRequest) -> Generator[ComposeStack]:
    if not request.config.getoption("--integration"):
        pytest.skip("Use --integration to start disposable Docker containers")
    with TemporaryDirectory(prefix="hw02-integration-") as temporary:
        instance = ComposeStack.create(Path(temporary))
        try:
            instance.run(
                "up", "--build", "-d", "--wait", "--wait-timeout", "90", timeout=600
            )
            yield instance
        finally:
            instance.cleanup()


@pytest.fixture(scope="session")
def database_engine(stack: ComposeStack) -> Generator[Engine]:
    engine = create_engine(
        stack.url(),
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": 5},
    )
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(database_engine: Engine) -> Generator[Session]:
    with Session(database_engine) as session:
        yield session


@pytest.fixture(scope="session")
def http_client(stack: ComposeStack) -> Generator[httpx2.Client]:
    with httpx2.Client(
        base_url=f"http://127.0.0.1:{stack.port('app', 8000)}",
        timeout=10,
        trust_env=False,
    ) as client:
        yield client
