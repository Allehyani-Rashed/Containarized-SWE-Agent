"""Miscellaneous helpers shared across project cache submodules."""

from __future__ import annotations


def is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


__all__ = ["is_truthy"]

