"""Shared local/container entry point; configure logging before Uvicorn starts."""

import logging
import os

import uvicorn
from pydantic import ValidationError

from conf.logging import configure_logging
from conf.settings import Settings


def main() -> None:
    configure_logging()
    try:
        settings = Settings()
    except ValidationError as error:
        logging.getLogger(__name__).error(
            "Invalid application configuration",
            extra={
                "invalid_settings": [
                    {"field": ".".join(map(str, item["loc"])), "type": item["type"]}
                    for item in error.errors(include_input=False, include_context=False)
                ]
            },
        )
        raise SystemExit(1) from None
    assert settings.db_password is not None
    configure_logging(settings.log_level, settings.db_password.get_secret_value())
    uvicorn.run(
        "main:application",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        log_config=None,
        access_log=False,
        lifespan="on",
        # Reserve five seconds of Compose's stop budget for pool cleanup and exit.
        timeout_graceful_shutdown=settings.shutdown_grace_seconds - 5,
    )


if __name__ == "__main__":
    main()
