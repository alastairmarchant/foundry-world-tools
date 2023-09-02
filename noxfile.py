"""Nox sessions."""
import os
import shlex
import shutil
import sys
import tempfile
from pathlib import Path
from textwrap import dedent
from typing import Iterable, Iterator

import nox


package = "fwt"
python_versions = ["3.11", "3.10", "3.9", "3.8"]
nox.needs_version = ">= 2021.10.1"
nox.options.sessions = (
    "pre-commit",
    "safety",
    "mypy",
    "tests",
    "typeguard",
    "xdoctest",
    "docs-build",
)


def install(
    session: nox.Session,
    *,
    groups: Iterable[str],
    root: bool = True,
    editable: bool = False,
) -> None:
    """Install the dependency groups using Poetry.

    Uses [work from here](
    https://github.com/cjolowicz/cookiecutter-hypermodern-python-instance/pull/679
    ) adapted using [this comment](
    https://github.com/cjolowicz/nox-poetry/issues/663#issuecomment-1429916978
    )

    This function installs the given dependency groups into the session's
    virtual environment. When ``root`` is true (the default), the function
    also installs the root package and its default dependencies.

    To avoid an editable install, the root package is not installed using
    ``poetry install``. Instead, the function invokes ``pip install .``
    to perform a PEP 517 build.

    Args:
        session: The Session object.
        groups: The dependency groups to install.
        root: Install the root package.
        editable: If the install should be editable,
            useful for live reloading docs.
    """
    with tempfile.NamedTemporaryFile(dir=".") as requirements:
        session.run(
            "poetry",
            "export",
            "--{}={}".format("only" if not root else "with", ",".join(groups)),
            "--format=requirements.txt",
            "--without-hashes",
            f"--output={requirements.name}",
            external=True,
        )
        session.install("-r", requirements.name)
    if root:
        if editable:
            session.install("-e", ".")
        else:
            session.install(".")


def export_requirements(session: nox.Session, *, extras: Iterable[str] = ()) -> Path:
    """Export a requirements file from Poetry.

    This function uses ``poetry export`` to generate a requirements file
    containing the default dependencies at the versions specified in
    ``poetry.lock``.

    Args:
        session: The Session object.
        extras: Extras supported by the project.

    Returns:
        The path to the requirements file.
    """
    output = session.run_always(
        "poetry",
        "export",
        "--format=requirements.txt",
        "--without-hashes",
        *[f"--extras={extra}" for extra in extras],
        external=True,
        silent=True,
        stderr=None,
    )

    if output is None:
        session.skip(
            "The command `poetry export` was not executed"
            " (a possible cause is specifying `--no-install`)"
        )

    assert isinstance(output, str)  # noqa: S101

    def _stripwarnings(lines: Iterable[str]) -> Iterator[str]:
        for line in lines:
            if line.startswith("Warning:"):
                print(line, file=sys.stderr)
                continue
            yield line

    text = "".join(_stripwarnings(output.splitlines(keepends=True)))

    path = session.cache_dir / "requirements.txt"
    path.write_text(text)

    return path


def activate_virtualenv_in_precommit_hooks(session: nox.Session) -> None:
    """Activate virtualenv in hooks installed by pre-commit.

    This function patches git hooks installed by pre-commit to activate the
    session's virtual environment. This allows pre-commit to locate hooks in
    that environment when invoked from git.

    Args:
        session: The Session object.
    """
    assert session.bin is not None  # noqa: S101

    # Only patch hooks containing a reference to this session's bindir. Support
    # quoting rules for Python and bash, but strip the outermost quotes so we
    # can detect paths within the bindir, like <bindir>/python.
    bindirs = [
        bindir[1:-1] if bindir[0] in "'\"" else bindir
        for bindir in (repr(session.bin), shlex.quote(session.bin))
    ]

    virtualenv = session.env.get("VIRTUAL_ENV")
    if virtualenv is None:
        return

    headers = {
        # pre-commit < 2.16.0
        "python": f"""\
            import os
            os.environ["VIRTUAL_ENV"] = {virtualenv!r}
            os.environ["PATH"] = os.pathsep.join((
                {session.bin!r},
                os.environ.get("PATH", ""),
            ))
            """,
        # pre-commit >= 2.16.0
        "bash": f"""\
            VIRTUAL_ENV={shlex.quote(virtualenv)}
            PATH={shlex.quote(session.bin)}"{os.pathsep}$PATH"
            """,
        # pre-commit >= 2.17.0 on Windows forces sh shebang
        "/bin/sh": f"""\
            VIRTUAL_ENV={shlex.quote(virtualenv)}
            PATH={shlex.quote(session.bin)}"{os.pathsep}$PATH"
            """,
    }

    hookdir = Path(".git") / "hooks"
    if not hookdir.is_dir():
        return

    for hook in hookdir.iterdir():
        if hook.name.endswith(".sample") or not hook.is_file():
            continue

        if not hook.read_bytes().startswith(b"#!"):
            continue

        text = hook.read_text()

        if not any(
            Path("A") == Path("a") and bindir.lower() in text.lower() or bindir in text
            for bindir in bindirs
        ):
            continue

        lines = text.splitlines()

        for executable, header in headers.items():
            if executable in lines[0].lower():
                lines.insert(1, dedent(header))
                hook.write_text("\n".join(lines))
                break


@nox.session(name="pre-commit", python=python_versions[0])
def precommit(session: nox.Session) -> None:
    """Lint using pre-commit."""
    args = session.posargs or [
        "run",
        "--all-files",
        "--hook-stage=manual",
        "--show-diff-on-failure",
    ]
    install(session, groups=["pre-commit"], root=False)
    session.run("pre-commit", *args)
    if args and args[0] == "install":
        activate_virtualenv_in_precommit_hooks(session)


@nox.session(python=python_versions[0])
def safety(session: nox.Session) -> None:
    """Scan dependencies for insecure packages."""
    # NOTE: Pass `extras` to `export_requirements` if the project supports any.
    requirements = export_requirements(session)
    install(session, groups=["safety"], root=False)
    session.run("safety", "check", "--full-report", f"--file={requirements}")


@nox.session(python=python_versions)
def mypy(session: nox.Session) -> None:
    """Type-check using mypy."""
    args = session.posargs or ["src", "docs/conf.py"]
    install(session, groups=["mypy", "tests"])
    session.run("mypy", *args)
    if not session.posargs:
        session.run("mypy", "--implicit-reexport", "tests")
    if not session.posargs:
        session.run("mypy", f"--python-executable={sys.executable}", "noxfile.py")


@nox.session(python=python_versions)
def tests(session: nox.Session) -> None:
    """Run the test suite."""
    install(session, groups=["coverage", "tests"])

    try:
        session.run("coverage", "run", "--parallel", "-m", "pytest", *session.posargs)
    finally:
        if session.interactive:
            session.notify("coverage", posargs=[])


@nox.session(python=python_versions[0])
def coverage(session: nox.Session) -> None:
    """Produce the coverage report."""
    args = session.posargs or ["report"]

    install(session, groups=["coverage"], root=False)

    if not session.posargs and any(Path().glob(".coverage.*")):
        session.run("coverage", "combine")

    session.run("coverage", *args)


@nox.session(python=python_versions[0])
def typeguard(session: nox.Session) -> None:
    """Runtime type checking using Typeguard."""
    install(session, groups=["typeguard", "tests"])
    session.run("pytest", f"--typeguard-packages={package}", *session.posargs)


@nox.session(python=python_versions)
def xdoctest(session: nox.Session) -> None:
    """Run examples with xdoctest."""
    if session.posargs:
        args = [package, *session.posargs]
    else:
        args = [f"--modname={package}", "--command=all"]
        if "FORCE_COLOR" in os.environ:
            args.append("--colored=1")

    install(session, groups=["xdoctest"])
    session.run("python", "-m", "xdoctest", *args)


@nox.session(name="docs-build", python=python_versions[0])
def docs_build(session: nox.Session) -> None:
    """Build the documentation."""
    args = session.posargs or ["docs", "docs/_build"]
    if not session.posargs and "FORCE_COLOR" in os.environ:
        args.insert(0, "--color")

    install(session, groups=["docs"])

    build_dir = Path("docs", "_build")
    if build_dir.exists():
        shutil.rmtree(build_dir)

    session.run("sphinx-build", *args)


@nox.session(python=python_versions[0])
def docs(session: nox.Session) -> None:
    """Build and serve the documentation with live reloading on file changes."""
    args = session.posargs or ["--open-browser", "docs", "docs/_build"]
    install(session, groups=["docs"], editable=True)

    build_dir = Path("docs", "_build")
    if build_dir.exists():
        shutil.rmtree(build_dir)

    session.run("sphinx-autobuild", *args)
