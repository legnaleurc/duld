FROM python:3.12.2-slim-bookworm AS base

# env
ENV POETRY_HOME=/opt/poetry
ENV POETRY_VERSION=1.8.2

# setup poetry
RUN python3 -m venv $POETRY_HOME
RUN $POETRY_HOME/bin/pip install poetry==$POETRY_VERSION
# add poetry to path
ENV PATH=$POETRY_HOME/bin:$PATH

WORKDIR /app


FROM base AS production-builder

RUN : \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml poetry.lock poetry.toml /app/
RUN poetry install --only=main --no-root


FROM base AS production

RUN : \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        p7zip ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY --from=production-builder /app/.venv /app/.venv
COPY . /app
