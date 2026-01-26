"""Aggregator configuration commands."""

import asyncio
import typer
from typing import Annotated

from ..core.config import get_config
from ..core.database import Database
from ..core.models import Aggregator

app = typer.Typer(no_args_is_help=True)


def _require_init() -> None:
    from .main import require_init
    require_init()


@app.command("set")
def set_aggregator(
    chat_ref: Annotated[str, typer.Option("--chat", help="Chat reference (@username or chat_id)")],
    via: Annotated[str, typer.Option("--via", help="Account to use for sending")],
) -> None:
    """Set aggregator chat."""
    _require_init()
    config = get_config()

    async def _set() -> None:
        async with Database(config.db_path) as db:
            account = await db.get_account(via)
            if not account:
                typer.echo(f"Account '{via}' not found.")
                raise typer.Exit(1)

            aggregator = Aggregator(chat_ref=chat_ref, account_name=via)
            await db.set_aggregator(aggregator)

    asyncio.run(_set())
    typer.echo(f"Aggregator set to '{chat_ref}' via account '{via}'.")


@app.command("show")
def show() -> None:
    """Show current aggregator configuration."""
    _require_init()
    config = get_config()

    async def _show() -> Aggregator | None:
        async with Database(config.db_path) as db:
            return await db.get_aggregator()

    aggregator = asyncio.run(_show())

    if not aggregator:
        typer.echo("No aggregator configured.")
        return

    typer.echo(f"Aggregator: {aggregator.chat_ref}")
    typer.echo(f"Via account: {aggregator.account_name}")
