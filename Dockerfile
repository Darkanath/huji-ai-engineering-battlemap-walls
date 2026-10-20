# syntax=docker/dockerfile:1
# Battlemap auto-walling: one CPU-only image for data tools, training, tests and the app.
# Build and test with: docker compose build && docker compose run --rm app pytest
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Ubuntu 24.04 marks the system Python as externally managed (PEP 668), so use a venv.
RUN python3 -m venv $VIRTUAL_ENV

# CPU-only PyTorch, in its own layer so code changes don't re-download it.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

WORKDIR /app
COPY . .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -e ".[dev]" \
    && chown -R ubuntu:ubuntu /app

# The base image's built-in user has UID 1000, matching the host user,
# so files written to the mounted volumes are not owned by root.
USER ubuntu

CMD ["pytest"]
