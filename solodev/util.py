"""Miscellaneous helper utilities for SoloDev."""

from __future__ import annotations

import datetime as _dt
import os
import re
from typing import Any, Iterable

_DURATION_PATTERN = re.compile(r"^\s*(\d+)([smhd])\s*$")


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return a new dictionary with override merged into base."""
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def parse_duration(value: str) -> _dt.timedelta:
    """Parse duration strings like ``30s`` or ``5m`` into timedeltas."""
    match = _DURATION_PATTERN.match(value)
    if not match:
        raise ValueError(f"Unsupported duration value: {value!r}")

    amount = int(match.group(1))
    unit = match.group(2)
    if unit == "s":
        return _dt.timedelta(seconds=amount)
    if unit == "m":
        return _dt.timedelta(minutes=amount)
    if unit == "h":
        return _dt.timedelta(hours=amount)
    if unit == "d":
        return _dt.timedelta(days=amount)
    raise ValueError(f"Unsupported duration unit: {unit}")  # pragma: no cover


def format_timedelta(delta: _dt.timedelta) -> str:
    """Render a human-friendly representation of a timedelta."""
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds}s"
    if total_seconds < 3600:
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes}m {seconds}s"
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"


def env_first(*keys: str, default: str | None = None) -> str | None:
    """Return the first non-empty environment variable among keys."""
    for key in keys:
        value = os.environ.get(key)
        if value:
            return value
    return default


def chunked(iterable: Iterable[Any], size: int) -> Iterable[list[Any]]:
    """Yield lists of length ``size`` from ``iterable``."""
    chunk: list[Any] = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def now_utc() -> _dt.datetime:
    """Return the current UTC datetime."""
    return _dt.datetime.now(tz=_dt.timezone.utc)
