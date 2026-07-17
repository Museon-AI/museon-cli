"""Museon CLI client."""

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("museoncli")
except PackageNotFoundError:  # pragma: no cover - only for an unpackaged source tree
    __version__ = "0.0.0+source"
