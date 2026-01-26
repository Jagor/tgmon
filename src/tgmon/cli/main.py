"""Main CLI entry point."""

import asyncio
import typer

from ..core.config import get_config
from ..core.database import Database

app = typer.Typer(
    name="tgmon",
    help="Telegram chat monitoring CLI tool",
    no_args_is_help=True,
)


@app.command()
def init() -> None:
    """Initialize tgmon in current directory."""
    config = get_config()

    if config.is_initialized():
        typer.echo("tgmon is already initialized.")
        raise typer.Exit(1)

    config.ensure_dirs()

    async def _init_db() -> None:
        async with Database(config.db_path) as db:
            await db.init_schema()

    asyncio.run(_init_db())
    typer.echo(f"Initialized tgmon in {config.base_path}")


def require_init() -> None:
    """Check that tgmon is initialized."""
    config = get_config()
    if not config.is_initialized():
        typer.echo("tgmon is not initialized. Run 'tgmon init' first.")
        raise typer.Exit(1)


# Import and register subcommands
from . import account, aggregator, watch, run

app.add_typer(account.app, name="account", help="Manage Telegram accounts")
app.add_typer(aggregator.app, name="aggregator", help="Configure aggregator chat")
app.add_typer(watch.app, name="watch", help="Manage watched chats")
app.command(name="run")(run.run_account)
app.command(name="run-all")(run.run_all)


if __name__ == "__main__":
    app()
