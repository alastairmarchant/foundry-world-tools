"""Python CLI tool for managing assets within Foundry Virtual Tabletop."""
from fwt.cli import cli


if __name__ == "__main__":
    cli(  # pragma: no cover, pylint: disable=no-value-for-parameter
        prog_name="foundry-world-tools"
    )
