"""Cooperative cancellation primitive shared with external adapters."""

from __future__ import annotations

import asyncio


class CancellationToken:
    """One-way cancellation signal that can cross application-service boundaries."""

    def __init__(self) -> None:
        self._event = asyncio.Event()

    @property
    def is_cancelled(self) -> bool:
        """Return whether cancellation has been requested."""

        return self._event.is_set()

    def cancel(self) -> None:
        """Request cooperative cancellation; repeated calls are harmless."""

        self._event.set()

    async def wait(self) -> None:
        """Wait until cancellation is requested."""

        await self._event.wait()

    def raise_if_cancelled(self) -> None:
        """Raise the asyncio cancellation signal when cancellation was requested."""

        if self.is_cancelled:
            raise asyncio.CancelledError

