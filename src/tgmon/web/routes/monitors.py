"""Monitor control routes."""

from flask import Blueprint, render_template, Response, jsonify

from ...core.config import get_config
from ...core.database import Database
from ..async_bridge import run_async
from ..monitor_manager import get_monitor_manager

bp = Blueprint("monitors", __name__, url_prefix="/monitors")


@bp.route("/")
def index():
    """Monitor control page."""
    manager = get_monitor_manager()
    config = get_config()

    if not config.is_initialized():
        return render_template(
            "monitors.html",
            is_running=False,
            enabled_accounts=0,
            total_watches=0,
            aggregator=None,
            ready=False,
        )

    async def _get_stats():
        async with Database(config.db_path) as db:
            accounts = await db.list_accounts()
            enabled_accounts = [a for a in accounts if a.enabled]
            total_watches = 0
            for acc in enabled_accounts:
                watches = await db.list_enabled_watches(acc.name)
                total_watches += len(watches)
            aggregator = await db.get_aggregator()
            return len(enabled_accounts), total_watches, aggregator

    enabled_accounts, total_watches, aggregator = run_async(_get_stats())
    ready = enabled_accounts > 0 and total_watches > 0 and aggregator is not None

    return render_template(
        "monitors.html",
        is_running=manager.is_running(),
        enabled_accounts=enabled_accounts,
        total_watches=total_watches,
        aggregator=aggregator,
        ready=ready,
    )


@bp.route("/start", methods=["POST"])
def start():
    """Start monitors."""
    manager = get_monitor_manager()
    if manager.start():
        return jsonify({"status": "started"})
    else:
        return jsonify({"status": "already_running"}), 400


@bp.route("/stop", methods=["POST"])
def stop():
    """Stop monitors."""
    manager = get_monitor_manager()
    if manager.stop():
        return jsonify({"status": "stopped"})
    else:
        return jsonify({"status": "not_running"}), 400


@bp.route("/status")
def status():
    """Get monitor status."""
    manager = get_monitor_manager()
    config = get_config()

    ready = False
    if config.is_initialized():
        async def _check_ready():
            async with Database(config.db_path) as db:
                accounts = await db.list_accounts()
                enabled_accounts = [a for a in accounts if a.enabled]
                if not enabled_accounts:
                    return False
                total_watches = 0
                for acc in enabled_accounts:
                    watches = await db.list_enabled_watches(acc.name)
                    total_watches += len(watches)
                if total_watches == 0:
                    return False
                aggregator = await db.get_aggregator()
                return aggregator is not None

        ready = run_async(_check_ready())

    return jsonify({"running": manager.is_running(), "ready": ready})


@bp.route("/logs")
def logs():
    """SSE endpoint for real-time logs."""
    manager = get_monitor_manager()

    def generate():
        for log in manager.get_logs():
            if log:
                yield f"event: log\ndata: {log}\n\n"
            else:
                yield f"event: ping\ndata: \n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
