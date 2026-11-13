# syntax=docker/dockerfile:1
# Battlemap tracer: one CPU-only image for tests, data tools, the tracer and the Gradio app.
# Build and test with: docker compose build && docker compose run --rm app pytest
FROM ubuntu:24.04

# uv installs the locked dependencies; pinned so the build is reproducible.
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /bin/

# Venv in /opt/venv on the PATH; uv uses the system Python 3.12 and never downloads one;
# copy (not hard-link) files out of the cache mount, which lives on another filesystem.
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=python3 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:$PATH

# Python 3.12 and venv support from Ubuntu; CA certificates for HTTPS to the model API.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies alone first, from the lockfile, so code changes don't reinstall them.
# PyTorch comes from its CPU wheel index (pyproject.toml), so the image stays CPU-only.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# Then the code, installed into the same venv as an editable project (with the dev group:
# pytest, ruff).
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen \
    && chown -R ubuntu:ubuntu /app

# The base image's built-in user has UID 1000, matching the host user,
# so files written to the mounted volumes are not owned by root.
USER ubuntu

CMD ["pytest"]
