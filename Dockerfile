FROM python:3.13-slim-trixie AS builder

# env
ENV POETRY_HOME=/opt/poetry

# setup poetry
RUN python3 -m venv $POETRY_HOME
RUN $POETRY_HOME/bin/pip install poetry
# add poetry to path
ENV PATH=$POETRY_HOME/bin:$PATH

WORKDIR /app
COPY pyproject.toml poetry.lock poetry.toml /app/
ARG POETRY_INSTALLER_NO_BINARY=pymediainfo
RUN poetry install --only=main --no-root

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
