"""Backward-compatibility shim -- use weilink._cli._hook instead."""

from weilink._cli._hook import hook_poll, run_hook_poll  # noqa: F401

__all__ = ["hook_poll", "run_hook_poll"]
