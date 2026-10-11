import json
import re
import tomllib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from main import HealthCheckError, HealthCheckResponse


def test_homepage_loads_react_application(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'class="main-text"' in response.text
    assert 'class="check-button"' in response.text
    assert "Перевірити БД</button>" in response.text
    assert "/_next/static/" in response.text
    assert response.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("extension", ["js", "css"])
def test_built_frontend_assets_are_served(client: TestClient, extension: str) -> None:
    html = client.get("/").text
    paths = re.findall(r'(?:src|href)="(/_next/static/[^\"]+)"', html)
    path = next(path for path in paths if path.endswith("." + extension))
    response = client.get(path)

    assert response.status_code == 200
    assert response.content


def test_unknown_paths_are_not_replaced_with_spa_html(client: TestClient) -> None:
    for path in (
        "/_next/static/missing.js",
        "/missing-api",
        "/frontend/package.json",
        "/openapi-ts.config.ts",
    ):
        assert client.get(path).status_code == 404


def test_exported_openapi_matches_running_api(client: TestClient) -> None:
    snapshot = Path(__file__).parents[1] / "frontend" / "openapi.json"
    assert (
        json.loads(snapshot.read_text(encoding="utf-8"))
        == client.get("/openapi.json").json()
    )


def test_healthchecker_returns_documented_success(client: TestClient) -> None:
    response = client.get("/healthchecker")

    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to FastAPI!"}
    HealthCheckResponse.model_validate(response.json())
    documented = client.get("/openapi.json").json()["paths"]["/healthchecker"]["get"]
    example = documented["responses"]["200"]["content"]["application/json"]["examples"]
    assert response.json() == example["database_available"]["value"]


def test_healthchecker_handles_database_failure(
    client: TestClient, db_session: MagicMock
) -> None:
    error = OperationalError("SELECT 1", {}, RuntimeError("connection failed"))
    with patch.object(db_session, "execute", side_effect=error):
        response = client.get("/healthchecker")

    assert response.status_code == 500
    assert response.json() == {"detail": "Error connecting to the database"}
    assert "connection failed" not in response.text
    HealthCheckError.model_validate(response.json())
    documented = client.get("/openapi.json").json()["paths"]["/healthchecker"]["get"]
    examples = documented["responses"]["500"]["content"]["application/json"]["examples"]
    assert response.json() == examples["database_unavailable"]["value"]


def test_healthchecker_rejects_empty_query_result(
    client: TestClient, db_session: MagicMock
) -> None:
    with patch.object(db_session, "execute") as execute:
        execute.return_value.fetchone.return_value = None
        response = client.get("/healthchecker")

    assert response.status_code == 500
    assert response.json() == {"detail": "Database is not configured correctly"}
    HealthCheckError.model_validate(response.json())
    documented = client.get("/openapi.json").json()["paths"]["/healthchecker"]["get"]
    examples = documented["responses"]["500"]["content"]["application/json"]["examples"]
    assert response.json() == examples["empty_result"]["value"]


def test_openapi_metadata_matches_project(client: TestClient) -> None:
    project_file = Path(__file__).parents[1] / "pyproject.toml"
    project = tomllib.loads(project_file.read_text())["project"]
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert project["name"] in schema["info"]["title"]
    assert schema["info"]["version"] == project["version"]
    assert "SELECT 1" in schema["info"]["description"]
    assert {tag["name"] for tag in schema["tags"]} == {"Database", "Web"}
    for path in ("/", "/healthchecker"):
        operation = schema["paths"][path]["get"]
        assert operation["summary"]
        assert operation["description"]


def test_openapi_documents_html_and_typed_json_responses(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    homepage = schema["paths"]["/"]["get"]["responses"]["200"]["content"]
    assert set(homepage) == {"text/html"}
    assert homepage["text/html"]["schema"]["type"] == "string"

    responses = schema["paths"]["/healthchecker"]["get"]["responses"]
    for status, model, field in (
        ("200", "HealthCheckResponse", "message"),
        ("500", "HealthCheckError", "detail"),
    ):
        content = responses[status]["content"]["application/json"]
        assert content["schema"]["$ref"] == f"#/components/schemas/{model}"
        assert field in schema["components"]["schemas"][model]["required"]


@pytest.mark.parametrize("path", ["/docs", "/redoc"])
def test_documentation_pages_reference_openapi(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "goit-cs-hw-02" in response.text
    assert "/openapi.json" in response.text
