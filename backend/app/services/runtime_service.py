"""Helpers for reloading runtime services after settings changes."""

import asyncio
import logging

logger = logging.getLogger(__name__)

_reload_lock = asyncio.Lock()


async def reload_runtime_services() -> None:
    """Rebuild settings-dependent services without requiring a process restart."""
    from app.services.agent_service import agent_service
    from app.services.agent_store import agent_store
    from app.services.gmail_push_service import gmail_push_service
    from app.services.notification_service import notification_service
    from app.services.trigger_scheduler import trigger_scheduler
    from app.services.user_service import user_service

    services = [
        ("user_service", user_service),
        ("agent_store", agent_store),
        ("agent_service", agent_service),
        ("notification_service", notification_service),
    ]

    async with _reload_lock:
        for _, service in services:
            reset = getattr(service, "reset", None)
            if callable(reset):
                reset()

        loop = asyncio.get_running_loop()
        for name, service in services:
            try:
                await loop.run_in_executor(None, service.initialize)
                logger.info("Runtime reload: %s initialized", name)
            except Exception as exc:
                logger.warning("Runtime reload: %s unavailable: %s", name, exc)

        if agent_store.is_ready and agent_service.is_ready:
            await trigger_scheduler.start()
            await gmail_push_service.start()