.PHONY: all build-package push-package clean-package build-docker push-docker clean-docker test lint format typecheck clean help

DOCKER_IMAGE := oaklight/weilink
VERSION := $(shell grep '__version__' src/weilink/__init__.py | head -1 | cut -d'"' -f2)

# Optional variables
V ?= $(VERSION)
PYPI_MIRROR ?=
REGISTRY_MIRROR ?=

all: lint format typecheck test

# ──────────────────────────────────────────────
# Package
# ──────────────────────────────────────────────

build-package:
	python -m build

push-package:
	twine upload dist/*

clean-package:
	rm -rf dist/ build/ src/*.egg-info

# ──────────────────────────────────────────────
# Docker
# ──────────────────────────────────────────────

build-docker:
	@echo "Building Docker image $(DOCKER_IMAGE):$(V)..."
	@BUILD_ARGS=""; \
	if [ -n "$(REGISTRY_MIRROR)" ]; then \
		echo "Using registry mirror: $(REGISTRY_MIRROR)"; \
		BUILD_ARGS="$$BUILD_ARGS --build-arg REGISTRY_MIRROR=$(REGISTRY_MIRROR)"; \
	fi; \
	LOCAL_WHEEL=""; \
	if [ -d "dist" ] && [ -n "$$(ls -A dist/*.whl 2>/dev/null)" ]; then \
		LOCAL_WHEEL=$$(ls dist/*.whl | head -n 1 | xargs basename); \
		echo "Found local wheel: $$LOCAL_WHEEL"; \
		BUILD_ARGS="$$BUILD_ARGS --build-arg LOCAL_WHEEL=$$LOCAL_WHEEL"; \
	elif [ -n "$(V)" ]; then \
		echo "Using version: $(V)"; \
		BUILD_ARGS="$$BUILD_ARGS --build-arg PACKAGE_VERSION=$(V)"; \
	else \
		echo "No local wheel or version specified, will install latest from PyPI"; \
	fi; \
	if [ -n "$(PYPI_MIRROR)" ]; then \
		echo "Using PyPI mirror: $(PYPI_MIRROR)"; \
		BUILD_ARGS="$$BUILD_ARGS --build-arg PYPI_MIRROR=$(PYPI_MIRROR)"; \
	fi; \
	cd docker && docker build -f Dockerfile $$BUILD_ARGS -t $(DOCKER_IMAGE):$(V) -t $(DOCKER_IMAGE):latest ..
	@echo "Docker image built successfully."

push-docker:
	@echo "Pushing Docker images $(DOCKER_IMAGE):$(V) and $(DOCKER_IMAGE):latest..."
	docker push $(DOCKER_IMAGE):$(V)
	docker push $(DOCKER_IMAGE):latest
	@echo "Docker images pushed successfully."

clean-docker:
	@echo "Cleaning Docker images..."
	docker rmi $(DOCKER_IMAGE):latest 2>/dev/null || true
	docker rmi $(DOCKER_IMAGE):$(V) 2>/dev/null || true

# ──────────────────────────────────────────────
# Development
# ──────────────────────────────────────────────

test:
	pytest tests/ -v

lint:
	ruff check src/ tests/ --fix

format:
	ruff format src/ tests/

typecheck:
	ty check

clean: clean-package
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov

help:
	@echo "Available targets:"
	@echo ""
	@echo "Package:"
	@echo "  build-package  - Build Python package"
	@echo "  push-package   - Upload to PyPI"
	@echo "  clean-package  - Remove build artifacts"
	@echo ""
	@echo "Docker:"
	@echo "  build-docker   - Build Docker image"
	@echo "  push-docker    - Push Docker image to registry"
	@echo "  clean-docker   - Clean Docker images"
	@echo ""
	@echo "Development:"
	@echo "  test           - Run tests"
	@echo "  lint           - Run ruff linter with auto-fix"
	@echo "  format         - Format code with ruff"
	@echo "  typecheck      - Run ty type checker"
	@echo "  clean          - Clean all generated files"
	@echo ""
	@echo "Usage examples:"
	@echo "  make build-docker"
	@echo "  make build-docker V=0.3.0"
	@echo "  make build-docker PYPI_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple"
	@echo "  make build-docker REGISTRY_MIRROR=docker.1ms.run"
	@echo ""
	@echo "Variables:"
	@echo "  V=<version>              - Specify version (default: auto-detected from __init__.py)"
	@echo "  PYPI_MIRROR=<url>        - PyPI mirror URL"
	@echo "  REGISTRY_MIRROR=<host>   - Docker registry mirror"
