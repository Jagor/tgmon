"""SQLite database operations."""

import aiosqlite
from pathlib import Path

from .models import Account, Aggregator, Watch


SCHEMA = """
-- Accounts
CREATE TABLE IF NOT EXISTS accounts (
    name TEXT PRIMARY KEY,
    api_id INTEGER NOT NULL,
    api_hash TEXT NOT NULL,
    phone TEXT,
    enabled INTEGER DEFAULT 1,
    session_file TEXT
);

-- Aggregator (single row)
CREATE TABLE IF NOT EXISTS aggregator (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    chat_ref TEXT NOT NULL,
    account_name TEXT NOT NULL,
    chat_id INTEGER,
    chat_title TEXT,
    FOREIGN KEY (account_name) REFERENCES accounts(name)
);

-- Watched chats
CREATE TABLE IF NOT EXISTS watches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_name TEXT NOT NULL,
    chat_ref TEXT NOT NULL,
    chat_id INTEGER,
    chat_title TEXT,
    enabled INTEGER DEFAULT 1,
    FOREIGN KEY (account_name) REFERENCES accounts(name),
    UNIQUE(account_name, chat_ref)
);
"""


class Database:
    """SQLite database manager."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Connect to database."""
        self._conn = await aiosqlite.connect(self.db_path, timeout=30.0)
        self._conn.row_factory = aiosqlite.Row
        # Enable WAL mode for better concurrency
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA busy_timeout=30000")
        # Run migrations on connect
        await self._migrate()

    async def close(self) -> None:
        """Close database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def __aenter__(self) -> "Database":
        await self.connect()
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def init_schema(self) -> None:
        """Initialize database schema."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()
        # Run migrations
        await self._migrate()

    async def _migrate(self) -> None:
        """Run database migrations."""
        if not self._conn:
            return

        # Add chat_title column to watches if it doesn't exist
        cursor = await self._conn.execute("PRAGMA table_info(watches)")
        columns = [row[1] for row in await cursor.fetchall()]
        if "chat_title" not in columns:
            await self._conn.execute("ALTER TABLE watches ADD COLUMN chat_title TEXT")

        # Add chat_id and chat_title columns to aggregator if they don't exist
        cursor = await self._conn.execute("PRAGMA table_info(aggregator)")
        columns = [row[1] for row in await cursor.fetchall()]
        if "chat_id" not in columns:
            await self._conn.execute("ALTER TABLE aggregator ADD COLUMN chat_id INTEGER")
        if "chat_title" not in columns:
            await self._conn.execute("ALTER TABLE aggregator ADD COLUMN chat_title TEXT")

        await self._conn.commit()

    # Account operations
    async def add_account(self, account: Account) -> None:
        """Add new account."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        await self._conn.execute(
            """INSERT INTO accounts (name, api_id, api_hash, phone, enabled, session_file)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                account.name,
                account.api_id,
                account.api_hash,
                account.phone,
                1 if account.enabled else 0,
                account.session_file,
            ),
        )
        await self._conn.commit()

    async def get_account(self, name: str) -> Account | None:
        """Get account by name."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        cursor = await self._conn.execute(
            "SELECT * FROM accounts WHERE name = ?", (name,)
        )
        row = await cursor.fetchone()
        if row:
            return Account(
                name=row["name"],
                api_id=row["api_id"],
                api_hash=row["api_hash"],
                phone=row["phone"],
                enabled=bool(row["enabled"]),
                session_file=row["session_file"],
            )
        return None

    async def list_accounts(self) -> list[Account]:
        """List all accounts."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        cursor = await self._conn.execute("SELECT * FROM accounts")
        rows = await cursor.fetchall()
        return [
            Account(
                name=row["name"],
                api_id=row["api_id"],
                api_hash=row["api_hash"],
                phone=row["phone"],
                enabled=bool(row["enabled"]),
                session_file=row["session_file"],
            )
            for row in rows
        ]

    async def update_account(self, name: str, **kwargs) -> None:
        """Update account fields."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        if not kwargs:
            return

        # Convert enabled to int if present
        if "enabled" in kwargs:
            kwargs["enabled"] = 1 if kwargs["enabled"] else 0

        fields = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [name]
        await self._conn.execute(
            f"UPDATE accounts SET {fields} WHERE name = ?", values
        )
        await self._conn.commit()

    async def remove_account(self, name: str) -> None:
        """Remove account."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        await self._conn.execute("DELETE FROM watches WHERE account_name = ?", (name,))
        await self._conn.execute("DELETE FROM aggregator WHERE account_name = ?", (name,))
        await self._conn.execute("DELETE FROM accounts WHERE name = ?", (name,))
        await self._conn.commit()

    # Aggregator operations
    async def set_aggregator(self, aggregator: Aggregator) -> None:
        """Set aggregator (upsert)."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        await self._conn.execute(
            """INSERT OR REPLACE INTO aggregator (id, chat_ref, account_name, chat_id, chat_title)
               VALUES (1, ?, ?, ?, ?)""",
            (aggregator.chat_ref, aggregator.account_name, aggregator.chat_id, aggregator.chat_title),
        )
        await self._conn.commit()

    async def update_aggregator(self, **kwargs) -> None:
        """Update aggregator fields."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        if not kwargs:
            return

        fields = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values())
        await self._conn.execute(
            f"UPDATE aggregator SET {fields} WHERE id = 1", values
        )
        await self._conn.commit()

    async def get_aggregator(self) -> Aggregator | None:
        """Get aggregator configuration."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        cursor = await self._conn.execute("SELECT * FROM aggregator WHERE id = 1")
        row = await cursor.fetchone()
        if row:
            return Aggregator(
                chat_ref=row["chat_ref"],
                account_name=row["account_name"],
                chat_id=row["chat_id"],
                chat_title=row["chat_title"],
            )
        return None

    async def remove_aggregator(self) -> None:
        """Remove aggregator configuration."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        await self._conn.execute("DELETE FROM aggregator WHERE id = 1")
        await self._conn.commit()

    # Watch operations
    async def add_watch(self, watch: Watch) -> int:
        """Add watched chat. Returns watch id."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        cursor = await self._conn.execute(
            """INSERT INTO watches (account_name, chat_ref, chat_id, chat_title, enabled)
               VALUES (?, ?, ?, ?, ?)""",
            (
                watch.account_name,
                watch.chat_ref,
                watch.chat_id,
                watch.chat_title,
                1 if watch.enabled else 0,
            ),
        )
        await self._conn.commit()
        return cursor.lastrowid or 0

    async def get_watch(self, watch_id: int) -> Watch | None:
        """Get watch by id."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        cursor = await self._conn.execute(
            "SELECT * FROM watches WHERE id = ?", (watch_id,)
        )
        row = await cursor.fetchone()
        if row:
            return Watch(
                id=row["id"],
                account_name=row["account_name"],
                chat_ref=row["chat_ref"],
                chat_id=row["chat_id"],
                chat_title=row["chat_title"],
                enabled=bool(row["enabled"]),
            )
        return None

    async def list_watches(self, account_name: str) -> list[Watch]:
        """List watches for account."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        cursor = await self._conn.execute(
            "SELECT * FROM watches WHERE account_name = ?", (account_name,)
        )
        rows = await cursor.fetchall()
        return [
            Watch(
                id=row["id"],
                account_name=row["account_name"],
                chat_ref=row["chat_ref"],
                chat_id=row["chat_id"],
                chat_title=row["chat_title"],
                enabled=bool(row["enabled"]),
            )
            for row in rows
        ]

    async def list_enabled_watches(self, account_name: str) -> list[Watch]:
        """List enabled watches for account."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        cursor = await self._conn.execute(
            "SELECT * FROM watches WHERE account_name = ? AND enabled = 1",
            (account_name,),
        )
        rows = await cursor.fetchall()
        return [
            Watch(
                id=row["id"],
                account_name=row["account_name"],
                chat_ref=row["chat_ref"],
                chat_id=row["chat_id"],
                chat_title=row["chat_title"],
                enabled=bool(row["enabled"]),
            )
            for row in rows
        ]

    async def update_watch(self, watch_id: int, **kwargs) -> None:
        """Update watch fields."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        if not kwargs:
            return

        if "enabled" in kwargs:
            kwargs["enabled"] = 1 if kwargs["enabled"] else 0

        fields = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [watch_id]
        await self._conn.execute(
            f"UPDATE watches SET {fields} WHERE id = ?", values
        )
        await self._conn.commit()

    async def remove_watch(self, watch_id: int) -> None:
        """Remove watch."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        await self._conn.execute("DELETE FROM watches WHERE id = ?", (watch_id,))
        await self._conn.commit()

    async def find_watch(self, account_name: str, chat_ref: str) -> Watch | None:
        """Find watch by account and chat_ref."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        cursor = await self._conn.execute(
            "SELECT * FROM watches WHERE account_name = ? AND chat_ref = ?",
            (account_name, chat_ref),
        )
        row = await cursor.fetchone()
        if row:
            return Watch(
                id=row["id"],
                account_name=row["account_name"],
                chat_ref=row["chat_ref"],
                chat_id=row["chat_id"],
                chat_title=row["chat_title"],
                enabled=bool(row["enabled"]),
            )
        return None
