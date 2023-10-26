"""Main logic of FWT."""
from __future__ import annotations

import filecmp
import json
import logging
import os
import re
import secrets
import shutil
import string
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from collections import UserDict
from contextlib import AbstractContextManager
from io import TextIOWrapper
from itertools import chain
from pathlib import Path, _posix_flavour, _windows_flavour  # type: ignore
from types import SimpleNamespace
from typing import Any, Generator, Iterable, Iterator, Literal

import jsonlines
from importlib_resources import as_file
from importlib_resources import files as resource_files
from typing_extensions import Never

from fwt.exceptions import (
    FUDNotFoundError,
    FWTConfigNoDataDirError,
    FWTFileError,
    FWTPathError,
)
from fwt.foundry import LATEST_VERSION, version_to_id_field
from fwt.typing import FoundryActor, FoundryItem, StrPath, StrPattern


# XXX add to FWTFileWriter and FWTFile
def cp_src_perm(src: StrPath, target: StrPath) -> None:
    """Copy mode bits, owner, and group of ``src`` to ``target``.

    Args:
        src: Source file.
        target: Target file.
    """
    st = os.stat(src)
    if "chown" in dir(os):
        os.chown(target, st.st_uid, st.st_gid)
    shutil.copymode(src, target)


def find_next_avaliable_path(output_path: Path) -> Path:
    """Increment file suffix until it does not exist.

    Args:
        output_path: Path to be incremented.

    Returns:
        Path with suffix incremented until the file does not exist.
    """
    output_path = Path(output_path)
    n = int(output_path.suffix[1:])
    while output_path.exists():
        n += 1
        output_path = output_path.with_suffix(f".{n}")
    return output_path


def find_foundry_user_dir(search_path: StrPath) -> Path:
    """Find the path to the Foundry user data directory.

    Searches for the Foundry ``options.json`` config file, and takes the data
    directory from there.

    Args:
        search_path: Path to search for config.

    Raises:
        FUDNotFoundError: Raised when the ``options.json`` config files could
            not be found.

    Returns:
        Path object pointing to the Foundry data directory.
    """
    try:
        search_path = Path(search_path)
        fvtt_options = next(
            f
            for p in (search_path, *search_path.parents)
            for f in p.glob("Config/options.json")
        )
        with fvtt_options.open() as options_file:
            data_path = json.load(options_file)["dataPath"]
        foundry_user_dir = Path(data_path) / "Data"
    except StopIteration as e:
        raise FUDNotFoundError(
            f"{search_path}: No Foundry user data directory found"
        ) from e
    return foundry_user_dir


def get_relative_to(path: StrPath, rs: StrPath) -> Path:
    """Resolves ``rs`` in relation to ``path``.

    Args:
        path: Absolute path to resolve against.
        rs: Path to resolve.

    Example:
        >>> str(
        >>>     get_relative_to(
        >>>         "/path/to/foundrydata/Data/worlds/test-world",
        >>>         "../test-world-2",
        >>>     )
        >>> )
        '/path/to/foundrydata/Data/worlds/test-world-2'

    Returns:
        Absolute path to ``rs``.
    """
    logging.debug("get_relative_to: Got base %s and rel %s", path, rs)
    pobj = Path(path)
    path = Path(path)
    # ! Can this just be done with ``Path.resolve`` and/or ``Path.relative_to``?
    if ".." in str(rs):
        rp = path / rs
        for e in rp.relative_to(path).parts:
            if e == "..":
                pobj = pobj.parent
            else:
                pobj = pobj / e
    else:
        pobj = path / rs
    logging.debug("get_relative_to: New rel path %s", pobj)
    return Path(pobj)


class FWTPath(Path):
    """Interface for representing paths in Foundry assets.

    Provides checks to ensure files are within Foundry user data directory.
    """

    # TODO: Remove need for _flavour?
    # XXX! Figure out how to have a path_dir
    _flavour = _windows_flavour if os.name == "nt" else _posix_flavour
    # TODO: Make this an instance variable
    foundry_user_dir: StrPath | None = None
    project_manafests = {"world.json", "module.json"}

    # TODO: Remove unused arguments
    def __init__(
        self,
        path: StrPath,
        foundry_user_dir: StrPath | None = None,
        exists: bool = True,
        check_for_project: bool = True,
        require_project: bool = False,
        version: int = LATEST_VERSION,
    ) -> None:
        """Initialise path.

        Args:
            path: File/dir path.
            foundry_user_dir: Path to Foundry user directory. Unused.
                Defaults to ``None``.
            exists: If the path must exist. Defaults to ``True``.
            check_for_project: If a project should be checked for.
                Defaults to ``True``.
            require_project: Require path be inside a project.
                Defaults to ``False``.
            version: Version of Foundry being used.
                Defaults to ``LATEST_VERSION``.

        Raises:
            FWTPathError: If the path does not exist.
        """
        self.orig_path = path
        self._fwt_fud = Path()
        self._fwt_rpd = Path()
        self._fwt_rtp = Path()
        self.manafest: Path | None = None
        self.project_name = ""
        self.project_type = ""
        self.version = version
        resolve_fvtt_path(self, path)
        test_ftp = self._fwt_fud / self._fwt_rtp
        if not test_ftp.exists() and exists:
            raise FWTPathError(f"Requested path {test_ftp} does not exist!")

    @property
    def is_project(self) -> bool:
        """``True`` if path contains a manifest file."""
        return self.manafest is not None

    def is_project_dir(self) -> bool:
        """``True`` if path is a project directory."""
        if self.is_project:
            return self.as_fpd() == self.as_ftp()
        return False

    def as_rpd(self) -> str:
        """Posix string of path to project root from Foundry data dir."""
        return self._fwt_rpd.as_posix()

    def to_rpd(self) -> Path:
        """Path to project root from Foundry data dir."""
        return self._fwt_rpd

    def as_rtp(self) -> str:
        """Posix string representation of target path relative to Foundry data dir."""
        return self._fwt_rtp.as_posix()

    def to_rtp(self) -> Path:
        """Target path relative to Foundry data dir."""
        return self._fwt_rtp

    def to_fpd(self) -> FWTPath:
        """Project absolute path from fs root."""
        return FWTPath(self._fwt_fud / self._fwt_rpd)

    def as_fpd(self) -> str:
        """Posix string of project absolute path from fs root."""
        return self.to_fpd().as_posix()

    def to_ftp(self) -> FWTPath:
        """Target absolute path from fs root."""
        return FWTPath(self._fwt_fud / self._fwt_rtp)

    def as_ftp(self) -> str:
        """Posix string of target absolute path from fs root."""
        return self.to_ftp().as_posix()

    def as_rpp(self) -> str:
        """Posix string of target path relative to project path."""
        return self.to_ftp().relative_to(self.to_fpd()).as_posix()

    def iterdir(self) -> Generator[FWTPath, None, None]:
        """Iterate over the files in this directory.

        Does not yield any result for the special paths '.' and '..'.
        """
        return (FWTPath(path) for path in super().iterdir())

    def to_abs(self) -> FWTPath:
        """Return an absolute version of this path."""
        return FWTPath(self.absolute())


# TODO: Remove this, path objects are supposed to be immutable
def reinit_fwtpath(fwtpath: FWTPath, newpath: Path) -> None:
    """Reinitialise ``FWTPath`` instance to the new path.

    Args:
        fwtpath: ``FWTPath`` instance.
        newpath: New path.
    """
    fwtpath._drv = newpath._drv  # type: ignore
    fwtpath._root = newpath._root  # type: ignore
    fwtpath._parts = newpath._parts  # type: ignore
    fwtpath._str = str(newpath)  # type: ignore


def resolve_fvtt_path(
    fwtpath: FWTPath,
    path: StrPath,
    foundry_user_dir: StrPath | None = None,
    exists: bool = True,
    check_for_project: bool = True,
    require_project: bool = False,
    version: int = LATEST_VERSION,
) -> None:
    """Resolve symlinks and relative paths into Foundry user dir paths."""
    if not fwtpath.is_absolute():
        cwd = os.environ.get("PWD", os.getcwd())
        # ! Seems to be same as temp_path = Path(cwd).relative_to(Path(path).absolute())
        temp_path = get_relative_to(Path(cwd), path)
        path = temp_path.as_posix()
        reinit_fwtpath(fwtpath, temp_path)
        logging.debug("Detected relative path. Translated to %s", path)
    if foundry_user_dir:
        fwtpath._fwt_fud = Path(foundry_user_dir)
    elif fwtpath.foundry_user_dir:
        fwtpath._fwt_fud = Path(fwtpath.foundry_user_dir)
    else:
        fwtpath._fwt_fud = find_foundry_user_dir(path)
    if not fwtpath._fwt_fud.exists():
        raise FUDNotFoundError(f"{path}: No Foundry user data directory found")
    if fwtpath.as_posix().startswith(fwtpath._fwt_fud.as_posix()):
        fwtpath._fwt_rtp = fwtpath.relative_to(fwtpath._fwt_fud)
        symlink = False
    else:
        logging.debug("Path is outside Foundry user directory. Possible symlink")
        symlink = True
        fwtpath._fwt_rtp = Path()
    if check_for_project or symlink:
        try:
            manafest = next(
                f
                for d in (fwtpath, *fwtpath.parents)
                for f in d.glob("*.json")
                if f.name in fwtpath.project_manafests
            )
            fwtpath.project_type = f"{manafest.stem}"
            fwtpath.project_name = json.loads(manafest.read_text())[
                version_to_id_field[version]
            ]
            if manafest.parent.name != fwtpath.project_name:
                logging.warning("project directory and name are different")
            if symlink:
                fwtpath._fwt_rpd = Path(
                    f"{fwtpath.project_type}s/{fwtpath.project_name}"
                )
                if fwtpath != manafest.parent:
                    fwtpath._fwt_rtp = Path(
                        fwtpath._fwt_rpd / fwtpath.relative_to(manafest.parent)
                    )
                else:
                    fwtpath._fwt_rtp = fwtpath._fwt_rpd
            else:
                fwtpath._fwt_rpd = manafest.parent.relative_to(fwtpath._fwt_fud)
            fwtpath.manafest = fwtpath._fwt_fud / fwtpath._fwt_rpd / manafest.name
        except StopIteration as e:
            if require_project or symlink:
                raise FWTPathError(
                    f"{path} is not part of a Foundry project"
                    + f" in the {fwtpath._fwt_fud} directory"
                ) from e
            elif len(fwtpath._fwt_rtp.parents) >= 3:
                fwtpath._fwt_rpd = list(fwtpath._fwt_rtp.parents)[-3]
            else:
                fwtpath._fwt_rpd = fwtpath._fwt_rtp
    reinit_fwtpath(fwtpath, fwtpath._fwt_fud / fwtpath._fwt_rtp)


class FWTConfig(UserDict):  # type: ignore
    """An object for loading and saving JSON config files."""

    def __init__(
        self, file_path: StrPath, mkconfig: bool = False, dataDir: str | None = None
    ) -> None:
        """Initialise config.

        Args:
            file_path: Path to config file.
            mkconfig: If a config should be created if ``file_path`` does not
                exist. Defaults to ``False``.
            dataDir: Path to data directory. Defaults to ``None``.

        Raises:
            FWTFileError: If the config file does not exist and ``mkconfig``
                is ``False``.
        """
        super().__init__(dataDir=dataDir)
        config_file = Path(file_path)
        if "~" in str(file_path):
            h = config_file
            # TODO: Replace with Path.expanduser
            self.config_file = Path(h.as_posix().replace("~", h.home().as_posix()))
        else:
            self.config_file = config_file
        if self.config_file.exists():
            if self.config_file.stat().st_size > 1:
                self.load()
                logging.debug(
                    "Loaded Config File. Config Data are: \n%s",
                    json.dumps(self.data, indent=4, sort_keys=True),
                )
            else:
                self.create_config()
        elif mkconfig:
            self.create_config()
        else:
            raise FWTFileError("Config file does not exist")
        self.setup()

    def setup(self) -> None:
        """Setup config, find and set user data directory.

        Raises:
            FWTConfigNoDataDirError: If user data directory could not be found.
        """
        fvtt_user_dir = self.data.get("dataDir", None)
        if not fvtt_user_dir:
            search_path = Path(os.environ.get("PWD", os.getcwd()))
            fvtt_user_dir = find_foundry_user_dir(search_path)
        if fvtt_user_dir:
            FWTPath.foundry_user_dir = fvtt_user_dir
        else:
            raise FWTConfigNoDataDirError("unable to determine fvtt_data_dir")
        print()

    def load(self) -> None:
        """Load config data from file."""
        with self.config_file.open("r+t", encoding="utf-8") as cf:
            try:
                config_data = json.load(cf)
                self.data.update(config_data)
                logging.debug("Loaded configuration file %s", self.config_file)
            except json.JSONDecodeError as e:
                logging.error("unable to parse config\n%s", e)
                self.data = {"error": f"{e}"}

    def save(self) -> None:
        """Save config to file."""
        with FWTFileWriter(self.config_file) as cf:
            config_json = json.dumps(self.data, indent=4, sort_keys=True)
            cf.write_fd.write(config_json)

    def create_config(self) -> None:
        """Generate and save FWT config with default presets."""
        logging.debug("create_config: %s", self.config_file)
        # ! Use importlib.resources when Python 3.8 support is dropped
        # ! Should these just be examples in docs instead of bundled with code?
        source = resource_files("fwt").joinpath("presets.json")
        with as_file(source) as file_path:
            with file_path.open(encoding="utf-8") as f:
                presets_json = json.load(f)

        self.data.update(presets_json)
        if not self.config_file.parent.exists():
            self.config_file.parent.mkdir()
        self.save()


class FWTFile:
    """Interface for changing files."""

    def __init__(
        self, path: StrPath, trash_dir: StrPath | None = None, keep_src: bool = False
    ) -> None:
        """Initialise file.

        Args:
            path: Path to file.
            trash_dir: Directory to move the file to if deleted, ``None`` will
                delete the file permanently. Defaults to ``None``.
            keep_src: If the original file should be kept when being moved.
                Defaults to ``False``.
        """
        self.__path = FWTPath(path)
        self.__new_path: FWTPath | None = None
        self.trash_path = False
        self.locked = False
        self.trash_dir: Path | None = None
        if trash_dir:
            trash_dir = Path(trash_dir)
            if trash_dir.is_absolute():
                self.trash_dir = trash_dir
            else:
                self.trash_dir = self.path.to_fpd() / trash_dir
        self.keep_src = keep_src

    @property
    def path(self) -> FWTPath:
        """Path to file."""
        return self.__path

    @path.setter
    def path(self, path: FWTPath) -> None:
        self.__path = FWTPath(path)

    @property
    def new_path(self) -> FWTPath | None:
        """Path to move file to when renaming, ``None`` if file was deleted."""
        return self.__new_path

    @new_path.setter
    def new_path(self, new_path: FWTPath | None) -> None:
        if new_path is None:
            self.__new_path = None
            return
        if new_path.exists():
            if self.path.samefile(new_path):
                logging.warning("New path is the same as path, ignoring")
                return
            if new_path.is_dir() and not self.path.is_dir():
                logging.debug(
                    "new path is dir and path is target updating new path to %s",
                    new_path / self.path.name,
                )
                self.new_path = new_path / self.path.name
                return
        self.__new_path = new_path

    def rename(self) -> bool:
        """Move or copy file to ``self.new_path``.

        Moves the file to ``self.new_path``, if ``self.keep_src`` is ``True``
        the file is copied and the original is not touched.

        Returns:
            ``True`` if the file was moved, else ``False``.
        """
        if not self.new_path:
            return False
        if self.keep_src:
            logging.debug("rename:keep_src requested using copy instead")
            return self.copy()
        if self.new_path.exists():
            logging.error(
                "Can't rename file %s\nTarget %s exists!",
                self.path,
                self.new_path,
            )
            return False
        os.renames(self.path, self.new_path)
        self.old_path = self.path
        self.path = self.new_path
        self.new_path = None
        logging.debug("rename:completed rename of %s -> %s", self.old_path, self.path)
        return True

    def copy(self, overwrite: bool = False) -> bool:
        """Copy file to ``self.new_path``, leaving the original untouched.

        Args:
            overwrite: If ``self.new_path`` already exist, and ``overwrite`` is
                ``True``, overwrite the existing file. Defaults to ``False``.

        Raises:
            FWTPathError: When ``self.new_path`` exists and ``overwrite`` is
                ``False``.

        Returns:
            True if file was copied.
        """
        if not self.new_path:
            return False
        if self.new_path.exists() and not overwrite:
            raise FWTPathError(
                f"Can't copy file {self.path}\nTarget {self.new_path} exists!"
            )
        os.makedirs(self.new_path.parent, exist_ok=True)
        shutil.copy2(self.path, self.new_path)
        # TODO: This is only used in logging, does not need to be instance variable
        self.copy_of = self.path
        self.path = self.new_path
        self.new_path = None
        logging.debug("copy:completed copy of %s -> %s", self.copy_of, self.path)
        return True

    def trash(self) -> bool:
        """Delete file by moving it to the trash directory.

        If the trash directory is None, delete the file.

        Returns:
            ``True`` if the file was successfully deleted, else ``False``.
        """
        if self.trash_dir:
            world_path = self.path.to_ftp().relative_to(self.path.to_fpd())
            self.new_path = FWTPath(self.trash_dir / world_path, exists=False)
            return self.rename()
        else:
            self.path.unlink()
            self.new_path = None
            logging.debug("trash: trash not set unlinking file")
            return True

    def __repr__(self) -> str:
        """String representation of target file absolute path."""
        return self.__str__()

    def __eq__(self, other: object) -> bool:
        """Compares object string representations to determine if they are equal.

        Args:
            other: The object to compare with.

        Returns:
            True if the objects are equal, False otherwise.
        """
        return self.__str__() == other.__str__()

    def __str__(self) -> str:
        """String representation of target file absolute path."""
        return self.path.as_ftp()


class FWTFileManager:
    """Manage project files and update Foundry db when file paths change."""

    def __init__(self, project_dir: StrPath, trash_dir: StrPath = "trash") -> None:
        """Initialise file manager.

        Args:
            project_dir: Path to project directory.
            trash_dir: Directory within ``project_dir`` to move deleted files
                to. Defaults to ``"trash"``.
        """
        logging.debug(
            "FWT_FileManager.__init__: Creating object with project dir %s",
            project_dir,
        )
        self.project_dir = FWTPath(project_dir, require_project=True).to_fpd()

        if isinstance(trash_dir, str):
            trash_dir = Path(trash_dir)
        if not trash_dir.is_absolute():
            trash_dir = self.project_dir / trash_dir
        self.trash_dir = find_next_avaliable_path(trash_dir / "session.0")
        self.trash_dir.mkdir(parents=True, exist_ok=True)

        self._dir_exclusions: set[str] = set()
        self._dir_exclusions.add(self.trash_dir.parent.as_posix() + "*")
        self._dir_exclusions.add((self.project_dir / "data").as_posix())
        self._dir_exclusions.add((self.project_dir / "packs").as_posix())
        self.__file_extensions: set[str] = set()
        self._files: list[FWTFile] = []
        self.rewrite_names_pattern = None
        self.remove_patterns: list[re.Pattern[str]] = []
        self.replace_patterns: list[tuple[re.Pattern[str], str]] = []
        self._dbs = FWTProjectDb(self.project_dir, FWTTextDb, self.trash_dir)

    @property
    def project_dir(self) -> FWTPath:
        """Path to project directory."""
        return self._project_dir

    @project_dir.setter
    def project_dir(self, project_dir: StrPath) -> None:
        project_dir = FWTPath(project_dir)
        if not project_dir.is_absolute() or not project_dir.exists():
            raise FWTFileError(f"invalid project dir {project_dir}")
        self._project_dir = project_dir

    @property
    def file_extensions(self) -> frozenset[str]:
        """List of file extensions for manager."""
        return frozenset(self.__file_extensions)

    def add_file_extensions(
        self, e: str | tuple[str, ...] | list[str] | set[str] | frozenset[str]
    ) -> None:
        """Add extension(s) to manager's extension list."""
        if isinstance(e, str):
            self.__file_extensions.add(e)
        elif isinstance(e, (tuple, list, set, frozenset)):
            for i in e:
                self.__file_extensions.add(i)

    @property
    def name(self) -> str:
        """Project directory name."""
        return self.project_dir.name

    @property
    def manafest(self) -> dict[str, str] | None:
        """Project manifest if ``self.project_dir`` is a project."""
        if self.project_dir.is_project and self.project_dir.manafest:
            manafest_data: dict[str, str] = json.loads(
                self.project_dir.manafest.read_text()
            )
            return manafest_data
        return None

    @manafest.setter
    def manafest(self, update: dict[str, str]) -> dict[str, str] | None:
        if self.project_dir.is_project and self.manafest:
            temp_manafest = self.manafest
            temp_manafest.update(update)
            with FWTFileWriter(
                self.project_dir.manafest, trash_dir=self.trash_dir
            ) as f:
                f.write(json.dumps(temp_manafest))
            return temp_manafest
        return None

    def add_exclude_dir(self, dir_pattern: str) -> None:
        """Add glob-style pattern to exclude directories.

        Args:
            dir_pattern: Glob-style pattern to exclude.
        """
        self._dir_exclusions.add(dir_pattern)

    def scan(self) -> None:
        """Scan files in ``self.project_dir``, add file matches to set."""
        scanner = FWTScan(self.project_dir)
        if self.file_extensions:
            ext_filter = FileExtensionsFilter()
            for e in self.file_extensions:
                ext_filter.add_match(e)
            scanner.add_filter(ext_filter)
        if self._dir_exclusions:
            dir_filter = DirNamesFilter()
            for d in self._dir_exclusions:
                dir_filter.add_match(d)
            scanner.add_filter(dir_filter)
        for f in scanner:
            self.add_file(f)

    def generate_rewrite_queue(self, lower: bool = False) -> None:
        """Generate rewrite queue for files.

        Args:
            lower: If paths should be lowercased. Defaults to ``False``.
        """
        logging.info("FWT_FileManager.generate_rewrite_queue starting")
        rewrite_queue: dict[StrPattern, str] = {}
        for f in self._files:
            if self.remove_patterns or self.replace_patterns or lower:
                rel_path = f.new_path.as_rpp() if f.new_path else f.path.as_rpp()
                logging.debug("rewrite file name starts as %s", rel_path)
                rel_path_parts = rel_path.split("/")
                new_rel_path = []
                for e in rel_path_parts:
                    for pat in self.remove_patterns:
                        e = pat.sub("", e)
                    for pat, rep in self.replace_patterns:
                        e = pat.sub(rep, e)
                    if lower:
                        e = e.lower()
                    new_rel_path.append(e)
                rel_path = "/".join(new_rel_path)
                logging.debug("rewrite filename to %s", rel_path)
                f.new_path = f.path.to_fpd() / rel_path
            if f.new_path:
                logging.debug(
                    "fm_generate_rewrite_queue: %s -> %s",
                    f.path.as_rtp(),
                    f.new_path.as_rtp(),
                )
                rewrite_queue.update({f.path.as_rtp(): f.new_path.as_rtp()})
        self.rewrite_queue: dict[StrPattern, str] = rewrite_queue

    def process_rewrite_queue(self, quote_find: bool = False) -> None:
        """Do db rewrites."""
        if len(self.rewrite_queue):
            self.db_replace(batch=self.rewrite_queue, quote_find=quote_find)

    def process_file_queue(self) -> None:
        """Do file renames and deletions."""
        for f in self._files:
            if f.new_path and f.keep_src:
                f.copy()
            elif f.new_path:
                f.rename()

    def add_remove_pattern(self, pattern: str) -> None:
        """Add regex pattern to list of patterns to be removed.

        Args:
            pattern: Removal pattern.
        """
        re_pattern = re.compile(pattern)
        self.remove_patterns.append(re_pattern)

    def add_replace_pattern(self, pattern_set: str) -> None:
        """Add regex pattern to list of patterns to replace.

        Args:
            pattern_set: Replacement pattern. Should be in the form
                ``"/original/replacement/"``, including slashes.
        """
        _, p, r, _ = (e for e in re.split(r"(?<![^\\]\\)/", pattern_set))
        re_pattern = re.compile(p)
        self.replace_patterns.append((re_pattern, r))

    def add_file(self, path: StrPath) -> FWTFile:
        """Add file to manager.

        Args:
            path: Path to file.

        Returns:
            FWTFile instance for file.
        """
        file = FWTFile(path, self.trash_dir)
        self._files.append(file)
        return file

    def db_replace(
        self, batch: dict[StrPattern, str], quote_find: bool = False
    ) -> None:
        """Replace filepaths for moved files in databases.

        Args:
            batch: Patterns to replace and their new value.
            quote_find: If quotes should be used on string patterns.
                Defaults to ``False``.
        """
        self.files_replace(
            (self.project_dir.manafest, *self.project_dir.glob("*/*db")),
            batch,
            quote_find,
        )

    def files_replace(
        self,
        files: Iterable[StrPath | None],
        batch: dict[StrPattern, str],
        quote_find: bool = False,
    ) -> None:
        """Replace filepaths for moved files in files.

        Args:
            files: Files to be updated.
            batch: Patterns to replace and their new value.
            quote_find: If quotes should be used on string patterns.
                Defaults to ``False``.

        Raises:
            TypeError: If pattern in batch is not a valid type.
        """
        for file in files:
            logging.debug("Opening db %s for rewrite", file)

            with FWTFileWriter(file, read_fd=True, trash_dir=self.trash_dir) as f:
                for _idx, line in enumerate(f.read_fd):
                    for find, replace in batch.items():
                        if isinstance(find, str):
                            if quote_find:
                                find, replace = f'"{find}"', f'"{replace}"'
                            line = line.replace(find, replace)
                        elif isinstance(find, re.Pattern):
                            line = find.sub(replace, line)
                        else:
                            raise TypeError("invalid member or rewrite queue")
                    f.write_fd.write(line)

    def find_remote_assets(self, src: StrPath) -> None:
        """Find all files in remote directory, set new path in current project.

        Args:
            src: Directory to check for files.
        """
        src = FWTPath(src)
        remote_assets = set()
        dbs = FWTProjectDb(self.project_dir, driver=FWTTextDb)
        path_re = re.compile(r"(?P<path>" + src.as_rpd() + r'[^"\\]+)')
        for db in dbs:
            for obj in db:
                for a in path_re.findall(obj):
                    if a:
                        logging.debug("find_remote_assets() found asset %s", a)
                        remote_assets.add(a)
        self._files = [
            FWTFile(src._fwt_fud / path, keep_src=True) for path in remote_assets
        ]
        for f in self._files:
            np = f.path.as_rtp().replace(f.path.as_rpd(), self.project_dir.as_rpd())
            f.new_path = FWTPath(np, exists=False)

    def rename_world(self, dst: FWTPath, keep_src: bool = False) -> None:
        """Rename a world folder, updating file paths in databases.

        Args:
            dst: Path to move world to.
            keep_src: ``True`` if the original world should be kept, and a copy
                should be made instead. Defaults to ``False``.

        Raises:
            FWTFileError: If the destination already exists.
        """
        dst = FWTPath(dst, exists=False)
        if dst.exists():
            raise FWTFileError("Cannot rename world using exiting directory")
        manafest_rpd = (
            f"{self.project_dir.project_type}s/{self.project_dir.project_name}"
        )
        dir_rewrite_match = re.compile(f'"{manafest_rpd}/([^"]+)"')
        dir_queue: dict[StrPattern, str] = {dir_rewrite_match: f'"{dst.as_rpd()}/\\1"'}
        name_rewrite_match = re.compile(re.escape(f'"{self.project_dir.project_name}"'))
        name_queue: dict[StrPattern, str] = {name_rewrite_match: f'"{dst.name}"'}

        if keep_src:
            shutil.copytree(self.project_dir, dst)
        else:
            os.renames(self.project_dir, dst)
        new_project = FWTFileManager(dst)
        new_project.files_replace(
            [
                new_project.project_dir.manafest,
            ],
            {**dir_queue, **name_queue},
        )
        new_project.db_replace(batch=dir_queue)


class FWTSetManager(FWTFileManager):
    """An object for managing duplicate assets."""

    def __init__(
        self,
        project_dir: StrPath,
        detect_method: str | None = None,
        trash_dir: StrPath = "trash",
    ) -> None:
        """Initialise set manager."""
        super().__init__(project_dir, trash_dir)
        self.preferred_patterns: list[str] = []
        self.rewrite_queue = {}
        self.sets: dict[int | str, FWTSet] = {}
        if detect_method:
            self.detect_method = detect_method

    def add_preferred_pattern(self, pp: str) -> None:
        """Add a "preferred pattern" to the list of preferred patterns.

        Args:
            pp: Pattern to be added. E.g. "<project_dir>/characters".
        """
        self.preferred_patterns.append(pp)

    @property
    def detect_method(self) -> str:
        """Detect method for identifying duplicate files."""
        return self._detect_method

    @detect_method.setter
    def detect_method(self, method: str) -> None:
        if method == "bycontent":
            self._detect_method = "bycontent"
        elif method == "byname":
            self._detect_method = "byname"
        else:
            raise ValueError(f"method must be bycontent or byname, got {method}")

    def scan(self) -> None:
        """Scan files in ``self.project_dir``, add file matches to set."""
        scanner = FWTScan(self.project_dir)
        if len(self.file_extensions):
            ext_filter = FileExtensionsFilter()
            for e in self.file_extensions:
                ext_filter.add_match(e)
            scanner.add_filter(ext_filter)
        if self._dir_exclusions:
            dir_filter = DirNamesFilter()
            for d in self._dir_exclusions:
                dir_filter.add_match(d)
            scanner.add_filter(dir_filter)
        for match in scanner:
            if self._detect_method == "bycontent":
                self.add_by_content(match)
            elif self._detect_method == "byname":
                self.add_by_name(match)

        single_sets = [k for k, v in self.sets.items() if len(v) < 2]
        for k in single_sets:
            del self.sets[k]

    def add_by_content(self, match: FWTPath) -> None:
        """Add match to set by file content.

        Args:
            match: File path to add.
        """
        with match.open("rb") as f:
            id_ = hash(f.read(4096))
            if id_ == 0:
                return  # empty file
        while not self.add_to_set(id_, match):
            id_ += 1

    def add_by_name(self, match: FWTPath) -> None:
        """Add match to set by file path.

        Args:
            match: File path to add.
        """
        id_str = (match.parent / match.stem).as_posix()
        self.add_to_set(id_str, match)

    def add_to_set(self, set_id: int | str, f: StrPath) -> bool:
        """Add a file to set. Deduplicates using the set method.

        Args:
            set_id: ID of set to add file to.
            f: Path to file to be added.

        Returns:
            ``True`` if the file was added to the set, else ``False``.
        """
        file_set = self.sets.get(set_id, FWTSet(set_id, trash_dir=self.trash_dir))
        if not file_set.files:
            self.sets[set_id] = file_set
            return file_set.add_file(f)
        elif self._detect_method == "bycontent" and filecmp.cmp(
            f, file_set._files[0].path, shallow=False
        ):
            return file_set.add_file(f)
        elif self._detect_method == "byname":
            return file_set.add_file(f)
        else:
            return False

    def process_file_queue(self) -> None:
        """Do file renames."""
        for fwtset in self.sets.values():
            if not fwtset.preferred:
                continue
            fwtset.preferred.rename()
            for f in fwtset.files:
                f.trash()

    def set_preferred_on_all(self) -> None:
        """Set preferred file for all sets."""
        logging.info("FWT_SetManager.set_preferred_on_all: Starting")
        for s in self.sets.values():
            for pattern in self.preferred_patterns:
                pattern = pattern.replace("<project_dir>", s.files[0].path.as_fpd())
                if s.choose_preferred(match=pattern):
                    logging.debug("Set preferred with %s", pattern)
                    break
            if not s.preferred:
                logging.debug("set preferred file to set item 0")
                s.choose_preferred(i=0)

    def generate_rewrite_queue(self, lower: bool = False) -> None:
        """Generate rewrite queue for sets.

        Args:
            lower: If paths should be lowercased. Unused in ``FWTSetManager``.
                Defaults to ``False``.
        """
        logging.info("FWT_SetManager.generate_rewrite_queue: Starting")
        rewrite_queue: dict[StrPattern, str] = {}
        for fwtset in self.sets.values():
            rewrite_queue.update(fwtset.rewrite_data)
        self.rewrite_queue = rewrite_queue


class FWTSet:
    """Class for handling duplicate files.

    An object that contains a set of files representing the same asset
    and methods for choosing a preferred file and removing the rest.
    """

    def __init__(self, set_id: int | str, trash_dir: StrPath) -> None:
        """Initialise set.

        Args:
            set_id: ID of the set.
            trash_dir: Directory to move deleted files to.
        """
        self.id = set_id
        self._files: list[FWTFile] = []
        self._preferred: FWTFile | None = None
        self.trash_dir = trash_dir

    @property
    def rewrite_data(self) -> dict[StrPattern, str]:
        """Generate dictionary of replacement paths for files in set."""
        data: dict[StrPattern, str] = {}
        if not self._preferred:
            return data
        if self._preferred.new_path:
            db_new_path = self._preferred.new_path.as_rtp()
            data.update({self._preferred.path.as_rtp(): db_new_path})
        else:
            db_new_path = self._preferred.path.as_rtp()
        for f in self._files:
            data.update({f.path.as_rtp(): db_new_path})
        logging.debug("FWTSet: Rewrite batch: %s", json.dumps(data, indent=4))
        return data

    @property
    def files(self) -> list[FWTFile]:
        """List of files in set."""
        return self._files

    @property
    def preferred(self) -> FWTFile | None:
        """Preferred file in set."""
        return self._preferred

    @preferred.setter
    def preferred(self, p: FWTFile | None) -> None:
        if p is None and self.preferred:
            self._files.append(self.preferred)
            self._preferred = None
        else:
            if p in self._files:
                if self._preferred:
                    self._files.append(self._preferred)
                self._preferred = p
                self._files.remove(p)
            else:
                raise ValueError(
                    "FWTSet: Preferred file not in set. Got preferred as "
                    + f"{p.path if p is not None else None}. Set contains: \n"
                    + "\n".join([f.path.as_posix() for f in self._files])
                )

    def choose_preferred(
        self, match: StrPattern | None = None, i: int | None = None
    ) -> bool:
        """Sets the preferred file to the first file matching the pattern.

        Sets the preferred file for the set to the first file matching the
        regex, if it is provided. If no pattern is provided, and ``i`` is
        provided, then preferred is set to ``self._files[i]``.

        Args:
            match: Regex string or pattern. Defaults to ``None``.
            i: Index of preferred file in list of files. Defaults to ``None``.

        Raises:
            ValueError: If the provided match is not a string or ``re.Pattern``.

        Returns:
            ``True`` if a preferred file was set, else ``False``.
        """
        pattern_match: re.Pattern[str] | None = None
        if match and isinstance(match, str):
            logging.debug("FWTSet: Testing set %s with match %s", self.id, match)
            pattern_match = re.compile(match)
        elif match and isinstance(match, re.Pattern):
            pattern_match = match
        elif match:
            raise ValueError(
                "choose_preferred requires a regex string or"
                "compiled pattern for the match parmater"
            )

        if pattern_match:
            for f in self._files:
                if pattern_match.search(str(f)):
                    self.preferred = f
                    logging.debug("FWTSet: Preferred file found %s", self.preferred)
                    break
        elif i is not None and i < len(self._files):
            self.preferred = self._files[i]

        if not self.preferred:
            logging.debug("FWTSet: No match in %s for %s", self.id, pattern_match)
            return False
        return True

    def add_file(
        self, path: StrPath, preferred: FWTFile | Literal[False] = False
    ) -> Literal[True]:
        """Add a file to the set.

        Args:
            path: Path to the file.
            preferred: If the file should be set as the preferred file.
                Defaults to ``False``.

        Returns:
            Always returns ``True``.
        """
        file = FWTFile(path, trash_dir=self.trash_dir)
        if file not in self._files:
            self._files.append(file)
        if preferred:
            self.preferred = file
        return True

    def __len__(self) -> int:
        """Length of set."""
        preferred_count = 1 if self.preferred else 0
        return len(self._files) + preferred_count

    def __str__(self) -> str:
        """String representation of FWTSet."""
        files = "\n".join([str(f) for f in self._files])
        return f"id:{self.id}\npreferred:{self.preferred}\nfiles:\n{files}"


class FWTFilter(ABC):
    """Class to filter paths to match a specified pattern."""

    chain_type: str = ""
    plugin_type: str = ""
    # TODO: Make this an instance variable
    _matches: list[str] = []

    def __init__(self, exclude: bool = False) -> None:
        """Initialise filter.

        Args:
            exclude: ``True`` if macthes should be excluded, otherwise matches are
                included. Defaults to ``False``.
        """
        self.exclude = exclude

    def _filter(self, p: FWTPath) -> FWTPath | None:
        """Not implemented."""
        raise NotImplementedError()

    def _process(self, p: FWTPath) -> FWTPath | None:
        """Not implemented."""
        raise NotImplementedError()

    def __call__(self, p: FWTPath) -> FWTPath | None:
        """Filter or process path.

        Args:
            p: Path to filter/process.

        Raises:
            NotImplementedError: Raised when ``self.chain_type`` is not valid.

        Returns:
            Filtered/processed file path or ``None``.
        """
        if self.chain_type == "filter":
            return self._filter(p)
        elif self.chain_type == "processor":
            return self._process(p)
        else:
            raise NotImplementedError()


class FileNamesFilter(FWTFilter):
    """File match. See ``pathlib.match``."""

    chain_type = "filter"
    plugin_type = "file"

    def add_match(self, m: str) -> None:
        """Add glob-style pattern to matches.

        Args:
            m: Glob-style pattern.
        """
        self._matches.append(m)

    def _filter(self, p: FWTPath) -> FWTPath | None:
        for m in self._matches:
            if self.exclude:
                if p.match(m):
                    continue
            else:
                if p.match(m):
                    return p
        return None


class FileExtensionsFilter(FWTFilter):
    """Case insensetive file extension match."""

    chain_type = "filter"
    plugin_type = "file"

    def add_match(self, m: str) -> None:
        """Add file extension to matches.

        Args:
            m: File extension string.
        """
        if m[0] != ".":
            m = "." + m
        self._matches.append(m)

    def _filter(self, p: FWTPath) -> FWTPath | None:
        e = p.suffix.lower()
        for m in self._matches:
            m = m.lower()
            if self.exclude:
                if e == m:
                    continue
            else:
                if e == m:
                    return p
        return None


class DirNamesFilter(FWTFilter):
    """Project relative dir match. See ``pathlib.match``."""

    chain_type = "filter"
    plugin_type = "dir"

    def __init__(self, exclude: bool = True) -> None:
        """Initialise filter.

        Args:
            exclude: ``True`` if macthes should be excluded, otherwise matches are
                included. Defaults to ``True``.
        """
        super().__init__(exclude)

    def add_match(self, m: str) -> None:
        """Add glob-style pattern to matches.

        Args:
            m: Glob-style pattern.
        """
        self._matches.append(m)

    def _filter(self, p: FWTPath) -> FWTPath | None:
        for m in self._matches:
            if self.exclude:
                if p.match(m):
                    logging.debug("DirNamesFilter: Exclude matched %s", p)
                    return None
            else:
                if p.match(m):
                    return p
        return p if self.exclude else None


class FWTChain(ABC):
    """Filter chain."""

    def __init__(self) -> None:
        """Initialise chain."""
        self._dir_filter_chain: list[FWTFilter] = []
        self._file_filter_chain: list[FWTFilter] = []
        self._file_processor_chain: list[FWTFilter] = []

    def add_filter(self, new_filter: FWTFilter) -> None:
        """Add filter to filter chain.

        Args:
            new_filter: Filter to be added.
        """
        if new_filter.plugin_type == "dir" and callable(new_filter):
            self._dir_filter_chain.append(new_filter)
        if new_filter.plugin_type == "file" and callable(new_filter):
            self._file_filter_chain.append(new_filter)

    def _dir_filter(self, p: FWTPath) -> Iterator[FWTPath]:
        for df in self._dir_filter_chain:
            dfp = df(p)
            if dfp is not None:
                p = dfp
            else:
                break
        if p and self._dir_cb(p):
            yield from self._dir_cb(p)
        elif p:
            yield p

    def _file_filter(self, p: FWTPath) -> Iterator[FWTPath]:
        for ff in self._file_filter_chain:
            ffp = ff(p)
            if ffp is not None:
                p = ffp
            else:
                break
        if p:
            yield from self._file_processor(p)

    def _file_processor(self, p: FWTPath) -> Iterator[FWTPath]:
        for fp in self._file_processor_chain:
            fpp = fp(p)
            if fpp is not None:
                p = fpp
            else:
                break
        if p:
            yield p

    @abstractmethod
    def _dir_cb(self, p: FWTPath) -> Iterator[FWTPath]:
        """Not implemented."""
        ...

    @abstractmethod
    def __iter__(self) -> Iterator[FWTPath]:
        """Not implemented."""
        ...


class FWTScan(FWTChain):
    """Directory scanner."""

    def __init__(self, root: FWTPath) -> None:
        """Initialise scanner.

        Args:
            root: Root directory for scanning.
        """
        super().__init__()
        self._root = root

    def _dir_cb(self, p: FWTPath) -> Iterator[FWTPath]:
        return self._walk(p)

    def _walk(self, path: FWTPath) -> Iterator[FWTPath]:
        for p in path.iterdir():
            if p.is_dir():
                yield from self._dir_filter(p)
            else:
                yield from self._file_filter(p)

    def __iter__(self) -> Iterator[FWTPath]:
        """Implement iter(self)."""
        return self._walk(self._root)


# TODO: Work out what needs to go in subscript
class FWTFileWriter(AbstractContextManager):  # type: ignore
    """Class to handle writing of files."""

    def __init__(
        self,
        dest_path: StrPath | None = None,
        trash_dir: StrPath | None = None,
        read_fd: bool = False,
        trash_overwrite: bool = True,
    ) -> None:
        """Initialise file writer.

        Args:
            dest_path: Destination path for file. Defaults to ``None``.
            trash_dir: Directory to move deleted files to. Defaults to ``None``.
            read_fd: If ``read_fd`` should be opened. Defaults to ``False``.
            trash_overwrite: If files in the trash directory should be deleted
                when another file is moved to that filepath. Defaults to ``True``.
        """
        self.__read_fd: bool = False
        self._trash_overwrite: bool = True
        self._trash_dir: Path | None = None
        self.setup(
            dest_path=dest_path,
            trash_dir=trash_dir,
            read_fd=read_fd,
            trash_overwrite=trash_overwrite,
        )

    def setup(
        self,
        dest_path: StrPath | None = None,
        trash_dir: StrPath | None = None,
        read_fd: bool | None = None,
        trash_overwrite: bool | None = None,
    ) -> None:
        """Setup file writer.

        Args:
            dest_path: Path to write file to. Defaults to ``None``.
            trash_dir: Directory to move deleted files to.
                Defaults to ``None``.
            read_fd: If ``read_fd`` should be opened. Defaults to ``None``.
            trash_overwrite: If files should overwrite existing files when
                moved to trash. Defaults to ``None``.
        """
        if read_fd is not None:
            self.__read_fd = read_fd
        if trash_overwrite is not None:
            self._trash_overwrite = trash_overwrite
        if trash_dir is not None:
            self._trash_dir = Path(trash_dir)
            self._trash_dir.parent.mkdir(parents=True, exist_ok=True)
        if dest_path:
            self._dest_path = Path(dest_path)
            self._temp_path = self._dest_path.with_suffix(".part")

    def _open_read_fd(self) -> TextIOWrapper:
        return self._dest_path.open("r+t", encoding="utf-8")

    def _open_write_fd(self) -> TextIOWrapper:
        return self._temp_path.open("w+t", encoding="utf-8")

    def __exit__(self, *args: Any) -> None:
        """Context manager teardown, close files, move files to trash."""
        if self.__read_fd:
            self.read_fd.close()
        self.write_fd.flush()
        if self.write_fd.tell() == 0:
            self.write_fd.close()
            self._temp_path.unlink()
            return
        self.write_fd.close()
        if self._trash_dir:
            rel_path = self._dest_path.relative_to(self._dest_path.parents[1])
            trash_path = self._trash_dir / rel_path
            trash_path.parent.mkdir(parents=True, exist_ok=True)
            if self._trash_overwrite or not trash_path.exists():
                try:
                    self._dest_path.replace(trash_path)
                except Exception as err:
                    self._temp_path.unlink()
                    raise err
        self._temp_path.rename(self._dest_path)

    def __enter__(self) -> FWTFileWriter:
        """Context manager setup, open files for reading/writing."""
        if not self._dest_path:
            raise ValueError("dest_path not provided")
        self.write_fd = self._open_write_fd()
        self.write = self.write_fd.write
        if self.__read_fd:
            self.read_fd = self._open_read_fd()
            self.read = self.read_fd.read
        return self

    def __call__(
        self,
        dest_path: StrPath | None = None,
        trash_dir: StrPath | None = None,
        read_fd: bool | None = None,
        trash_overwrite: bool | None = None,
    ) -> FWTFileWriter:
        """Setup and return self.

        Args:
            dest_path: Path to write file to. Defaults to ``None``.
            trash_dir: Directory to move deleted files to.
                Defaults to ``None``.
            read_fd: If ``read_fd`` should be opened. Defaults to ``None``.
            trash_overwrite: If files should overwrite existing files when
                moved to trash. Defaults to ``None``.

        Returns:
            Self.
        """
        self.setup(
            dest_path=dest_path,
            trash_dir=trash_dir,
            read_fd=read_fd,
            trash_overwrite=trash_overwrite,
        )
        return self


class FWTDb:
    """A lightweight object to manage reading / writing data files."""

    def __init__(self, data_file: StrPath, trash_dir: StrPath | None = None) -> None:
        """Initialise database object.

        Args:
            data_file: Path to data file.
            trash_dir: Directory to move deleted files to. Defaults to ``None``.
        """
        self.file_context = FWTFileWriter(trash_dir=trash_dir, trash_overwrite=False)
        self._data_file = Path(data_file)

    def writer(self) -> FWTFileWriter:
        """Return the file writer for the database.

        Returns:
            File writer for the database
        """
        return self.file_context(dest_path=self.path)

    @property
    def path(self) -> str:
        """Path to data file."""
        return self._data_file.as_posix()

    def __iter__(self) -> Iterator[Any]:
        """Not implemented."""
        raise NotImplementedError()


class FWTTextDb(FWTDb):
    """A lightweight object to manage reading / writing text files."""

    def open(self) -> FWTFileWriter:
        """Open data file and return file writer.

        Returns:
            File writer for ``self.path``.
        """
        return FWTFileWriter(dest_path=self.path)

    def __iter__(self) -> Iterator[str]:
        """Iterate over the lines of the text file."""
        with open(self.path, "r+t") as f:
            yield from f


class FWTNeDB(FWTDb):
    """A lightweight object to manage reading and writing NeDB files."""

    def __init__(self, data_file: StrPath, trash_dir: StrPath | None = None) -> None:
        """Initialise NeDB object.

        Args:
            data_file: Path to data file.
            trash_dir: Directory to move deleted files to. Defaults to ``None``.
        """
        super().__init__(data_file, trash_dir)
        self._data: list[dict[str, Any]] = []
        self._ids: dict[str, int] = {}

    @property
    def ids(self) -> tuple[str, ...]:
        """List of ids in database."""
        return tuple(self._ids.keys())

    def gen_id(self) -> str:
        """Generate ID.

        Returns:
            Randomly generated ID.
        """
        valid_chars = string.ascii_letters + string.digits
        n = "".join(secrets.choice(valid_chars) for _ in range(16))
        return n

    def find(self, query: Never, projection: Never) -> Never:
        """Not implemented."""
        raise NotImplementedError()

    def update(self, query: Never, update: Never, options: Never) -> Never:
        """Not implemented."""
        raise NotImplementedError()

    def find_generator(
        self,
        lookup_val: Any,
        lookup_key: str = "_id",
        lookup_obj: dict[str, Any] | list[Any] | object | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Perform lookup on data using key and value.

        Args:
            lookup_val: Value to match.
            lookup_key: Key to match. Defaults to "_id".
            lookup_obj: Object to perform lookup on. Defaults to None.

        Yields:
            Objects containing the lookup key/value pair.
        """
        if lookup_obj is None:
            lookup_obj = self._data
        if isinstance(lookup_obj, dict):
            logging.debug("obj_lookup_generater: Found dict object")
            for k, v in lookup_obj.items():
                if k == lookup_key and (v == lookup_val or lookup_val == "*"):
                    yield lookup_obj
                else:
                    yield from self.find_generator(v, lookup_key, lookup_val)
        elif isinstance(lookup_obj, list):
            logging.debug("obj_lookup_generator: Found list object")
            for item in lookup_obj:
                yield from self.find_generator(item, lookup_key, lookup_val)
        else:
            logging.debug("obj_lookup_generator: Got unknown object")

    def load(self) -> None:
        """Load data from NeDB file."""
        with open(self.path) as f:
            self._data = [json.loads(x) for x in f.readlines()]
        for i, obj in enumerate(self._data, start=0):
            self._ids.update({obj["_id"]: i})

    def save(self) -> None:
        """Save data to NeDB file."""
        with self.writer() as f:
            writer = jsonlines.Writer(f.write_fd, compact=True, sort_keys=True)
            writer.write_all(self._data)

    def __getitem__(self, key: str) -> dict[str, Any]:
        """Get an item from the database.

        Args:
            key: Item key.

        Raises:
            KeyError: If the item was not found in the database.

        Returns:
            Database entry.
        """
        if key in self._ids.keys():
            return self._data[self._ids[key]]
        raise KeyError

    def __iter__(self) -> Iterator[dict[str, Any]]:
        """Implement iter(self).

        Returns:
            Iterator of database entries.
        """
        if not self._data:
            self.load()
        return self._data.__iter__()


class FWTProjectDb:
    """Class for handling project db files."""

    def __init__(
        self, project_dir: FWTPath, driver: type[FWTDb], trash_dir: StrPath = "trash"
    ) -> None:
        """Initialise project db."""
        self.project_dir = FWTPath(project_dir, require_project=True)
        if trash_dir:
            if isinstance(trash_dir, str):
                trash_dir = Path(trash_dir)
            if not trash_dir.is_absolute():
                trash_dir = self.project_dir / trash_dir
            trash_dir = find_next_avaliable_path(trash_dir / "session.0")
            self.trash_dir = trash_dir
        self.data = SimpleNamespace(
            **{
                f.stem: driver(f, trash_dir=trash_dir)
                for f in self.project_dir.glob("data/*db")
            }
        )
        self.packs = SimpleNamespace(
            **{
                f.stem: driver(f, trash_dir=trash_dir)
                for f in self.project_dir.glob("packs/*db")
            }
        )

    def __iter__(self) -> Iterator[FWTDb]:
        """Implement iter(self).

        Returns:
            Chain object whose elements are the entries of the data and packs databases.
        """
        return chain(self.data.__dict__.values(), self.packs.__dict__.values())


class FWTAssetDownloader:
    """Class to handle the downloading of Foundry assets."""

    def __init__(self, project_dir: FWTPath) -> None:
        """Initialise asset downloader.

        Args:
            project_dir: Path to project directory.
        """
        self.r20re = re.compile(
            r'(?P<url>(?P<base>https://s3\.amazonaws\.com/files\.d20\.io/images/(?:[^/]+/)+)(?:\w+)\.(?P<ext>png|jpg|jpeg)[^"]*)'
        )
        self.url_regex = re.compile(r'\w+://[^"]*\.(?P<ext>(png)|(jpg)|(webp))')
        self.project_dir = FWTPath(project_dir)
        self.agent_string = (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/80.0.3987.87 Safari/537.36"
        )

    def check_url(self, url: str) -> bool:
        """Test a URL to see if it is accessible.

        Args:
            url: URL to check.

        Returns:
            ``True`` if the URL can be accessed.
        """
        req = urllib.request.Request(
            url,
            method="HEAD",
            headers={"User-Agent": self.agent_string},
        )
        resp = urllib.request.urlopen(req)  # noqa: S310
        if resp.status == 200:
            return True
        else:
            logging.error("URL %s returned HTTP Status of %s", url, resp.status)
            return False

    def download_url(self, u: str, path: StrPath) -> None:
        """Download an asset from a URL to a specified path.

        Args:
            u: URL to asset.
            path: Path to save asset to.
        """
        split_url = urllib.parse.urlsplit(u)
        url_path = urllib.parse.unquote(split_url.path)
        split_url = split_url._replace(path=urllib.parse.quote(url_path))
        url = urllib.parse.urlunsplit(split_url)
        r20_match = self.r20re.search(url)
        if r20_match:
            url_parts = r20_match.groupdict()
            for size in ("original", "max", "med"):
                check_url = f'{url_parts["base"]}{size}.{url_parts["ext"]}'
                if self.check_url(check_url):
                    url = check_url
                    break

        logging.debug("Downloading URL %s", url)
        req = urllib.request.Request(
            url, method="GET", headers={"User-Agent": self.agent_string}
        )
        try:
            resp = urllib.request.urlopen(req)  # noqa: S310
        except urllib.error.HTTPError as e:
            logging.error("Download error: %s for URL %s", e, url)
        else:
            if resp.status == 200:
                with open(path, "wb") as f:
                    f.write(resp.read())

    def format_filename(self, name: str) -> str:
        """Remove special characters in filenames.

        Args:
            name: Original filename.

        Returns:
            Formatted filename with no special characters.
        """
        filename = re.sub(r"[^A-Za-z0-9\-\ \.]", "", name)
        filename = filename.replace(" ", "-").lower()
        return re.sub(r"^\.", "", filename)

    def download_item_images(self, item: FoundryItem, asset_dir: str = "items") -> None:
        """Download remote images from items to local disk.

        Args:
            item: Item object to download files for.
            asset_dir: Directory to store downloaded images. Defaults to ``"items"``.

        Raises:
            FileNotFoundError: If the asset failed to download.
        """
        item_name = item["name"]
        item_img = item["img"]
        if self.project_dir.version <= 9:
            item_desc = item["data"]["description"]["value"]
        else:
            item_desc = item["system"]["description"]["value"]

        if not item_img:
            logging.error("\nNo image set for %s. Skipping \n", item_name)
            return
        logging.debug("checking if item img, %s, is a URL", item_img)
        img_match = self.url_regex.match(item_img)
        desc_match = self.url_regex.search(item_desc)
        item_dir = Path(asset_dir) / self.format_filename(item_name)
        if img_match:
            logging.debug("Item image is a URL %s", item_img)
            filename = self.format_filename(f"image.{img_match.group('ext')}")
            target_path = FWTPath(self.project_dir / item_dir / filename, exists=False)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            self.download_url(item_img, target_path)
            if target_path.exists():
                item["img"] = target_path.as_rtp()
            else:
                raise FileNotFoundError(f"Downloaded file {target_path} was not found")
        if desc_match:
            item_desc = self.item_download_from_desc(item_desc, item_name, item_dir)
            if self.project_dir.version <= 9:
                item["data"]["description"]["value"] = item_desc
            else:
                item["system"]["description"]["value"] = item_desc

    def item_download_from_desc(
        self, item_desc: str, item_name: str, item_dir: Path
    ) -> str:
        """Download images from an item description, update the description.

        Args:
            item_desc: Item descritpion to pull image from.
            item_name: Name of the item.
            item_dir: Directory to download images to.

        Raises:
            FileNotFoundError: If a downloaded file could not be found.

        Returns:
            Updated description.
        """
        urls = set()
        for match in self.url_regex.finditer(item_desc):
            if match[0] in urls:
                continue
            urls.add(match[0])
            filename = self.format_filename(
                f"{item_name}-desc-{len(urls)}.{match.group('ext')}"
            )
            target_path = FWTPath(self.project_dir / item_dir / filename, exists=False)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            self.download_url(match[0], target_path)
            if target_path.exists():
                logging.debug("Downloaded %s to %s", match[0], target_path)
                item_desc = item_desc.replace(match[0], target_path.as_rtp())
            else:
                raise FileNotFoundError(f"Downloaded file {target_path} was not found")
        return item_desc

    def download_actor_images(
        self, actor: FoundryActor, asset_dir: str = "characters"
    ) -> None:
        """Download remote images from actors to local disk.

        Args:
            actor: Actor object to download files for.
            asset_dir: Directory to store downloaded images.
                Defaults to ``"characters"``.

        Raises:
            FileNotFoundError: If the asset failed to download.
        """
        actor_img = actor["img"]
        if self.project_dir.version <= 9:
            token_img = actor["token"]["img"]
            actor_bio = actor["data"]["details"]["biography"]["value"]
        else:
            token_img = actor["prototypeToken"]["texture"]["src"]
            actor_bio = actor["system"]["details"]["biography"]["value"]
        actor_name = actor["name"]
        if not actor_img or not token_img:
            logging.error("\nNo image file for %s. Skipping\n", actor_name)
            return
        logging.debug("checking %s", actor_img)
        img_match = self.url_regex.match(actor_img) if actor_img else None
        logging.debug("checking %s", token_img)
        token_match = self.url_regex.match(token_img) if token_img else None
        bio_match = self.r20re.search(actor_bio) if actor_bio else None
        character_dir = self.get_character_dir(
            actor_img, token_img, actor_name, asset_dir
        )
        if img_match:
            logging.debug("Found actor image URL match: %s - %s", actor_name, actor_img)
            filename = self.format_filename(f"avatar.{img_match.group('ext')}")
            target_path = FWTPath(
                self.project_dir / character_dir / filename, exists=False
            )
            target_path.parent.mkdir(parents=True, exist_ok=True)
            self.download_url(actor_img, target_path)
            if target_path.exists():
                actor["img"] = target_path.as_rtp()
                actor_img = actor["img"]
            else:
                logging.error("Downloaded file %s was not found", target_path)

        if token_match:
            filename = self.format_filename(f"token.{token_match.group('ext')}")
            target_path = FWTPath(
                self.project_dir / character_dir / filename, exists=False
            )
            target_path.parent.mkdir(parents=True, exist_ok=True)
            self.download_url(token_img, target_path)
            if target_path.exists():
                if self.project_dir.version <= 9:
                    actor["token"]["img"] = target_path.as_rtp()
                else:
                    proto_token = actor["prototypeToken"]
                    proto_token["texture"]["src"] = target_path.as_rtp()
            else:
                raise FileNotFoundError(f"Downloaded file {target_path} was not found")

        if bio_match:
            actor_bio = self.actor_download_from_bio(
                actor_bio, actor_name, character_dir
            )
            if self.project_dir.version <= 9:
                actor["data"]["details"]["biography"]["value"] = actor_bio
            else:
                actor["system"]["details"]["biography"]["value"] = actor_bio

    def get_character_dir(
        self, actor_img: str, token_img: str, actor_name: str, asset_dir: str
    ) -> Path:
        """Get the director to save character images to.

        Checks where the actor currently has local images saved, and downloads
        images to that directory. If the actor does not have an local images,
        they are downloaded to ``<asset_dir>/<actor_name>``.

        Args:
            actor_img: Actor image URL/path.
            token_img: Actor token image URL/path.
            actor_name: Actor name.
            asset_dir: Backup path to save images to.

        Returns:
            Path to save images to.
        """
        if actor_img and not self.url_regex.match(actor_img):
            try:
                return Path(actor_img).parent.relative_to(self.project_dir.to_rpd())
            except ValueError:
                pass
        if token_img and not self.url_regex.match(token_img):
            try:
                return Path(token_img).parent.relative_to(self.project_dir.to_rpd())
            except ValueError:
                pass
        return Path(asset_dir) / self.format_filename(actor_name)

    def actor_download_from_bio(
        self, actor_bio: str, actor_name: str, character_dir: Path
    ) -> str:
        """Download images from an actor bio, update the bio.

        Args:
            actor_bio: Actor bio to pull images from.
            actor_name: Name of the actor.
            character_dir: Directory to download images to.

        Raises:
            FileNotFoundError: If a downloaded file could not be found.

        Returns:
            Updated bio.
        """
        urls = set()
        for match in self.r20re.finditer(actor_bio):
            if match.group("url") in urls:
                continue
            urls.add(match.group("url"))
            filename = f"{actor_name}-bio-{len(urls)}.{match.group('ext')}"
            target_path = FWTPath(
                self.project_dir / character_dir / filename, exists=False
            )
            target_path.parent.mkdir(parents=True, exist_ok=True)
            self.download_url(match.group("url"), target_path)
            if target_path.exists():
                logging.debug("Downloaded %s to %s", match.group("url"), target_path)
                actor_bio = actor_bio.replace(match.group("url"), target_path.as_rtp())
            else:
                raise FileNotFoundError(f"Downloaded file {target_path} was not found")
        return actor_bio
