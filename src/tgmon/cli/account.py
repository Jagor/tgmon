"""Account management commands."""

import asyncio
import typer
from typing import Annotated

from ..core.config import get_config
from ..core.database import Database
from ..core.models import Account
from ..telegram.client import TelegramClient

app = typer.Typer(no_args_is_help=True)


def _require_init() -> None:
    from .main import require_init
    require_init()


@app.command("add")
def add(
    name: Annotated[str, typer.Argument(help="Account name")],
    api_id: Annotated[int, typer.Option("--api-id", help="Telegram API ID")],
    api_hash: Annotated[str, typer.Option("--api-hash", help="Telegram API hash")],
) -> None:
    """Add a new Telegram account."""
    _require_init()
    config = get_config()

    async def _add() -> None:
        async with Database(config.db_path) as db:
            existing = await db.get_account(name)
            if existing:
                typer.echo(f"Account '{name}' already exists.")
                raise typer.Exit(1)

            session_file = str(config.session_file(name))
            account = Account(
                name=name,
                api_id=api_id,
                api_hash=api_hash,
                session_file=session_file,
            )
            await db.add_account(account)

    asyncio.run(_add())
    typer.echo(f"Account '{name}' added. Use 'tgmon account login {name}' to authorize.")


@app.command("login")
def login(
    name: Annotated[str, typer.Argument(help="Account name")],
) -> None:
    """Authorize account interactively."""
    _require_init()
    config = get_config()

    async def _login() -> None:
        async with Database(config.db_path) as db:
            account = await db.get_account(name)
            if not account:
                typer.echo(f"Account '{name}' not found.")
                raise typer.Exit(1)

            client = TelegramClient(account)
            await client.connect()

            if await client.is_authorized():
                typer.echo(f"Account '{name}' is already authorized.")
                await client.disconnect()
                return

            phone = typer.prompt("Enter phone number")
            await db.update_account(name, phone=phone)

            await client.send_code(phone)
            code = typer.prompt("Enter the code you received")

            try:
                await client.sign_in(phone, code)
            except Exception as e:
                if "password" in str(e).lower() or "2fa" in str(e).lower():
                    password = typer.prompt("Enter 2FA password", hide_input=True)
                    await client.sign_in_password(password)
                else:
                    raise

            typer.echo(f"Account '{name}' authorized successfully.")
            await client.disconnect()

    asyncio.run(_login())


@app.command("list")
def list_accounts() -> None:
    """List all accounts."""
    _require_init()
    config = get_config()

    async def _list() -> list[Account]:
        async with Database(config.db_path) as db:
            return await db.list_accounts()

    accounts = asyncio.run(_list())

    if not accounts:
        typer.echo("No accounts configured.")
        return

    for acc in accounts:
        status = "enabled" if acc.enabled else "disabled"
        typer.echo(f"  {acc.name} ({status}) - API ID: {acc.api_id}")


@app.command("enable")
def enable(
    name: Annotated[str, typer.Argument(help="Account name")],
) -> None:
    """Enable an account."""
    _require_init()
    config = get_config()

    async def _enable() -> None:
        async with Database(config.db_path) as db:
            account = await db.get_account(name)
            if not account:
                typer.echo(f"Account '{name}' not found.")
                raise typer.Exit(1)
            await db.update_account(name, enabled=True)

    asyncio.run(_enable())
    typer.echo(f"Account '{name}' enabled.")


@app.command("disable")
def disable(
    name: Annotated[str, typer.Argument(help="Account name")],
) -> None:
    """Disable an account."""
    _require_init()
    config = get_config()

    async def _disable() -> None:
        async with Database(config.db_path) as db:
            account = await db.get_account(name)
            if not account:
                typer.echo(f"Account '{name}' not found.")
                raise typer.Exit(1)
            await db.update_account(name, enabled=False)

    asyncio.run(_disable())
    typer.echo(f"Account '{name}' disabled.")


@app.command("remove")
def remove(
    name: Annotated[str, typer.Argument(help="Account name")],
    keep_session: Annotated[bool, typer.Option("--keep-session", help="Keep session file")] = False,
) -> None:
    """Remove an account."""
    _require_init()
    config = get_config()

    async def _remove() -> str | None:
        async with Database(config.db_path) as db:
            account = await db.get_account(name)
            if not account:
                typer.echo(f"Account '{name}' not found.")
                raise typer.Exit(1)
            session_file = account.session_file
            await db.remove_account(name)
            return session_file

    session_file = asyncio.run(_remove())

    if not keep_session and session_file:
        from pathlib import Path
        session_path = Path(session_file)
        if session_path.exists():
            session_path.unlink()

    typer.echo(f"Account '{name}' removed.")


@app.command("dialogs")
def dialogs(
    name: Annotated[str, typer.Argument(help="Account name")],
    users: Annotated[bool, typer.Option("--users", "-u", help="Show private chats instead of groups/channels")] = False,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Limit number of results")] = 50,
) -> None:
    """List dialogs with their IDs. Shows groups/channels by default."""
    _require_init()
    config = get_config()

    async def _dialogs() -> None:
        async with Database(config.db_path) as db:
            account = await db.get_account(name)
            if not account:
                typer.echo(f"Account '{name}' not found.")
                raise typer.Exit(1)

            client = TelegramClient(account)
            await client.connect()

            if not await client.is_authorized():
                typer.echo(f"Account '{name}' is not authorized. Run 'tgmon account login {name}' first.")
                await client.disconnect()
                raise typer.Exit(1)

            if users:
                typer.echo("Private chats:")
            else:
                typer.echo("Groups and channels:")

            typer.echo(f"{'ID':<20} {'Type':<10} Name")
            typer.echo("-" * 60)

            count = 0
            async for dialog in client.iter_dialogs():
                if users:
                    if not dialog.is_user:
                        continue
                else:
                    if dialog.is_user:
                        continue

                chat_id = dialog.id
                title = dialog.title or dialog.name or "Unknown"

                if dialog.is_user:
                    chat_type = "user"
                elif dialog.is_group:
                    chat_type = "group"
                elif dialog.is_channel:
                    chat_type = "channel"
                else:
                    chat_type = "other"

                typer.echo(f"{chat_id:<20} {chat_type:<10} {title}")

                count += 1
                if count >= limit:
                    typer.echo(f"\n... (showing first {limit}, use --limit to see more)")
                    break

            await client.disconnect()

    asyncio.run(_dialogs())
