import os
import shutil
import tempfile
from pathlib import Path
from typing import Iterator, Optional

import pytest
from pytest_mock import MockerFixture

from fwt import lib


@pytest.fixture(autouse=True)
def patch_imports(mocker: MockerFixture):
    mocker.patch("fwt.lib.shutil", wraps=shutil)


@pytest.fixture()
def temp_fs() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(dir=os.getenv("RUNNER_TEMP")) as tmp_dir:
        old_cwd = os.getcwd()
        os.chdir(tmp_dir)
        yield Path(tmp_dir)
        os.chdir(old_cwd)


@pytest.mark.parametrize("chown", [True, False])
def test_cp_src_perm(mocker: MockerFixture, temp_fs: Path, chown: bool):
    mocker.patch("fwt.lib.os")
    mocker.patch("fwt.lib.dir", return_value=["chown"] if chown else [])

    src = temp_fs / "path/to/src.txt"
    target = temp_fs / "path/to/target.txt"

    src.mkdir(parents=True)
    src.touch()
    target.touch()

    lib.cp_src_perm(src, target)
    lib.os.stat.assert_called_once_with(src)
    stat = lib.os.stat(src)
    if chown:
        lib.os.chown.assert_called_once_with(target, stat.st_uid, stat.st_gid)
    lib.shutil.copymode.assert_called_once_with(src, target)


@pytest.mark.parametrize("n", [0, 3, 10])
def test_find_next_avaliable_path(n: int, temp_fs: Path):
    (temp_fs / "trash").mkdir()
    for i in range(0, n):
        (temp_fs / f"trash/session.{i}").touch()

    test_path = Path("./trash/session.0")
    result = lib.find_next_avaliable_path(test_path)

    assert result == Path(f"./trash/session.{n}")


def test_find_foundry_user_dir(temp_fs: Path):
    search_path = temp_fs / "foundryuserdir/Data/worlds"
    search_path.mkdir(parents=True)
    config_path = temp_fs / "foundryuserdir/Config/options.json"
    config_path.parent.mkdir(parents=True)
    config_path.touch()
    config_path.write_text(
        lib.json.dumps({"dataPath": (temp_fs / "foundryuserdir").as_posix()}),
        encoding="utf-8",
    )
    result = lib.find_foundry_user_dir(search_path)
    expected = temp_fs / "foundryuserdir/Data"

    assert result == expected


def test_find_foundry_user_dir_not_found(temp_fs: Path):
    search_path = temp_fs / "other/path"
    search_path.mkdir(parents=True)
    config_path = temp_fs / "foundryuserdir/Config/options.json"
    config_path.parent.mkdir(parents=True)
    config_path.touch()

    with pytest.raises(lib.FUDNotFoundError) as err:
        lib.find_foundry_user_dir(search_path)

    assert err.match(r"^.*: No Foundry user data directory found$")


@pytest.mark.parametrize(
    ("path_from", "path_to", "expected"),
    [
        [
            "/home/foundry/foundrydata/Data/worlds/test-world",
            "../test-world-2",
            "/home/foundry/foundrydata/Data/worlds/test-world-2",
        ],
        [
            "/home/foundry/foundrydata/Data/",
            "/home/foundry/foundrydata/Data/worlds/test-world",
            "/home/foundry/foundrydata/Data/worlds/test-world",
        ],
        [
            "/home/foundry/foundrydata/",
            "./Config/options.json",
            "/home/foundry/foundrydata/Config/options.json",
        ],
        [
            "/home/foundry/foundrydata/",
            "../../Config/../options.json",
            "/home/options.json",
        ],
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


class TestFWTPath:
    @pytest.mark.parametrize("version", [9, 10, 11])
    @pytest.mark.parametrize("asset", ["actor1.webp", "missing.png"])
    def test_init(self, mocker: MockerFixture, temp_fs: Path, version: int, asset: str):
        (temp_fs / "foundrydata/worlds/test-world/assets").mkdir(parents=True)
        (temp_fs / "foundrydata/worlds/test-world/assets/actor1.webp").touch()

        def mock_resolve_path(fwt_path: lib.FWTPath, path: str):
            fwt_path._fwt_fud = temp_fs / "foundrydata/Data"
            fwt_path._fwt_rtp = Path(f"worlds/test-world/assets/{asset}")
            fwt_path._fwt_rpd = Path("worlds/test-world")
            fwt_path.project_type = "test-world"
            fwt_path.project_name = "world"
            fwt_path.manafest = Path(
                temp_fs / "foundrydata/worlds/test-world/world.json"
            )

        mocker.patch("fwt.lib.resolve_fvtt_path", side_effect=mock_resolve_path)

        result = lib.FWTPath(
            f"./test-world/assets/{asset}", exists=False, version=version
        )

        lib.resolve_fvtt_path.assert_called_once_with(
            Path(f"test-world/assets/{asset}"), f"./test-world/assets/{asset}"
        )

        assert result._fwt_fud == temp_fs / "foundrydata/Data"
        assert result._fwt_rtp == lib.Path(f"worlds/test-world/assets/{asset}")
        assert result._fwt_rpd == lib.Path("worlds/test-world")
        assert result.project_type == "test-world"
        assert result.project_name == "world"
        assert result.manafest == lib.Path(
            temp_fs / "foundrydata/worlds/test-world/world.json"
        )

    @pytest.mark.parametrize("version", [9, 10, 11])
    def test_exists(self, mocker: MockerFixture, temp_fs: Path, version: int):
        (temp_fs / "foundrydata/worlds/test-world/assets").mkdir(parents=True)

        def mock_resolve_path(fwt_path: lib.FWTPath, path: str):
            fwt_path._fwt_fud = temp_fs / "foundrydata/Data"
            fwt_path._fwt_rtp = Path("worlds/test-world/assets/missing.png")
            fwt_path._fwt_rpd = Path("worlds/test-world")
            fwt_path.project_type = "test-world"
            fwt_path.project_name = "world"
            fwt_path.manafest = temp_fs / "foundrydata/worlds/test-world/world.json"

        mocker.patch("fwt.lib.resolve_fvtt_path", side_effect=mock_resolve_path)

        with pytest.raises(lib.FWTPathError):
            lib.FWTPath("./test-world/assets/missing.png", exists=True, version=version)

        lib.resolve_fvtt_path.assert_called_once_with(
            Path("test-world/assets/missing.png"), "./test-world/assets/missing.png"
        )

    @pytest.mark.parametrize("manifest", [True, False])
    def test_is_project(self, mocker: MockerFixture, manifest: bool):
        def mock_resolve_path(fwt_path: lib.FWTPath, path: str):
            fwt_path._fwt_fud = lib.Path("/home/foundry/foundrydata/Data")
            fwt_path._fwt_rtp = lib.Path("worlds/test-world/assets/actor1.webp")
            fwt_path._fwt_rpd = lib.Path("worlds/test-world")
            fwt_path.project_type = "test-world"
            fwt_path.project_name = "world"
            fwt_path.manafest = (
                lib.Path("/home/foundry/foundrydata/worlds/test-world/world.json")
                if manifest
                else None
            )

        mocker.patch("fwt.lib.resolve_fvtt_path", side_effect=mock_resolve_path)

        result = lib.FWTPath("./test-world/assets/actor1.webp", exists=False)

        assert result.is_project is manifest

    @pytest.mark.parametrize("is_project", [True, False])
    @pytest.mark.parametrize("is_asset", [True, False])
    def test_is_project_dir(
        self, mocker: MockerFixture, is_project: bool, is_asset: bool
    ):
        mock_ftp = "/home/foundry/foundrydata/Data/worlds/test-world"
        if is_asset:
            mock_ftp += "/assets/actor1.webp"

        mocker.patch("fwt.lib.FWTPath.__init__", return_value=None)
        mocker.patch(
            "fwt.lib.FWTPath.is_project",
            new_callable=mocker.Mock(return_value=is_project),
        )
        mocker.patch(
            "fwt.lib.FWTPath.as_fpd",
            return_value="/home/foundry/foundrydata/Data/worlds/test-world",
        )
        mocker.patch("fwt.lib.FWTPath.as_ftp", return_value=mock_ftp)

        result = lib.FWTPath(
            "./test-world/assets/actor1.webp", exists=False
        ).is_project_dir()

        assert result is (is_project and not is_asset)

    def test_as_rpd(self, mocker: MockerFixture):
        def mock_resolve_path(fwt_path: lib.FWTPath, path: str):
            fwt_path._fwt_fud = lib.Path("/home/foundry/foundrydata/Data")
            fwt_path._fwt_rtp = lib.Path("worlds/test-world/assets/actor1.webp")
            fwt_path._fwt_rpd = lib.Path("worlds/test-world")
            fwt_path.project_type = "test-world"
            fwt_path.project_name = "world"
            fwt_path.manafest = lib.Path(
                "/home/foundry/foundrydata/worlds/test-world/world.json"
            )

        mocker.patch("fwt.lib.resolve_fvtt_path", side_effect=mock_resolve_path)

        result = lib.FWTPath("./test-world/assets/actor1.webp", exists=False).as_rpd()

        assert result == "worlds/test-world"

    def test_to_rpd(self, mocker: MockerFixture):
        def mock_resolve_path(fwt_path: lib.FWTPath, path: str):
            fwt_path._fwt_fud = lib.Path("/home/foundry/foundrydata/Data")
            fwt_path._fwt_rtp = lib.Path("worlds/test-world/assets/actor1.webp")
            fwt_path._fwt_rpd = lib.Path("worlds/test-world")
            fwt_path.project_type = "test-world"
            fwt_path.project_name = "world"
            fwt_path.manafest = lib.Path(
                "/home/foundry/foundrydata/worlds/test-world/world.json"
            )

        mocker.patch("fwt.lib.resolve_fvtt_path", side_effect=mock_resolve_path)

        result = lib.FWTPath("./test-world/assets/actor1.webp", exists=False).to_rpd()

        assert result == lib.Path("worlds/test-world")

    def test_as_rtp(self, mocker: MockerFixture):
        def mock_resolve_path(fwt_path: lib.FWTPath, path: str):
            fwt_path._fwt_fud = lib.Path("/home/foundry/foundrydata/Data")
            fwt_path._fwt_rtp = lib.Path("worlds/test-world/assets/actor1.webp")
            fwt_path._fwt_rpd = lib.Path("worlds/test-world")
            fwt_path.project_type = "test-world"
            fwt_path.project_name = "world"
            fwt_path.manafest = lib.Path(
                "/home/foundry/foundrydata/worlds/test-world/world.json"
            )

        mocker.patch("fwt.lib.resolve_fvtt_path", side_effect=mock_resolve_path)

        result = lib.FWTPath("./test-world/assets/actor1.webp", exists=False).as_rtp()

        assert result == "worlds/test-world/assets/actor1.webp"

    def test_to_rtp(self, mocker: MockerFixture):
        def mock_resolve_path(fwt_path: lib.FWTPath, path: str):
            fwt_path._fwt_fud = lib.Path("/home/foundry/foundrydata/Data")
            fwt_path._fwt_rtp = lib.Path("worlds/test-world/assets/actor1.webp")
            fwt_path._fwt_rpd = lib.Path("worlds/test-world")
            fwt_path.project_type = "test-world"
            fwt_path.project_name = "world"
            fwt_path.manafest = lib.Path(
                "/home/foundry/foundrydata/worlds/test-world/world.json"
            )

        mocker.patch("fwt.lib.resolve_fvtt_path", side_effect=mock_resolve_path)

        result = lib.FWTPath("./test-world/assets/actor1.webp", exists=False).to_rtp()

        assert result == lib.Path("worlds/test-world/assets/actor1.webp")

    def test_to_fpd(self, mocker: MockerFixture, temp_fs: Path):
        (temp_fs / "foundrydata/Data/worlds/test-world/assets").mkdir(parents=True)
        (temp_fs / "foundrydata/Data/worlds/test-world/assets/actor1.webp").touch()

        def mock_resolve_path(fwt_path: lib.FWTPath, path: str):
            fwt_path._fwt_fud = temp_fs / "foundrydata/Data"
            fwt_path._fwt_rtp = Path("worlds/test-world/assets/actor1.webp")
            fwt_path._fwt_rpd = Path("worlds/test-world")
            fwt_path.project_type = "test-world"
            fwt_path.project_name = "world"
            fwt_path.manafest = temp_fs / "foundrydata/worlds/test-world/world.json"

        mocker.patch("fwt.lib.resolve_fvtt_path", side_effect=mock_resolve_path)

        result = lib.FWTPath("./test-world/assets/actor1.webp", exists=False).to_fpd()

        assert result == temp_fs / "foundrydata/Data/worlds/test-world"

    def test_as_fpd(self, mocker: MockerFixture, temp_fs: Path):
        (temp_fs / "foundrydata/Data/worlds/test-world/assets").mkdir(parents=True)
        (temp_fs / "foundrydata/Data/worlds/test-world/assets/actor1.webp").touch()

        def mock_resolve_path(fwt_path: lib.FWTPath, path: str):
            fwt_path._fwt_fud = temp_fs / "foundrydata/Data"
            fwt_path._fwt_rtp = lib.Path("worlds/test-world/assets/actor1.webp")
            fwt_path._fwt_rpd = lib.Path("worlds/test-world")
            fwt_path.project_type = "test-world"
            fwt_path.project_name = "world"
            fwt_path.manafest = temp_fs / "foundrydata/worlds/test-world/world.json"

        mocker.patch("fwt.lib.resolve_fvtt_path", side_effect=mock_resolve_path)

        result = lib.FWTPath("./test-world/assets/actor1.webp", exists=False).as_fpd()

        assert result == (temp_fs / "foundrydata/Data/worlds/test-world").as_posix()

    def test_to_ftp(self, mocker: MockerFixture, temp_fs: Path):
        (temp_fs / "foundrydata/Data/worlds/test-world/assets").mkdir(parents=True)
        (temp_fs / "foundrydata/Data/worlds/test-world/assets/actor1.webp").touch()

        def mock_resolve_path(fwt_path: lib.FWTPath, path: str):
            fwt_path._fwt_fud = temp_fs / "foundrydata/Data"
            fwt_path._fwt_rtp = lib.Path("worlds/test-world/assets/actor1.webp")
            fwt_path._fwt_rpd = lib.Path("worlds/test-world")
            fwt_path.project_type = "test-world"
            fwt_path.project_name = "world"
            fwt_path.manafest = temp_fs / "foundrydata/worlds/test-world/world.json"

        mocker.patch("fwt.lib.resolve_fvtt_path", side_effect=mock_resolve_path)

        result = lib.FWTPath("./test-world/assets/actor1.webp", exists=False).to_ftp()

        assert (
            result == temp_fs / "foundrydata/Data/worlds/test-world/assets/actor1.webp"
        )

    def test_as_ftp(self, mocker: MockerFixture, temp_fs: Path):
        (temp_fs / "foundrydata/Data/worlds/test-world/assets").mkdir(parents=True)
        (temp_fs / "foundrydata/Data/worlds/test-world/assets/actor1.webp").touch()

        def mock_resolve_path(fwt_path: lib.FWTPath, path: str):
            fwt_path._fwt_fud = temp_fs / "foundrydata/Data"
            fwt_path._fwt_rtp = lib.Path("worlds/test-world/assets/actor1.webp")
            fwt_path._fwt_rpd = lib.Path("worlds/test-world")
            fwt_path.project_type = "test-world"
            fwt_path.project_name = "world"
            fwt_path.manafest = temp_fs / "foundrydata/worlds/test-world/world.json"

        mocker.patch("fwt.lib.resolve_fvtt_path", side_effect=mock_resolve_path)

        result = lib.FWTPath("./test-world/assets/actor1.webp", exists=False).as_ftp()

        assert (
            result
            == (
                temp_fs / "foundrydata/Data/worlds/test-world/assets/actor1.webp"
            ).as_posix()
        )

    def test_as_rpp(self, mocker: MockerFixture, temp_fs: Path):
        (temp_fs / "foundrydata/Data/worlds/test-world/assets").mkdir(parents=True)
        (temp_fs / "foundrydata/Data/worlds/test-world/assets/actor1.webp").touch()

        def mock_resolve_path(fwt_path: lib.FWTPath, path: str):
            fwt_path._fwt_fud = temp_fs / "foundrydata/Data"
            fwt_path._fwt_rtp = lib.Path("worlds/test-world/assets/actor1.webp")
            fwt_path._fwt_rpd = lib.Path("worlds/test-world")
            fwt_path.project_type = "test-world"
            fwt_path.project_name = "world"
            fwt_path.manafest = temp_fs / "foundrydata/worlds/test-world/world.json"

        mocker.patch("fwt.lib.resolve_fvtt_path", side_effect=mock_resolve_path)

        result = lib.FWTPath("./test-world/assets/actor1.webp", exists=False).as_rpp()

        assert result == "assets/actor1.webp"

    def test_iterdir(self, mocker: MockerFixture, temp_fs: Path):
        world_dir = "foundrydata/Data/worlds/test-world"
        (temp_fs / world_dir).mkdir(parents=True)
        for f in ["actor1.webp", "actor2.webp", "actor3.webp"]:
            (temp_fs / world_dir / f).touch()
        (temp_fs / world_dir / "npcs").mkdir(parents=True)
        (temp_fs / world_dir / "assets").mkdir(parents=True)

        def mock_resolve_path(fwt_path: lib.FWTPath, path: str):
            fwt_path._fwt_fud = temp_fs / "foundrydata/Data"
            fwt_path._fwt_rtp = lib.Path("worlds/test-world/assets/")
            fwt_path._fwt_rpd = lib.Path("worlds/test-world")
            fwt_path.project_type = "test-world"
            fwt_path.project_name = "world"
            fwt_path.manafest = temp_fs / world_dir / "world.json"

        mocker.patch("fwt.lib.resolve_fvtt_path", side_effect=mock_resolve_path)

        result = lib.FWTPath(temp_fs / world_dir, exists=False).iterdir()

        expected = ["actor1.webp", "actor2.webp", "actor3.webp", "npcs", "assets"]

        assert sorted(result) == sorted(
            lib.FWTPath(temp_fs / world_dir / f, exists=False) for f in expected
        )

    def test_to_abs(self, mocker: MockerFixture, temp_fs: Path):
        (temp_fs / "foundrydata/Data/worlds/test-world/assets").mkdir(parents=True)
        (temp_fs / "foundrydata/Data/worlds/test-world/assets/actor1.webp").touch()

        def mock_resolve_path(fwt_path: lib.FWTPath, path: str):
            fwt_path._fwt_fud = temp_fs / "foundrydata/Data"
            fwt_path._fwt_rtp = Path("worlds/test-world/assets/actor1.webp")
            fwt_path._fwt_rpd = Path("worlds/test-world")
            fwt_path.project_type = "test-world"
            fwt_path.project_name = "world"
            fwt_path.manafest = temp_fs / "foundrydata/worlds/test-world/world.json"

        mocker.patch("fwt.lib.resolve_fvtt_path", side_effect=mock_resolve_path)
        mocker.patch(
            "fwt.lib.FWTPath.absolute",
            return_value=temp_fs / "foundrydata/worlds/test-world/assets/actor1.webp",
        )

        result = lib.FWTPath("./test-world/assets/actor1.webp", exists=False).to_abs()

        assert result == lib.FWTPath(
            temp_fs / "foundrydata/worlds/test-world/assets/actor1.webp", exists=False
        )


def test_reinit_fwtpath(mocker: MockerFixture):
    mock_fwtpath = mocker.MagicMock()
    other_path = lib.Path("/home/foundry/foundrydata/worlds")
    lib.reinit_fwtpath(mock_fwtpath, other_path)
    assert mock_fwtpath._drv == other_path._drv  # type: ignore
    assert mock_fwtpath._root == other_path._root  # type: ignore
    assert mock_fwtpath._parts == other_path._parts  # type: ignore
    assert mock_fwtpath._str == str(other_path)


class TestResolveFVTTPath:
    @pytest.mark.parametrize("symlink", [True, False])
    @pytest.mark.parametrize("version", [9, 10, 11])
    @pytest.mark.parametrize("is_absolute", [True, False])
    @pytest.mark.parametrize(
        ("foundry_user_dir", "pass_user_dir"),
        [
            [False, False],
            [True, False],
            [True, True],
        ],
    )
    def test_resolves(
        self,
        mocker: MockerFixture,
        temp_fs: Path,
        symlink: bool,
        version: int,
        is_absolute: bool,
        foundry_user_dir: bool,
        pass_user_dir: bool,
    ):
        (temp_fs / "foundrydata/Data/worlds/").mkdir(parents=True)
        if symlink:
            (temp_fs / "external-worlds/test-world/assets").mkdir(parents=True)
            (temp_fs / "foundrydata/Data/worlds/test-world/").symlink_to(
                temp_fs / "external-worlds/test-world/", target_is_directory=True
            )
            os.chdir(temp_fs / "external-worlds/test-world")
        else:
            (temp_fs / "foundrydata/Data/worlds/test-world/assets").mkdir(parents=True)
            os.chdir(temp_fs / "foundrydata/Data/worlds/test-world")
        Path("assets/actor1.webp").touch()
        if version == 9:
            Path("world.json").write_text('{"name": "test-world"}', encoding="utf-8")
        else:
            Path("world.json").write_text('{"id": "test-world"}', encoding="utf-8")

        def mock_reinit_fwtpath(fwtpath, newpath):
            fwtpath._drv = newpath._drv  # type: ignore
            fwtpath._root = newpath._root  # type: ignore
            fwtpath._parts = newpath._parts  # type: ignore
            fwtpath._str = str(newpath)  # type: ignore

        mocker.patch("fwt.lib.os.environ", new={})
        if symlink:
            mocker.patch(
                "fwt.lib.get_relative_to",
                return_value=temp_fs / "external-worlds/test-world/assets/actor1.webp",
            )
        else:
            mocker.patch(
                "fwt.lib.get_relative_to",
                return_value=temp_fs
                / "foundrydata/Data/worlds/test-world/assets/actor1.webp",
            )
        mocker.patch("fwt.lib.reinit_fwtpath", side_effect=mock_reinit_fwtpath)
        mocker.patch(
            "fwt.lib.find_foundry_user_dir", return_value=temp_fs / "foundrydata/Data"
        )

        mocker.patch("fwt.lib.FWTPath.__init__", return_value=None)

        if is_absolute and symlink:
            orig_path = (
                temp_fs / "external-worlds/test-world/assets/actor1.webp"
            ).as_posix()
        elif is_absolute:
            orig_path = (
                temp_fs / "foundrydata/Data/worlds/test-world/assets/actor1.webp"
            ).as_posix()
        else:
            orig_path = "./actor1.webp"

        fwtpath = lib.FWTPath(orig_path, exists=False)

        fwtpath.orig_path = orig_path
        fwtpath._fwt_fud = Path()
        fwtpath._fwt_rpd = Path()
        fwtpath._fwt_rtp = Path()
        fwtpath.manafest = None
        fwtpath.project_name = ""
        fwtpath.project_type = ""
        fwtpath.version = version

        user_dir = None
        if pass_user_dir:
            user_dir = temp_fs / "foundrydata/Data"

        if foundry_user_dir:
            fwtpath.foundry_user_dir = temp_fs / "foundrydata/Data"

        lib.resolve_fvtt_path(
            fwtpath,
            orig_path,
            foundry_user_dir=user_dir,
            version=version,
        )

        lib.reinit_fwtpath.assert_any_call(
            fwtpath, temp_fs / "foundrydata/Data/worlds/test-world/assets/actor1.webp"
        )
        assert lib.reinit_fwtpath.call_count == 2 - is_absolute

        if not (foundry_user_dir or pass_user_dir):
            if symlink:
                lib.find_foundry_user_dir.assert_called_once_with(
                    (
                        temp_fs / "external-worlds/test-world/assets/actor1.webp"
                    ).as_posix()
                )
            else:
                lib.find_foundry_user_dir.assert_called_once_with(
                    (
                        temp_fs
                        / "foundrydata/Data/worlds/test-world/assets/actor1.webp"
                    ).as_posix()
                )
        else:
            lib.find_foundry_user_dir.assert_not_called()

        assert fwtpath._fwt_fud == temp_fs / "foundrydata/Data"
        assert fwtpath._fwt_rpd == Path("worlds/test-world")
        assert fwtpath._fwt_rtp == Path("worlds/test-world/assets/actor1.webp")
        assert (
            fwtpath.manafest
            == temp_fs / "foundrydata/Data/worlds/test-world/world.json"
        )
        assert fwtpath.project_name == "test-world"
        assert fwtpath.project_type == "world"

    def test_wrong_id(
        self,
        mocker: MockerFixture,
        temp_fs: Path,
    ):
        (temp_fs / "foundrydata/Data/worlds/test-world/assets").mkdir(parents=True)
        os.chdir(temp_fs / "foundrydata/Data/worlds/test-world")
        Path("assets/actor1.webp").touch()
        Path("world.json").write_text('{"id": "test-world-2"}', encoding="utf-8")

        def mock_reinit_fwtpath(fwtpath, newpath):
            fwtpath._drv = newpath._drv  # type: ignore
            fwtpath._root = newpath._root  # type: ignore
            fwtpath._parts = newpath._parts  # type: ignore
            fwtpath._str = str(newpath)  # type: ignore

        mocker.patch("fwt.lib.os.environ", new={})
        mocker.patch(
            "fwt.lib.get_relative_to",
            return_value=temp_fs
            / "foundrydata/Data/worlds/test-world/assets/actor1.webp",
        )
        mocker.patch("fwt.lib.reinit_fwtpath", side_effect=mock_reinit_fwtpath)
        mocker.patch(
            "fwt.lib.find_foundry_user_dir", return_value=temp_fs / "foundrydata/Data"
        )

        mocker.patch("fwt.lib.FWTPath.__init__", return_value=None)

        orig_path = (
            temp_fs / "foundrydata/Data/worlds/test-world/assets/actor1.webp"
        ).as_posix()

        fwtpath = lib.FWTPath(orig_path, exists=False)

        fwtpath.orig_path = orig_path
        fwtpath._fwt_fud = Path()
        fwtpath._fwt_rpd = Path()
        fwtpath._fwt_rtp = Path()
        fwtpath.manafest = None
        fwtpath.project_name = ""
        fwtpath.project_type = ""
        fwtpath.version = 11

        user_dir = temp_fs / "foundrydata/Data"

        lib.resolve_fvtt_path(
            fwtpath,
            orig_path,
            foundry_user_dir=user_dir,
            version=11,
        )

        lib.reinit_fwtpath.assert_called_once_with(
            fwtpath, temp_fs / "foundrydata/Data/worlds/test-world/assets/actor1.webp"
        )
        lib.find_foundry_user_dir.assert_not_called()

        assert fwtpath._fwt_fud == temp_fs / "foundrydata/Data"
        assert fwtpath._fwt_rpd == Path("worlds/test-world")
        assert fwtpath._fwt_rtp == Path("worlds/test-world/assets/actor1.webp")
        assert (
            fwtpath.manafest
            == temp_fs / "foundrydata/Data/worlds/test-world/world.json"
        )
        assert fwtpath.project_name == "test-world-2"
        assert fwtpath.project_type == "world"

    def test_data_dir_does_not_exist(
        self,
        mocker: MockerFixture,
        temp_fs: Path,
    ):
        mocker.patch("fwt.lib.os.environ", new={})
        mocker.patch(
            "fwt.lib.get_relative_to",
            return_value=temp_fs
            / "foundrydata/Data/worlds/test-world/assets/actor1.webp",
        )
        mocker.patch("fwt.lib.reinit_fwtpath")
        mocker.patch(
            "fwt.lib.find_foundry_user_dir", return_value=temp_fs / "foundrydata/Data"
        )

        mocker.patch("fwt.lib.FWTPath.__init__", return_value=None)

        orig_path = (
            temp_fs / "foundrydata/Data/worlds/test-world/assets/actor1.webp"
        ).as_posix()

        fwtpath = lib.FWTPath(orig_path, exists=False)

        fwtpath.orig_path = orig_path
        fwtpath._fwt_fud = Path()
        fwtpath._fwt_rpd = Path()
        fwtpath._fwt_rtp = Path()
        fwtpath.manafest = None
        fwtpath.project_name = ""
        fwtpath.project_type = ""
        fwtpath.version = 11

        user_dir = temp_fs / "foundrydata/Data"

        with pytest.raises(lib.FUDNotFoundError):
            lib.resolve_fvtt_path(
                fwtpath,
                orig_path,
                foundry_user_dir=user_dir,
                version=11,
            )

        lib.reinit_fwtpath.assert_not_called()
        lib.find_foundry_user_dir.assert_not_called()

        assert fwtpath._fwt_fud == temp_fs / "foundrydata/Data"
        assert fwtpath._fwt_rpd == Path()
        assert fwtpath._fwt_rtp == Path()
        assert fwtpath.manafest is None
        assert fwtpath.project_name == ""
        assert fwtpath.project_type == ""

    def test_no_manifest(
        self,
        mocker: MockerFixture,
        temp_fs: Path,
    ):
        (temp_fs / "foundrydata/Data/worlds/test-world/assets").mkdir(parents=True)
        os.chdir(temp_fs / "foundrydata/Data/worlds/test-world")
        Path("assets/actor1.webp").touch()

        def mock_reinit_fwtpath(fwtpath, newpath):
            fwtpath._drv = newpath._drv  # type: ignore
            fwtpath._root = newpath._root  # type: ignore
            fwtpath._parts = newpath._parts  # type: ignore
            fwtpath._str = str(newpath)  # type: ignore

        mocker.patch("fwt.lib.os.environ", new={})
        mocker.patch(
            "fwt.lib.get_relative_to",
            return_value=temp_fs
            / "foundrydata/Data/worlds/test-world/assets/actor1.webp",
        )
        mocker.patch("fwt.lib.reinit_fwtpath", side_effect=mock_reinit_fwtpath)
        mocker.patch(
            "fwt.lib.find_foundry_user_dir", return_value=temp_fs / "foundrydata/Data"
        )

        mocker.patch("fwt.lib.FWTPath.__init__", return_value=None)

        orig_path = (
            temp_fs / "foundrydata/Data/worlds/test-world/assets/actor1.webp"
        ).as_posix()

        fwtpath = lib.FWTPath(orig_path, exists=False)

        fwtpath.orig_path = orig_path
        fwtpath._fwt_fud = Path()
        fwtpath._fwt_rpd = Path()
        fwtpath._fwt_rtp = Path()
        fwtpath.manafest = None
        fwtpath.project_name = ""
        fwtpath.project_type = ""
        fwtpath.version = 11

        user_dir = temp_fs / "foundrydata/Data"

        lib.resolve_fvtt_path(
            fwtpath,
            orig_path,
            foundry_user_dir=user_dir,
            version=11,
        )

        lib.reinit_fwtpath.assert_called_once_with(
            fwtpath, temp_fs / "foundrydata/Data/worlds/test-world/assets/actor1.webp"
        )
        lib.find_foundry_user_dir.assert_not_called()

        assert fwtpath._fwt_fud == temp_fs / "foundrydata/Data"
        assert fwtpath._fwt_rpd == Path("worlds/test-world")
        assert fwtpath._fwt_rtp == Path("worlds/test-world/assets/actor1.webp")
        assert fwtpath.manafest is None
        assert fwtpath.project_name == ""
        assert fwtpath.project_type == ""

    def test_no_manifest_short_parents(
        self,
        mocker: MockerFixture,
        temp_fs: Path,
    ):
        (temp_fs / "foundrydata/Data/worlds/test-world/assets").mkdir(parents=True)
        os.chdir(temp_fs / "foundrydata/Data/worlds/test-world")
        Path("assets/actor1.webp").touch()

        def mock_reinit_fwtpath(fwtpath, newpath):
            fwtpath._drv = newpath._drv  # type: ignore
            fwtpath._root = newpath._root  # type: ignore
            fwtpath._parts = newpath._parts  # type: ignore
            fwtpath._str = str(newpath)  # type: ignore

        mocker.patch("fwt.lib.os.environ", new={})
        mocker.patch(
            "fwt.lib.get_relative_to",
            return_value=temp_fs / "foundrydata/Data/worlds/test-world",
        )
        mocker.patch("fwt.lib.reinit_fwtpath", side_effect=mock_reinit_fwtpath)
        mocker.patch(
            "fwt.lib.find_foundry_user_dir", return_value=temp_fs / "foundrydata/Data"
        )

        mocker.patch("fwt.lib.FWTPath.__init__", return_value=None)

        orig_path = (temp_fs / "foundrydata/Data/worlds/test-world").as_posix()

        fwtpath = lib.FWTPath(orig_path, exists=False)

        fwtpath.orig_path = orig_path
        fwtpath._fwt_fud = Path()
        fwtpath._fwt_rpd = Path()
        fwtpath._fwt_rtp = Path()
        fwtpath.manafest = None
        fwtpath.project_name = ""
        fwtpath.project_type = ""
        fwtpath.version = 11

        user_dir = temp_fs / "foundrydata/Data"

        lib.resolve_fvtt_path(
            fwtpath,
            orig_path,
            foundry_user_dir=user_dir,
            version=11,
        )

        lib.reinit_fwtpath.assert_called_once_with(
            fwtpath, temp_fs / "foundrydata/Data/worlds/test-world"
        )
        lib.find_foundry_user_dir.assert_not_called()

        assert fwtpath._fwt_fud == temp_fs / "foundrydata/Data"
        assert fwtpath._fwt_rpd == Path("worlds/test-world")
        assert fwtpath._fwt_rtp == Path("worlds/test-world")
        assert fwtpath.manafest is None
        assert fwtpath.project_name == ""
        assert fwtpath.project_type == ""

    def test_no_manifest_require_project(
        self,
        mocker: MockerFixture,
        temp_fs: Path,
    ):
        (temp_fs / "foundrydata/Data/worlds/test-world/assets").mkdir(parents=True)
        os.chdir(temp_fs / "foundrydata/Data/worlds/test-world")
        Path("assets/actor1.webp").touch()

        mocker.patch("fwt.lib.os.environ", new={})
        mocker.patch(
            "fwt.lib.get_relative_to",
            return_value=temp_fs
            / "foundrydata/Data/worlds/test-world/assets/actor1.webp",
        )
        mocker.patch("fwt.lib.reinit_fwtpath")
        mocker.patch(
            "fwt.lib.find_foundry_user_dir", return_value=temp_fs / "foundrydata/Data"
        )

        mocker.patch("fwt.lib.FWTPath.__init__", return_value=None)

        orig_path = (
            temp_fs / "foundrydata/Data/worlds/test-world/assets/actor1.webp"
        ).as_posix()

        fwtpath = lib.FWTPath(orig_path, exists=False)

        fwtpath.orig_path = orig_path
        fwtpath._fwt_fud = Path()
        fwtpath._fwt_rpd = Path()
        fwtpath._fwt_rtp = Path()
        fwtpath.manafest = None
        fwtpath.project_name = ""
        fwtpath.project_type = ""
        fwtpath.version = 11

        user_dir = temp_fs / "foundrydata/Data"

        with pytest.raises(lib.FWTPathError):
            lib.resolve_fvtt_path(
                fwtpath,
                orig_path,
                foundry_user_dir=user_dir,
                version=11,
                require_project=True,
            )

        lib.reinit_fwtpath.assert_not_called()
        lib.find_foundry_user_dir.assert_not_called()

        assert fwtpath._fwt_fud == temp_fs / "foundrydata/Data"
        assert fwtpath._fwt_rpd == Path()
        assert fwtpath._fwt_rtp == Path("worlds/test-world/assets/actor1.webp")
        assert fwtpath.manafest is None
        assert fwtpath.project_name == ""
        assert fwtpath.project_type == ""

    def test_no_check(
        self,
        mocker: MockerFixture,
        temp_fs: Path,
    ):
        (temp_fs / "foundrydata/Data/worlds/test-world/assets").mkdir(parents=True)
        os.chdir(temp_fs / "foundrydata/Data/worlds/test-world")
        Path("assets/actor1.webp").touch()
        Path("world.json").write_text('{"id": "test-world"}', encoding="utf-8")

        def mock_reinit_fwtpath(fwtpath, newpath):
            fwtpath._drv = newpath._drv  # type: ignore
            fwtpath._root = newpath._root  # type: ignore
            fwtpath._parts = newpath._parts  # type: ignore
            fwtpath._str = str(newpath)  # type: ignore

        mocker.patch("fwt.lib.os.environ", new={})
        mocker.patch(
            "fwt.lib.get_relative_to",
            return_value=temp_fs
            / "foundrydata/Data/worlds/test-world/assets/actor1.webp",
        )
        mocker.patch("fwt.lib.reinit_fwtpath", side_effect=mock_reinit_fwtpath)
        mocker.patch(
            "fwt.lib.find_foundry_user_dir", return_value=temp_fs / "foundrydata/Data"
        )

        mocker.patch("fwt.lib.FWTPath.__init__", return_value=None)

        orig_path = (
            temp_fs / "foundrydata/Data/worlds/test-world/assets/actor1.webp"
        ).as_posix()

        fwtpath = lib.FWTPath(orig_path, exists=False)

        fwtpath.orig_path = orig_path
        fwtpath._fwt_fud = Path()
        fwtpath._fwt_rpd = Path()
        fwtpath._fwt_rtp = Path()
        fwtpath.manafest = None
        fwtpath.project_name = ""
        fwtpath.project_type = ""
        fwtpath.version = 11

        user_dir = temp_fs / "foundrydata/Data"

        lib.resolve_fvtt_path(
            fwtpath,
            orig_path,
            foundry_user_dir=user_dir,
            version=11,
            check_for_project=False,
        )

        lib.reinit_fwtpath.assert_called_once_with(
            fwtpath, temp_fs / "foundrydata/Data/worlds/test-world/assets/actor1.webp"
        )
        lib.find_foundry_user_dir.assert_not_called()

        assert fwtpath._fwt_fud == temp_fs / "foundrydata/Data"
        assert fwtpath._fwt_rpd == Path()
        assert fwtpath._fwt_rtp == Path("worlds/test-world/assets/actor1.webp")
        assert fwtpath.manafest is None
        assert fwtpath.project_name == ""
        assert fwtpath.project_type == ""

    def test_manifest_parent(
        self,
        mocker: MockerFixture,
        temp_fs: Path,
    ):
        (temp_fs / "foundrydata/Data/worlds/").mkdir(parents=True)
        (temp_fs / "external-worlds/test-world/assets").mkdir(parents=True)
        (temp_fs / "foundrydata/Data/worlds/test-world/").symlink_to(
            temp_fs / "external-worlds/test-world/", target_is_directory=True
        )
        os.chdir(temp_fs / "external-worlds/test-world")
        Path("assets/actor1.webp").touch()
        Path("world.json").write_text('{"id": "test-world"}', encoding="utf-8")

        def mock_reinit_fwtpath(fwtpath, newpath):
            fwtpath._drv = newpath._drv  # type: ignore
            fwtpath._root = newpath._root  # type: ignore
            fwtpath._parts = newpath._parts  # type: ignore
            fwtpath._str = str(newpath)  # type: ignore

        mocker.patch("fwt.lib.os.environ", new={})
        mocker.patch(
            "fwt.lib.get_relative_to",
            return_value=temp_fs / "external-worlds/test-world/assets/actor1.webp",
        )
        mocker.patch("fwt.lib.reinit_fwtpath", side_effect=mock_reinit_fwtpath)
        mocker.patch(
            "fwt.lib.find_foundry_user_dir", return_value=temp_fs / "foundrydata/Data"
        )

        mocker.patch("fwt.lib.FWTPath.__init__", return_value=None)

        orig_path = (temp_fs / "external-worlds/test-world").as_posix()

        fwtpath = lib.FWTPath(orig_path, exists=False)

        fwtpath.orig_path = orig_path
        fwtpath._fwt_fud = Path()
        fwtpath._fwt_rpd = Path()
        fwtpath._fwt_rtp = Path()
        fwtpath.manafest = None
        fwtpath.project_name = ""
        fwtpath.project_type = ""
        fwtpath.version = 11

        user_dir = temp_fs / "foundrydata/Data"

        lib.resolve_fvtt_path(
            fwtpath,
            orig_path,
            foundry_user_dir=user_dir,
        )

        lib.reinit_fwtpath.assert_called_once_with(
            fwtpath, temp_fs / "foundrydata/Data/worlds/test-world"
        )
        lib.find_foundry_user_dir.assert_not_called()

        assert fwtpath._fwt_fud == temp_fs / "foundrydata/Data"
        assert fwtpath._fwt_rpd == Path("worlds/test-world")
        assert fwtpath._fwt_rtp == Path("worlds/test-world")
        assert (
            fwtpath.manafest
            == temp_fs / "foundrydata/Data/worlds/test-world/world.json"
        )
        assert fwtpath.project_name == "test-world"
        assert fwtpath.project_type == "world"


class TestFWTConfig:
    @pytest.mark.parametrize("data_dir", [None, "foundrydata/Data"])
    def test_init(
        self, mocker: MockerFixture, temp_fs: Path, data_dir: Optional[str]
    ) -> None:
        mocker.patch("fwt.lib.FWTConfig.load")
        mocker.patch("fwt.lib.FWTConfig.create_config")
        mocker.patch("fwt.lib.FWTConfig.setup")

        file_path = temp_fs / "config.json"
        file_path.write_text(f'{{"dataDir": "{temp_fs / "foundrydata/Data"}"}}')

        result = lib.FWTConfig(file_path, mkconfig=True, dataDir=data_dir)

        if data_dir:
            assert result["dataDir"] == data_dir
        else:
            assert result["dataDir"] is None
        assert result.config_file == file_path

        result.load.assert_called_once()
        result.create_config.assert_not_called()
        result.setup.assert_called_once()

    def test_init_home_path(self, mocker: MockerFixture, temp_fs: Path) -> None:
        mocker.patch("fwt.lib.FWTConfig.load")
        mocker.patch("fwt.lib.FWTConfig.create_config")
        mocker.patch("fwt.lib.FWTConfig.setup")

        file_path = Path("~/config.json")

        result = lib.FWTConfig(file_path, mkconfig=True)

        assert result.config_file == Path().home() / "config.json"

    def test_init_empty_file(self, mocker: MockerFixture, temp_fs: Path) -> None:
        mocker.patch("fwt.lib.FWTConfig.load")
        mocker.patch("fwt.lib.FWTConfig.create_config")
        mocker.patch("fwt.lib.FWTConfig.setup")

        file_path = temp_fs / "config.json"
        file_path.touch()

        result = lib.FWTConfig(file_path, mkconfig=False)

        assert result["dataDir"] is None
        assert result.config_file == file_path

        result.load.assert_not_called()
        result.create_config.assert_called_once()
        result.setup.assert_called_once()

    def test_init_file_does_not_exist(
        self, mocker: MockerFixture, temp_fs: Path
    ) -> None:
        mocker.patch("fwt.lib.FWTConfig.load")
        mocker.patch("fwt.lib.FWTConfig.create_config")
        mocker.patch("fwt.lib.FWTConfig.setup")

        file_path = temp_fs / "config.json"

        with pytest.raises(lib.FWTFileError) as err:
            lib.FWTConfig(file_path, mkconfig=False)

        lib.FWTConfig.load.assert_not_called()
        lib.FWTConfig.create_config.assert_not_called()
        lib.FWTConfig.setup.assert_not_called()

        assert err.value.args[0] == "Config file does not exist"

    def test_init_mkconfig(self, mocker: MockerFixture, temp_fs: Path) -> None:
        mocker.patch("fwt.lib.FWTConfig.load")
        mocker.patch("fwt.lib.FWTConfig.create_config")
        mocker.patch("fwt.lib.FWTConfig.setup")

        file_path = temp_fs / "config.json"

        result = lib.FWTConfig(file_path, mkconfig=True)

        result.load.assert_not_called()
        result.create_config.assert_called_once()
        result.setup.assert_called_once()

    def test_setup(self, mocker: MockerFixture, temp_fs: Path) -> None:
        mocker.patch("fwt.lib.FWTPath")
        mocker.patch("fwt.lib.find_foundry_user_dir")
        mocker.patch("fwt.lib.FWTConfig.__init__", return_value=None)

        config = lib.FWTConfig(temp_fs / "config.json")
        config.data = {"dataDir": (temp_fs / "foundrydata/Data").as_posix()}

        config.setup()

        lib.find_foundry_user_dir.assert_not_called()
        assert lib.FWTPath.foundry_user_dir == (temp_fs / "foundrydata/Data").as_posix()

    def test_setup_data_dir_none(self, mocker: MockerFixture, temp_fs: Path) -> None:
        mocker.patch("fwt.lib.os.environ.get", return_value=temp_fs.as_posix())
        mocker.patch("fwt.lib.FWTPath")
        mocker.patch(
            "fwt.lib.find_foundry_user_dir",
            return_value=(temp_fs / "foundrydata/Data").as_posix(),
        )
        mocker.patch("fwt.lib.FWTConfig.__init__", return_value=None)

        config = lib.FWTConfig(temp_fs / "config.json")
        config.data = {}

        config.setup()

        lib.find_foundry_user_dir.assert_called_once_with(temp_fs)
        assert lib.FWTPath.foundry_user_dir == (temp_fs / "foundrydata/Data").as_posix()

    def test_setup_raises(self, mocker: MockerFixture, temp_fs: Path) -> None:
        mocker.patch("fwt.lib.os.environ.get", return_value=temp_fs.as_posix())
        mocker.patch("fwt.lib.FWTPath")
        mocker.patch("fwt.lib.find_foundry_user_dir", return_value=None)
        mocker.patch("fwt.lib.FWTConfig.__init__", return_value=None)

        config = lib.FWTConfig(temp_fs / "config.json")
        config.data = {}

        with pytest.raises(lib.FWTConfigNoDataDirError) as err:
            config.setup()

        lib.find_foundry_user_dir.assert_called_once_with(temp_fs)
        assert err.value.args[0] == "unable to determine fvtt_data_dir"

    def test_load_valid_config(self, mocker: MockerFixture, temp_fs: Path):
        mocker.patch("fwt.lib.FWTConfig.__init__", return_value=None)

        config_path = temp_fs / "config.json"
        config_path.write_text('{"key": "value"}', encoding="utf-8")

        config = lib.FWTConfig(config_path)
        config.config_file = config_path
        config.data = {}

        config.load()

        assert config.data == {"key": "value"}

    def test_load_valid_config_with_existing_data(
        self, mocker: MockerFixture, temp_fs: Path
    ):
        mocker.patch("fwt.lib.FWTConfig.__init__", return_value=None)

        config_path = temp_fs / "config.json"
        config_path.write_text('{"new_key": "new_value"}', encoding="utf-8")

        config = lib.FWTConfig(config_path)
        config.config_file = config_path
        config.data = {"existing_key": "existing_value"}
        config.load()

        assert config.data == {"existing_key": "existing_value", "new_key": "new_value"}

    def test_load_invalid_config(self, mocker: MockerFixture, temp_fs: Path):
        mocker.patch("fwt.lib.FWTConfig.__init__", return_value=None)

        config_path = temp_fs / "config.json"
        config_path.write_text("invalid_json", encoding="utf-8")

        config = lib.FWTConfig(config_path)
        config.config_file = config_path
        config.data = {}

        config.load()

        assert config.data == {"error": "Expecting value: line 1 column 1 (char 0)"}

    def test_save(self, mocker: MockerFixture, temp_fs: Path):
        mocker.patch("fwt.lib.FWTConfig.__init__", return_value=None)
        mocker.patch("fwt.lib.FWTFileWriter")

        config_path = temp_fs / "config.json"
        config_path.write_text('{"new_key": "new_value"}', encoding="utf-8")

        config = lib.FWTConfig(config_path)
        config.config_file = config_path
        config.data = {"key": "value"}

        config.save()

        lib.FWTFileWriter.assert_called_once_with(config_path)
        lib.FWTFileWriter(
            config_path
        ).__enter__().write_fd.write.assert_called_once_with('{\n    "key": "value"\n}')

    def test_create_config(self, mocker: MockerFixture, temp_fs: Path):
        resource_path = temp_fs / "fwt"
        mocker.patch("fwt.lib.FWTConfig.__init__", return_value=None)
        mocker.patch("fwt.lib.resource_files", return_value=resource_path)

        resource_path.mkdir(parents=True)
        (resource_path / "presets.json").write_text(
            '{"preset": "value"}', encoding="utf-8"
        )

        config_path = temp_fs / "config.json"
        config_path.write_text('{"new_key": "new_value"}', encoding="utf-8")

        config = lib.FWTConfig(config_path)
        config.config_file = config_path
        config.data = {"key": "value"}

        config.create_config()

        lib.resource_files.assert_called_once_with("fwt")

        assert config.data == {"key": "value", "preset": "value"}

        assert config.config_file.parent.exists()
        assert config.config_file.exists()

    def test_create_config_parent_doesnt_exist(
        self, mocker: MockerFixture, temp_fs: Path
    ):
        resource_path = temp_fs / "fwt"
        mocker.patch("fwt.lib.FWTConfig.__init__", return_value=None)
        mocker.patch("fwt.lib.resource_files", return_value=resource_path)

        resource_path.mkdir(parents=True)
        (resource_path / "presets.json").write_text(
            '{"preset": "value"}', encoding="utf-8"
        )

        config_path = temp_fs / "config" / "config.json"

        config = lib.FWTConfig(config_path)
        config.config_file = config_path
        config.data = {"key": "value"}

        config.create_config()

        lib.resource_files.assert_called_once_with("fwt")

        assert config.data == {"key": "value", "preset": "value"}

        assert config.config_file.parent.exists()
        assert config.config_file.exists()


class TestFWTFile:
    @pytest.fixture(autouse=True)
    def patch_fwtpath(self, mocker: MockerFixture):
        mocker.patch("fwt.lib.FWTPath.__init__", return_value=None)

    def test_init(self, temp_fs: Path):
        """Testing with no trash directory provided."""
        file = lib.FWTFile(temp_fs / "file.txt")
        assert file._FWTFile__path == lib.FWTPath(temp_fs / "file.txt")
        assert file._FWTFile__new_path is None
        assert file.trash_path is False
        assert file.locked is False
        assert file.trash_dir is None
        assert file.keep_src is False

    def test_init_trash_dir(self, mocker: MockerFixture, temp_fs: Path):
        """Testing with trash directory provided."""
        mocker.patch("fwt.lib.FWTPath")
        trash_dir = "./trash"
        file = lib.FWTFile(temp_fs / "file.txt", trash_dir=trash_dir, keep_src=True)
        assert file._FWTFile__path == lib.FWTPath(temp_fs / "file.txt")
        assert file._FWTFile__new_path is None
        assert file.trash_path is False
        assert file.locked is False
        assert file.trash_dir == file.path.to_fpd() / trash_dir
        assert file.keep_src is True

    def test_init_trash_dir_absolute(self, temp_fs: Path):
        """Testing with trash directory provided."""
        trash_dir = temp_fs / "trash"
        file = lib.FWTFile(temp_fs / "file.txt", trash_dir=trash_dir, keep_src=True)
        assert file._FWTFile__path == lib.FWTPath(temp_fs / "file.txt")
        assert file._FWTFile__new_path is None
        assert file.trash_path is False
        assert file.locked is False
        assert file.trash_dir == trash_dir
        assert file.keep_src is True

    def test_path_getter(self, temp_fs: Path):
        """Verify that the path property returns the correct file path."""
        trash_dir = temp_fs / "trash"
        file = lib.FWTFile(temp_fs / "file.txt", trash_dir=trash_dir, keep_src=True)
        assert file.path == lib.FWTPath(temp_fs / "file.txt")

    def test_path_setter(self, mocker: MockerFixture, temp_fs: Path):
        mocker.patch("fwt.lib.FWTPath", wraps=Path)
        file = lib.FWTFile(temp_fs / "file.txt")
        expected_path = temp_fs / "file.txt"
        lib.FWTPath.assert_called_once_with(expected_path)
        assert file.path == lib.FWTPath(expected_path)

        updated_path = temp_fs / "new_file.txt"
        file.path = updated_path
        lib.FWTPath.assert_any_call(updated_path)
        assert file.path == lib.FWTPath(updated_path)

    def test_new_path_getter(self, temp_fs: Path):
        file = lib.FWTFile(temp_fs / "file.txt")
        assert file.new_path is None

        file._FWTFile__new_path = temp_fs / "new_file.txt"
        assert file.new_path == temp_fs / "new_file.txt"

    def test_new_path_set_to_none(self, temp_fs: Path):
        file = lib.FWTFile(temp_fs / "file.txt")
        file.new_path = None
        assert file.new_path is None

    def test_same_path_as_existing(self, mocker: MockerFixture, temp_fs: Path):
        mocker.patch("fwt.lib.logging")
        mocker.patch("fwt.lib.FWTPath", wraps=Path)
        file = lib.FWTFile(temp_fs / "file.txt")
        (temp_fs / "file.txt").touch()
        file.new_path = temp_fs / "file.txt"
        lib.logging.warning.assert_called_with("New path is the same as path, ignoring")

    def test_new_path_is_dir_and_path_is_not(
        self, mocker: MockerFixture, temp_fs: Path
    ):
        mocker.patch("fwt.lib.logging")
        mocker.patch("fwt.lib.FWTPath", wraps=Path)
        file = lib.FWTFile(temp_fs / "file.txt")
        (temp_fs / "file.txt").touch()
        (temp_fs / "dir").mkdir()
        file.new_path = temp_fs / "dir"
        lib.logging.debug.assert_called_with(
            "new path is dir and path is target updating new path to %s",
            temp_fs / "dir" / "file.txt",
        )
        assert file.new_path == temp_fs / "dir" / "file.txt"

    def test_valid_new_path(self, mocker: MockerFixture, temp_fs: Path):
        mocker.patch("fwt.lib.FWTPath", wraps=Path)
        (temp_fs / "file.txt").touch()
        (temp_fs / "new_file.txt").touch()
        file = lib.FWTFile(temp_fs / "file.txt")
        file.new_path = temp_fs / "new_file.txt"
        assert file.new_path == temp_fs / "new_file.txt"

    def test_rename_no_new_path(self, temp_fs: Path):
        file = lib.FWTFile(temp_fs / "file.txt")
        assert file.rename() is False

    def test_rename_keep_src(self, mocker: MockerFixture, temp_fs: Path):
        file = lib.FWTFile(temp_fs / "file.txt", keep_src=True)
        file.new_path = temp_fs / "new_path"

        (temp_fs / "file.txt").touch()

        def mock_copy():
            shutil.copy2(temp_fs / "file.txt", temp_fs / "new_file.txt")
            return True

        mocker.patch.object(file, "copy", side_effect=mock_copy)
        assert file.rename() is True
        file.copy.assert_called_once()

        assert (temp_fs / "file.txt").exists()
        assert (temp_fs / "new_file.txt").exists()

    def test_rename_new_path_exists(self, mocker: MockerFixture, temp_fs: Path):
        mocker.patch("fwt.lib.logging")

        (temp_fs / "file.txt").touch()
        (temp_fs / "new_file.txt").touch()

        file = lib.FWTFile(temp_fs / "file.txt")
        file.new_path = temp_fs / "new_file.txt"

        assert file.rename() is False

        lib.logging.error.assert_called_once_with(
            "Can't rename file %s\nTarget %s exists!",
            temp_fs / "file.txt",
            temp_fs / "new_file.txt",
        )

    def test_rename_successful(self, mocker: MockerFixture, temp_fs: Path):
        mocker.patch("fwt.lib.logging")

        (temp_fs / "file.txt").touch()

        file = lib.FWTFile(temp_fs / "file.txt")
        file.new_path = temp_fs / "new_file.txt"

        assert file.rename() is True

        assert not (temp_fs / "file.txt").exists()
        assert (temp_fs / "new_file.txt").exists()

        lib.logging.debug.assert_called_once_with(
            "rename:completed rename of %s -> %s",
            temp_fs / "file.txt",
            temp_fs / "new_file.txt",
        )

    def test_copy_file(self, mocker: MockerFixture, temp_fs: Path):
        mocker.patch("fwt.lib.logging")
        old_path = temp_fs / "file.txt"
        new_path = temp_fs / "fwt" / "new_file.txt"

        old_path.write_text("file contents", encoding="utf-8")

        file = lib.FWTFile(old_path)
        file.new_path = new_path

        result = file.copy()

        lib.logging.debug.assert_called_once_with(
            "copy:completed copy of %s -> %s", file.copy_of, file.path
        )

        assert new_path.parent.exists()
        assert file.copy_of == old_path
        assert file.path == new_path
        assert file.new_path is None
        assert result is True
        assert new_path.read_text(encoding="utf-8") == "file contents"

    def test_file_exists_and_overwrite_false(self, temp_fs: Path):
        old_path = temp_fs / "file.txt"
        new_path = temp_fs / "new_file.txt"

        old_path.write_text("file contents", encoding="utf-8")
        new_path.write_text("new file contents", encoding="utf-8")

        file = lib.FWTFile(old_path)
        file.new_path = new_path

        with pytest.raises(lib.FWTPathError):
            file.copy()

        assert file.path == old_path
        assert file.new_path == new_path
        assert new_path.read_text(encoding="utf-8") == "new file contents"

    def test_file_exists_and_overwrite_true(self, temp_fs):
        old_path = temp_fs / "file.txt"
        new_path = temp_fs / "new_file.txt"

        old_path.write_text("file contents", encoding="utf-8")
        new_path.write_text("new file contents", encoding="utf-8")

        file = lib.FWTFile(old_path)
        file.new_path = new_path

        result = file.copy(overwrite=True)

        assert file.copy_of == old_path
        assert file.path == new_path
        assert file.new_path is None
        assert result is True
        assert new_path.read_text(encoding="utf-8") == "file contents"

    def test_no_new_path(self, temp_fs: Path):
        old_path = temp_fs / "file.txt"

        file = lib.FWTFile(old_path)

        result = file.copy(overwrite=True)

        assert result is False
        assert file.path == old_path
        assert file.new_path is None

    def test_trash_with_trash_dir(self, mocker: MockerFixture, temp_fs: Path):
        foundry_data = temp_fs / "foundry_data"
        world_data = foundry_data / "Data" / "worlds" / "test-world"
        file_path = world_data / "file.txt"
        trash_dir = world_data / "trash"

        def mock_rename():
            file_path.rename(trash_dir / "file.txt")
            return True

        mocker.patch("fwt.lib.FWTFile.rename", side_effect=mock_rename)
        mocker.patch("fwt.lib.FWTPath.to_ftp", return_value=file_path)
        mocker.patch("fwt.lib.FWTPath.to_fpd", return_value=world_data)
        mocker.patch("fwt.lib.FWTPath.unlink", side_effect=Path.unlink)

        file_path.parent.mkdir(parents=True)
        file_path.touch()
        trash_dir.mkdir(parents=True)

        path = lib.FWTPath(file_path)
        file = lib.FWTFile(path, trash_dir=trash_dir)

        new_path = trash_dir / "file.txt"
        assert file.trash() is True
        assert file.new_path == new_path
        assert not path.exists()
        assert new_path.exists()

    def test_trash_without_trash_dir(self, mocker: MockerFixture, temp_fs: Path):
        mocker.patch("fwt.lib.logging")

        foundry_data = temp_fs / "foundry_data"
        world_data = foundry_data / "Data" / "worlds" / "test-world"
        file_path = world_data / "file.txt"

        def mock_unlink():
            file_path.unlink()

        mocker.patch("fwt.lib.FWTFile.rename")
        mocker.patch("fwt.lib.FWTPath.to_ftp", return_value=file_path)
        mocker.patch("fwt.lib.FWTPath.to_fpd", return_value=world_data)
        mocker.patch("fwt.lib.FWTPath.unlink", side_effect=mock_unlink)

        file_path.parent.mkdir(parents=True)
        file_path.touch()

        path = lib.FWTPath(file_path)
        file = lib.FWTFile(path, trash_dir=None)

        assert file.trash() is True
        assert not path.exists()
        assert file.new_path is None
        path.unlink.assert_called_once()
        lib.logging.debug.assert_called_once_with("trash: trash not set unlinking file")

    def test_repr(self, mocker: MockerFixture, temp_fs: Path):
        path = temp_fs / "file.txt"
        mocker.patch("fwt.lib.FWTFile.__str__", return_value=str(path))

        file = lib.FWTFile(path)

        assert repr(file) == str(path)
        file.__str__.assert_called_once()

    def test_eq_equal_strings(self, mocker: MockerFixture, temp_fs: Path):
        mocker.patch("fwt.lib.FWTPath", wraps=Path)
        mocker.patch(
            "fwt.lib.FWTFile.__str__",
            side_effect=[
                (temp_fs / "file.txt").as_posix(),
                (temp_fs / "file.txt").as_posix(),
            ],
        )
        assert lib.FWTFile(temp_fs / "file.txt") == lib.FWTFile(temp_fs / "file.txt")

    def test_eq_not_equal_strings(self, mocker: MockerFixture, temp_fs: Path):
        mocker.patch("fwt.lib.FWTPath", wraps=Path)
        mocker.patch(
            "fwt.lib.FWTFile.__str__",
            side_effect=[
                (temp_fs / "file1.txt").as_posix(),
                (temp_fs / "file2.txt").as_posix(),
            ],
        )
        assert lib.FWTFile(temp_fs / "file1.txt") != lib.FWTFile(temp_fs / "file2.txt")

    def test_eq_equal_strings_different_objects(
        self, mocker: MockerFixture, temp_fs: Path
    ):
        mocker.patch("fwt.lib.FWTPath", wraps=Path)
        mocker.patch(
            "fwt.lib.FWTFile.__str__",
            side_effect=[
                (temp_fs / "file1.txt").as_posix(),
            ],
        )
        assert lib.FWTFile(temp_fs / "file1.txt") == temp_fs / "file1.txt"

    def test_eq_not_equal_strings_different_objects(
        self, mocker: MockerFixture, temp_fs: Path
    ):
        mocker.patch("fwt.lib.FWTPath", wraps=Path)
        mocker.patch(
            "fwt.lib.FWTFile.__str__",
            side_effect=[
                (temp_fs / "file1.txt").as_posix(),
            ],
        )
        assert lib.FWTFile(temp_fs / "file1.txt") != temp_fs / "file2.txt"

    def test_str(self, mocker: MockerFixture, temp_fs: Path):
        path = temp_fs / "file.txt"

        mocker.patch("fwt.lib.FWTPath.as_ftp", return_value=path.as_posix())

        file = lib.FWTFile(path)

        assert str(file) == path.as_posix()


class TestFWTFileManager:
    @pytest.fixture(autouse=True)
    def mock_dependencies(self, temp_fs: Path, mocker: MockerFixture):
        project_dir = temp_fs / "test-world"
        project_dir.mkdir()

        class MockFWTPath:
            def __init__(self, path: str | Path, require_project: bool = False):
                self.__path = Path(path)

            def __getattr__(self, attr):
                return getattr(self.__path, attr)

            def to_fpd(self) -> Path:
                return project_dir

            def __eq__(self, __value: object) -> bool:
                return self.__path == __value

        mocker.patch("fwt.lib.FWTPath", side_effect=MockFWTPath)
        mocker.patch("fwt.lib.FWTProjectDb")
        mocker.patch("fwt.lib.FWTTextDb")
        mocker.patch("fwt.lib.find_next_avaliable_path", side_effect=lambda x: x)

    def test_init(self, temp_fs: Path, mocker: MockerFixture):
        mocker.patch("fwt.lib.FWTFileManager.project_dir")
        fm = lib.FWTFileManager(temp_fs / "test-world")

        assert fm.project_dir == temp_fs / "test-world"
        assert fm.trash_dir == temp_fs / "test-world" / "trash" / "session.0"
        assert fm.trash_dir.exists()
        assert fm._dir_exclusions == {
            fm.trash_dir.parent.as_posix() + "*",
            (fm.project_dir / "data").as_posix(),
            (fm.project_dir / "packs").as_posix(),
        }
        assert fm._FWTFileManager__file_extensions == set()
        assert fm._files == []
        assert fm.rewrite_names_pattern is None
        assert fm.remove_patterns == []
        assert fm.replace_patterns == []
        lib.FWTProjectDb.assert_called_once_with(
            fm.project_dir, lib.FWTTextDb, fm.trash_dir
        )
        assert fm._dbs == lib.FWTProjectDb(fm.project_dir, lib.FWTTextDb, fm.trash_dir)

    def test_init_with_trash_dir(self, temp_fs: Path, mocker: MockerFixture):
        mocker.patch("fwt.lib.FWTFileManager.project_dir")
        fm = lib.FWTFileManager(
            temp_fs / "test-world", trash_dir=temp_fs / "test-world" / "trash"
        )

        assert fm.project_dir == temp_fs / "test-world"
        assert fm.trash_dir == temp_fs / "test-world" / "trash" / "session.0"
        assert fm.trash_dir.exists()
        assert fm._dir_exclusions == {
            fm.trash_dir.parent.as_posix() + "*",
            (fm.project_dir / "data").as_posix(),
            (fm.project_dir / "packs").as_posix(),
        }
        assert fm._FWTFileManager__file_extensions == set()
        assert fm._files == []
        assert fm.rewrite_names_pattern is None
        assert fm.remove_patterns == []
        assert fm.replace_patterns == []
        lib.FWTProjectDb.assert_called_once_with(
            fm.project_dir, lib.FWTTextDb, fm.trash_dir
        )
        assert fm._dbs == lib.FWTProjectDb(fm.project_dir, lib.FWTTextDb, fm.trash_dir)

    def test_project_dir(self, temp_fs: Path, mocker: MockerFixture):
        mocker.patch("fwt.lib.FWTFileManager.__init__", return_value=None)
        fm = lib.FWTFileManager(temp_fs / "test-world")
        fm._project_dir = temp_fs / "test-world"
        assert fm.project_dir == temp_fs / "test-world"

    def test_set_project_dir(self, temp_fs: Path, mocker: MockerFixture):
        mocker.patch("fwt.lib.FWTFileManager.__init__", return_value=None)
        fm = lib.FWTFileManager(temp_fs / "test-world")
        fm.project_dir = temp_fs / "test-world"
        assert fm._project_dir == temp_fs / "test-world"

    @pytest.mark.parametrize("absolute_path", [True, False])
    def test_set_project_dir_raises(
        self, temp_fs: Path, mocker: MockerFixture, absolute_path: bool
    ):
        mocker.patch("fwt.lib.FWTFileManager.__init__", return_value=None)
        fm = lib.FWTFileManager(
            (temp_fs / "other-world") if absolute_path else Path("test-world")
        )
        project_dir = temp_fs / "other-world" if absolute_path else Path("test-world")
        with pytest.raises(lib.FWTFileError):
            fm.project_dir = project_dir

    def test_file_extensions(self, temp_fs: Path, mocker: MockerFixture):
        mocker.patch("fwt.lib.FWTFileManager.__init__", return_value=None)
        fm = lib.FWTFileManager(temp_fs / "test-world")
        fm._FWTFileManager__file_extensions = {".jpg", ".png"}
        assert fm.file_extensions == frozenset()
