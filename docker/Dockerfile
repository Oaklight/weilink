# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12
ARG REGISTRY_MIRROR
FROM ${REGISTRY_MIRROR:-docker.io}/python:${PYTHON_VERSION}-alpine AS base

ARG PYPI_MIRROR
ARG LOCAL_WHEEL
ARG PACKAGE_VERSION

# Prevents Python from writing pyc files and enables unbuffered output.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Create a non-privileged user (alpine syntax).
ARG UID=10001
RUN adduser -D -u "${UID}" appuser

# Copy local wheels if available
RUN mkdir -p /tmp/dist/
COPY . /tmp/build/
RUN if [ -d "/tmp/build/dist" ] && [ "$(ls -A /tmp/build/dist 2>/dev/null)" ]; then \
        cp /tmp/build/dist/*.whl /tmp/dist/ 2>/dev/null || true; \
    fi

# Install weilink[server]: local wheel > specific version > latest from PyPI
# Then remove pip/setuptools to save ~10MB
RUN if [ -n "$LOCAL_WHEEL" ] && [ -f "/tmp/dist/$LOCAL_WHEEL" ]; then \
        echo "Installing from local wheel: $LOCAL_WHEEL"; \
        if [ -n "$PYPI_MIRROR" ]; then \
            pip install -i "$PYPI_MIRROR" --no-cache-dir "/tmp/dist/${LOCAL_WHEEL}[server]"; \
        else \
            pip install --no-cache-dir "/tmp/dist/${LOCAL_WHEEL}[server]"; \
        fi; \
    elif [ -n "$PACKAGE_VERSION" ]; then \
        echo "Installing weilink version: $PACKAGE_VERSION"; \
        if [ -n "$PYPI_MIRROR" ]; then \
            pip install -i "$PYPI_MIRROR" --no-cache-dir "weilink[server]==$PACKAGE_VERSION"; \
        else \
            pip install --no-cache-dir "weilink[server]==$PACKAGE_VERSION"; \
        fi; \
    else \
        echo "Installing latest weilink from PyPI"; \
        if [ -n "$PYPI_MIRROR" ]; then \
            pip install -i "$PYPI_MIRROR" --no-cache-dir "weilink[server]"; \
        else \
            pip install --no-cache-dir "weilink[server]"; \
        fi; \
    fi && \
    pip uninstall -y pip setuptools 2>/dev/null || true && \
    rm -rf /tmp/dist/ /tmp/build/

# Data directory for session tokens — mount a volume here to persist across restarts.
RUN mkdir -p /data/weilink && chown appuser:appuser /data/weilink
VOLUME /data/weilink

USER appuser

EXPOSE 8000 8080

CMD ["weilink", "mcp", "-t", "sse", "--host", "0.0.0.0", "-p", "8000", "--admin-port", "8080", "-d", "/data/weilink"]
