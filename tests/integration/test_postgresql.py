from unittest.mock import patch

import httpx2
import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool, QueuePool

from conf import db
from tests.integration.stack import ComposeStack

pytestmark = pytest.mark.integration


def test_real_api_returns_documented_success(http_client: httpx2.Client) -> None:
    response = http_client.get("/healthchecker")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to FastAPI!"}
    schema = http_client.get("/openapi.json").json()
    documented = schema["paths"]["/healthchecker"]["get"]["responses"]["200"]
    assert (
        response.json()
        == documented["content"]["application/json"]["examples"]["database_available"][
            "value"
        ]
    )


def test_database_is_percona_17(db_session: Session) -> None:
    assert "Percona" in db_session.execute(text("SELECT version()")).scalar_one()
    version = int(db_session.execute(text("SHOW server_version_num")).scalar_one())
    assert 170000 <= version < 180000


def test_application_role_has_only_required_privileges(
    db_session: Session, stack: ComposeStack
) -> None:
    role = db_session.execute(
        text(
            "SELECT current_user, rolsuper, rolcreatedb, rolcreaterole, "
            "rolreplication, rolbypassrls, rolinherit "
            "FROM pg_roles WHERE rolname = current_user"
        )
    ).one()
    assert role[0] == stack.username
    assert not any(role[1:])
    assert db_session.execute(text("SELECT 1")).scalar_one() == 1
    for privilege, expected in (("CONNECT", True), ("CREATE", False), ("TEMP", False)):
        actual = db_session.execute(
            text("SELECT has_database_privilege(current_user, current_database(), :p)"),
            {"p": privilege},
        ).scalar_one()
        assert actual is expected
    assert not db_session.execute(
        text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
    ).scalar_one()
    assert (
        db_session.execute(
            text(
                "SELECT count(*) FROM pg_auth_members "
                "WHERE member = (SELECT oid FROM pg_roles WHERE rolname = current_user)"
            )
        ).scalar_one()
        == 0
    )


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE public.permission_probe (id int)",
        "CREATE TEMP TABLE permission_probe (id int)",
        "CREATE ROLE permission_probe",
        "SELECT rolpassword FROM pg_authid",
    ],
)
def test_forbidden_operations_are_rejected(
    database_engine: Engine, statement: str
) -> None:
    with pytest.raises(DBAPIError) as error, database_engine.connect() as connection:
        with connection.begin():
            connection.execute(text(statement))
    assert getattr(error.value.orig, "pgcode", None) == "42501"


@pytest.mark.parametrize("admin", [False, True], ids=["app", "admin"])
def test_wrong_password_is_rejected(stack: ComposeStack, admin: bool) -> None:
    engine = create_engine(
        stack.url(admin=admin).set(password="deliberately-wrong-test-password"),
        poolclass=NullPool,
        connect_args={"connect_timeout": 5},
    )
    try:
        with pytest.raises(OperationalError, match="password authentication failed"):
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
    finally:
        engine.dispose()


def test_administrator_password_works(stack: ComposeStack) -> None:
    engine = create_engine(stack.url(admin=True), connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT current_user")).scalar_one()
                == "postgres"
            )
    finally:
        engine.dispose()


@pytest.mark.parametrize("request_fails", [False, True])
def test_session_returns_connection_to_pool(
    db_session: Session, database_engine: Engine, request_fails: bool
) -> None:
    assert isinstance(database_engine.pool, QueuePool)
    before = database_engine.pool.checkedout()
    with (
        patch.object(db, "SessionLocal", return_value=db_session),
        patch.object(db_session, "close", wraps=db_session.close) as close,
    ):
        dependency = db.get_db()
        session = next(dependency)
        assert session.execute(text("SELECT 1")).scalar_one() == 1
        assert database_engine.pool.checkedout() == before + 1
        if request_fails:
            with pytest.raises(RuntimeError, match="request failed"):
                dependency.throw(RuntimeError("request failed"))
        else:
            with pytest.raises(StopIteration):
                next(dependency)
        close.assert_called_once()
        assert database_engine.pool.checkedout() == before


def test_app_receives_only_its_own_secret(stack: ComposeStack) -> None:
    stack.run(
        "exec",
        "-T",
        "app",
        "/app/.venv/bin/python3",
        "-c",
        "\n".join(
            [
                "import os",
                "from pathlib import Path",
                "assert os.getuid() == 65532",
                "assert Path('/run/secrets/db_password').is_file()",
                "assert not Path('/run/secrets/postgres_password').exists()",
                "assert not Path('/app/.env').exists()",
                "assert 'DB_PASSWORD' not in os.environ",
                "assert 'POSTGRES_PASSWORD' not in os.environ",
            ]
        ),
    )


def test_initialization_is_repeatable(
    stack: ComposeStack, database_engine: Engine, http_client: httpx2.Client
) -> None:
    stack.run("exec", "-T", "db", "bash", "/docker-entrypoint-initdb.d/10-app-role.sh")
    database_engine.dispose()
    with database_engine.connect() as connection:
        assert (
            connection.execute(text("SELECT current_user")).scalar_one()
            == stack.username
        )
    assert http_client.get("/healthchecker").status_code == 200
