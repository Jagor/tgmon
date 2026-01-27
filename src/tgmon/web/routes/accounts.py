"""Account management routes."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify

from ...core.config import get_config
from ...core.database import Database
from ...core.models import Account
from ...telegram.client import TelegramClient
from ..async_bridge import run_async

bp = Blueprint("accounts", __name__, url_prefix="/accounts")

# Store login state between requests
_login_state: dict[str, dict] = {}


def _require_init() -> bool:
    """Check if tgmon is initialized."""
    config = get_config()
    return config.is_initialized()


@bp.route("/")
def list_accounts():
    """List all accounts."""
    if not _require_init():
        flash("tgmon is not initialized. Run 'tgmon init' first.", "error")
        return render_template("accounts/list.html", accounts=[], auth_status={})

    config = get_config()

    async def _list():
        async with Database(config.db_path) as db:
            return await db.list_accounts()

    accounts = run_async(_list())

    # Check authorization status for each account
    auth_status = {}
    for account in accounts:
        async def _check_auth(acc):
            try:
                client = TelegramClient(acc)
                await client.connect()
                authorized = await client.is_authorized()
                await client.disconnect()
                return authorized
            except Exception:
                return None  # Unknown/error

        auth_status[account.name] = run_async(_check_auth(account))

    return render_template("accounts/list.html", accounts=accounts, auth_status=auth_status)


@bp.route("/add", methods=["GET", "POST"])
def add_account():
    """Add a new account."""
    if not _require_init():
        flash("tgmon is not initialized. Run 'tgmon init' first.", "error")
        return redirect(url_for("accounts.list_accounts"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        api_id = request.form.get("api_id", "").strip()
        api_hash = request.form.get("api_hash", "").strip()

        if not all([name, api_id, api_hash]):
            flash("All fields are required.", "error")
            return render_template("accounts/add.html")

        try:
            api_id_int = int(api_id)
        except ValueError:
            flash("API ID must be a number.", "error")
            return render_template("accounts/add.html")

        config = get_config()

        async def _add():
            async with Database(config.db_path) as db:
                existing = await db.get_account(name)
                if existing:
                    return False, "Account already exists."

                session_file = str(config.session_file(name))
                account = Account(
                    name=name,
                    api_id=api_id_int,
                    api_hash=api_hash,
                    session_file=session_file,
                )
                await db.add_account(account)
                return True, None

        success, error = run_async(_add())
        if success:
            flash(f"Account '{name}' added.", "success")
            return redirect(url_for("accounts.login", name=name))
        else:
            flash(error, "error")
            return render_template("accounts/add.html")

    return render_template("accounts/add.html")


@bp.route("/<name>/login", methods=["GET", "POST"])
def login(name: str):
    """Login to account."""
    if not _require_init():
        flash("tgmon is not initialized.", "error")
        return redirect(url_for("accounts.list_accounts"))

    config = get_config()

    async def _get_account():
        async with Database(config.db_path) as db:
            return await db.get_account(name)

    account = run_async(_get_account())
    if not account:
        flash(f"Account '{name}' not found.", "error")
        return redirect(url_for("accounts.list_accounts"))

    state = _login_state.get(name, {"step": "phone"})

    if request.method == "POST":
        action = request.form.get("action")

        if action == "send_code":
            phone = request.form.get("phone", "").strip()
            if not phone:
                flash("Phone number is required.", "error")
                return render_template("accounts/login.html", account=account, state=state)

            async def _send_code():
                async with Database(config.db_path) as db:
                    await db.update_account(name, phone=phone)

                client = TelegramClient(account)
                await client.connect()

                try:
                    if await client.is_authorized():
                        return True, "already_authorized", None

                    phone_code_hash = await client.send_code(phone)
                    return True, "code_sent", phone_code_hash
                finally:
                    await client.disconnect()

            try:
                success, result, phone_code_hash = run_async(_send_code())
                if result == "already_authorized":
                    flash("Account is already authorized.", "success")
                    if name in _login_state:
                        del _login_state[name]
                    return redirect(url_for("accounts.list_accounts"))

                _login_state[name] = {"step": "code", "phone": phone, "phone_code_hash": phone_code_hash}
                flash("Code sent. Enter the code you received.", "success")
            except Exception as e:
                flash(f"Failed to send code: {e}", "error")

        elif action == "verify_code":
            code = request.form.get("code", "").strip()
            phone = state.get("phone", "")
            phone_code_hash = state.get("phone_code_hash", "")

            if not code:
                flash("Code is required.", "error")
                return render_template("accounts/login.html", account=account, state=state)

            async def _verify_code():
                client = TelegramClient(account)
                await client.connect()

                try:
                    await client.sign_in(phone, code, phone_code_hash)
                    return True, None
                except Exception as e:
                    error_msg = str(e).lower()
                    if "password" in error_msg or "2fa" in error_msg:
                        return False, "2fa_required"
                    return False, str(e)
                finally:
                    await client.disconnect()

            try:
                success, result = run_async(_verify_code())
                if success:
                    flash("Account authorized successfully.", "success")
                    if name in _login_state:
                        del _login_state[name]
                    return redirect(url_for("accounts.list_accounts"))
                elif result == "2fa_required":
                    _login_state[name] = {"step": "2fa", "phone": phone}
                    flash("2FA required. Enter your password.", "info")
                else:
                    flash(f"Failed to verify code: {result}", "error")
            except Exception as e:
                flash(f"Error: {e}", "error")

        elif action == "verify_2fa":
            password = request.form.get("password", "")

            if not password:
                flash("Password is required.", "error")
                return render_template("accounts/login.html", account=account, state=state)

            async def _verify_2fa():
                client = TelegramClient(account)
                await client.connect()

                try:
                    await client.sign_in_password(password)
                    return True, None
                except Exception as e:
                    return False, str(e)
                finally:
                    await client.disconnect()

            try:
                success, error = run_async(_verify_2fa())
                if success:
                    flash("Account authorized successfully.", "success")
                    if name in _login_state:
                        del _login_state[name]
                    return redirect(url_for("accounts.list_accounts"))
                else:
                    flash(f"Failed to verify password: {error}", "error")
            except Exception as e:
                flash(f"Error: {e}", "error")

    state = _login_state.get(name, {"step": "phone"})
    return render_template("accounts/login.html", account=account, state=state)


@bp.route("/<name>/enable", methods=["POST"])
def enable(name: str):
    """Enable an account."""
    config = get_config()

    async def _enable():
        async with Database(config.db_path) as db:
            account = await db.get_account(name)
            if not account:
                return False
            await db.update_account(name, enabled=True)
            return True

    if run_async(_enable()):
        flash(f"Account '{name}' enabled.", "success")
    else:
        flash(f"Account '{name}' not found.", "error")

    return redirect(url_for("accounts.list_accounts"))


@bp.route("/<name>/disable", methods=["POST"])
def disable(name: str):
    """Disable an account."""
    config = get_config()

    async def _disable():
        async with Database(config.db_path) as db:
            account = await db.get_account(name)
            if not account:
                return False
            await db.update_account(name, enabled=False)
            return True

    if run_async(_disable()):
        flash(f"Account '{name}' disabled.", "success")
    else:
        flash(f"Account '{name}' not found.", "error")

    return redirect(url_for("accounts.list_accounts"))


@bp.route("/<name>/delete", methods=["POST"])
def delete(name: str):
    """Delete an account."""
    config = get_config()

    async def _delete():
        async with Database(config.db_path) as db:
            account = await db.get_account(name)
            if not account:
                return False, None
            session_file = account.session_file
            await db.remove_account(name)
            return True, session_file

    success, session_file = run_async(_delete())
    if success:
        if session_file:
            from pathlib import Path
            session_path = Path(session_file)
            if session_path.exists():
                session_path.unlink()
        flash(f"Account '{name}' deleted.", "success")
    else:
        flash(f"Account '{name}' not found.", "error")

    return redirect(url_for("accounts.list_accounts"))


@bp.route("/<name>/dialogs")
def dialogs(name: str):
    """Get dialogs for an account (AJAX endpoint)."""
    config = get_config()
    show_users = request.args.get("users", "0") == "1"
    search = request.args.get("search", "").strip().lower()
    offset = int(request.args.get("offset", "0"))
    limit = int(request.args.get("limit", "50"))

    async def _get_dialogs():
        async with Database(config.db_path) as db:
            account = await db.get_account(name)
            if not account:
                return None, "Account not found", set()

            # Get existing watches for this account
            watches = await db.list_watches(name)
            existing_ids = {str(w.chat_id) for w in watches if w.chat_id}
            existing_refs = {w.chat_ref.lower() for w in watches}

        client = TelegramClient(account)
        await client.connect()

        try:
            if not await client.is_authorized():
                return None, "Account not authorized", set()

            all_dialogs = []
            async for dialog in client.iter_dialogs():
                if show_users:
                    if not dialog.is_user:
                        continue
                else:
                    if dialog.is_user:
                        continue

                chat_id = dialog.id
                title = dialog.title or dialog.name or "Unknown"

                # Apply search filter
                if search:
                    if search not in title.lower() and search not in str(chat_id):
                        continue

                if dialog.is_user:
                    chat_type = "user"
                elif dialog.is_group:
                    chat_type = "group"
                elif dialog.is_channel:
                    chat_type = "channel"
                else:
                    chat_type = "other"

                # Check if already added
                is_added = (
                    str(chat_id) in existing_ids or
                    title.lower() in existing_refs or
                    (hasattr(dialog.entity, 'username') and dialog.entity.username and
                     f"@{dialog.entity.username.lower()}" in existing_refs)
                )

                all_dialogs.append({
                    "id": chat_id,
                    "title": title,
                    "type": chat_type,
                    "added": is_added,
                })

            total = len(all_dialogs)
            paginated = all_dialogs[offset:offset + limit]

            return {"dialogs": paginated, "total": total, "offset": offset, "limit": limit}, None, existing_ids
        finally:
            await client.disconnect()

    result, error, _ = run_async(_get_dialogs())
    if error:
        return jsonify({"error": error}), 400

    return jsonify(result)
