"""Python CLI tool for managing assets within Foundry Virtual Tabletop."""
from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("foundry-world-tools")
except PackageNotFoundError:
    __version__ = "unknown"
