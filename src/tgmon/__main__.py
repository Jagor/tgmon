"""Allow running tgmon as a module: python -m tgmon"""

from .cli.main import app

if __name__ == "__main__":
    app()
