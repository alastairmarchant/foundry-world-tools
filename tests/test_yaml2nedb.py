import pytest
from pytest import CaptureFixture
from pytest_mock import MockerFixture

from fwt import yaml2nedb


@pytest.fixture(autouse=True)
def patch_imports(mocker: MockerFixture):
    """Wrap functions to allow testing for calls."""
    mocker.patch("fwt.yaml2nedb.Path", side_effect=mocker.Mock(wraps=yaml2nedb.Path))
    mocker.patch(
        "fwt.yaml2nedb.jsonlines", side_effect=mocker.Mock(wraps=yaml2nedb.jsonlines)
    )
    mocker.patch(
        "fwt.yaml2nedb.yaml.safe_load_all",
        side_effect=mocker.Mock(wraps=yaml2nedb.yaml.safe_load_all),
    )


def test_yaml2nedb(mocker: MockerFixture):
    yaml_str = "\n".join(
        [
            "_id: 1",
            "name: Item 1",
            "---",
            "_id: 2",
            "name: Item 2",
            "---",
            "_id: 3",
            "name: Item 3",
        ]
    )

    mock_file_stream = mocker.MagicMock(
        __enter__=mocker.MagicMock(return_value=yaml_str)
    )

    mock_jsonlines_writer = mocker.MagicMock()

    mocker.patch("fwt.yaml2nedb.open", return_value=mock_file_stream)
    mocker.patch("fwt.yaml2nedb.jsonlines.Writer", return_value=mock_jsonlines_writer)

    yaml2nedb.yaml2nedb("test.yaml")

    yaml2nedb.open.assert_called_once_with("test.yaml")

    yaml2nedb.jsonlines.Writer.assert_called_once_with(
        yaml2nedb.sys.stdout, compact=True
    )

    expected = [
        {"_id": 1, "name": "Item 1"},
        {"_id": 2, "name": "Item 2"},
        {"_id": 3, "name": "Item 3"},
    ]

    mock_jsonlines_writer.write_all.assert_called_once_with(expected)


def test_show_help(mocker: MockerFixture, capsys: CaptureFixture):
    mocker.patch("fwt.yaml2nedb.sys.argv", new=["/path/to/fwt/yaml2nedb.py"])
    yaml2nedb.show_help()
    captured = capsys.readouterr()

    expected = f"{yaml2nedb.__doc__}\nUSAGE:\n  yaml2nedb.py <filename>\n"

    assert captured.out == expected
