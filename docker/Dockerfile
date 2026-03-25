# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12
ARG REGISTRY_MIRROR
FROM ${REGISTRY_MIRROR:-docker.io}/python:${PYTHON_VERSION}-slim AS base

ARG PYPI_MIRROR
ARG LOCAL_WHEEL
ARG PACKAGE_VERSION

# Prevents Python from writing pyc files and enables unbuffered output.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Create a non-privileged user.
ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --uid "${UID}" \
    appuser

# Copy local wheels if available
RUN mkdir -p /tmp/dist/
COPY . /tmp/build/
RUN if [ -d "/tmp/build/dist" ] && [ "$(ls -A /tmp/build/dist 2>/dev/null)" ]; then \
        cp /tmp/build/dist/*.whl /tmp/dist/ 2>/dev/null || true; \
    fi

# Install weilink: local wheel > specific version > latest from PyPI
RUN if [ -n "$LOCAL_WHEEL" ] && [ -f "/tmp/dist/$LOCAL_WHEEL" ]; then \
        echo "Installing from local wheel: $LOCAL_WHEEL"; \
        if [ -n "$PYPI_MIRROR" ]; then \
            pip install -i "$PYPI_MIRROR" --no-cache-dir "/tmp/dist/${LOCAL_WHEEL}"; \
        else \
            pip install --no-cache-dir "/tmp/dist/${LOCAL_WHEEL}"; \
        fi; \
    elif [ -n "$PACKAGE_VERSION" ]; then \
        echo "Installing weilink version: $PACKAGE_VERSION"; \
        if [ -n "$PYPI_MIRROR" ]; then \
            pip install -i "$PYPI_MIRROR" --no-cache-dir "weilink==$PACKAGE_VERSION"; \
        else \
            pip install --no-cache-dir "weilink==$PACKAGE_VERSION"; \
        fi; \
    else \
        echo "Installing latest weilink from PyPI"; \
        if [ -n "$PYPI_MIRROR" ]; then \
            pip install -i "$PYPI_MIRROR" --no-cache-dir weilink; \
        else \
            pip install --no-cache-dir weilink; \
        fi; \
    fi && \
    rm -rf /tmp/dist/ /tmp/build/

# Data directory for session tokens — mount a volume here to persist across restarts.
RUN mkdir -p /data/weilink && chown appuser:appuser /data/weilink
VOLUME /data/weilink

USER appuser

EXPOSE 8080

CMD ["weilink-admin", "--host", "0.0.0.0", "--port", "8080", "-d", "/data/weilink"]
