"""Web server command."""

import typer
from typing import Annotated


def _require_init() -> None:
    from .main import require_init
    require_init()


def web(
    host: Annotated[str, typer.Option("--host", "-h", help="Host to bind to")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", "-p", help="Port to bind to")] = 5000,
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug mode")] = False,
) -> None:
    """Start the web interface."""
    _require_init()

    from ..web import create_app

    app = create_app()
    typer.echo(f"Starting web interface at http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)
