"""Python CLI tool for managing assets within Foundry Virtual Tabletop."""
from fwt.cli import main


__all__ = ["main"]

if __name__ == "__main__":
    main(  # pragma: no cover, pylint: disable=no-value-for-parameter
        prog_name="foundry-world-tools"
    )
