"""CompactBench — open benchmark for AI conversation compaction methods."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("compactbench")
except PackageNotFoundError:  # pragma: no cover - during local dev without install
    __version__ = "0.0.0+local"

__all__ = ["__version__"]
