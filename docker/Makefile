DOCKER_REPO = oaklight/weilink-admin
VERSION := $(shell grep '__version__' ../src/weilink/__init__.py | head -1 | cut -d'"' -f2)

# Optional variables
REGISTRY_MIRROR ?=
PYPI_MIRROR ?=

BUILD_ARGS =
ifneq ($(REGISTRY_MIRROR),)
BUILD_ARGS += --build-arg REGISTRY_MIRROR=$(REGISTRY_MIRROR)
endif
ifneq ($(PYPI_MIRROR),)
BUILD_ARGS += --build-arg PYPI_MIRROR=$(PYPI_MIRROR)
endif

.PHONY: build push help

build:
	@echo "Building Docker image $(DOCKER_REPO):$(VERSION)..."
	docker build -f Dockerfile $(BUILD_ARGS) -t $(DOCKER_REPO):$(VERSION) -t $(DOCKER_REPO):latest ..
	@echo "Docker image built successfully."

push:
	@echo "Pushing Docker images $(DOCKER_REPO):$(VERSION) and $(DOCKER_REPO):latest..."
	docker push $(DOCKER_REPO):$(VERSION)
	docker push $(DOCKER_REPO):latest
	@echo "Docker images pushed successfully."

help:
	@echo "Available targets:"
	@echo ""
	@echo "  build  - Build Docker image"
	@echo "  push   - Push Docker image to registry"
	@echo "  help   - Show this help message"
	@echo ""
	@echo "Usage examples:"
	@echo "  make build"
	@echo "  make build PYPI_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple"
	@echo "  make build REGISTRY_MIRROR=docker.1ms.run"
	@echo ""
	@echo "Docker run examples:"
	@echo "  docker run -p 8080:8080 -v weilink-data:/data/weilink $(DOCKER_REPO):latest"
	@echo "  # Multiple profiles:"
	@echo "  docker run -p 8080:8080 -v bot-personal:/data/weilink $(DOCKER_REPO):latest"
	@echo "  docker run -p 8081:8080 -v bot-work:/data/weilink $(DOCKER_REPO):latest"
	@echo ""
	@echo "Variables:"
	@echo "  REGISTRY_MIRROR=<host>  - Docker registry mirror"
	@echo "  PYPI_MIRROR=<url>       - PyPI mirror URL"
