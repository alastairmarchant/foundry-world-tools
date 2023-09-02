"""Test cases for the __main__ module."""
import os
from typing import List, cast
from unittest.mock import Mock

import pytest
from click.testing import CliRunner
from pytest_mock import MockerFixture

from fwt import cli as cli


PRESETS = {
    "dedup": {
        "bycontent": True,
        "command": "dedup",
        "description": "Find duplicate image files and chooses files from the "
        + "characters,journal,scenes directories to keep",
        "ext": [".png", ".jpg", ".jpeg", ".gif", ".webp"],
        "preferred": [
            "<project_dir>/characters.*token.*",
            "<project_dir>/characters",
            "<project_dir>/journal",
            "<project_dir>/scenes/backgrounds",
            "<project_dir>/scenes",
        ],
    },
}


@pytest.fixture
def runner() -> CliRunner:
    """Fixture for invoking command-line interfaces."""
    return CliRunner()


@pytest.fixture(autouse=True)
def patch_imports(mocker: MockerFixture) -> None:
    mocker.patch("fwt.cli.click.echo")
    mocker.patch("fwt.cli.click.edit")
    mocker.patch("fwt.cli.click.get_app_dir", return_value="~/.config/fwt")

    mocker.patch("fwt.cli.Path", wraps=cli.Path)

    mocker.patch("fwt.cli.setup_logging")
    mocker.patch("fwt.cli.FWTAssetDownloader")
    mocker.patch(
        "fwt.cli.FWTConfig", return_value={"dataDir": "./path/to/foundrydata/"}
    )
    mocker.patch("fwt.cli.FWTFileManager")
    mocker.patch("fwt.cli.FWTNeDB")
    mocker.patch("fwt.cli.FWTPath")
    mocker.patch("fwt.cli.FWTProjectDb")
    mocker.patch("fwt.cli.FWTSetManager")


def test_main_succeeds(runner: CliRunner) -> None:
    """It exits with a status code of zero."""
    result = runner.invoke(cli.main)
    assert result.exit_code == 0


@pytest.mark.parametrize(
    "args",
    [
        ["--config", "./config.json"],
        [],
    ],
)
def test_main_gets_config(runner: CliRunner, args: List[str]) -> None:
    result = runner.invoke(cli.main, args=args)

    if args:
        cast(Mock, cli.Path).assert_called_once_with(args[1])
        cast(Mock, cli.click.get_app_dir).assert_not_called()
    else:
        cast(Mock, cli.click.get_app_dir).assert_called_once_with("fwt")
        cast(Mock, cli.Path).assert_called_once_with("~/.config/fwt")

    assert result.exit_code == 0


def test_main_edit_config(runner: CliRunner) -> None:
    result = runner.invoke(cli.main, args=["--config", "./config.json", "--edit"])

    cast(Mock, cli.click.edit).assert_called_once_with(filename="config.json")

    assert result.exit_code == 0


def test_main_exits_on_data_dir_failure(
    mocker: MockerFixture, runner: CliRunner
) -> None:
    mocker.patch("fwt.cli.FWTConfig", side_effect=cli.FWTConfigNoDataDirError)
    result = runner.invoke(cli.main, args=["--config", "./config.json"])

    assert result.exit_code == 2


def test_main_exits_on_config_failure(mocker: MockerFixture, runner: CliRunner) -> None:
    mocker.patch("fwt.cli.FWTConfig", side_effect=cli.FWTFileError)
    result = runner.invoke(cli.main, args=["--config", "./config.json"])

    assert result.exit_code == 2


def test_main_no_exit_on_default_config_failure(
    mocker: MockerFixture, runner: CliRunner
) -> None:
    mocker.patch("fwt.cli.FWTConfig", side_effect=cli.FWTFileError)
    result = runner.invoke(cli.main)

    assert result.exit_code == 0


def test_main_exits_on_config_error(mocker: MockerFixture, runner: CliRunner) -> None:
    mocker.patch("fwt.cli.FWTConfig", return_value={"error": "Error with config."})
    result = runner.invoke(cli.main)

    assert result.exit_code == 2


def test_main_preset_with_no_presets(mocker: MockerFixture, runner: CliRunner) -> None:
    mocker.patch("fwt.cli.FWTConfig", return_value={"presets": {}})
    result = runner.invoke(cli.main, args=["--preset", "dedup"])

    assert result.exit_code == 2


def test_main_command_not_in_preset(mocker: MockerFixture, runner: CliRunner) -> None:
    mocker.patch(
        "fwt.cli.FWTConfig", return_value={"presets": {"dedup": {"command": "other"}}}
    )
    result = runner.invoke(cli.main, args=["--preset", "dedup", "dedup"])

    assert result.exit_code == 2


def test_main_preset_not_in_presets(mocker: MockerFixture, runner: CliRunner) -> None:
    mocker.patch("fwt.cli.FWTConfig", return_value={"presets": {"other": {}}})
    result = runner.invoke(cli.main, args=["--preset", "dedup"])

    assert result.exit_code == 2


def test_main_with_preset(mocker: MockerFixture, runner: CliRunner) -> None:
    mocker.patch(
        "fwt.cli.FWTConfig",
        return_value={
            "presets": PRESETS,
        },
    )
    with runner.isolated_filesystem():
        os.mkdir("test_dir")
        result = runner.invoke(
            cli.main, args=["--preset", "dedup", "dedup", "test_dir"]
        )

    assert result.exit_code == 0


def test_main_show_presets_fail(mocker: MockerFixture, runner: CliRunner) -> None:
    mocker.patch(
        "fwt.cli.FWTConfig",
        return_value={
            "presets": {},
        },
    )
    with runner.isolated_filesystem():
        os.mkdir("test_dir")
        result = runner.invoke(cli.main, args=["--showpresets"])

    cast(Mock, cli.click.echo).assert_not_called()

    assert result.exit_code == 2


def test_main_show_presets(mocker: MockerFixture, runner: CliRunner) -> None:
    mocker.patch(
        "fwt.cli.FWTConfig",
        return_value={
            "presets": PRESETS,
        },
    )
    with runner.isolated_filesystem():
        os.mkdir("test_dir")
        result = runner.invoke(cli.main, args=["--showpresets"])

    cast(Mock, cli.click.echo).assert_called_once_with(
        "\nPresets:\n"
        + "\n".join(
            [
                f"\t{k}: {v['command']} command, {v['description']}"
                for (k, v) in PRESETS.items()
            ]
        )
    )

    assert result.exit_code == 0


def test_main_mkconfig_exits(runner: CliRunner) -> None:
    result = runner.invoke(cli.main, args=["--mkconfig"])

    assert result.exit_code == 0


def test_main_no_help(mocker: MockerFixture, runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        os.mkdir("test_dir")
        result = runner.invoke(
            cli.main, args=["--config", "config.json", "info", "test_dir"]
        )

    print(result.output)

    assert result.exit_code == 0
