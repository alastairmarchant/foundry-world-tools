#! /usr/local/bin/python3
"""A command-line utility for converting a nedb file into a yaml file.

A command-line utility for converting a nedb (jsonlines) file to a yaml
file containing a document for each json object. nedb2yaml.py reads a nedb
file given as a command-line parameter and prints the corresponding YAML
structure on standard out. nedb2yaml is useful as a git diff textconv.
For more information see
https://git-scm.com/docs/git-diff-files#Documentation/git-diff-files.txt---textconv

"""
import sys
from pathlib import Path
from typing import List

import jsonlines
import yaml

from fwt.typing import StrOrBytesPath


def nedb2yaml(file: StrOrBytesPath) -> List[str]:
    """Convert jsonlines file to yaml.

    Args:
        file: Path to file.

    Returns:
        File contents as yaml, with a new yaml string for each entry.
    """
    file_output = []
    with jsonlines.open(file) as reader:
        for line in reader:
            file_output.append(yaml.dump(line, indent=2))
    return file_output


def show_help() -> None:
    """Show help text for nedb2yaml."""
    print(f"{__doc__}\nUSAGE:\n  {Path(sys.argv[0]).name} <filename>")


if __name__ == "__main__":
    if len(sys.argv) == 2:
        if sys.argv[1] in ("-h", "--help"):
            show_help()
            sys.exit(0)
        nedbfile = Path(sys.argv[1])
        if nedbfile.exists():
            output = nedb2yaml(nedbfile)
            print("---\n".join(output))
            sys.exit(0)
        else:
            print(f"Error: File {nedbfile!r} does not exist!")
            show_help()
            sys.exit(1)
    else:
        print(
            f"\nError: {sys.argv[0]} requires 1 parameter, "
            + "the path of a nedb file."
        )
        show_help()
        sys.exit(1)
