"""Keep Bash scenarios in the dedicated Linux test container."""

import os
import sys

import pytest


def pytest_configure(config: pytest.Config) -> None:
    if sys.platform != "linux" or os.environ.get("HW02_BASH_TEST_CONTAINER") != "1":
        raise pytest.UsageError("Run Bash scenarios in Docker with: make test-bash")
