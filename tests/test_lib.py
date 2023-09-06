import os
import tempfile
from pathlib import Path, _posix_flavour, _windows_flavour

import pytest
from pytest_mock import MockerFixture

from fwt import lib


class MockPathBase(Path):
    _flavour = _windows_flavour if os.name == "nt" else _posix_flavour


@pytest.fixture(autouse=True)
def patch_imports(mocker: MockerFixture):
    mocker.patch("fwt.lib.os")
    mocker.patch("fwt.lib.Path", wraps=lib.Path)
    mocker.patch("fwt.lib.shutil")


@pytest.mark.parametrize("chown", [True, False])
def test_cp_src_perm(mocker: MockerFixture, chown: bool):
    mocker.patch("fwt.lib.dir", return_value=["chown"] if chown else [])
    src = "./path/to/src"
    target = "./path/to/target"
    lib.cp_src_perm(src, target)
    lib.os.stat.assert_called_once_with(src)
    stat = lib.os.stat(src)
    if chown:
        lib.os.chown.assert_called_once_with(target, stat.st_uid, stat.st_gid)
    lib.shutil.copymode.assert_called_once_with(src, target)


@pytest.mark.parametrize("n", [0, 3, 10])
def test_find_next_avaliable_path(n: int, mocker: MockerFixture):
    class MockPath(MockPathBase):
        def exists(self) -> bool:
            return int(self.suffix[1:]) < n

    mocker.patch("fwt.lib.Path", side_effect=MockPath)

    test_path = Path("./path/to/trash/session.0")
    result = lib.find_next_avaliable_path(test_path)

    assert result == Path(f"./path/to/trash/session.{n}")


def test_find_foundry_user_dir():
    with tempfile.TemporaryDirectory(dir=os.getenv("RUNNER_TEMP")) as tmp_dir:
        search_path = lib.Path(tmp_dir, "foundryuserdir/Data/worlds")
        search_path.mkdir(parents=True)
        config_path = lib.Path(tmp_dir, "foundryuserdir/Config/options.json")
        config_path.parent.mkdir(parents=True)
        config_path.touch()
        config_path.write_text(
            lib.json.dumps({"dataPath": str(lib.Path(tmp_dir, "foundryuserdir"))})
        )
        result = lib.find_foundry_user_dir(search_path)
        expected = lib.Path(tmp_dir, "./foundryuserdir/Data")

    assert result == expected


def test_find_foundry_user_dir_not_found():
    with pytest.raises(lib.FUDNotFoundError) as err:
        with tempfile.TemporaryDirectory(dir=os.getenv("RUNNER_TEMP")) as tmp_dir:
            search_path = lib.Path(tmp_dir, "other/path")
            search_path.mkdir(parents=True)
            config_path = lib.Path(tmp_dir, "foundryuserdir/Config/options.json")
            config_path.parent.mkdir(parents=True)
            config_path.touch()
            lib.find_foundry_user_dir(search_path)

    assert err.match(r"^.*: No Foundry user data directory found$")


@pytest.mark.parametrize(
    ("path_from", "path_to", "expected"),
    [
        [
            "/path/to/foundrydata/Data/worlds/test-world",
            "../test-world-2",
            "/path/to/foundrydata/Data/worlds/test-world-2",
        ],
        [
            "/path/to/foundrydata/Data/",
            "/path/to/foundrydata/Data/worlds/test-world",
            "/path/to/foundrydata/Data/worlds/test-world",
        ],
        [
            "/path/to/foundrydata/",
            "./Config/options.json",
            "/path/to/foundrydata/Config/options.json",
        ],
        ["/path/to/foundrydata/", "../../Config/../options.json", "/path/options.json"],
    ],
)
def test_get_relative_to(path_from: str, path_to: str, expected: str):
    path = lib.Path(path_from)
    rs = lib.Path(path_to)

    result = lib.get_relative_to(path, rs)

    assert result == lib.Path(expected)

    if rs.is_absolute():
        assert result == rs
    else:
        assert result == (path / rs).resolve()


@pytest.mark.parametrize("version", [9, 10, 11])
@pytest.mark.parametrize("asset", ["actor1.webp", "missing.png"])
def test_fwtpath(mocker: MockerFixture, version: int, asset: str):
    class MockPath(MockPathBase):
        def exists(self) -> bool:
            return not str(self).endswith("missing.png")

    mocker.patch("fwt.lib.Path", side_effect=MockPath)

    def mock_resolve_path(fwt_path: lib.FWTPath, path: str):
        fwt_path._fwt_fud = lib.Path("/path/to/foundrydata/Data")
        fwt_path._fwt_rtp = lib.Path(f"worlds/test-world/assets/{asset}")
        fwt_path._fwt_rpd = lib.Path("worlds/test-world")
        fwt_path.project_type = "test-world"
        fwt_path.project_name = "world"
        fwt_path.manafest = lib.Path(
            "/path/to/foundrydata/worlds/test-world/world.json"
        )

    mocker.patch("fwt.lib.resolve_fvtt_path", side_effect=mock_resolve_path)

    result = lib.FWTPath(f"./test-world/assets/{asset}", exists=False, version=version)

    lib.resolve_fvtt_path.assert_called_once_with(
        MockPath(f"test-world/assets/{asset}"), f"./test-world/assets/{asset}"
    )

    assert result._fwt_fud == lib.Path("/path/to/foundrydata/Data")
    assert result._fwt_rtp == lib.Path(f"worlds/test-world/assets/{asset}")
    assert result._fwt_rpd == lib.Path("worlds/test-world")
    assert result.project_type == "test-world"
    assert result.project_name == "world"
    assert result.manafest == lib.Path(
        "/path/to/foundrydata/worlds/test-world/world.json"
    )


@pytest.mark.parametrize("version", [9, 10, 11])
def test_fwtpath_exists(mocker: MockerFixture, version: int):
    class MockPath(MockPathBase):
        def exists(self) -> bool:
            return False

    mocker.patch("fwt.lib.Path", side_effect=MockPath)

    def mock_resolve_path(fwt_path: lib.FWTPath, path: str):
        fwt_path._fwt_fud = lib.Path("/path/to/foundrydata/Data")
        fwt_path._fwt_rtp = lib.Path("worlds/test-world/assets/missing.png")
        fwt_path._fwt_rpd = lib.Path("worlds/test-world")
        fwt_path.project_type = "test-world"
        fwt_path.project_name = "world"
        fwt_path.manafest = lib.Path(
            "/path/to/foundrydata/worlds/test-world/world.json"
        )

    mocker.patch("fwt.lib.resolve_fvtt_path", side_effect=mock_resolve_path)

    with pytest.raises(lib.FWTPathError):
        lib.FWTPath("./test-world/assets/missing.png", exists=True, version=version)

    lib.resolve_fvtt_path.assert_called_once_with(
        MockPath("test-world/assets/missing.png"), "./test-world/assets/missing.png"
    )
