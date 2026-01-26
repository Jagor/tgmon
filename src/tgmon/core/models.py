"""Pydantic models for tgmon."""

from pydantic import BaseModel


class Account(BaseModel):
    """Telegram account."""

    name: str
    api_id: int
    api_hash: str
    phone: str | None = None
    enabled: bool = True
    session_file: str | None = None


class Aggregator(BaseModel):
    """Aggregator chat configuration."""

    chat_ref: str
    account_name: str


class Watch(BaseModel):
    """Watched chat configuration."""

    id: int | None = None
    account_name: str
    chat_ref: str
    chat_id: int | None = None
    enabled: bool = True
