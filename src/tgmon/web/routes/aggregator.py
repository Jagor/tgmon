"""Aggregator configuration routes."""

from flask import Blueprint, render_template, request, redirect, url_for, flash

from ...core.config import get_config
from ...core.database import Database
from ...core.models import Aggregator
from ...telegram.client import TelegramClient
from ...telegram.formatter import Formatter
from ..async_bridge import run_async

bp = Blueprint("aggregator", __name__, url_prefix="/aggregator")


def _require_init() -> bool:
    """Check if tgmon is initialized."""
    config = get_config()
    return config.is_initialized()


@bp.route("/")
def show():
    """Show aggregator configuration."""
    if not _require_init():
        flash("tgmon is not initialized. Run 'tgmon init' first.", "error")
        return render_template("aggregator.html", aggregator=None, accounts=[])

    config = get_config()

    async def _get_data():
        async with Database(config.db_path) as db:
            aggregator = await db.get_aggregator()
            accounts = await db.list_accounts()
            return aggregator, accounts

    aggregator, accounts = run_async(_get_data())
    return render_template("aggregator.html", aggregator=aggregator, accounts=accounts)


@bp.route("/set", methods=["POST"])
def set_aggregator():
    """Set aggregator configuration."""
    if not _require_init():
        flash("tgmon is not initialized.", "error")
        return redirect(url_for("aggregator.show"))

    chat_ref = request.form.get("chat_ref", "").strip()
    account_name = request.form.get("account", "").strip()

    if not all([chat_ref, account_name]):
        flash("All fields are required.", "error")
        return redirect(url_for("aggregator.show"))

    config = get_config()

    async def _set():
        async with Database(config.db_path) as db:
            account = await db.get_account(account_name)
            if not account:
                return False, "Account not found.", None

            # Resolve chat to get ID and title
            chat_id = None
            chat_title = None
            try:
                client = TelegramClient(account)
                await client.connect()
                try:
                    if await client.is_authorized():
                        entity = await client.get_entity(chat_ref)
                        chat_id = entity.id
                        formatter = Formatter()
                        chat_title = formatter.get_chat_name(entity)
                finally:
                    await client.disconnect()
            except Exception:
                pass

            aggregator = Aggregator(
                chat_ref=chat_ref,
                account_name=account_name,
                chat_id=chat_id,
                chat_title=chat_title,
            )
            await db.set_aggregator(aggregator)
            return True, None, chat_title

    success, error, chat_title = run_async(_set())
    if success:
        display_name = chat_title or chat_ref
        flash(f"Aggregator set to '{display_name}' via '{account_name}'.", "success")
    else:
        flash(error, "error")

    return redirect(url_for("aggregator.show"))


@bp.route("/remove", methods=["POST"])
def remove_aggregator():
    """Remove aggregator configuration."""
    if not _require_init():
        flash("tgmon is not initialized.", "error")
        return redirect(url_for("aggregator.show"))

    config = get_config()

    async def _remove():
        async with Database(config.db_path) as db:
            await db.remove_aggregator()

    run_async(_remove())
    flash("Aggregator configuration removed.", "success")

    return redirect(url_for("aggregator.show"))
