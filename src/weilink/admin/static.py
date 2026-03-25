"""Static assets for admin panel UI."""

import importlib.resources


def _load_html() -> str:
    """Load admin.html from the package data."""
    package = __package__ or __name__
    return importlib.resources.files(package).joinpath("admin.html").read_text("utf-8")


def load_locale(lang: str) -> str | None:
    """Load a locale JSON file by language code.

    Args:
        lang: Language code (e.g. "en", "zh").

    Returns:
        JSON string or None if not found.
    """
    package = __package__ or __name__
    path = importlib.resources.files(package).joinpath(f"locales/{lang}.json")
    try:
        return path.read_text("utf-8")
    except FileNotFoundError:
        return None


ADMIN_HTML = _load_html()
