"""Standalone admin panel server CLI.

Delegates to the unified ``weilink admin`` CLI.
Can also be invoked directly via ``python -m weilink.admin``.

Examples::

    # Default profile (~/.weilink/)
    weilink admin --host 0.0.0.0 --port 8080

    # Custom profile for a different bot
    weilink admin -d /data/bot-work -p 9090
"""

from __future__ import annotations


def main(argv: list[str] | None = None) -> None:
    """Run the WeiLink admin panel as a standalone server."""
    import sys

    from weilink.cli import main as cli_main

    cli_args = ["admin"]
    if argv is not None:
        cli_args.extend(argv)
    else:
        cli_args.extend(sys.argv[1:])
    cli_main(cli_args)


if __name__ == "__main__":
    main()
