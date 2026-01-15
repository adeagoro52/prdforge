"""PRDForge CLI - Command-line interface for PRD-driven AI code generation.

Usage:
    prdforge serve     Start the web dashboard server
    prdforge init      Initialize a project configuration
    prdforge version   Show version information
    prdforge run       Execute a PRD file
"""

import json
import sys
from pathlib import Path
from typing import Optional

import click

# Version info
__version__ = "0.1.0"


# Custom Click context for shared options
class Context:
    """Shared context for CLI commands."""

    def __init__(self):
        self.config_path: Optional[Path] = None
        self.verbose: bool = False


pass_context = click.make_pass_decorator(Context, ensure=True)


@click.group()
@click.option(
    "-c", "--config",
    type=click.Path(exists=False),
    help="Path to config file (default: prdforge.yaml in current directory)",
)
@click.option(
    "-v", "--verbose",
    is_flag=True,
    help="Enable verbose output",
)
@click.version_option(__version__, prog_name="PRDForge")
@pass_context
def cli(ctx: Context, config: Optional[str], verbose: bool):
    """PRDForge - PRD-driven AI code generation platform.

    Where PRDs are forged into code.
    """
    ctx.config_path = Path(config) if config else None
    ctx.verbose = verbose


@cli.command()
@click.option(
    "-h", "--host",
    default="127.0.0.1",
    help="Host to bind to (default: 127.0.0.1)",
)
@click.option(
    "-p", "--port",
    default=8000,
    type=int,
    help="Port to bind to (default: 8000)",
)
@click.option(
    "--reload",
    is_flag=True,
    help="Enable auto-reload for development",
)
@pass_context
def serve(ctx: Context, host: str, port: int, reload: bool):
    """Start the PRDForge web dashboard server.

    The server provides a web interface for managing projects,
    viewing runs, and controlling PRD execution.
    """
    click.echo(f"Starting PRDForge server on http://{host}:{port}")

    if ctx.config_path:
        click.echo(f"Using config: {ctx.config_path}")

    # TODO: Phase 2 - Implement actual server
    click.echo("")
    click.echo(click.style("Server not yet implemented.", fg="yellow"))
    click.echo("The web dashboard will be available in Phase 2.")
    click.echo("See docs/prds/prd_prdforge_standalone_project.json for details.")


@cli.command()
@click.option(
    "-n", "--name",
    help="Project name (default: directory name)",
)
@click.option(
    "-p", "--path",
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    default=".",
    help="Project directory path (default: current directory)",
)
@click.option(
    "-f", "--format",
    type=click.Choice(["yaml", "json"]),
    default="yaml",
    help="Config file format (default: yaml)",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing config file",
)
@pass_context
def init(ctx: Context, name: Optional[str], path: str, format: str, force: bool):
    """Initialize a PRDForge project configuration.

    Creates a prdforge.yaml (or .json) file in the specified directory
    with default configuration values.
    """
    from src.config import PRDForgeConfig, ProjectConfig
    from src.config.loader import write_config_file
    from src.config.models import ProjectType

    project_path = Path(path).resolve()

    # Determine output file path
    ext = "yaml" if format == "yaml" else "json"
    output_path = project_path / f"prdforge.{ext}"

    if output_path.exists() and not force:
        click.echo(
            click.style(f"Config file already exists: {output_path}", fg="red")
        )
        click.echo("Use --force to overwrite.")
        sys.exit(1)

    # Create default configuration
    project_name = name or project_path.name
    project_config = ProjectConfig(
        name=project_name,
        path=str(project_path),
        project_type=ProjectType.LOCAL,
    )
    config = PRDForgeConfig(projects=[project_config])

    # Write config file
    try:
        write_config_file(config, output_path, format=format)
        click.echo(click.style(f"Created: {output_path}", fg="green"))
        click.echo("")
        click.echo("Next steps:")
        click.echo("  1. Edit the config file to customize settings")
        click.echo("  2. Create a PRD file in docs/prds/")
        click.echo("  3. Run: prdforge run <prd-file>")
    except Exception as e:
        click.echo(click.style(f"Error creating config: {e}", fg="red"))
        sys.exit(1)


@cli.command()
def version():
    """Show PRDForge version and system information."""
    import platform

    click.echo(f"PRDForge v{__version__}")
    click.echo("")
    click.echo("System Information:")
    click.echo(f"  Python: {platform.python_version()}")
    click.echo(f"  Platform: {platform.system()} {platform.release()}")
    click.echo(f"  Architecture: {platform.machine()}")


@cli.command()
@click.argument("prd_file", type=click.Path(exists=True))
@click.option(
    "-b", "--base-branch",
    default="develop",
    help="Base branch for the run (default: develop)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Simulate execution without making changes",
)
@click.option(
    "--skip-completed",
    is_flag=True,
    default=True,
    help="Skip tasks already marked as completed (default: true)",
)
@click.option(
    "-e", "--executor",
    type=click.Choice(["claude-cli", "dry-run"]),
    default="claude-cli",
    help="Executor to use (default: claude-cli)",
)
@pass_context
def run(
    ctx: Context,
    prd_file: str,
    base_branch: str,
    dry_run: bool,
    skip_completed: bool,
    executor: str,
):
    """Execute a PRD file.

    Runs through all tasks in the PRD file, executing each one
    using the configured AI executor.
    """
    from src.prd import parse_prd

    prd_path = Path(prd_file).resolve()

    click.echo(f"Loading PRD: {prd_path}")

    try:
        prd = parse_prd(prd_path)
    except Exception as e:
        click.echo(click.style(f"Error loading PRD: {e}", fg="red"))
        sys.exit(1)

    click.echo(f"Feature: {prd.meta.feature_name}")
    click.echo(f"Total tasks: {prd.total_tasks}")
    click.echo(f"Completed: {prd.completed_count}")
    click.echo(f"Progress: {prd.progress_percent:.1f}%")
    click.echo("")

    pending = prd.get_pending_tasks()
    if not pending:
        click.echo(click.style("All tasks completed!", fg="green"))
        return

    executable = prd.get_executable_tasks()
    click.echo(f"Pending tasks: {len(pending)}")
    click.echo(f"Executable now: {len(executable)}")

    if dry_run:
        click.echo("")
        click.echo(click.style("DRY RUN - No changes will be made", fg="yellow"))

    click.echo("")
    click.echo("Next executable tasks:")
    for task in executable[:5]:
        click.echo(f"  • {task.id}: {task.description[:60]}...")

    # TODO: Implement actual execution
    click.echo("")
    click.echo(click.style("Full execution not yet implemented.", fg="yellow"))
    click.echo("Use the RunManager API directly for now.")


@cli.command("list-prds")
@click.option(
    "-p", "--path",
    type=click.Path(exists=True, file_okay=False),
    default=".",
    help="Directory to search for PRDs",
)
@pass_context
def list_prds(ctx: Context, path: str):
    """List PRD files in a directory."""
    from src.prd import PRDFormatDetector, parse_prd

    search_path = Path(path).resolve()
    extensions = PRDFormatDetector.list_extensions()

    click.echo(f"Searching for PRDs in: {search_path}")
    click.echo("")

    found = []
    for ext in extensions:
        found.extend(search_path.rglob(f"*{ext}"))

    if not found:
        click.echo("No PRD files found.")
        return

    for prd_path in sorted(found):
        try:
            prd = parse_prd(prd_path)
            progress = f"{prd.progress_percent:.0f}%"
            rel_path = prd_path.relative_to(search_path)
            click.echo(f"  [{progress:>3}] {rel_path}")
            click.echo(f"        {prd.meta.feature_name}")
        except Exception:
            rel_path = prd_path.relative_to(search_path)
            click.echo(f"  [ERR] {rel_path}")


@cli.command("db-init")
@click.option(
    "--path",
    type=click.Path(),
    default="~/.prdforge/prdforge.db",
    help="Database path",
)
@pass_context
def db_init(ctx: Context, path: str):
    """Initialize the PRDForge database."""
    from src.db import Database

    db_path = Path(path).expanduser()
    click.echo(f"Initializing database at: {db_path}")

    try:
        db = Database(db_path)
        db.initialize()
        click.echo(click.style("Database initialized successfully.", fg="green"))
        click.echo(f"Schema version: {db.get_schema_version()}")
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"))
        sys.exit(1)


def main():
    """Entry point for PRDForge CLI."""
    cli()


if __name__ == "__main__":
    main()
