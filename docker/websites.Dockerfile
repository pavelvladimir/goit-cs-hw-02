# Rocky supplies the Bash, curl and CA certificates used by both targets.
FROM rockylinux/rockylinux:10-minimal@sha256:bc5c1e7a2ec7f4bcef1e51c7f0ebb2d43f05409e0108cdd34f693921d0604360 AS base

WORKDIR /app
ENV WEBSITE_LOG_FILE=/output/website_status.log
RUN mkdir /output && chown 65532:65532 /output
COPY --chmod=755 check_websites.sh ./
USER 65532:65532

FROM base AS tests
USER 0:0
COPY --from=ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 /uv /usr/local/bin/uv

# Python only drives the tests; Bash/curl remain the Rocky system packages.
ENV UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_PYTHON=3.13.16 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HW02_BASH_TEST_CONTAINER=1 \
    PATH="/app/.venv/bin:$PATH"

RUN UV_PYTHON_DOWNLOADS=automatic uv python install "$UV_PYTHON" --no-cache
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --only-group bash-test --no-cache
COPY docker/init-app-role.sh ./docker/
COPY tests/bash ./tests/bash

USER 65532:65532
# Exclude the application's conftest and keep all generated files in /tmp.
CMD ["python", "-m", "pytest", "--confcutdir=tests/bash", "-p", "no:cacheprovider", "tests/bash"]

# The default target contains only the script and Rocky runtime, no test tools.
FROM base AS runner
ENTRYPOINT ["/app/check_websites.sh"]
