"""Flask web application factory."""

import os
from flask import Flask, render_template, redirect, url_for, flash, request

from ..core.config import get_config
from ..core.database import Database
from .async_bridge import run_async
from .monitor_manager import get_monitor_manager


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.urandom(24)

    from .routes import accounts, watches, aggregator, monitors

    app.register_blueprint(accounts.bp)
    app.register_blueprint(watches.bp)
    app.register_blueprint(aggregator.bp)
    app.register_blueprint(monitors.bp)

    @app.route("/")
    def index():
        config = get_config()

        if not config.is_initialized():
            return render_template(
                "index.html",
                initialized=False,
                accounts_count=0,
                watches_count=0,
                aggregator=None,
                monitor_running=False,
            )

        async def _get_stats():
            async with Database(config.db_path) as db:
                accounts = await db.list_accounts()
                total_watches = 0
                for acc in accounts:
                    watches = await db.list_watches(acc.name)
                    total_watches += len(watches)
                aggregator = await db.get_aggregator()
                return len(accounts), total_watches, aggregator

        accounts_count, watches_count, aggregator = run_async(_get_stats())
        manager = get_monitor_manager()

        return render_template(
            "index.html",
            initialized=True,
            accounts_count=accounts_count,
            watches_count=watches_count,
            aggregator=aggregator,
            monitor_running=manager.is_running(),
        )

    @app.route("/init", methods=["POST"])
    def init():
        """Initialize tgmon."""
        config = get_config()

        if config.is_initialized():
            flash("tgmon is already initialized.", "info")
            return redirect(url_for("index"))

        config.ensure_dirs()

        async def _init_db():
            async with Database(config.db_path) as db:
                await db.init_schema()

        run_async(_init_db())
        flash(f"tgmon initialized in {config.base_path}", "success")
        return redirect(url_for("index"))

    return app
