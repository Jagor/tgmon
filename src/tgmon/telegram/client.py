"""Telethon client wrapper."""

from telethon import TelegramClient as TelethonClient
from telethon.sessions import StringSession
from telethon.tl.types import User, Chat, Channel

from ..core.models import Account


class TelegramClient:
    """Wrapper around Telethon client."""

    def __init__(self, account: Account) -> None:
        self.account = account
        self._client = TelethonClient(
            account.session_file or account.name,
            account.api_id,
            account.api_hash,
        )

    @property
    def client(self) -> TelethonClient:
        """Get underlying Telethon client."""
        return self._client

    async def connect(self) -> None:
        """Connect to Telegram."""
        await self._client.connect()

    async def disconnect(self) -> None:
        """Disconnect from Telegram."""
        await self._client.disconnect()

    async def is_authorized(self) -> bool:
        """Check if client is authorized."""
        return await self._client.is_user_authorized()

    async def send_code(self, phone: str) -> None:
        """Send authorization code."""
        await self._client.send_code_request(phone)

    async def sign_in(self, phone: str, code: str) -> None:
        """Sign in with code."""
        await self._client.sign_in(phone, code)

    async def sign_in_password(self, password: str) -> None:
        """Sign in with 2FA password."""
        await self._client.sign_in(password=password)

    async def get_entity(self, entity_ref: str | int):
        """Get entity by reference (username or ID)."""
        # Convert string to int if it looks like a numeric ID
        if isinstance(entity_ref, str):
            try:
                entity_ref = int(entity_ref)
            except ValueError:
                pass  # Keep as string (username)
        return await self._client.get_entity(entity_ref)

    async def get_me(self) -> User:
        """Get current user."""
        return await self._client.get_me()

    async def send_message(self, entity, message: str, **kwargs):
        """Send text message."""
        return await self._client.send_message(entity, message, **kwargs)

    async def send_file(self, entity, file, **kwargs):
        """Send file/media."""
        return await self._client.send_file(entity, file, **kwargs)

    async def download_media(self, message, file=None):
        """Download media from message."""
        return await self._client.download_media(message, file)

    def add_event_handler(self, callback, event):
        """Add event handler."""
        self._client.add_event_handler(callback, event)

    def remove_event_handler(self, callback, event):
        """Remove event handler."""
        self._client.remove_event_handler(callback, event)

    async def run_until_disconnected(self) -> None:
        """Run client until disconnected."""
        await self._client.run_until_disconnected()

    async def iter_dialogs(self):
        """Iterate over all dialogs."""
        async for dialog in self._client.iter_dialogs():
            yield dialog

    async def __aenter__(self) -> "TelegramClient":
        await self.connect()
        return self

    async def __aexit__(self, *args) -> None:
        await self.disconnect()
