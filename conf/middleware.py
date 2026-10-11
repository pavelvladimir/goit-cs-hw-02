"""HTTP request context around the entire FastAPI error handler."""

import logging
from time import perf_counter
from uuid import UUID, uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from conf.logging import request_id_context

logger = logging.getLogger("app.access")


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied_id = Headers(scope=scope).get("x-request-id", "")
        try:
            if len(supplied_id) != 36:
                raise ValueError("Expected a UUID")
            request_id = str(UUID(supplied_id))
        except ValueError:
            request_id = str(uuid4())

        token = request_id_context.set(request_id)
        started = perf_counter()
        status = 500
        complete = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal status, complete
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body"):
                complete = True

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as error:
            # Uvicorn owns this stack trace; logging here would duplicate it.
            error.__dict__["_request_log_id"] = request_id
            raise
        finally:
            try:
                level = logging.INFO
                if status >= 500 or not complete:
                    level = logging.ERROR
                elif status >= 400:
                    level = logging.WARNING
                logger.log(
                    level,
                    "request_completed" if complete else "request_incomplete",
                    extra={
                        "request_id": request_id,
                        "method": scope["method"],
                        # Route templates omit query strings and dynamic path values.
                        "path": getattr(scope.get("route"), "path", "<unmatched>"),
                        "status": status,
                        "duration_ms": round((perf_counter() - started) * 1000, 3),
                    },
                )
            finally:
                request_id_context.reset(token)
