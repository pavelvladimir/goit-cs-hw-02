# Pin multi-platform indexes; Docker selects the matching platform manifest.
FROM debian:trixie-slim@sha256:a29215f6a35e51e22adffa17f89e9d2ef06214e64a2bad10d765c46aea49f11f AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 /uv /usr/local/bin/uv

ENV UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/bin/python3 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-cache

COPY main.py ./
COPY conf ./conf
COPY scripts ./scripts
COPY frontend/openapi.json ./frontend/openapi.json
RUN .venv/bin/python -B -m scripts.export_openapi --check

FROM node:22-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS frontend-builder
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /frontend
RUN npm install --global pnpm@12.11.2 && npm cache clean --force
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile --store-dir /tmp/pnpm-store \
    && rm -rf /tmp/pnpm-store
COPY frontend/tsconfig.json frontend/next.config.ts frontend/openapi-ts.config.ts frontend/postcss.config.mjs frontend/.htmlvalidate.json ./
COPY --from=builder /app/frontend/openapi.json ./openapi.json
COPY frontend/src ./src
RUN pnpm run build

# Pin the Python 3.13 runtime so an alias update cannot change its ABI.
FROM gcr.io/distroless/python3:nonroot@sha256:83aa8d4f74a4d7f7cf2d472054139bef71a927b76c680c0f2e1021d6b1d6d732

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=builder --chown=65532:65532 /app/.venv /app/.venv

COPY --chown=65532:65532 main.py ./
COPY --chown=65532:65532 conf ./conf
COPY --from=frontend-builder --chown=65532:65532 /frontend/out ./frontend/out

USER 65532:65532
EXPOSE 8000

ENTRYPOINT ["/app/.venv/bin/python3"]
CMD ["-m", "conf.server"]
