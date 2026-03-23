.PHONY: all build-package push-package clean-package test lint format typecheck clean help

PYPI_MIRROR ?=

all: lint format typecheck test

build-package:
	python -m build

push-package:
	twine upload dist/*

clean-package:
	rm -rf dist/ build/ src/*.egg-info

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
	@echo "  build-package  - Build Python package"
	@echo "  push-package   - Upload to PyPI"
	@echo "  clean-package  - Remove build artifacts"
	@echo "  test           - Run tests"
	@echo "  lint           - Run ruff linter with auto-fix"
	@echo "  format         - Format code with ruff"
	@echo "  typecheck      - Run ty type checker"
	@echo "  clean          - Clean all generated files"
	@echo ""
	@echo "Variables:"
	@echo "  PYPI_MIRROR=<url>  - PyPI mirror URL for pip install"
