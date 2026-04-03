"""Startup banner and PyPI version check (zero external dependencies)."""

from __future__ import annotations

import json
import logging
import urllib.request
from urllib.error import URLError

from weilink import __version__

logger = logging.getLogger(__name__)

CHANGELOG_URL = "https://weilink.readthedocs.io/en/latest/changelog/"
PYPI_JSON_URL = "https://pypi.org/pypi/weilink/json"


def get_ascii_banner() -> str:
    """Return the WeiLink ASCII art banner."""
    return r"""
 __        __   _ _     _       _
 \ \      / /__(_) |   (_)_ __ | | __
  \ \ /\ / / _ \ | |   | | '_ \| |/ /
   \ V  V /  __/ | |___| | | | |   <
    \_/\_/ \___|_|_____|_|_| |_|_|\_\
"""


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse a version string into a comparable tuple of integers.

    Pre-release suffixes (e.g. ``0.3.0b2``) are stripped so that
    ``0.3.0`` > ``0.3.0b2`` holds true.
    """
    parts: list[int] = []
    for segment in v.split("."):
        num = ""
        for ch in segment:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    return tuple(parts)


def get_latest_pypi_version() -> str | None:
    """Fetch the latest stable version from PyPI (sync, 3s timeout).

    Returns ``None`` on any network or parsing failure.
    """
    try:
        req = urllib.request.Request(
            PYPI_JSON_URL,
            headers={
                "Accept": "application/json",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
        return data["info"]["version"]
    except (URLError, OSError, KeyError, json.JSONDecodeError, ValueError):
        return None


def version_check() -> str:
    """Return version string with update notice (for ``--version`` flag)."""
    lines = [__version__]
    latest = get_latest_pypi_version()
    if latest and _parse_version(latest) > _parse_version(__version__):
        lines.extend(
            [
                f"New version available: {latest}",
                "Update with: pip install --upgrade weilink",
                f"Changelog: {CHANGELOG_URL}",
            ]
        )
    return "\n".join(lines)


def display_startup_banner(no_banner: bool = False) -> None:
    """Print the startup banner and version info to stdout."""
    if not no_banner:
        print(get_ascii_banner())

    latest = get_latest_pypi_version()

    if latest and _parse_version(latest) > _parse_version(__version__):
        print(f"  WeiLink v{__version__}")
        print(f"  Update available: v{latest}")
        print("    pip install --upgrade weilink")
        print(f"    {CHANGELOG_URL}")
    else:
        print(f"  WeiLink v{__version__} (latest)")
    print()
