"""
Background trigger scheduler (v2).

Runs an asyncio loop that ticks every TICK_SECONDS, checks Cosmos DB agent
documents for due triggers, and fires them by sending the trigger prompt to
the agent's Foundry thread via agent_service.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

TICK_SECONDS = 60  # check every minute


class TriggerScheduler:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="trigger")

    async def start(self):
        """Start the scheduler loop. Safe to call multiple times."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Trigger scheduler started (tick every %ds)", TICK_SECONDS)

    async def stop(self):
        """Gracefully stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._executor.shutdown(wait=False)
        logger.info("Trigger scheduler stopped")

    async def _loop(self):
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Scheduler tick error: %s", e, exc_info=True)
            await asyncio.sleep(TICK_SECONDS)

    async def _tick(self):
        """Single scheduler tick: find due agents and fire their triggers."""
        from app.services.agent_store import agent_store
        from app.services.agent_service import agent_service

        if not agent_store.is_ready or not agent_service.is_ready:
            logger.warning("Scheduler tick skipped: agent_store.is_ready=%s agent_service.is_ready=%s",
                           agent_store.is_ready, agent_service.is_ready)
            return

        due_agents = agent_store.get_due_agents()
        logger.info("Scheduler tick: %d due agent(s) found", len(due_agents))
        if not due_agents:
            return

        logger.info("Scheduler: %d due agent(s)", len(due_agents))
        loop = asyncio.get_running_loop()

        tasks = [
            loop.run_in_executor(self._executor, self._fire_trigger_sync, agent_doc)
            for agent_doc in due_agents
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for agent_doc, result in zip(due_agents, results):
            if isinstance(result, Exception):
                logger.error(
                    "Failed to fire trigger for agent %s: %s",
                    agent_doc.get("id"),
                    result,
                    exc_info=True,
                )

    @staticmethod
    def _fire_trigger_sync(agent_doc: dict):
        """Execute a trigger (runs in a thread pool)."""
        from app.services.agent_store import agent_store
        from app.services.agent_service import agent_service

        agent_id = agent_doc["id"]
        foundry_agent_id = agent_doc.get("foundry_agent_id", "")
        thread_id = agent_doc.get("thread_id", "")
        provider = (agent_doc.get("provider") or agent_service.provider or "azure_foundry").strip().lower()
        model = agent_doc.get("model", "gpt-4.1-mini")
        trigger = agent_doc["trigger"]
        prompt = trigger["prompt"]
        description = trigger.get("description", "")

        logger.info(
            "Firing trigger for agent %s (%s): %s",
            agent_id,
            agent_doc.get("name", ""),
            description,
        )

        if not thread_id or (provider == "azure_foundry" and not foundry_agent_id):
            logger.warning(
                "Agent %s missing foundry_agent_id or thread_id — skipping trigger.",
                agent_id,
            )
            return

        # Run the agent non-streaming (no one is watching)
        # NOTE: Do NOT prefix with [Scheduled trigger: ...] — that phrasing
        # causes some models to treat it as an "automated/unsolicited" request
        # and refuse.  The system instructions already tell the agent that
        # trigger prompts are user-approved.
        prefixed_prompt = prompt
        logger.info(
            "Agent %s: sending trigger prompt (%d chars) to thread %s via foundry agent %s",
            agent_id, len(prefixed_prompt), thread_id, foundry_agent_id,
        )
        agent_service.mark_trigger_run_start(agent_id)
        try:
            result = agent_service.run_non_streaming(
                agent_id=agent_id,
                foundry_agent_id=foundry_agent_id,
                thread_id=thread_id,
                model=model,
                content=prefixed_prompt,
                tools=agent_doc.get("tools", []),
                provider=provider,
                custom_instructions=agent_doc.get("custom_instructions", ""),
            )

            # Update trigger metadata in Cosmos
            agent_store.update_trigger_after_run(agent_id)

            logger.info(
                "Agent %s trigger complete: %d chars response, first 200 chars: %s",
                agent_id,
                len(result) if result else 0,
                (result[:200] if result else "(empty)"),
            )
        finally:
            agent_service.mark_trigger_run_end(agent_id)


trigger_scheduler = TriggerScheduler()
