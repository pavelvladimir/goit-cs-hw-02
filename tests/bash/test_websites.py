"""Run the real Bash/curl script against deterministic loopback HTTP responses."""

import os
import shutil
import socket
import subprocess
import time
from collections.abc import Generator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class LocalWebsite:
    url: str
    requests: Queue[str]

    def requested_paths(self) -> list[str]:
        paths = []
        while True:
            try:
                paths.append(self.requests.get_nowait())
            except Empty:
                return paths


@pytest.fixture
def website() -> Generator[LocalWebsite]:
    requests: Queue[str] = Queue()
    release_timeout = Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            requests.put(self.path)
            path = urlsplit(self.path).path
            if path == "/timeout":
                # Keep the connection open without a response beyond curl's
                # real 15s deadline. Teardown releases it even if the test fails.
                release_timeout.wait(30)
                return
            redirects = {
                "/redirect": "/ok",
                "/redirect-missing": "/missing",
                "/loop": "/loop",
            }
            status = {
                "/ok": 200,
                "/empty": 204,
                "/missing": 404,
                "/error": 500,
                "/broken": 200,
            }.get(path, 404)
            body = b"" if path == "/empty" else b"OK"
            self.send_response(302 if path in redirects else status)
            if path in redirects:
                self.send_header("Location", redirects[path])
            # A 200 header with a truncated body must still be DOWN.
            length = 100 if path == "/broken" else len(body)
            self.send_header("Content-Length", str(length))
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = False
    worker = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
    worker.start()
    try:
        yield LocalWebsite(f"http://127.0.0.1:{server.server_port}", requests)
    finally:
        release_timeout.set()
        server.shutdown()
        server.server_close()  # Joins request threads, including /timeout.
        worker.join(timeout=5)
        assert not worker.is_alive()


@dataclass
class WebsiteChecker:
    bash: str
    script: Path
    working_directory: Path
    environment: dict[str, str]

    @property
    def log(self) -> Path:
        return Path(
            self.environment.get(
                "WEBSITE_LOG_FILE", str(self.script.parent / "website_status.log")
            )
        )

    def run(self, *urls: str, success: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [self.bash, str(self.script), *urls],
            cwd=self.working_directory,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if success:
            assert result.returncode == 0, result.stderr
            assert result.stdout == f"Results have been written to {self.log}\n"
        assert not (self.working_directory / "website_status.log").exists()
        return result


@pytest.fixture
def checker(tmp_path: Path) -> WebsiteChecker:
    bash = shutil.which("bash")
    assert bash is not None, "Bash is required to test the homework script"
    assert shutil.which("curl") is not None, "curl is required for Bash tests"
    script_directory = tmp_path / "script directory with spaces"
    script_directory.mkdir()
    script = script_directory / "check_websites.sh"
    shutil.copy2(ROOT / "check_websites.sh", script)
    working_directory = tmp_path / "unrelated working directory"
    working_directory.mkdir()
    curl_directory = tmp_path / "curl config"
    curl_directory.mkdir()
    (curl_directory / ".curlrc").write_text("", encoding="utf-8")
    # No inherited proxies, BASH_ENV or curl config can change the requests.
    # The script and real curl are unmodified; only URLs and environment differ.
    environment = {
        "PATH": os.environ.get("PATH", os.defpath),
        "LC_ALL": "C",
        "CURL_HOME": str(curl_directory),
        "NO_PROXY": "*",
    }
    return WebsiteChecker(bash, script, working_directory, environment)


@pytest.mark.parametrize(
    ("path", "status", "visited"),
    [
        ("/ok", "UP", ["/ok"]),
        ("/redirect", "UP", ["/redirect", "/ok"]),
        ("/redirect-missing", "DOWN", ["/redirect-missing", "/missing"]),
        ("/missing", "DOWN", ["/missing"]),
        ("/error", "DOWN", ["/error"]),
        ("/empty", "DOWN", ["/empty"]),
    ],
)
def test_http_status_and_redirects(
    checker: WebsiteChecker,
    website: LocalWebsite,
    path: str,
    status: str,
    visited: list[str],
) -> None:
    url = website.url + path
    result = checker.run(url)
    assert checker.log.read_text() == f"<{url}> is {status}\n"
    assert website.requested_paths() == visited
    assert result.stderr == ""


def test_truncated_http_200_is_down(
    checker: WebsiteChecker, website: LocalWebsite
) -> None:
    url = website.url + "/broken"
    result = checker.run(url)
    assert checker.log.read_text() == f"<{url}> is DOWN\n"
    assert "curl: (18)" in result.stderr
    assert website.requested_paths() == ["/broken"]


def test_redirect_loop_stops_after_ten_redirects(
    checker: WebsiteChecker, website: LocalWebsite
) -> None:
    url = website.url + "/loop"
    result = checker.run(url)
    assert checker.log.read_text() == f"<{url}> is DOWN\n"
    assert "curl: (47)" in result.stderr
    assert website.requested_paths() == ["/loop"] * 11


def test_real_timeout_is_down_and_next_website_is_checked(
    checker: WebsiteChecker, website: LocalWebsite
) -> None:
    started = time.monotonic()
    result = checker.run(website.url + "/timeout", website.url + "/ok")
    elapsed = time.monotonic() - started
    assert 14 <= elapsed < 20, f"Expected a 15s curl timeout, got {elapsed:.3f}s"
    assert "curl: (28)" in result.stderr
    assert checker.log.read_text() == (
        f"<{website.url}/timeout> is DOWN\n<{website.url}/ok> is UP\n"
    )
    assert website.requested_paths() == ["/timeout", "/ok"]


def test_unavailable_port_is_down(checker: WebsiteChecker) -> None:
    # Reserve a port without listening, preventing another process from taking it.
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{reserved.getsockname()[1]}/"
        started = time.monotonic()
        result = checker.run(url)
        elapsed = time.monotonic() - started
    assert checker.log.read_text() == f"<{url}> is DOWN\n"
    # Linux loopback refuses a bound, non-listening port without waiting for
    # curl's 5s connect timeout. The host macOS network stack is not involved.
    assert "curl: (7)" in result.stderr
    assert elapsed < 5, f"Connection failure took {elapsed:.3f}s"


def test_mixed_results_preserve_order_and_url_arguments(
    checker: WebsiteChecker, website: LocalWebsite
) -> None:
    paths = ["/missing", "/ok?first=1&second=two%20words", "/broken", "/redirect"]
    checker.run(*(website.url + path for path in paths))
    assert checker.log.read_text() == "".join(
        f"<{website.url}{path}> is {status}\n"
        for path, status in zip(paths, ["DOWN", "UP", "DOWN", "UP"], strict=True)
    )
    assert website.requested_paths() == [*paths, "/ok"]


def test_next_run_replaces_log(checker: WebsiteChecker, website: LocalWebsite) -> None:
    checker.run(website.url + "/ok", website.url + "/missing")
    assert len(checker.log.read_text().splitlines()) == 2
    checker.run(website.url + "/error")
    assert checker.log.read_text() == f"<{website.url}/error> is DOWN\n"


def test_external_log_with_read_only_script_directory(
    checker: WebsiteChecker, website: LocalWebsite
) -> None:
    original_log = checker.log
    original_log.write_text("previous local run\n")
    log_directory = checker.working_directory / "external logs"
    log_directory.mkdir()
    checker.environment["WEBSITE_LOG_FILE"] = str(log_directory / "website_status.log")
    checker.script.parent.chmod(0o555)
    try:
        checker.run(website.url + "/ok", website.url + "/missing")
        checker.run(website.url + "/error")
        assert checker.log.read_text() == f"<{website.url}/error> is DOWN\n"
        assert original_log.read_text() == "previous local run\n"
    finally:
        checker.script.parent.chmod(0o755)


def test_missing_curl_preserves_existing_log(
    checker: WebsiteChecker, website: LocalWebsite, tmp_path: Path
) -> None:
    checker.log.write_text("previous run\n")
    empty_path = tmp_path / "empty PATH"
    empty_path.mkdir()
    checker.environment["PATH"] = str(empty_path)
    result = checker.run(website.url + "/ok", success=False)
    assert result.returncode == 1
    assert result.stderr == "Error: curl is required.\n"
    assert result.stdout == ""
    assert checker.log.read_text() == "previous run\n"
    assert website.requested_paths() == []


@pytest.mark.parametrize("existing_log", [False, True])
def test_log_permission_denied_before_any_request(
    checker: WebsiteChecker, website: LocalWebsite, existing_log: bool
) -> None:
    assert os.geteuid() != 0, "Permission tests must run as the non-root container user"
    if existing_log:
        checker.log.write_text("previous run\n")
        checker.log.chmod(0o444)
    else:
        checker.log.parent.chmod(0o555)
    try:
        result = checker.run(website.url + "/ok", success=False)
        assert result.returncode == 1
        assert result.stderr == f"Error: cannot write log file: {checker.log}\n"
        assert result.stdout == ""
        assert website.requested_paths() == []
        if existing_log:
            assert checker.log.read_text() == "previous run\n"
        else:
            assert not checker.log.exists()
    finally:
        checker.log.parent.chmod(0o755)
        if existing_log:
            checker.log.chmod(0o644)


def test_write_failure_after_open_does_not_report_success(
    checker: WebsiteChecker, website: LocalWebsite
) -> None:
    # Linux /dev/full opens successfully but rejects a write with ENOSPC.
    checker.environment["WEBSITE_LOG_FILE"] = "/dev/full"
    result = checker.run(website.url + "/ok", success=False)
    assert result.returncode == 1
    assert result.stderr == "Error: cannot write log file: /dev/full\n"
    assert result.stdout == ""
    assert website.requested_paths() == ["/ok"]
