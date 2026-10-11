"""Isolated Compose lifecycle for real PostgreSQL and HTTP integration tests."""

import os
import secrets
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import URL

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class ComposeStack:
    command: list[str]
    environment: dict[str, str] = field(repr=False)
    project: str
    password: SecretStr = field(repr=False)
    admin_password: SecretStr = field(repr=False)
    database: str = "integration_db"
    username: str = "integration_app"
    connect_timeout: int = 3

    @classmethod
    def create(cls, directory: Path) -> "ComposeStack":
        project = "hw02-test-" + secrets.token_hex(8)
        # '$' must remain literal through dotenv, Compose, psql and SQLAlchemy.
        password = SecretStr(secrets.token_urlsafe(24) + "@:/?#%$&")
        admin_password = SecretStr(secrets.token_urlsafe(32))
        values = {
            "DB_HOST": "db",
            "DB_PORT": "5432",
            "DB_NAME": "integration_db",
            "DB_USER": "integration_app",
            "APP_PORT": "8000",
            "LOG_LEVEL": "INFO",
            "SHUTDOWN_GRACE_SECONDS": "20",
            "TEST_APP_IMAGE": project + "-app",
        }
        # Use the same file-backed secrets configuration as the local app,
        # pointing it at private temporary files instead of the user's files.
        secret_directory = directory / "secrets"
        secret_directory.mkdir(mode=0o700)
        for name, value in (
            ("DB_PASSWORD", password),
            ("POSTGRES_PASSWORD", admin_password),
        ):
            path = secret_directory / name.lower()
            path.write_text(value.get_secret_value() + "\n", encoding="utf-8")
            # Non-root container UIDs can read each bind-mounted file; the
            # private parent directory protects access on the host.
            path.chmod(0o444)
            values[name + "_SECRET_FILE"] = str(path)

        env_file = directory / ".env"
        # Generated values contain no apostrophes; single quotes disable expansion.
        env_file.write_text(
            "".join(f"{key}='{value}'\n" for key, value in values.items()),
            encoding="utf-8",
        )
        env_file.chmod(0o600)
        command = [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-p",
            project,
            "-f",
            str(ROOT / "docker-compose.yaml"),
        ]
        command.extend(["-f", str(ROOT / "compose.test.yaml")])
        # Explicit --env-file prevents reading the developer's .env. Remove
        # inherited overrides too, while preserving Docker connection settings.
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.upper().startswith(("DB_", "POSTGRES_", "COMPOSE_"))
            and key.upper()
            not in {"APP_PORT", "TEST_APP_IMAGE", "LOG_LEVEL", "SHUTDOWN_GRACE_SECONDS"}
        }
        return cls(
            command,
            environment,
            project,
            password,
            admin_password,
        )

    def redact(self, output: str) -> str:
        for secret in (self.password, self.admin_password):
            output = output.replace(secret.get_secret_value(), "[REDACTED]")
        return output

    def run(self, *arguments: str, timeout: int = 60) -> str:
        result = subprocess.run(
            [*self.command, *arguments],
            cwd=ROOT,
            env=self.environment,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode:
            output = self.redact(result.stdout + result.stderr)
            raise RuntimeError(
                f"Compose {arguments[0]} failed for {self.project}:\n{output[-6000:]}"
            )
        return result.stdout.strip()

    def port(self, service: str, container_port: int) -> int:
        address = self.run("port", service, str(container_port))
        host, port = address.rsplit(":", 1)
        if host != "127.0.0.1":
            raise RuntimeError(f"Test port is not restricted to loopback: {address}")
        return int(port)

    def url(self, *, admin: bool = False) -> URL:
        return URL.create(
            "postgresql+psycopg2",
            username="postgres" if admin else self.username,
            password=(
                self.admin_password if admin else self.password
            ).get_secret_value(),
            host="127.0.0.1",
            port=self.port("db", 5432),
            database=self.database,
        )

    def cleanup(self) -> None:
        # The random project name scopes removal to this fixture's resources.
        self.run("down", "--volumes", "--remove-orphans", timeout=60)
        result = subprocess.run(
            ["docker", "image", "rm", self.project + "-app"],
            env=self.environment,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if result.returncode and "No such image" not in result.stderr:
            raise RuntimeError(self.redact(result.stderr))
