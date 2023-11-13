import os
import tempfile
from pathlib import Path
from typing import Iterator

from behave import fixture, use_fixture


@fixture
def temp_fs(context) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(dir=os.getenv("RUNNER_TEMP")) as tmp_dir:
        old_cwd = os.getcwd()
        context.test_data = Path(__file__).absolute().parent / "steps" / "data"
        context.path = Path(tmp_dir)
        os.chdir(context.path)
        yield context.path
        os.chdir(old_cwd)


def before_scenario(context, scenario):
    use_fixture(temp_fs, context)
