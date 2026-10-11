"""One JSON stream for application and server logs, without exception payloads."""

import json
import logging
import logging.config
from contextvars import ContextVar
from datetime import UTC, datetime
from traceback import walk_tb
from urllib.parse import quote, quote_plus

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def __init__(self, password: str = "") -> None:
        super().__init__()
        self.secrets = sorted(
            {
                password,
                quote(password, safe=""),
                quote_plus(password, safe=""),
                json.dumps(password, ensure_ascii=False)[1:-1],
                json.dumps(password, ensure_ascii=True)[1:-1],
            }
            - {""},
            key=len,
            reverse=True,
        )

    def format(self, record: logging.LogRecord) -> str:
        exception = record.exc_info[1] if record.exc_info else None
        request_id = getattr(record, "request_id", None) or request_id_context.get()
        # Uvicorn logs unhandled errors after the middleware has reset its context.
        if request_id is None and exception is not None:
            request_id = getattr(exception, "_request_log_id", None)
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if request_id is not None:
            payload["request_id"] = request_id
        for field in ("method", "path", "status", "duration_ms", "invalid_settings"):
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if exception is not None:
            # Do not serialize exception text, SQL, source lines or local variables.
            payload["exception"] = {
                "type": type(exception).__name__,
                "frames": [
                    {
                        "file": frame.f_code.co_filename,
                        "line": line,
                        "function": frame.f_code.co_name,
                    }
                    for frame, line in walk_tb(exception.__traceback__)
                ]
                if exception.__traceback__ is not None
                else [],
            }

        # Redact all string values, including nested frames, before encoding.
        # Replacing text in the final JSON could corrupt its syntax or numbers.
        def redact(value: object) -> object:
            if isinstance(value, str):
                for secret in self.secrets:
                    value = value.replace(secret, "[REDACTED]")
                return value
            if isinstance(value, list):
                return [redact(item) for item in value]
            if isinstance(value, dict):
                return {key: redact(item) for key, item in value.items()}
            return value

        return json.dumps(redact(payload), ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: str = "INFO", password: str = "") -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"json": {"()": JsonFormatter, "password": password}},
            "handlers": {
                "stdout": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "json",
                    "level": level,
                }
            },
            "root": {"handlers": ["stdout"], "level": level},
            "loggers": {
                name: {"handlers": [], "propagate": True, "level": logger_level}
                for name, logger_level in (
                    ("uvicorn", "NOTSET"),
                    ("uvicorn.error", "NOTSET"),
                    ("uvicorn.access", "NOTSET"),
                    ("sqlalchemy", "WARNING"),
                )
            },
        }
    )
