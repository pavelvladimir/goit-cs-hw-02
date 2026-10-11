from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import make_url

from conf.settings import Settings


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    for name in (
        "DB_HOST",
        "DB_PORT",
        "DB_CONNECT_TIMEOUT",
        "SHUTDOWN_GRACE_SECONDS",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
        "DB_PASSWORD_FILE",
        "LOG_LEVEL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DB_HOST", "db")
    monkeypatch.setenv("DB_NAME", "hw02")
    monkeypatch.setenv("DB_USER", "hw02_app")
    monkeypatch.setenv("DB_PASSWORD", "unit-test-only")


@pytest.mark.parametrize("name", ["DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"])
def test_required_setting_cannot_be_missing(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.delenv(name)
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DB_HOST", ""),
        ("LOG_LEVEL", "VERBOSE"),
        ("DB_HOST", "postgresql://db"),
        ("DB_PORT", "0"),
        ("DB_PORT", "65536"),
        ("DB_PORT", "not-a-port"),
        ("DB_CONNECT_TIMEOUT", "-1"),
        ("DB_CONNECT_TIMEOUT", "0"),
        ("DB_CONNECT_TIMEOUT", "1"),
        ("DB_CONNECT_TIMEOUT", "31"),
        ("DB_CONNECT_TIMEOUT", "not-a-timeout"),
        ("SHUTDOWN_GRACE_SECONDS", "0"),
        ("SHUTDOWN_GRACE_SECONDS", "5"),
        ("SHUTDOWN_GRACE_SECONDS", "121"),
        ("SHUTDOWN_GRACE_SECONDS", "not-a-timeout"),
        ("DB_NAME", ""),
        ("DB_USER", "postgres"),
        ("DB_USER", "pg_monitor"),
        ("DB_USER", "invalid user"),
        ("DB_PASSWORD", ""),
        ("DB_PASSWORD", "   "),
        ("DB_PASSWORD", "line1\nline2"),
    ],
)
def test_invalid_settings_fail_without_echoing_password(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError) as error:
        Settings()
    assert "unit-test-only" not in str(error.value)
    assert "input_value" not in str(error.value)


def test_url_preserves_special_password_characters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password = "quoted'@:/?#%$& special-secret"
    monkeypatch.setenv("DB_PASSWORD", password)
    settings = Settings()
    url = settings.database_url
    assert url.password == password
    assert url.host == "db"
    assert url.port == 5432
    assert url.username == "hw02_app"
    assert make_url(url.render_as_string(hide_password=False)).password == password
    assert password not in repr(settings)
    assert password not in str(url)


def test_dotenv_and_environment_precedence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".env").write_text(
        "DB_HOST=dotenv-db\nDB_PASSWORD='dotenv-secret'\nAPP_PORT=8000\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("DB_PASSWORD")
    settings = Settings()
    assert settings.db_host == "db"
    assert settings.database_url.password == "dotenv-secret"


def test_password_file_preserves_spaces_and_removes_final_newline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secret = tmp_path / "db_password"
    secret.write_text(" file-secret with spaces \n", encoding="utf-8")
    monkeypatch.setenv("DB_PASSWORD", "")
    monkeypatch.setenv("DB_PASSWORD_FILE", str(secret))
    assert Settings().database_url.password == " file-secret with spaces "


def test_password_and_file_are_mutually_exclusive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DB_PASSWORD_FILE", str(tmp_path / "secret"))
    with pytest.raises(ValidationError, match="exactly one"):
        Settings()


@pytest.mark.parametrize("content", [None, b"\xff", b"", b"\n", b"bad\x00secret"])
def test_unusable_secret_file_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, content: bytes | None
) -> None:
    secret = tmp_path / "secret"
    if content is not None:
        secret.write_bytes(content)
    monkeypatch.delenv("DB_PASSWORD")
    monkeypatch.setenv("DB_PASSWORD_FILE", str(secret))
    with pytest.raises(ValidationError):
        Settings()
