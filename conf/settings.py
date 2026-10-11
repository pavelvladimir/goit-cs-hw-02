"""Validated application configuration from the environment or local .env file."""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    db_host: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.:-]+$")
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_connect_timeout: int = Field(default=3, ge=2, le=30)
    shutdown_grace_seconds: int = Field(default=20, ge=6, le=120)
    db_name: str = Field(pattern=r"^[a-z_][a-z0-9_]{0,62}$")
    db_user: str = Field(pattern=r"^[a-z_][a-z0-9_]{0,62}$")
    db_password: SecretStr | None = None
    db_password_file: Path | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @field_validator("db_user")
    @classmethod
    def require_application_user(cls, value: str) -> str:
        if value == "postgres" or value.startswith("pg_"):
            raise ValueError("DB_USER must be a dedicated application role")
        return value

    @field_validator("db_password", "db_password_file", mode="before")
    @classmethod
    def empty_secret_is_unset(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def load_password(self) -> Self:
        if (self.db_password is None) == (self.db_password_file is None):
            raise ValueError("Set exactly one of DB_PASSWORD or DB_PASSWORD_FILE")
        if self.db_password_file is not None:
            try:
                password = self.db_password_file.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                raise ValueError(
                    "DB_PASSWORD_FILE must be readable UTF-8 text"
                ) from None
            self.db_password = SecretStr(password.rstrip("\r\n"))

        assert self.db_password is not None
        password = self.db_password.get_secret_value()
        if not password.strip() or any(char in password for char in "\x00\r\n"):
            raise ValueError("Database password must be nonempty and single-line")
        return self

    @property
    def database_url(self) -> URL:
        assert self.db_password is not None
        # URL.create handles reserved characters without manual URL escaping.
        return URL.create(
            "postgresql+psycopg2",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )
