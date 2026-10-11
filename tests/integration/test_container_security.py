"""Verify kernel-enforced restrictions in the real distroless application."""

import errno
import json
import re
from textwrap import dedent
from uuid import UUID

import httpx2
import pytest

from tests.integration.stack import ComposeStack

pytestmark = pytest.mark.integration


def test_server_and_its_threads_cannot_gain_privileges(stack: ComposeStack) -> None:
    output = stack.run(
        "exec",
        "-T",
        "app",
        "/app/.venv/bin/python3",
        "-c",
        dedent("""
            import json
            from pathlib import Path

            fields = (
                'Uid', 'Gid', 'NoNewPrivs',
                'CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb',
            )
            threads = []
            # Inspect PID 1 and its worker threads, not only this exec process.
            for path in Path('/proc/1/task').glob('*/status'):
                status = dict(
                    line.split(':', 1) for line in path.read_text().splitlines()
                )
                threads.append({field: status[field].strip() for field in fields})
            print(json.dumps({
                'command': Path('/proc/1/cmdline').read_text().split(chr(0)),
                'threads': threads,
            }))
        """),
    )
    state = json.loads(output)
    assert "conf.server" in state["command"]
    assert state["threads"]
    for thread in state["threads"]:
        # Real, effective, saved and filesystem IDs must all remain non-root.
        assert list(map(int, thread["Uid"].split())) == [65532] * 4
        assert list(map(int, thread["Gid"].split())) == [65532] * 4
        assert thread["NoNewPrivs"] == "1"
        for field in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"):
            assert int(thread[field], 16) == 0, field


def test_root_filesystem_rejects_writes(stack: ComposeStack) -> None:
    output = stack.run(
        "exec",
        "-T",
        "app",
        "/app/.venv/bin/python3",
        "-c",
        dedent("""
            import json
            import os
            from pathlib import Path
            from uuid import uuid4

            root_mounts = [
                line.split()[5].split(',')
                for line in Path('/proc/1/mountinfo').read_text().splitlines()
                if line.split()[4] == '/'
            ]
            errors = {}
            # Both directories are writable by UID 65532 without read_only.
            # EROFS proves the mount restriction, rather than a permissions error.
            for directory in ('/app/conf', '/tmp'):
                path = Path(directory) / ('.hardening-probe-' + uuid4().hex)
                try:
                    descriptor = os.open(
                        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                    )
                except OSError as error:
                    errors[directory] = error.errno
                else:
                    os.close(descriptor)
                    path.unlink()
                    errors[directory] = None
            print(json.dumps({'root_mounts': root_mounts, 'write_errors': errors}))
        """),
    )
    state = json.loads(output)
    assert len(state["root_mounts"]) == 1
    assert "ro" in state["root_mounts"][0]
    assert state["write_errors"] == {"/app/conf": errno.EROFS, "/tmp": errno.EROFS}


def test_hardened_app_serves_files_docs_and_database_check(
    http_client: httpx2.Client,
) -> None:
    for path, expected_content in (
        ("/", 'class="check-button"'),
        ("/docs", "/openapi.json"),
    ):
        response = http_client.get(path)
        assert response.status_code == 200, path
        assert expected_content in response.text
        assert (
            str(UUID(response.headers["x-request-id"]))
            == response.headers["x-request-id"]
        )
    html = http_client.get("/").text
    assets = re.findall(r'(?:src|href)="(/_next/static/[^\"]+)"', html)
    assert any(path.endswith(".js") for path in assets)
    assert any(path.endswith(".css") for path in assets)
    for path in assets:
        response = http_client.get(path)
        assert response.status_code == 200
        assert response.content
    response = http_client.get("/healthchecker")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to FastAPI!"}
