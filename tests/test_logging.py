import pytest
from pytest_mock import MockerFixture

from fwt import _logging


@pytest.fixture(autouse=True)
def patch_imports(mocker: MockerFixture):
    mocker.patch("fwt._logging.logging")


@pytest.mark.parametrize(
    ("log_level", "log_file"),
    [
        ["QUIET", "fwt.log"],
        ["INFO", "fwt.log"],
        ["DEBUG", None],
        ["QUIET", None],
    ],
)
def test_setup_logging(log_level: str, log_file: str):
    _logging.setup_logging(log_level, log_file)

    if log_file:
        _logging.logging.basicConfig.assert_called_once_with(
            filename=log_file, level=_logging.logging.DEBUG
        )

    if log_level == "QUIET":
        _logging.logging.StreamHandler.assert_not_called()
        if not log_file:
            _logging.logging.basicConfig.assert_not_called()
    else:
        if log_file:
            _logging.logging.StreamHandler.assert_called_once()
            _logging.logging.StreamHandler().setLevel.assert_called_once_with(log_level)
            _logging.logging.getLogger.assert_called_once_with("")
            _logging.logging.getLogger("").addHandler.assert_called_once_with(
                _logging.logging.StreamHandler()
            )
        else:
            _logging.logging.basicConfig.assert_called_once_with(level=log_level)
