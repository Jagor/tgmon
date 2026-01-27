"""Watch list management routes."""

from flask import Blueprint, render_template, request, redirect, url_for, flash

from ...core.config import get_config
from ...core.database import Database
from ...core.models import Watch
from ...telegram.client import TelegramClient
from ...telegram.formatter import Formatter
from ..async_bridge import run_async
from ..monitor_manager import get_monitor_manager

bp = Blueprint("watches", __name__, url_prefix="/watches")


def _restart_if_running() -> None:
    """Restart monitor if it's running to apply watch changes."""
    manager = get_monitor_manager()
    if manager.is_running():
        manager.restart()


def _require_init() -> bool:
    """Check if tgmon is initialized."""
    config = get_config()
    return config.is_initialized()


@bp.route("/")
def list_watches():
    """List all watches grouped by account."""
    if not _require_init():
        flash("tgmon is not initialized. Run 'tgmon init' first.", "error")
        return render_template("watches/list.html", accounts_watches={})

    config = get_config()

    async def _list():
        async with Database(config.db_path) as db:
            accounts = await db.list_accounts()
            result = {}
            for acc in accounts:
                watches = await db.list_watches(acc.name)
                result[acc.name] = watches
            return result, accounts

    accounts_watches, accounts = run_async(_list())
    return render_template("watches/list.html", accounts_watches=accounts_watches, accounts=accounts)


@bp.route("/add", methods=["GET", "POST"])
def add_watch():
    """Add a new watch."""
    if not _require_init():
        flash("tgmon is not initialized. Run 'tgmon init' first.", "error")
        return redirect(url_for("watches.list_watches"))

    config = get_config()

    async def _get_accounts():
        async with Database(config.db_path) as db:
            return await db.list_accounts()

    accounts = run_async(_get_accounts())

    if request.method == "POST":
        import json

        account_name = request.form.get("account", "").strip()
        chat_ref = request.form.get("chat_ref", "").strip()
        chat_refs_json = request.form.get("chat_refs", "").strip()

        # Collect all chat refs to add
        chat_refs_to_add = []
        if chat_ref:
            chat_refs_to_add.append(chat_ref)
        if chat_refs_json:
            try:
                selected = json.loads(chat_refs_json)
                chat_refs_to_add.extend(str(ref) for ref in selected)
            except json.JSONDecodeError:
                pass

        if not account_name:
            flash("Account is required.", "error")
            return render_template("watches/add.html", accounts=accounts)

        if not chat_refs_to_add:
            flash("Select at least one chat.", "error")
            return render_template("watches/add.html", accounts=accounts)

        async def _add_multiple():
            async with Database(config.db_path) as db:
                acc = await db.get_account(account_name)
                if not acc:
                    return False, "Account not found.", 0, 0

                # Connect to resolve chats
                client = None
                formatter = Formatter()
                try:
                    client = TelegramClient(acc)
                    await client.connect()
                    is_authorized = await client.is_authorized()
                except Exception:
                    is_authorized = False

                added = 0
                skipped = 0

                for ref in chat_refs_to_add:
                    existing = await db.find_watch(account_name, ref)
                    if existing:
                        skipped += 1
                        continue

                    # Resolve chat
                    chat_id = None
                    chat_title = None
                    if client and is_authorized:
                        try:
                            entity = await client.get_entity(ref)
                            chat_id = entity.id
                            chat_title = formatter.get_chat_name(entity)
                        except Exception:
                            pass

                    watch = Watch(
                        account_name=account_name,
                        chat_ref=ref,
                        chat_id=chat_id,
                        chat_title=chat_title,
                    )
                    await db.add_watch(watch)
                    added += 1

                if client:
                    await client.disconnect()

                return True, None, added, skipped

        success, error, added, skipped = run_async(_add_multiple())

        if success:
            if added > 0:
                flash(f"Added {added} watch(es).", "success")
                _restart_if_running()
            if skipped > 0:
                flash(f"Skipped {skipped} (already exist).", "info")
            return redirect(url_for("watches.list_watches"))
        else:
            flash(error, "error")
            return render_template("watches/add.html", accounts=accounts)

    return render_template("watches/add.html", accounts=accounts)


@bp.route("/<int:watch_id>/enable", methods=["POST"])
def enable(watch_id: int):
    """Enable a watch."""
    config = get_config()

    async def _enable():
        async with Database(config.db_path) as db:
            watch = await db.get_watch(watch_id)
            if not watch:
                return False
            await db.update_watch(watch_id, enabled=True)
            return True

    if run_async(_enable()):
        flash(f"Watch #{watch_id} enabled.", "success")
        _restart_if_running()
    else:
        flash(f"Watch #{watch_id} not found.", "error")

    return redirect(url_for("watches.list_watches"))


@bp.route("/<int:watch_id>/disable", methods=["POST"])
def disable(watch_id: int):
    """Disable a watch."""
    config = get_config()

    async def _disable():
        async with Database(config.db_path) as db:
            watch = await db.get_watch(watch_id)
            if not watch:
                return False
            await db.update_watch(watch_id, enabled=False)
            return True

    if run_async(_disable()):
        flash(f"Watch #{watch_id} disabled.", "success")
        _restart_if_running()
    else:
        flash(f"Watch #{watch_id} not found.", "error")

    return redirect(url_for("watches.list_watches"))


@bp.route("/<int:watch_id>/delete", methods=["POST"])
def delete(watch_id: int):
    """Delete a watch."""
    config = get_config()

    async def _delete():
        async with Database(config.db_path) as db:
            watch = await db.get_watch(watch_id)
            if not watch:
                return False, False
            was_enabled = watch.enabled
            await db.remove_watch(watch_id)
            return True, was_enabled

    success, was_enabled = run_async(_delete())
    if success:
        flash(f"Watch #{watch_id} deleted.", "success")
        if was_enabled:
            _restart_if_running()
    else:
        flash(f"Watch #{watch_id} not found.", "error")

    return redirect(url_for("watches.list_watches"))


@bp.route("/account/<account_name>/enable-all", methods=["POST"])
def enable_all(account_name: str):
    """Enable all watches for an account."""
    config = get_config()

    async def _enable_all():
        async with Database(config.db_path) as db:
            watches = await db.list_watches(account_name)
            for watch in watches:
                await db.update_watch(watch.id, enabled=True)
            return len(watches)

    count = run_async(_enable_all())
    flash(f"Enabled {count} watch(es) for '{account_name}'.", "success")
    if count > 0:
        _restart_if_running()
    return redirect(url_for("watches.list_watches"))


@bp.route("/account/<account_name>/disable-all", methods=["POST"])
def disable_all(account_name: str):
    """Disable all watches for an account."""
    config = get_config()

    async def _disable_all():
        async with Database(config.db_path) as db:
            watches = await db.list_watches(account_name)
            for watch in watches:
                await db.update_watch(watch.id, enabled=False)
            return len(watches)

    count = run_async(_disable_all())
    flash(f"Disabled {count} watch(es) for '{account_name}'.", "success")
    if count > 0:
        _restart_if_running()
    return redirect(url_for("watches.list_watches"))


@bp.route("/<int:watch_id>/edit", methods=["GET", "POST"])
def edit(watch_id: int):
    """Edit a watch."""
    if not _require_init():
        flash("tgmon is not initialized.", "error")
        return redirect(url_for("watches.list_watches"))

    config = get_config()

    async def _get_watch():
        async with Database(config.db_path) as db:
            return await db.get_watch(watch_id)

    watch = run_async(_get_watch())
    if not watch:
        flash(f"Watch #{watch_id} not found.", "error")
        return redirect(url_for("watches.list_watches"))

    if request.method == "POST":
        chat_ref = request.form.get("chat_ref", "").strip()

        if not chat_ref:
            flash("Chat reference is required.", "error")
            return render_template("watches/edit.html", watch=watch)

        async def _update():
            async with Database(config.db_path) as db:
                # Check for duplicates
                existing = await db.find_watch(watch.account_name, chat_ref)
                if existing and existing.id != watch_id:
                    return False, "Watch already exists for this chat."

                await db.update_watch(watch_id, chat_ref=chat_ref, chat_id=None, chat_title=None)
                return True, None

        success, error = run_async(_update())
        if success:
            flash(f"Watch #{watch_id} updated.", "success")
            return redirect(url_for("watches.list_watches"))
        else:
            flash(error, "error")
            return render_template("watches/edit.html", watch=watch)

    return render_template("watches/edit.html", watch=watch)
