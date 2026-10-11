"""Export the real API contract without credentials, requests or a database."""

import argparse
import json
import os
from pathlib import Path
from unittest.mock import patch

from conf.settings import Settings

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "frontend" / "openapi.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    # Importing the app creates a lazy SQLAlchemy engine. Override every setting
    # and disable dotenv so metadata export never reads local secrets or connects.
    with (
        patch.dict(Settings.model_config, {"env_file": None}),
        patch.dict(
            os.environ,
            {
                "DB_HOST": "openapi.invalid",
                "DB_PORT": "5432",
                "DB_CONNECT_TIMEOUT": "3",
                "SHUTDOWN_GRACE_SECONDS": "20",
                "DB_NAME": "openapi",
                "DB_USER": "openapi_app",
                "DB_PASSWORD": "schema-export-only",
                "DB_PASSWORD_FILE": "",
                "LOG_LEVEL": "INFO",
            },
            clear=True,
        ),
    ):
        from main import app

        schema = json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True)
    content = schema + "\n"
    if args.check:
        if (
            not SCHEMA_PATH.is_file()
            or SCHEMA_PATH.read_text(encoding="utf-8") != content
        ):
            raise SystemExit("OpenAPI is stale. Run: make generate-api")
        print("OpenAPI matches FastAPI.")
    else:
        SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
        SCHEMA_PATH.write_text(content, encoding="utf-8")
        print("Exported frontend/openapi.json.")


if __name__ == "__main__":
    main()
