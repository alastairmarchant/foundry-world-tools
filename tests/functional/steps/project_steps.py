from pathlib import Path

import behave
from behave.runner import Context


def create_config_file():
    config_path = Path("config.json")
    config_path.write_text(
        f'{{"dataDir": "{Path("Data").absolute()}"}}',
        encoding="utf-8",
    )


def create_project_directory(context):
    project_dir = Path("Data/worlds/test-world").absolute()
    project_dir.mkdir(parents=True, exist_ok=True)
    context.project_dir = project_dir


def create_project(context):
    create_config_file()
    create_project_directory(context)
    module_json: Path = context.project_dir / "module.json"
    module_json.write_text('{"id": "test-world"}', encoding="utf-8")


@behave.given("a project directory does not exist")
def not_in_project_dir(context: Context) -> None:
    create_config_file()
    create_project_directory(context)


@behave.given("a project directory exists")
def in_project_dir(context: Context) -> None:
    create_project(context)
