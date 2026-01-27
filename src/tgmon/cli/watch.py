"""Watch list management commands."""

import asyncio
import typer
from typing import Annotated

from ..core.config import get_config
from ..core.database import Database
from ..core.models import Watch

app = typer.Typer(no_args_is_help=True)


def _require_init() -> None:
    from .main import require_init
    require_init()


@app.command("add")
def add(
    account: Annotated[str, typer.Argument(help="Account name")],
    chat_ref: Annotated[str, typer.Option("--chat", help="Chat reference (@username or chat_id)")],
) -> None:
    """Add a chat to watch list."""
    _require_init()
    config = get_config()

    async def _add() -> int:
        async with Database(config.db_path) as db:
            acc = await db.get_account(account)
            if not acc:
                typer.echo(f"Account '{account}' not found.")
                raise typer.Exit(1)

            existing = await db.find_watch(account, chat_ref)
            if existing:
                typer.echo(f"Chat '{chat_ref}' is already in watch list for '{account}'.")
                raise typer.Exit(1)

            watch = Watch(account_name=account, chat_ref=chat_ref)
            return await db.add_watch(watch)

    watch_id = asyncio.run(_add())
    typer.echo(f"Added watch #{watch_id}: '{chat_ref}' for account '{account}'.")


@app.command("remove")
def remove(
    account: Annotated[str, typer.Argument(help="Account name")],
    watch_id: Annotated[int, typer.Argument(help="Watch ID")],
) -> None:
    """Remove a chat from watch list."""
    _require_init()
    config = get_config()

    async def _remove() -> None:
        async with Database(config.db_path) as db:
            watch = await db.get_watch(watch_id)
            if not watch or watch.account_name != account:
                typer.echo(f"Watch #{watch_id} not found for account '{account}'.")
                raise typer.Exit(1)
            await db.remove_watch(watch_id)

    asyncio.run(_remove())
    typer.echo(f"Watch #{watch_id} removed.")


@app.command("list")
def list_watches(
    account: Annotated[str, typer.Argument(help="Account name")],
) -> None:
    """List watched chats for an account."""
    _require_init()
    config = get_config()

    async def _list() -> list[Watch]:
        async with Database(config.db_path) as db:
            acc = await db.get_account(account)
            if not acc:
                typer.echo(f"Account '{account}' not found.")
                raise typer.Exit(1)
            return await db.list_watches(account)

    watches = asyncio.run(_list())

    if not watches:
        typer.echo(f"No watches configured for account '{account}'.")
        return

    for w in watches:
        status = "enabled" if w.enabled else "disabled"
        if w.chat_id:
            typer.echo(f"  #{w.id}: {w.chat_ref} ({w.chat_id}) [{status}]")
        else:
            typer.echo(f"  #{w.id}: {w.chat_ref} [{status}]")


@app.command("enable")
def enable(
    account: Annotated[str, typer.Argument(help="Account name")],
    watch_id: Annotated[int, typer.Argument(help="Watch ID")],
) -> None:
    """Enable a watch."""
    _require_init()
    config = get_config()

    async def _enable() -> None:
        async with Database(config.db_path) as db:
            watch = await db.get_watch(watch_id)
            if not watch or watch.account_name != account:
                typer.echo(f"Watch #{watch_id} not found for account '{account}'.")
                raise typer.Exit(1)
            await db.update_watch(watch_id, enabled=True)

    asyncio.run(_enable())
    typer.echo(f"Watch #{watch_id} enabled.")


@app.command("disable")
def disable(
    account: Annotated[str, typer.Argument(help="Account name")],
    watch_id: Annotated[int, typer.Argument(help="Watch ID")],
) -> None:
    """Disable a watch."""
    _require_init()
    config = get_config()

    async def _disable() -> None:
        async with Database(config.db_path) as db:
            watch = await db.get_watch(watch_id)
            if not watch or watch.account_name != account:
                typer.echo(f"Watch #{watch_id} not found for account '{account}'.")
                raise typer.Exit(1)
            await db.update_watch(watch_id, enabled=False)

    asyncio.run(_disable())
    typer.echo(f"Watch #{watch_id} disabled.")
