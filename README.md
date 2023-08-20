# Foundry World Tools

[![PyPI](https://img.shields.io/pypi/v/foundry-world-tools.svg)][pypi_]
[![Status](https://img.shields.io/pypi/status/foundry-world-tools.svg)][status]
[![Python Version](https://img.shields.io/pypi/pyversions/foundry-world-tools)][python version]
[![License](https://img.shields.io/pypi/l/foundry-world-tools)][license]

[![Read the documentation at https://foundry-world-tools.readthedocs.io/](https://img.shields.io/readthedocs/foundry-world-tools/latest.svg?label=Read%20the%20Docs)][read the docs]
[![Tests](https://github.com/alastairmarchant/foundry-world-tools/workflows/Tests/badge.svg)][tests]
[![Codecov](https://codecov.io/gh/alastairmarchant/foundry-world-tools/branch/main/graph/badge.svg)][codecov]

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)][pre-commit]
[![Black](https://img.shields.io/badge/code%20style-black-000000.svg)][black]

[pypi_]: https://pypi.org/project/foundry-world-tools/
[status]: https://pypi.org/project/foundry-world-tools/
[python version]: https://pypi.org/project/foundry-world-tools
[read the docs]: https://foundry-world-tools.readthedocs.io/
[tests]: https://github.com/alastairmarchant/foundry-world-tools/actions?workflow=Tests
[codecov]: https://app.codecov.io/gh/alastairmarchant/foundry-world-tools
[pre-commit]: https://github.com/pre-commit/pre-commit
[black]: https://github.com/psf/black
[foundry vtt]: https://foundryvtt.com/
[foundry user data]: https://foundryvtt.com/article/user-data/
[foundry-world-tools]: https://github.com/nathan-sain/foundry-world-tools

This is a fork of [foundry-world-tools] written by Nathan Sain. The original repo has not been updated since early 2022, and does not support newer versions of Foundry.

Foundry World Tools (FWT) is a Python CLI crafted for efficient asset management in [Foundry VTT] projects. With FWT, you can easily relocate files or remove duplicated files. When any files are modified, the corresponding databases are also updated. Instead of deleting files, FWT moves them to a designated trash directory within the world directory, and it creates backup copies of updated database files for added security.

## Features

- Move/rename files and update Foundry databases with new file locations
- Identify and remove duplicate files, allowing matching based on contents or filenames
- Mass file renaming based on patterns
- Download remotely hosted files
- Copy all assets from outside project directory into that project directory
- Conversion between Foundry database files and yaml
  - Utilities for displaying database file git diff as yaml

## Installation

You can install _Foundry World Tools_ via [pip] from [PyPI]:

```console
pip install foundry-world-tools
```

## Foundry User Data Directory

In order for FWT to correctly update file paths in the database, it must know the location of the user data directory, as file paths are stored relative to this. If the configuration file does not have the user data directory or the `--dataDir` option is not passed FWT will attempt to auto-detect the user data path. This is will work best when FWT is used within in a project directory. If run from outside the user data directory, this will fail.

For information about the Foundry User Data, see [Foundry User Data].

## Deleting Files

FWT doesn't delete any files. When file paths are removed from the the database the corresponding files are moved to a trash directory located in the root of the project directory. Additionally when databases are to be modified, before changes are made, a unmodified version of the database file is stored in the trash directory. FWT uses a incrementing trash directory scheme. The first trash directory is trash/session.0 and on consecutive runs new trash directories will be created: trash/session.1, trash/session.2 etc. This makes it possible to preserve files and databases across multiple runs as well as easily removing all of the trash files by deleting the trash folder.

## Usage

Please see the [Command-line Reference] for details.

## Contributing

Contributions are very welcome.
To learn more, see the [Contributor Guide].

## License

Distributed under the terms of the [MIT license][license],
_Foundry World Tools_ is free and open source software.

## Issues

If you encounter any problems,
please [file an issue] along with a detailed description.

## Credits

This is a fork of [foundry-world-tools] written by [https://github.com/nathan-sain](Nathan Sain).

This project was generated from [@cjolowicz]'s [Hypermodern Python Cookiecutter] template.

[@cjolowicz]: https://github.com/cjolowicz
[pypi]: https://pypi.org/
[hypermodern python cookiecutter]: https://github.com/cjolowicz/cookiecutter-hypermodern-python
[file an issue]: https://github.com/alastairmarchant/foundry-world-tools/issues
[pip]: https://pip.pypa.io/

<!-- github-only -->

[config]: https://github.com/alastairmarchant/foundry-world-tools/blob/main/CONFIG.md
[license]: https://github.com/alastairmarchant/foundry-world-tools/blob/main/LICENSE
[contributor guide]: https://github.com/alastairmarchant/foundry-world-tools/blob/main/CONTRIBUTING.md
[command-line reference]: https://foundry-world-tools.readthedocs.io/en/latest/usage.html
