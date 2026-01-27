"""Async-to-sync utilities for Flask routes."""

import asyncio
from typing import Coroutine, TypeVar

T = TypeVar("T")


def run_async(coro: Coroutine[None, None, T]) -> T:
    """Run async coroutine from sync context."""
    return asyncio.run(coro)
