"""
Delegation worker — background loop that processes pending delegation tasks.

Picks up pending delegations from the delegation_store, executes them
on the sub-agent's thread via agent_service.run_non_streaming(), and
stores the result summary back.

Runs alongside trigger_scheduler as a separate asyncio task.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

TICK_SECONDS = 5  # poll every 5 seconds for responsive delegation
MAX_RESULT_LENGTH = 2000  # truncate result summaries to prevent bloat


class DelegationWorker:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="delegation")

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Delegation worker started (tick every %ds)", TICK_SECONDS)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._executor.shutdown(wait=False)
        logger.info("Delegation worker stopped")

    async def _loop(self):
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Delegation worker tick error: %s", e, exc_info=True)
            await asyncio.sleep(TICK_SECONDS)

    async def _tick(self):
        from app.services.delegation_store import delegation_store

        if not delegation_store.is_ready:
            return

        pending = delegation_store.get_pending_delegations()
        if not pending:
            return

        # Sort by priority (high first)
        priority_order = {"high": 0, "normal": 1, "low": 2}
        pending.sort(key=lambda d: priority_order.get(d.get("priority", "normal"), 1))

        logger.info("Delegation worker: %d pending delegation(s)", len(pending))
        loop = asyncio.get_running_loop()

        # Process up to 4 concurrently
        batch = pending[:4]
        tasks = [
            loop.run_in_executor(self._executor, self._execute_delegation, doc)
            for doc in batch
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for doc, result in zip(batch, results):
            if isinstance(result, Exception):
                logger.error(
                    "Delegation %s failed: %s", doc.get("id"), result, exc_info=True,
                )

    @staticmethod
    def _execute_delegation(delegation: dict):
        """Execute a single delegation (runs in thread pool)."""
        from app.services.delegation_store import delegation_store
        from app.services.agent_store import agent_store
        from app.services.agent_service import agent_service

        delegation_id = delegation["id"]
        master_agent_id = delegation["master_agent_id"]
        sub_agent_id = delegation["sub_agent_id"]
        task = delegation["task"]

        # Mark as running
        delegation_store.mark_running(delegation_id, master_agent_id)

        # Load sub-agent
        sub = agent_store.get_agent(sub_agent_id)
        if not sub:
            delegation_store.mark_failed(
                delegation_id, master_agent_id,
                f"Sub-agent {sub_agent_id} not found.",
            )
            return

        thread_id = sub.get("thread_id", "")
        foundry_agent_id = sub.get("foundry_agent_id", "")
        provider = (sub.get("provider") or "azure_foundry").strip().lower()
        model = sub.get("model", "gpt-4.1-mini")

        if not thread_id:
            delegation_store.mark_failed(
                delegation_id, master_agent_id,
                "Sub-agent has no active thread (send it a message first).",
            )
            return

        # Build the delegation prompt
        prompt = (
            f"[Delegated task from master agent]\n\n"
            f"{task}\n\n"
            f"Complete this task using your available tools. When done, provide a structured summary:\n"
            f"- **Objective**: What was asked\n"
            f"- **Findings**: Key data points and results\n"
            f"- **Confidence**: High / Medium / Low\n"
            f"- **Recommended Actions**: What should happen next"
        )

        logger.info(
            "Executing delegation %s: sub=%s (%s) task=%.80s",
            delegation_id, sub_agent_id, sub.get("name", ""), task,
        )

        try:
            result = agent_service.run_non_streaming(
                agent_id=sub_agent_id,
                foundry_agent_id=foundry_agent_id,
                thread_id=thread_id,
                model=model,
                content=prompt,
                tools=sub.get("tools", []),
                provider=provider,
                custom_instructions=sub.get("custom_instructions", ""),
            )

            # Truncate if too long
            summary = result or "(no response)"
            if len(summary) > MAX_RESULT_LENGTH:
                summary = summary[:MAX_RESULT_LENGTH] + "\n\n[...truncated]"

            delegation_store.mark_completed(delegation_id, master_agent_id, summary)
            logger.info(
                "Delegation %s completed: %d chars response",
                delegation_id, len(summary),
            )
        except Exception as e:
            error_msg = str(e)
            if len(error_msg) > 500:
                error_msg = error_msg[:500] + "..."
            delegation_store.mark_failed(delegation_id, master_agent_id, error_msg)
            logger.error("Delegation %s failed: %s", delegation_id, e, exc_info=True)


delegation_worker = DelegationWorker()
