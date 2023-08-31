"""CLI logic for FWT."""
import json
import logging
from pathlib import Path
from typing import Optional, Tuple

import click

from fwt._logging import LOG_LEVELS, setup_logging
from fwt.exceptions import FWTConfigNoDataDirError, FWTFileError
from fwt.lib import (
    FWTAssetDownloader,
    FWTConfig,
    FWTFileManager,
    FWTNeDB,
    FWTPath,
    FWTProjectDb,
    FWTSetManager,
)


@click.group(invoke_without_command=True)
@click.option(
    "--loglevel",
    type=click.Choice(LOG_LEVELS, case_sensitive=False),
    default="ERROR",
    help="Log level for console output",
)
@click.option(
    "--logfile",
    help="Output log messages to a file",
    type=click.Path(exists=False, file_okay=True, resolve_path=True),
)
@click.option("--config", help="specify a config file to load", type=click.Path())
@click.option(
    "--mkconfig", is_flag=True, default=False, help="Create a new default config file"
)
@click.option(
    "--dataDir",
    help="Foundry data directory",
    type=click.Path(exists=True, file_okay=False),
)
@click.option("--edit", is_flag=True, help="edit the presets file", default=False)
@click.option(
    "--showpresets", is_flag=True, default=False, help="show presets avaliable"
)
@click.option(
    "--preset",
    help=(
        "load a given preset. Where possible presets are merged "
        "with options otherwise options override presets"
    ),
)
@click.pass_context
def main(
    ctx: click.Context,
    loglevel: str,
    logfile: Optional[str],
    datadir: Optional[str],
    showpresets: bool,
    preset: Optional[str],
    config: Optional[str],
    edit: bool,
    mkconfig: bool,
) -> None:
    """Commands for managing asset files in foundry worlds."""
    ctx.ensure_object(dict)
    setup_logging(loglevel, logfile)
    logging.debug("Started cli with options %s", json.dumps(ctx.params))
    if config:
        config_file = Path(config)
    else:
        config_dir = click.get_app_dir("fwt")
        config_file = Path(config_dir) / "config.json"
    if edit:
        click.echo(f"Opening file {config_file} for editing")
        click.edit(filename=str(config_file))
        ctx.exit()
    logging.info("Attempting to load config from %s", config_file)
    try:
        ctx.obj["CONFIG"] = FWTConfig(config_file, mkconfig=mkconfig, dataDir=datadir)
    except FWTConfigNoDataDirError:
        ctx.fail(
            "Foundry dataDir not specified and unable to "
            "automatically determine the location. Set --dataDir"
            " or add dataDir to your config file"
        )
    except FWTFileError:
        if config:
            ctx.fail("Config file not found. Use --mkconfig to create it")
    if ctx.obj.get("CONFIG", {}).get("error", False):
        ctx.fail(f'Error loading config: {ctx.obj["CONFIG"]["error"]}')
    if preset:
        presets = ctx.obj.get("CONFIG", {}).get("presets", {})

        if not presets:
            ctx.fail("Preset not found: There are no presets defined")
        elif preset not in presets:
            ctx.fail(
                f"Preset not found. Presets avaliable are: "
                f" {', '.join(presets.keys())}"
            )
        preset_obj = presets[preset]
        if ctx.invoked_subcommand not in preset_obj["command"]:
            ctx.fail(
                f"Preset {preset} is not a valid preset for the"
                f" {ctx.invoked_subcommand} command"
            )
        ctx.obj["PRESET"] = preset_obj
    elif showpresets:
        presets = ctx.obj.get("CONFIG", {}).get("presets", {})
        if presets:
            click.echo(
                "\nPresets:\n"
                + "\n".join(
                    [
                        f"\t{k}: {v['command']} command, {v['description']}"
                        for (k, v) in presets.items()
                    ]
                )
            )
        else:
            ctx.fail("There are no presets defined")
    elif mkconfig:
        ctx.exit()
    elif not ctx.invoked_subcommand:
        click.echo(ctx.get_help())


@main.command()
@click.option(
    "--ext",
    multiple=True,
    help="file extension filter. May be used multiple times.",
)
@click.option(
    "--preferred",
    multiple=True,
    help=(
        "a pattern used to select a preferred file name "
        "from a list of duplicates. The string <project_dir> will be replaced "
        "with the full path to the world directory. May be used multiple times."
    ),
)
@click.option(
    "--byname",
    is_flag=True,
    default=False,
    help="method for finding duplicates",
)
@click.option(
    "--bycontent",
    is_flag=True,
    default=False,
    help="method for finding duplicates",
)
@click.option(
    "--exclude-dir",
    multiple=True,
    help="Directory name or path to exclude. May be used multiple times.",
    type=click.Path(exists=True, file_okay=False),
)
@click.argument(
    "dir_",
    metavar="DIR",
    type=click.Path(exists=True, file_okay=False),
)
@click.pass_context
def dedup(
    ctx: click.Context,
    dir_: str,
    ext: Tuple[str, ...],
    preferred: Tuple[str, ...],
    byname: bool,
    bycontent: bool,
    exclude_dir: Tuple[str, ...],
) -> None:
    """Scans for duplicate files, removes duplicates and updates fvtt's databases.

    DIR should be a directory containing a world.json file.
    """
    logging.debug("dedup started with options %s", json.dumps(ctx.params))
    dedup_dir = FWTPath(dir_)
    dup_manager = FWTSetManager(dedup_dir)
    preset = ctx.obj.get("PRESET", None)
    if preset:
        preferred += tuple(preset.get("preferred", []))
        byname = preset.get("byname", byname)
        bycontent = preset.get("bycontent", bycontent)
        ext += tuple(preset.get("ext", []))
        exclude_dir += tuple(preset.get("exclude-dir", []))
    for ex_dir in exclude_dir:
        dup_manager.add_exclude_dir(ex_dir)
    no_method = not byname and not bycontent
    both_methods = byname and bycontent
    if no_method or both_methods:
        ctx.fail(
            "one of --bycontent or --byname must be set to preform dedup"
            f"got byname={byname} and bycontent={bycontent}"
        )
    if bycontent:
        dup_manager.detect_method = "bycontent"
    elif byname:
        dup_manager.detect_method = "byname"
    for pp in preferred:
        dup_manager.add_preferred_pattern(pp)
    dup_manager.add_file_extensions(ext)
    dup_manager.scan()
    dup_manager.set_preferred_on_all()
    dup_manager.generate_rewrite_queue()
    dup_manager.process_file_queue()
    dup_manager.process_rewrite_queue()


@main.command()
@click.option(
    "--ext",
    multiple=True,
    help="file extension filter. May be used multiple times.",
)
@click.option(
    "--remove",
    multiple=True,
    help="characters matching this pattern will be removed from file names",
)
@click.option(
    "--replace",
    multiple=True,
    help="/pattern/replacment/ similar to sed for rewriting file names",
)
@click.option(
    "--lower", is_flag=True, default=False, help="convert file names to lower case"
)
@click.argument(
    "input_dir", metavar="DIR", type=click.Path(exists=True, file_okay=False)
)
@click.pass_context
def renameall(
    ctx: click.Context,
    input_dir: str,
    ext: Tuple[str, ...],
    remove: Tuple[str, ...],
    replace: Tuple[str, ...],
    lower: bool,
) -> None:
    """Scans files, renames based on a pattern and updates the world databases.

    DIR should be a directory containing a world.json file.
    """
    logging.debug("renameall started with options %s", json.dumps(ctx.params))
    project_dir = FWTPath(input_dir)
    file_manager = FWTFileManager(project_dir)
    preset = ctx.obj.get("PRESET", None)
    if preset:
        ext += tuple(preset.get("ext", ()))
        remove += tuple(preset.get("remove", ()))
        lower = lower or preset.get("lower", "")
        replace += tuple(preset.get("replace", ()))
    if not remove and not replace and not lower:
        ctx.fail("no action reqested set an option")
    file_manager.add_file_extensions(ext)
    for pattern in remove:
        file_manager.add_remove_pattern(pattern)
    for pattern_set in replace:
        file_manager.add_replace_pattern(pattern_set)
    file_manager.scan()
    file_manager.generate_rewrite_queue(lower)
    file_manager.process_file_queue()
    file_manager.process_rewrite_queue()


@main.command()
@click.argument("src", type=click.Path(exists=True, file_okay=True, resolve_path=True))
@click.argument("target", type=click.Path(exists=False))
@click.option("--keep-src", is_flag=True, default=False, help="keep source file")
@click.pass_context
def rename(ctx: click.Context, src: str, target: str, keep_src: bool) -> None:
    """Rename a file and update the project databases."""
    logging.debug("rename started with options %s", json.dumps(ctx.params))
    src_path = FWTPath(src)
    target_path = FWTPath(target, exists=False)

    if src_path.is_project and target_path.is_project:
        same_project = src_path.as_rpd() == target_path.as_rpd()
        if not same_project and not keep_src:
            ctx.fail(
                "File rename with src and target being different projects."
                " different projects are only supported with --keep-src"
            )

    if src_path.is_project_dir():
        fm = FWTFileManager(src_path.to_fpd())
        fm.rename_world(target_path, keep_src)
    else:
        if src_path.is_project:
            fm = FWTFileManager(src_path.to_fpd())
        elif target_path.is_project:
            fm = FWTFileManager(target_path.to_fpd())
        else:
            ctx.fail("No project directory found!")
        src_fwtfile = fm.add_file(src_path)
        src_fwtfile.new_path = target_path
        if keep_src:
            src_fwtfile.keep_src = True
        fm.generate_rewrite_queue()
        fm.process_file_queue()
        fm.process_rewrite_queue()


@main.command()
@click.pass_context
@click.argument(
    "input_dir",
    metavar="DIR",
    type=click.Path(exists=True, file_okay=False),
)
@click.option(
    "--type",
    "input_type",
    type=click.Choice(["actors", "items"], case_sensitive=False),
    help="Database type. Currently supports actors and items",
    required=True,
)
@click.option(
    "--asset-dir",
    type=click.Path(exists=False, file_okay=False),
    help="Directory in the world root to store images",
    required=True,
)
def download(
    ctx: click.Context, input_dir: str, input_type: str, asset_dir: str
) -> None:
    """Download linked assets to the project directory."""
    logging.debug("Download started with options %s", json.dumps(ctx.params))
    project_dir = FWTPath(input_dir, require_project=True)
    dbs = FWTProjectDb(project_dir, driver=FWTNeDB)
    downloader = FWTAssetDownloader(project_dir)
    if input_type == "actors":
        for actor in dbs.data.actors:
            downloader.download_actor_images(actor, asset_dir)
        dbs.data.actors.save()
    elif input_type == "items":
        for item in dbs.data.items:
            downloader.download_item_images(item, asset_dir)
        dbs.data.items.save()
    else:
        ctx.fail("--type only allows 'actors' or 'items'")


@main.command()
@click.pass_context
@click.option("--from", "_from", type=click.Path(exists=True), required=True)
@click.option("--to", type=click.Path(exists=True), required=True)
def pull(ctx: click.Context, _from: str, to: str) -> None:
    """Pull assets from external projects."""
    logging.debug("pull command started with options %s", json.dumps(ctx.params))
    fm = FWTFileManager(to)
    fm.find_remote_assets(_from)
    fm.generate_rewrite_queue()
    fm.process_file_queue()
    fm.process_rewrite_queue()


@main.command()
@click.pass_context
@click.argument("input_dir", metavar="DIR", type=click.Path(exists=True))
def info(ctx: click.Context, input_dir: str) -> None:
    """Provides basic information about a Foundry project."""
    logging.debug("info command started with options %s", json.dumps(ctx.params))
    project = FWTPath(input_dir)
    o = []
    o.append(f"Project: {'yes' if project.is_project else 'no'}")
    if project.is_project:
        o.append(f"Project Name: {project.project_name}")
        o.append(f"Project Type: {project.project_type}")
    click.echo("\n".join(o))
