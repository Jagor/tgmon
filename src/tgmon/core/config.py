"""Application configuration and paths."""

from pathlib import Path
from typing import Self


class Config:
    """Application configuration."""

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or Path.cwd() / ".tgmon"

    @property
    def sessions_path(self) -> Path:
        """Path to sessions directory."""
        return self.base_path / "sessions"

    @property
    def db_path(self) -> Path:
        """Path to SQLite database."""
        return self.base_path / "tgmon.db"

    def ensure_dirs(self) -> None:
        """Create necessary directories."""
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.sessions_path.mkdir(parents=True, exist_ok=True)

    def session_file(self, account_name: str) -> Path:
        """Get session file path for account."""
        return self.sessions_path / f"{account_name}.session"

    def is_initialized(self) -> bool:
        """Check if tgmon is initialized."""
        return self.db_path.exists()


_config: Config | None = None


def get_config() -> Config:
    """Get global config instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def set_config(config: Config) -> None:
    """Set global config instance."""
    global _config
    _config = config
