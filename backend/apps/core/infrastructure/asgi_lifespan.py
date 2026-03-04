"""Module for asgi lifespan."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)


Hook = Callable[[], Awaitable[None]]


class LifespanApp:
    def __init__(self, *, on_startup: Hook | None = None, on_shutdown: Hook | None = None) -> None:
        self._on_startup = on_startup
        self._on_shutdown = on_shutdown

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        while True:
            message = await receive()
            msg_type = message.get("type")
            if msg_type == "lifespan.startup":
                try:
                    if self._on_startup:
                        await self._on_startup()
                except Exception as e:
                    logger.exception("操作失败")
                    await send({"type": "lifespan.startup.failed", "message": str(e)})
                    return
                await send({"type": "lifespan.startup.complete"})
                continue
            if msg_type == "lifespan.shutdown":
                try:
                    if self._on_shutdown:
                        await self._on_shutdown()
                except Exception as e:
                    logger.exception("操作失败")
                    await send({"type": "lifespan.shutdown.failed", "message": str(e)})
                    return
                await send({"type": "lifespan.shutdown.complete"})
                return
