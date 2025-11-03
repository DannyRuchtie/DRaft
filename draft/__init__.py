"""DRaft package initialization."""

from importlib import metadata

try:
    __version__ = metadata.version("draft")
except metadata.PackageNotFoundError:  # pragma: no cover - best effort value during development
    __version__ = "0.0.0"

__all__ = ["__version__"]
