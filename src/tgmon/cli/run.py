"""Run monitoring commands."""

import asyncio
import signal
import typer
from typing import Annotated

from ..core.config import get_config
from ..core.database import Database
from ..core.models import Account
from ..telegram.client import TelegramClient
from ..telegram.monitor import Monitor


def _require_init() -> None:
    from .main import require_init
    require_init()


def run_account(
    account: Annotated[str, typer.Argument(help="Account name")],
) -> None:
    """Run monitoring for a single account."""
    _require_init()
    config = get_config()

    async def _run() -> None:
        # Load all data first, then close db connection
        async with Database(config.db_path) as db:
            acc = await db.get_account(account)
            if not acc:
                typer.echo(f"Account '{account}' not found.")
                raise typer.Exit(1)

            if not acc.enabled:
                typer.echo(f"Account '{account}' is disabled.")
                raise typer.Exit(1)

            aggregator = await db.get_aggregator()
            if not aggregator:
                typer.echo("Aggregator not configured. Use 'tgmon aggregator set'.")
                raise typer.Exit(1)

            watches = await db.list_enabled_watches(account)
            if not watches:
                typer.echo(f"No enabled watches for account '{account}'.")
                raise typer.Exit(1)

            # Get aggregator account
            agg_account = await db.get_account(aggregator.account_name)
            if not agg_account:
                typer.echo(f"Aggregator account '{aggregator.account_name}' not found.")
                raise typer.Exit(1)

        # DB connection closed here

        # Create shared aggregator client
        agg_client = TelegramClient(agg_account)
        await agg_client.connect()

        if not await agg_client.is_authorized():
            typer.echo(f"Aggregator account '{agg_account.name}' is not authorized.")
            await agg_client.disconnect()
            raise typer.Exit(1)

        monitor = Monitor(
            account=acc,
            aggregator=aggregator,
            watches=watches,
            agg_client=agg_client,
        )

        stop_event = asyncio.Event()

        def handle_signal() -> None:
            typer.echo("\nStopping...")
            stop_event.set()

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, handle_signal)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                pass

        typer.echo(f"Starting monitor for account '{account}'...")
        typer.echo(f"Watching {len(watches)} chat(s), forwarding to {aggregator.chat_ref}")
        typer.echo("Press Ctrl+C to stop.\n")

        try:
            await monitor.start()
            # Update resolved chat info in database (brief connection)
            async with Database(config.db_path) as db:
                for watch_id, (chat_id, chat_title) in monitor.get_resolved_chats().items():
                    await db.update_watch(watch_id, chat_id=chat_id, chat_title=chat_title)
                agg_resolved = monitor.get_resolved_aggregator()
                if agg_resolved:
                    await db.update_aggregator(chat_id=agg_resolved[0], chat_title=agg_resolved[1])
            await stop_event.wait()
        except KeyboardInterrupt:
            pass
        finally:
            await monitor.stop()
            await agg_client.disconnect()

    asyncio.run(_run())


def run_all() -> None:
    """Run monitoring for all enabled accounts."""
    _require_init()
    config = get_config()

    async def _run_all() -> None:
        # Load all data first, then close db connection
        async with Database(config.db_path) as db:
            accounts = await db.list_accounts()
            enabled = [a for a in accounts if a.enabled]

            if not enabled:
                typer.echo("No enabled accounts.")
                raise typer.Exit(1)

            aggregator = await db.get_aggregator()
            if not aggregator:
                typer.echo("Aggregator not configured. Use 'tgmon aggregator set'.")
                raise typer.Exit(1)

            agg_account = await db.get_account(aggregator.account_name)
            if not agg_account:
                typer.echo(f"Aggregator account '{aggregator.account_name}' not found.")
                raise typer.Exit(1)

            watches_data: list[tuple[Account, list]] = []
            for acc in enabled:
                watches = await db.list_enabled_watches(acc.name)
                if watches:
                    watches_data.append((acc, watches))
                    typer.echo(f"Account '{acc.name}': {len(watches)} watch(es)")

            if not watches_data:
                typer.echo("No watches configured for any enabled account.")
                raise typer.Exit(1)

        # DB connection closed here

        # Create shared aggregator client
        agg_client = TelegramClient(agg_account)
        await agg_client.connect()

        if not await agg_client.is_authorized():
            typer.echo(f"Aggregator account '{agg_account.name}' is not authorized.")
            await agg_client.disconnect()
            raise typer.Exit(1)

        # Create monitors with shared agg_client
        monitors: list[Monitor] = []
        for acc, watches in watches_data:
            monitor = Monitor(
                account=acc,
                aggregator=aggregator,
                watches=watches,
                agg_client=agg_client,
            )
            monitors.append(monitor)

        stop_event = asyncio.Event()

        def handle_signal() -> None:
            typer.echo("\nStopping all monitors...")
            stop_event.set()

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, handle_signal)
            except NotImplementedError:
                pass

        typer.echo(f"\nStarting {len(monitors)} monitor(s)...")
        typer.echo(f"Forwarding to {aggregator.chat_ref}")
        typer.echo("Press Ctrl+C to stop.\n")

        try:
            await asyncio.gather(*[m.start() for m in monitors])
            # Update resolved chat info in database (brief connection)
            async with Database(config.db_path) as db:
                agg_updated = False
                for monitor in monitors:
                    for watch_id, (chat_id, chat_title) in monitor.get_resolved_chats().items():
                        await db.update_watch(watch_id, chat_id=chat_id, chat_title=chat_title)
                    if not agg_updated:
                        agg_resolved = monitor.get_resolved_aggregator()
                        if agg_resolved:
                            await db.update_aggregator(chat_id=agg_resolved[0], chat_title=agg_resolved[1])
                            agg_updated = True
            await stop_event.wait()
        except KeyboardInterrupt:
            pass
        finally:
            await asyncio.gather(*[m.stop() for m in monitors])
            await agg_client.disconnect()

    asyncio.run(_run_all())
