"""Release pooled database connections after the server drains requests."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from conf.db import engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    try:
        yield
    finally:
        await run_in_threadpool(engine.dispose)
        logger.info("Database connection pool closed")
