"""Click the built React frontend against the real distroless API and Percona."""

import os
import subprocess

import pytest

from tests.integration.stack import ROOT, ComposeStack

pytestmark = pytest.mark.integration


def test_browser_checks_real_database(stack: ComposeStack) -> None:
    result = subprocess.run(
        ["pnpm", "--dir", str(ROOT / "frontend"), "test"],
        env={
            **os.environ,
            "FRONTEND_BASE_URL": f"http://127.0.0.1:{stack.port('app', 8000)}",
        },
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, stack.redact(result.stdout + result.stderr)
