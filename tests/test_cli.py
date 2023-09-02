"""Test cases for the __main__ module."""
import os
from typing import List, cast
from unittest.mock import Mock

import pytest
from click.testing import CliRunner
from pytest_mock import MockerFixture
from typing_extensions import TypedDict

from fwt import cli as cli


class PresetDict(TypedDict):
    command: str
    description: str


class DedupPresetDict(PresetDict):
    ext: List[str]
    bycontent: bool
    preferred: List[str]


class RenameallPresetDict(PresetDict):
    ext: List[str]
    replace: List[str]
    remove: List[str]
    lower: bool


class AllPresets(TypedDict):
    showinfo: PresetDict
    dedupimg: DedupPresetDict
    fixnames: RenameallPresetDict


PRESETS: AllPresets = {
    "showinfo": {
        "command": "info",
        "description": "Show info for dir",
    },
    "dedupimg": {
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
    "fixnames": {
        "command": "renameall",
        "description": "Fix names for files",
        "ext": [],
        "replace": ["/-/_/"],
        "remove": ["@", "#"],
        "lower": True,
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
        "fwt.cli.FWTConfig",
        return_value={
            "dataDir": "./path/to/foundrydata/",
            "presets": PRESETS,
        },
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
    result = runner.invoke(cli.main, args=["--preset", "showinfo"])

    assert result.exit_code == 2


def test_main_command_not_in_preset(mocker: MockerFixture, runner: CliRunner) -> None:
    mocker.patch(
        "fwt.cli.FWTConfig",
        return_value={"presets": {"showinfo": {"command": "other"}}},
    )
    result = runner.invoke(cli.main, args=["--preset", "showinfo", "info"])

    assert result.exit_code == 2


def test_main_preset_not_in_presets(mocker: MockerFixture, runner: CliRunner) -> None:
    mocker.patch("fwt.cli.FWTConfig", return_value={"presets": {"other": {}}})
    result = runner.invoke(cli.main, args=["--preset", "showinfo"])

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
            cli.main, args=["--preset", "showinfo", "info", "test_dir"]
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
                f"\t{k}: {cast(PresetDict, v)['command']} command, "
                + f"{cast(PresetDict, v)['description']}"
                for (k, v) in PRESETS.items()
            ]
        )
    )

    assert result.exit_code == 0


def test_main_mkconfig_exits(runner: CliRunner) -> None:
    result = runner.invoke(cli.main, args=["--mkconfig"])

    assert result.exit_code == 0


def test_main_no_help(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        os.mkdir("test_dir")
        result = runner.invoke(
            cli.main, args=["--config", "config.json", "info", "test_dir"]
        )

    assert result.exit_code == 0


@pytest.mark.parametrize("by", ["name", "content"])
def test_dedup(runner: CliRunner, by: str) -> None:
    with runner.isolated_filesystem():
        os.mkdir("test_dir")
        os.mkdir("test_exc")
        result = runner.invoke(
            cli.main,
            args=["dedup", "test_dir", f"--by{by}", "--exclude-dir", "test_exc"],
        )

    cast(Mock, cli.FWTPath).assert_called_once_with("test_dir")
    cast(Mock, cli.FWTSetManager).assert_called_once_with(cli.FWTPath("test_dir"))
    dup_manager = cast(Mock, cli.FWTSetManager(cli.FWTPath("test_dir")))
    dup_manager.add_exclude_dir.assert_called_once_with("test_exc")

    assert dup_manager.detect_method == f"by{by}"
    dup_manager.add_preferred_pattern.assert_not_called()

    dup_manager.add_file_extensions.assert_called_once_with(tuple())
    dup_manager.scan.assert_called_once_with()
    dup_manager.set_preferred_on_all.assert_called_once_with()
    dup_manager.generate_rewrite_queue.assert_called_once_with()
    dup_manager.process_file_queue.assert_called_once_with()
    dup_manager.process_rewrite_queue.assert_called_once_with()

    assert result.exit_code == 0


def test_dedup_with_preset(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        os.mkdir("test_dir")
        result = runner.invoke(
            cli.main, args=["--preset", "dedupimg", "dedup", "test_dir"]
        )

    cast(Mock, cli.FWTPath).assert_called_once_with("test_dir")
    cast(Mock, cli.FWTSetManager).assert_called_once_with(cli.FWTPath("test_dir"))
    dup_manager = cast(Mock, cli.FWTSetManager(cli.FWTPath("test_dir")))
    dup_manager.add_exclude_dir.assert_not_called()

    preset = PRESETS["dedupimg"]

    assert dup_manager.detect_method == "bycontent"
    for pattern in preset["preferred"]:
        dup_manager.add_preferred_pattern.assert_any_call(pattern)

    dup_manager.add_file_extensions.assert_called_once_with(tuple(preset["ext"]))
    dup_manager.scan.assert_called_once_with()
    dup_manager.set_preferred_on_all.assert_called_once_with()
    dup_manager.generate_rewrite_queue.assert_called_once_with()
    dup_manager.process_file_queue.assert_called_once_with()
    dup_manager.process_rewrite_queue.assert_called_once_with()

    assert result.exit_code == 0


def test_dedup_no_method(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        os.mkdir("test_dir")
        result = runner.invoke(cli.main, args=["dedup", "test_dir"])

    cast(Mock, cli.FWTPath).assert_called_once_with("test_dir")
    cast(Mock, cli.FWTSetManager).assert_called_once_with(cli.FWTPath("test_dir"))
    dup_manager = cast(Mock, cli.FWTSetManager(cli.FWTPath("test_dir")))

    dup_manager.add_preferred_pattern.assert_not_called()

    dup_manager.add_file_extensions.assert_not_called()
    dup_manager.scan.assert_not_called()
    dup_manager.set_preferred_on_all.assert_not_called()
    dup_manager.generate_rewrite_queue.assert_not_called()
    dup_manager.process_file_queue.assert_not_called()
    dup_manager.process_rewrite_queue.assert_not_called()

    assert result.exit_code == 2


def test_dedup_both_methods(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        os.mkdir("test_dir")
        result = runner.invoke(
            cli.main, args=["dedup", "test_dir", "--bycontent", "--byname"]
        )

    cast(Mock, cli.FWTPath).assert_called_once_with("test_dir")
    cast(Mock, cli.FWTSetManager).assert_called_once_with(cli.FWTPath("test_dir"))
    dup_manager = cast(Mock, cli.FWTSetManager(cli.FWTPath("test_dir")))

    dup_manager.add_preferred_pattern.assert_not_called()

    dup_manager.add_file_extensions.assert_not_called()
    dup_manager.scan.assert_not_called()
    dup_manager.set_preferred_on_all.assert_not_called()
    dup_manager.generate_rewrite_queue.assert_not_called()
    dup_manager.process_file_queue.assert_not_called()
    dup_manager.process_rewrite_queue.assert_not_called()

    assert result.exit_code == 2


def test_renameall(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        os.mkdir("test_dir")
        result = runner.invoke(
            cli.main,
            args=["renameall", "test_dir", "--replace", "/-/_/", "--remove", "@"],
        )

    cast(Mock, cli.FWTPath).assert_called_once_with("test_dir")
    cast(Mock, cli.FWTFileManager).assert_called_once_with(cli.FWTPath("test_dir"))
    file_manager = cast(Mock, cli.FWTFileManager(cli.FWTPath("test_dir")))

    file_manager.add_remove_pattern.assert_called_once_with("@")
    file_manager.add_replace_pattern.assert_called_once_with("/-/_/")

    file_manager.add_file_extensions.assert_called_once_with(tuple())
    file_manager.scan.assert_called_once_with()
    file_manager.generate_rewrite_queue.assert_called_once_with(False)
    file_manager.process_file_queue.assert_called_once_with()
    file_manager.process_rewrite_queue.assert_called_once_with()

    assert result.exit_code == 0


def test_renameall_with_preset(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        os.mkdir("test_dir")
        result = runner.invoke(
            cli.main, args=["--preset", "fixnames", "renameall", "test_dir"]
        )

    cast(Mock, cli.FWTPath).assert_called_once_with("test_dir")
    cast(Mock, cli.FWTFileManager).assert_called_once_with(cli.FWTPath("test_dir"))
    file_manager = cast(Mock, cli.FWTFileManager(cli.FWTPath("test_dir")))

    preset = PRESETS["fixnames"]

    for remove_pattern in preset["remove"]:
        file_manager.add_remove_pattern.assert_any_call(remove_pattern)
    for replace_pattern in preset["replace"]:
        file_manager.add_replace_pattern.assert_any_call(replace_pattern)

    file_manager.add_file_extensions.assert_called_once_with(
        tuple(preset.get("ext", ()))
    )
    file_manager.scan.assert_called_once_with()
    file_manager.generate_rewrite_queue.assert_called_once_with(preset["lower"])
    file_manager.process_file_queue.assert_called_once_with()
    file_manager.process_rewrite_queue.assert_called_once_with()

    assert result.exit_code == 0


def test_renameall_no_options(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        os.mkdir("test_dir")
        result = runner.invoke(cli.main, args=["renameall", "test_dir"])

    cast(Mock, cli.FWTPath).assert_called_once_with("test_dir")
    cast(Mock, cli.FWTFileManager).assert_called_once_with(cli.FWTPath("test_dir"))
    file_manager = cast(Mock, cli.FWTFileManager(cli.FWTPath("test_dir")))

    file_manager.add_remove_pattern.assert_not_called()
    file_manager.add_replace_pattern.assert_not_called()
    file_manager.add_file_extensions.assert_not_called()
    file_manager.scan.assert_not_called()
    file_manager.generate_rewrite_queue.assert_not_called()
    file_manager.process_file_queue.assert_not_called()
    file_manager.process_rewrite_queue.assert_not_called()

    assert result.exit_code == 2


@pytest.mark.parametrize("keep_src", [True, False])
def test_rename(runner: CliRunner, mocker: MockerFixture, keep_src: bool) -> None:
    world_path = "./foundrydata/test-world"
    test_file = f"{world_path}/test.png"
    out_file = f"{world_path}/test-rename.png"

    def mock_fwt_path(path: str, exists: bool = True) -> Mock:
        return cast(
            Mock,
            mocker.MagicMock(
                as_rpd=mocker.MagicMock(return_value=world_path),
                to_fpd=mocker.MagicMock(
                    return_value="/path/to/foundrydata" + world_path.lstrip(".")
                ),
                is_project=True,
                is_project_dir=mocker.MagicMock(return_value=False),
            ),
        )

    mocker.patch("fwt.cli.FWTPath", side_effect=mock_fwt_path)
    with runner.isolated_filesystem():
        test_path = cli.Path(test_file).absolute()
        test_path.parent.mkdir(parents=True)
        test_path.touch()
        result = runner.invoke(
            cli.main,
            args=["rename", test_file, out_file] + (["--keep-src"] if keep_src else []),
        )

    print(result.output)

    cast(Mock, cli.FWTPath).assert_any_call(str(test_path))
    cast(Mock, cli.FWTPath).assert_any_call(out_file, exists=False)
    cast(Mock, cli.FWTFileManager).assert_called_once_with(
        cli.FWTPath(test_file).to_fpd()
    )
    file_manager = cast(Mock, cli.FWTFileManager(cli.FWTPath(test_file).to_fpd()))

    file_manager.add_file.assert_called_once()

    file_manager.generate_rewrite_queue.assert_called_once_with()
    file_manager.process_file_queue.assert_called_once_with()
    file_manager.process_rewrite_queue.assert_called_once_with()

    assert result.exit_code == 0


def test_rename_src_is_project(runner: CliRunner, mocker: MockerFixture) -> None:
    world_path = "./foundrydata/test-world"
    test_file = f"{world_path}/test.png"
    out_file = f"{world_path}/test-rename.png"

    def mock_fwt_path(path: str, exists: bool = True) -> Mock:
        return cast(
            Mock,
            mocker.MagicMock(
                as_rpd=mocker.MagicMock(return_value=world_path),
                to_fpd=mocker.MagicMock(
                    return_value="/path/to/foundrydata" + world_path.lstrip(".")
                ),
                is_project=path.endswith(test_file.lstrip(".")),
                is_project_dir=mocker.MagicMock(return_value=False),
            ),
        )

    mocker.patch("fwt.cli.FWTPath", side_effect=mock_fwt_path)
    with runner.isolated_filesystem():
        test_path = cli.Path(test_file).absolute()
        test_path.parent.mkdir(parents=True)
        test_path.touch()
        result = runner.invoke(cli.main, args=["rename", test_file, out_file])

    print(result.output)

    cast(Mock, cli.FWTPath).assert_any_call(str(test_path))
    cast(Mock, cli.FWTPath).assert_any_call(out_file, exists=False)
    cast(Mock, cli.FWTFileManager).assert_called_once_with(
        cli.FWTPath(test_file).to_fpd()
    )
    file_manager = cast(Mock, cli.FWTFileManager(cli.FWTPath(test_file).to_fpd()))

    file_manager.add_file.assert_called_once()

    file_manager.generate_rewrite_queue.assert_called_once_with()
    file_manager.process_file_queue.assert_called_once_with()
    file_manager.process_rewrite_queue.assert_called_once_with()

    assert result.exit_code == 0


def test_rename_target_is_project(runner: CliRunner, mocker: MockerFixture) -> None:
    world_path = "./foundrydata/test-world"
    test_file = f"{world_path}/test.png"
    out_file = f"{world_path}/test-rename.png"

    def mock_fwt_path(path: str, exists: bool = True) -> Mock:
        return cast(
            Mock,
            mocker.MagicMock(
                as_rpd=mocker.MagicMock(return_value=world_path),
                to_fpd=mocker.MagicMock(
                    return_value="/path/to/foundrydata" + world_path.lstrip(".")
                ),
                is_project=path.endswith(out_file.lstrip(".")),
                is_project_dir=mocker.MagicMock(return_value=False),
            ),
        )

    mocker.patch("fwt.cli.FWTPath", side_effect=mock_fwt_path)
    with runner.isolated_filesystem():
        test_path = cli.Path(test_file).absolute()
        test_path.parent.mkdir(parents=True)
        test_path.touch()
        result = runner.invoke(cli.main, args=["rename", test_file, out_file])

    print(result.output)

    cast(Mock, cli.FWTPath).assert_any_call(str(test_path))
    cast(Mock, cli.FWTPath).assert_any_call(out_file, exists=False)
    cast(Mock, cli.FWTFileManager).assert_called_once_with(
        cli.FWTPath(out_file).to_fpd()
    )
    file_manager = cast(Mock, cli.FWTFileManager(cli.FWTPath(test_file).to_fpd()))

    file_manager.add_file.assert_called_once()

    file_manager.generate_rewrite_queue.assert_called_once_with()
    file_manager.process_file_queue.assert_called_once_with()
    file_manager.process_rewrite_queue.assert_called_once_with()

    assert result.exit_code == 0


def test_rename_no_project(runner: CliRunner, mocker: MockerFixture) -> None:
    world_path = "./foundrydata/test-world"
    test_file = f"{world_path}/test.png"
    out_file = f"{world_path}/test-rename.png"

    def mock_fwt_path(path: str, exists: bool = True) -> Mock:
        return cast(
            Mock,
            mocker.MagicMock(
                as_rpd=mocker.MagicMock(return_value=world_path),
                to_fpd=mocker.MagicMock(
                    return_value="/path/to/foundrydata" + world_path.lstrip(".")
                ),
                is_project=False,
                is_project_dir=mocker.MagicMock(return_value=False),
            ),
        )

    mocker.patch("fwt.cli.FWTPath", side_effect=mock_fwt_path)
    with runner.isolated_filesystem():
        test_path = cli.Path(test_file).absolute()
        test_path.parent.mkdir(parents=True)
        test_path.touch()
        result = runner.invoke(cli.main, args=["rename", test_file, out_file])

    print(result.output)

    cast(Mock, cli.FWTPath).assert_any_call(str(test_path))
    cast(Mock, cli.FWTPath).assert_any_call(out_file, exists=False)

    cast(Mock, cli.FWTFileManager.add_file).assert_not_called()
    cast(Mock, cli.FWTFileManager.generate_rewrite_queue).assert_not_called()
    cast(Mock, cli.FWTFileManager.process_file_queue).assert_not_called()
    cast(Mock, cli.FWTFileManager.process_rewrite_queue).assert_not_called()

    assert result.exit_code == 2


def test_rename_different_projects(runner: CliRunner, mocker: MockerFixture) -> None:
    world_path = "./foundrydata/test-world"
    test_file = f"{world_path}/test.png"
    out_file = f"{world_path}-2/test-rename.png"

    def mock_fwt_path(path: str, exists: bool = True) -> Mock:
        return cast(
            Mock,
            mocker.MagicMock(
                as_rpd=mocker.MagicMock(return_value="/".join(path.split("/")[:-1])),
                to_fpd=mocker.MagicMock(
                    return_value="/path/to/foundrydata" + world_path.lstrip(".")
                ),
                is_project=True,
                is_project_dir=mocker.MagicMock(return_value=False),
            ),
        )

    mocker.patch("fwt.cli.FWTPath", side_effect=mock_fwt_path)
    with runner.isolated_filesystem():
        test_path = cli.Path(test_file).absolute()
        test_path.parent.mkdir(parents=True)
        test_path.touch()
        result = runner.invoke(cli.main, args=["rename", test_file, out_file])

    print(result.output)

    cast(Mock, cli.FWTPath).assert_any_call(str(test_path))
    cast(Mock, cli.FWTPath).assert_any_call(out_file, exists=False)

    cast(Mock, cli.FWTFileManager.add_file).assert_not_called()
    cast(Mock, cli.FWTFileManager.generate_rewrite_queue).assert_not_called()
    cast(Mock, cli.FWTFileManager.process_file_queue).assert_not_called()
    cast(Mock, cli.FWTFileManager.process_rewrite_queue).assert_not_called()

    assert result.exit_code == 2


def test_rename_src_is_project_dir(runner: CliRunner, mocker: MockerFixture) -> None:
    world_path = "./foundrydata/test-world"
    test_file = f"{world_path}/"
    out_file = f"{world_path}-2/"

    def mock_fwt_path(path: str, exists: bool = True) -> Mock:
        return cast(
            Mock,
            mocker.MagicMock(
                as_rpd=mocker.MagicMock(return_value=path),
                to_fpd=mocker.MagicMock(
                    return_value="/path/to/foundrydata" + world_path.lstrip(".")
                ),
                is_project=False,
                is_project_dir=mocker.MagicMock(return_value=True),
            ),
        )

    mocker.patch("fwt.cli.FWTPath", side_effect=mock_fwt_path)
    with runner.isolated_filesystem():
        test_path = cli.Path(test_file).absolute()
        test_path.parent.mkdir(parents=True)
        test_path.touch()
        result = runner.invoke(cli.main, args=["rename", test_file, out_file])

    print(result.output)

    cast(Mock, cli.FWTPath).assert_any_call(str(test_path))
    cast(Mock, cli.FWTPath).assert_any_call(out_file, exists=False)
    cast(Mock, cli.FWTFileManager).assert_called_once_with(
        cli.FWTPath(test_file).to_fpd()
    )
    file_manager = cast(Mock, cli.FWTFileManager(cli.FWTPath(test_file).to_fpd()))

    cast(Mock, file_manager.rename_world).assert_called_once()

    cast(Mock, file_manager.generate_rewrite_queue).assert_not_called()
    cast(Mock, file_manager.process_file_queue).assert_not_called()
    cast(Mock, file_manager.process_rewrite_queue).assert_not_called()

    assert result.exit_code == 0


def test_download_actors(runner: CliRunner, mocker: MockerFixture) -> None:
    mocker.patch(
        "fwt.cli.FWTProjectDb",
        return_value=mocker.MagicMock(
            data=mocker.MagicMock(
                actors=mocker.MagicMock(
                    __iter__=lambda self: iter([{"_id": 1}, {"_id": 2}, {"_id": 3}]),
                    save=mocker.MagicMock(),
                )
            )
        ),
    )
    with runner.isolated_filesystem():
        os.mkdir("test_dir")
        result = runner.invoke(
            cli.main,
            args=["download", "test_dir", "--type", "actors", "--asset-dir", "actors"],
        )

    print(result.output)

    cast(Mock, cli.FWTPath).assert_any_call("test_dir", require_project=True)
    cast(Mock, cli.FWTProjectDb).assert_called_once_with(
        cli.FWTPath("test_dir", require_project=True), driver=cli.FWTNeDB
    )
    cast(Mock, cli.FWTAssetDownloader).assert_called_once_with(
        cli.FWTPath("test_dir", require_project=True)
    )

    dbs = cli.FWTProjectDb(
        cli.FWTPath("test_dir", require_project=True), driver=cli.FWTNeDB
    )
    downloader = cli.FWTAssetDownloader(cli.FWTPath("test_dir", require_project=True))

    for actor in dbs.data.actors:
        cast(Mock, downloader.download_actor_images).assert_any_call(actor, "actors")

    assert result.exit_code == 0


def test_download_items(runner: CliRunner, mocker: MockerFixture) -> None:
    mocker.patch(
        "fwt.cli.FWTProjectDb",
        return_value=mocker.MagicMock(
            data=mocker.MagicMock(
                items=mocker.MagicMock(
                    __iter__=lambda self: iter([{"_id": 1}, {"_id": 2}, {"_id": 3}]),
                    save=mocker.MagicMock(),
                )
            )
        ),
    )
    with runner.isolated_filesystem():
        os.mkdir("test_dir")
        result = runner.invoke(
            cli.main,
            args=["download", "test_dir", "--type", "items", "--asset-dir", "items"],
        )

    print(result.output)

    cast(Mock, cli.FWTPath).assert_any_call("test_dir", require_project=True)
    cast(Mock, cli.FWTProjectDb).assert_called_once_with(
        cli.FWTPath("test_dir", require_project=True), driver=cli.FWTNeDB
    )
    cast(Mock, cli.FWTAssetDownloader).assert_called_once_with(
        cli.FWTPath("test_dir", require_project=True)
    )

    dbs = cli.FWTProjectDb(
        cli.FWTPath("test_dir", require_project=True), driver=cli.FWTNeDB
    )
    downloader = cli.FWTAssetDownloader(cli.FWTPath("test_dir", require_project=True))

    for item in dbs.data.items:
        cast(Mock, downloader.download_item_images).assert_any_call(item, "items")

    assert result.exit_code == 0


def test_pull(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        os.mkdir("test-world")
        os.mkdir("test-world-2")
        result = runner.invoke(
            cli.main, args=["pull", "--from", "test-world", "--to", "test-world-2"]
        )

    print(result.output)

    cast(Mock, cli.FWTFileManager).assert_called_once_with("test-world-2")
    file_manager = cli.FWTFileManager("test-world-2")

    cast(Mock, file_manager.find_remote_assets).assert_called_once_with("test-world")
    cast(Mock, file_manager.generate_rewrite_queue).assert_called_once_with()
    cast(Mock, file_manager.process_file_queue).assert_called_once_with()
    cast(Mock, file_manager.process_rewrite_queue).assert_called_once_with()

    assert result.exit_code == 0


@pytest.mark.parametrize("is_project", [True, False])
def test_info(runner: CliRunner, is_project: bool, mocker: MockerFixture) -> None:
    mocker.patch(
        "fwt.cli.FWTPath",
        return_value=mocker.MagicMock(
            is_project=is_project,
            project_name="test-world",
            project_type="world",
        ),
    )
    with runner.isolated_filesystem():
        os.mkdir("test-world")
        result = runner.invoke(cli.main, args=["info", "test-world"])

    print(result.output)

    cast(Mock, cli.FWTPath).assert_called_once_with("test-world")

    if is_project:
        cast(Mock, cli.click.echo).assert_called_once_with(
            "\n".join(
                [
                    "Project: yes",
                    "Project Name: test-world",
                    "Project Type: world",
                ]
            )
        )
    else:
        cast(Mock, cli.click.echo).assert_called_once_with("Project: no")

    assert result.exit_code == 0
