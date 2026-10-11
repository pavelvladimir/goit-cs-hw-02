import logging
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from conf.db import get_db
from conf.lifecycle import lifespan
from conf.middleware import RequestLoggingMiddleware

app = FastAPI(
    lifespan=lifespan,
    title="goit-cs-hw-02 | FastAPI & PostgreSQL",
    version="0.1.0",
    summary="Перевірка підключення FastAPI до PostgreSQL у Docker Compose.",
    description="""
Домашнє завдання до модуля **«Основи операційних систем»**.

Застосунок працює у distroless-контейнері та підключається до
**Percona PostgreSQL 17** через SQLAlchemy.

- **GET /healthchecker** виконує `SELECT 1` у базі даних. Відповідь `200`
  підтверджує успішне виконання цього запиту на момент перевірки.
- **GET /** повертає HTML-сторінку з кнопкою «Перевірити БД».

Для перевірки API розгорніть **GET /healthchecker**, натисніть
**Try it out → Execute** та порівняйте відповідь із прикладами нижче.
Параметри й авторизація не потрібні. Запит не змінює дані.

Формат OpenAPI доступний за [посиланням /openapi.json](/openapi.json).
""",
    openapi_tags=[
        {
            "name": "Database",
            "description": "Перевірка з'єднання з PostgreSQL та виконання SQL-запиту.",
        },
        {
            "name": "Web",
            "description": "Вебсторінка для ручної перевірки підключення до БД.",
        },
    ],
    swagger_ui_parameters={"displayRequestDuration": True},
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR / "frontend" / "out"
app.mount(
    "/_next/static",
    StaticFiles(directory=FRONTEND_DIR / "_next" / "static", check_dir=False),
    name="next-static",
)


class HealthCheckResponse(BaseModel):
    """Успішне виконання контрольного запиту до бази даних."""

    message: Literal["Welcome to FastAPI!"] = Field(
        description="Повідомлення про успішне підключення та виконання SELECT 1.",
        examples=["Welcome to FastAPI!"],
    )


class HealthCheckError(BaseModel):
    """Помилка контрольного запиту без внутрішніх деталей з'єднання."""

    detail: Literal[
        "Error connecting to the database", "Database is not configured correctly"
    ] = Field(
        description=(
            "Причина невдалої перевірки: помилка БД або відсутність результату."
        ),
        examples=[
            "Error connecting to the database",
            "Database is not configured correctly",
        ],
    )


@app.get(
    "/",
    response_class=HTMLResponse,
    tags=["Web"],
    operation_id="show_homepage",
    summary="Відкрити сторінку перевірки БД",
    description=(
        "Повертає HTML-сторінку з кнопкою «Перевірити БД». Натискання кнопки "
        "викликає GET /healthchecker та відображає успішний результат або помилку. "
        "Завантаження самої сторінки не перевіряє підключення до бази даних."
    ),
    response_description="HTML-сторінка для перевірки підключення до PostgreSQL.",
    responses={
        200: {
            "content": {
                "text/html": {
                    "examples": {
                        "page_fragment": {
                            "summary": "Фрагмент HTML-сторінки",
                            "description": ("Скорочений приклад повної HTML-сторінки."),
                            "value": ('<button type="button">Перевірити БД</button>'),
                        }
                    }
                }
            }
        }
    },
)
def index() -> FileResponse:
    return FileResponse(
        FRONTEND_DIR / "index.html",
        media_type="text/html",
        headers={"Cache-Control": "no-cache"},
    )


@app.get(
    "/healthchecker",
    response_model=HealthCheckResponse,
    tags=["Database"],
    operation_id="check_database",
    summary="Перевірити підключення до PostgreSQL",
    description=(
        "Виконує SQL-запит `SELECT 1` через сесію SQLAlchemy. Повертає `200` "
        "і повідомлення `Welcome to FastAPI!`, якщо запит завершився успішно "
        "та повернув рядок. Помилка з'єднання або виконання SQL повертає `500` "
        "з повідомленням `Error connecting to the database`. Якщо результат "
        "порожній, повертає `500` з повідомленням "
        "`Database is not configured correctly`. Дані в базі не змінюються."
    ),
    response_description="Контрольний SQL-запит успішно повернув результат.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "database_available": {
                            "summary": "База даних доступна",
                            "value": {"message": "Welcome to FastAPI!"},
                        }
                    }
                }
            }
        },
        500: {
            "model": HealthCheckError,
            "description": (
                "Контрольний SQL-запит завершився помилкою або не повернув рядка."
            ),
            "content": {
                "application/json": {
                    "examples": {
                        "database_unavailable": {
                            "summary": "Помилка з'єднання або SQL-запиту",
                            "value": {"detail": "Error connecting to the database"},
                        },
                        "empty_result": {
                            "summary": "SQL-запит не повернув результату",
                            "value": {"detail": "Database is not configured correctly"},
                        },
                    }
                }
            },
        },
    },
)
def healthchecker(db: Annotated[Session, Depends(get_db)]) -> HealthCheckResponse:
    try:
        result = db.execute(text("SELECT 1")).fetchone()
    except SQLAlchemyError as error:
        logger.exception("Database health check failed")
        raise HTTPException(
            status_code=500, detail="Error connecting to the database"
        ) from error

    if result is None:
        raise HTTPException(
            status_code=500, detail="Database is not configured correctly"
        )
    return HealthCheckResponse(message="Welcome to FastAPI!")


application = RequestLoggingMiddleware(app)


if __name__ == "__main__":
    from conf.server import main

    main()
