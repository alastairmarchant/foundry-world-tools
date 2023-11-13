import behave
from behave.runner import Context
from click.testing import CliRunner

from fwt import cli


@behave.when("we run the info command")
def run_info(context: Context) -> None:
    runner = CliRunner()
    context.result = runner.invoke(
        cli.main, ["--config", "./config.json", "info", str(context.project_dir)]
    )
    assert context.result.exit_code == 0


@behave.then("the project info will be printed")
def project_info_printed(context: Context) -> None:
    assert (
        context.result.output
        == "\nProject: yes\nProject Name: test-world\nProject Type: module\n"
    )


@behave.then("the project info will not be printed")
def project_info_not_printed(context: Context) -> None:
    assert context.result.output == "\nProject: no\n"
