from typing import cast
from unittest.mock import Mock

import pytest
from pytest import CaptureFixture
from pytest_mock import MockerFixture

from fwt import nedb2yaml


@pytest.fixture(autouse=True)
def patch_imports(mocker: MockerFixture) -> None:
    mocker.patch("fwt.nedb2yaml.Path", side_effect=mocker.Mock(wraps=nedb2yaml.Path))
    mocker.patch(
        "fwt.nedb2yaml.jsonlines", side_effect=mocker.Mock(wraps=nedb2yaml.jsonlines)
    )
    mocker.patch(
        "fwt.nedb2yaml.yaml.dump", side_effect=mocker.Mock(wraps=nedb2yaml.yaml.dump)
    )


def test_nedb2yaml(mocker: MockerFixture) -> None:
    db_lines = [
        {"_id": 1, "name": "Item 1"},
        {"_id": 2, "name": "Item 2"},
        {"_id": 3, "name": "Item 3"},
    ]

    mock_context_manager = mocker.MagicMock(
        __enter__=mocker.MagicMock(return_value=db_lines)
    )

    mocker.patch("fwt.nedb2yaml.jsonlines.open", return_value=mock_context_manager)

    result = nedb2yaml.nedb2yaml("test.db")

    cast(Mock, nedb2yaml.jsonlines.open).assert_called_once_with("test.db")

    for line in db_lines:
        cast(Mock, nedb2yaml.yaml.dump).assert_any_call(line, indent=2)

    expected = [
        "_id: 1\nname: Item 1\n",
        "_id: 2\nname: Item 2\n",
        "_id: 3\nname: Item 3\n",
    ]

    assert result == expected


def test_show_help(mocker: MockerFixture, capsys: CaptureFixture[str]) -> None:
    mocker.patch("fwt.nedb2yaml.sys.argv", new=["/path/to/fwt/nedb2yaml.py"])
    nedb2yaml.show_help()
    captured = capsys.readouterr()

    expected = f"{nedb2yaml.__doc__}\nUSAGE:\n  nedb2yaml.py <filename>\n"

    assert captured.out == expected
