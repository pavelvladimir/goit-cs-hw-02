import json
import time
from uuid import uuid4

import httpx2
import pytest

from tests.integration.stack import ComposeStack

pytestmark = pytest.mark.integration


def test_container_logs_json_and_correlates_one_access_record(
    stack: ComposeStack,
    http_client: httpx2.Client,
) -> None:
    request_id = str(uuid4())
    response = http_client.get(
        "/healthchecker?token=private-query",
        headers={"X-Request-ID": request_id, "Authorization": "Bearer private-header"},
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == request_id
    # The response can reach the client just before middleware writes its log.
    for _ in range(20):
        output = stack.run("logs", "--no-color", "--no-log-prefix", "app")
        records = [json.loads(line) for line in output.splitlines()]
        related = [
            record for record in records if record.get("request_id") == request_id
        ]
        if related:
            break
        time.sleep(0.05)
    assert len(related) == 1
    assert (
        related[0].items()
        >= {
            "logger": "app.access",
            "message": "request_completed",
            "level": "INFO",
            "path": "/healthchecker",
            "status": 200,
            "method": "GET",
        }.items()
    )
    assert related[0]["duration_ms"] >= 0
    assert any(record["logger"] == "uvicorn.error" for record in records)
    assert all(record["logger"] != "uvicorn.access" for record in records)
    for secret in (
        "private-query",
        "private-header",
        stack.password.get_secret_value(),
        stack.admin_password.get_secret_value(),
    ):
        assert secret not in output
