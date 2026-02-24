FROM python:3.13-slim-trixie AS builder

# install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock /app/
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.13-slim-trixie AS production

RUN : \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        7zip libmagic1t64 libmediainfo0v5 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY . /app
