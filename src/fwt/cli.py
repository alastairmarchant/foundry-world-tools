import logging
from typing import Optional

import click

from fwt import lib


@click.group(invoke_without_command=True)
@click.option("--loglevel", default="ERROR", help="Log level for console output")
@click.option(
    "--logfile",
    help="log DEBUG messages to file",
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
def cli(
    ctx: click.Context,
    loglevel: Optional[str],
    logfile: Optional[str],
    datadir: Optional[str],
    showpresets: bool,
    preset: Optional[str],
    config: Optional[str],
    edit: bool,
    mkconfig: bool,
):
    """Commands for managing asset files in foundry worlds"""
    ctx.ensure_object(dict)
    if logfile:
        logging.basicConfig(filename=logfile, level=logging.DEBUG)
    if loglevel.lower() != "quiet":
        loglevel = loglevel.upper()
        level_check = loglevel in lib.LOG_LEVELS
        if not level_check:
            ctx.fail(
                f"loglevel {loglevel} must be one of " f"{lib.LOG_LEVELS+['QUIET']}"
            )
        loglevel = getattr(lib.logging, loglevel)
        if logfile:
            consoleHandler = logging.StreamHandler()
            consoleHandler.setLevel(loglevel)
            logging.getLogger("").addHandler(consoleHandler)
        else:
            logging.basicConfig(level=loglevel)
    logging.debug(f"started cli with options {lib.json.dumps(ctx.params)}")
    if config:
        config_file = lib.Path(config)
    else:
        config_dir = click.get_app_dir("fwt")
        config_file = lib.Path(config_dir) / "config.json"
    if edit:
        click.echo(f"Opening file {config_file} for editing")
        click.edit(filename=config_file)
        ctx.exit()
    logging.info(f"Attempting to load config from {config_file}")
    try:
        config_data = lib.FWTConfig(config_file, mkconfig=mkconfig, dataDir=datadir)
    except lib.FWTConfigNoDataDir:
        ctx.fail(
            "Foundry dataDir not specified and unable to "
            "automatically determine the location. Set --dataDir"
            " or add dataDir to your config file"
        )
    except lib.FWTFileError:
        if config:
            ctx.fail("Config file not found. Use --mkconfig to create it")
        config_data = {}
    if config_data.get("error", False):
        ctx.fail(f'Error loading config: {config_data["error"]}')
    ctx.obj["CONFIG"] = config_data
    ctx.obj["CONFIG_LOADED"] = True
    if preset:
        if ctx.obj["CONFIG_LOADED"]:
            presets = ctx.obj["CONFIG"].get("presets", {})
        try:
            preset_obj = presets[preset]
        except NameError:
            ctx.fail("Preset not found: There are no presets defined")
        except KeyError:
            ctx.fail(
                f"Preset not found. Presets avaliable are: "
                f" {', '.join(presets.keys())}"
            )
        if ctx.invoked_subcommand not in preset_obj["command"]:
            ctx.fail(
                f"Preset {preset} is not a valid preset for the"
                f" {ctx.invoked_subcommand} command"
            )
        ctx.obj["PRESET"] = preset_obj
    elif showpresets:
        if ctx.obj["CONFIG_LOADED"]:
            presets = ctx.obj["CONFIG"].get("presets", {})
        try:
            click.echo(
                "\nPresets:\n"
                + "\n".join(
                    [
                        f"\t{k}: {v['command']} command, {v['description']}"
                        for (k, v) in presets.items()
                    ]
                )
            )
        except NameError:
            ctx.fail("There are no presets defined")
    elif mkconfig:
        ctx.exit()
    elif not ctx.invoked_subcommand:
        click.echo(ctx.get_help())


@cli.command()
@click.option(
    "--ext", multiple=True, help="file extension filter. May be used multiple times."
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
    "--byname", is_flag=True, default=False, help="method for finding duplicates"
)
@click.option(
    "--bycontent", is_flag=True, default=False, help="method for finding duplicates"
)
@click.option(
    "--exclude-dir",
    multiple=True,
    help="Directory name or path to exclude. May be used multiple times.",
)
@click.argument("dir", type=click.Path(exists=True, file_okay=False))
@click.pass_context
def dedup(ctx, dir, ext, preferred, byname, bycontent, exclude_dir):
    """Scans for duplicate files, removes duplicates and updates fvtt's databases.

    DIR should be a directory containing a world.json file"""
    logging.debug(f"dedup started with options {lib.json.dumps(ctx.params)}")
    dir = lib.FWTPath(dir)
    dup_manager = lib.FWTSetManager(dir)
    preset = ctx.obj.get("PRESET", None)
    if preset:
        preferred += tuple(preset.get("preferred", []))
        byname = preset.get("byname", byname)
        bycontent = preset.get("bycontent", bycontent)
        ext += tuple(preset.get("ext", []))
        exclude_dir += tuple(preset.get("exclude-dir", []))
    for dir in exclude_dir:
        dup_manager.add_exclude_dir(dir)
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


@cli.command()
@click.option(
    "--ext", multiple=True, help="file extension filter. May be used multiple times."
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
@click.argument("dir", type=click.Path(exists=True, file_okay=False))
@click.pass_context
def renameall(ctx, dir, ext, remove, replace, lower):
    """Scans files, renames based on a pattern and updates the world databases.

    DIR should be a directory containing a world.json file"""
    logging.debug(f"renameall started with options {lib.json.dumps(ctx.params)}")
    dir = lib.FWTPath(dir)
    file_manager = lib.FWTFileManager(dir)
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


@cli.command()
@click.argument("src", type=click.Path(exists=True, file_okay=True, resolve_path=True))
@click.argument("target", type=click.Path(exists=False))
@click.option("--keep-src", is_flag=True, default=False, help="keep source file")
@click.pass_context
def rename(ctx, src, target, keep_src):
    """Rename a file and update the project databases"""
    logging.debug(f"rename started with options {lib.json.dumps(ctx.params)}")
    src = lib.FWTPath(src)
    target = lib.FWTPath(target, exists=False)

    if src.is_project and target.is_project:
        same_project = src.as_rpd() == target.as_rpd()
        if not same_project and not keep_src:
            ctx.fail(
                "file rename with src and target being different projects."
                f" different projects are only supported with --keep-src"
            )

    if src.is_project_dir():
        fm = lib.FWTFileManager(src.to_fpd())
        fm.rename_world(target, keep_src)
    else:
        if src.is_project:
            fm = lib.FWTFileManager(src.to_fpd())
        elif target.is_project:
            fm = lib.FWTFileManager(target.to_fpd())
        else:
            ctx.fail("No project directory found!")
        src_fwtfile = fm.add_file(src)
        src_fwtfile.new_path = target
        if keep_src:
            src_fwtfile.keep_src = True
        fm.generate_rewrite_queue()
        fm.process_file_queue()
        fm.process_rewrite_queue()


@cli.command()
@click.pass_context
@click.argument("dir", type=click.Path(exists=True))
@click.option("--type", help="Database type. Currently supports actors and items")
@click.option("--asset-dir", help="Directory in the world root to store images")
def download(ctx, dir, type, asset_dir):
    """Download linked assets to the project directory"""
    logging.debug(f"download started with options {lib.json.dumps(ctx.params)}")
    if not type:
        ctx.fail("Missing required option --type")
    if not asset_dir:
        ctx.fail("Missing required option --asset-dir")
    project_dir = lib.FWTPath(dir, require_project=True)
    dbs = lib.FWTProjectDb(project_dir, driver=lib.FWTNeDB)
    downloader = lib.FWTAssetDownloader(project_dir)
    if type == "actors":
        for actor in dbs.data.actors:
            downloader.download_actor_images(actor, asset_dir)
        dbs.data.actors.save()
    elif type == "items":
        for item in dbs.data.items:
            downloader.download_item_images(item, asset_dir)
        dbs.data.items.save()
    else:
        ctx.fail("--type only allows 'actors' or 'items'")


@cli.command()
@click.pass_context
@click.option("--from", "_from", type=click.Path(exists=True))
@click.option("--to", type=click.Path(exists=True))
def pull(ctx, _from, to):
    logging.debug(f"pull command started with options {lib.json.dumps(ctx.params)}")
    """Pull assets from external projects"""
    if not _from:
        ctx.fail("Missing required option --from")
    if not to:
        ctx.fail("Missing required option --to")
    fm = lib.FWTFileManager(to)
    fm.find_remote_assets(_from)
    fm.generate_rewrite_queue()
    fm.process_file_queue()
    fm.process_rewrite_queue()


@cli.command()
@click.pass_context
@click.argument("dir", type=click.Path(exists=True))
def info(ctx, dir):
    logging.debug(f"info command started with options {lib.json.dumps(ctx.params)}")
    project = lib.FWTPath(dir)
    o = []
    o.append(f"Project: {'yes' if project.is_project else 'no'}")
    if project.is_project:
        o.append(f"Project Name: {project.project_name}")
        o.append(f"Project Type: {project.project_type}")
    click.echo("\n".join(o))
