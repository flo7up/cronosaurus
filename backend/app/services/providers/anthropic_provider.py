"""
Anthropic provider — uses Microsoft Agent Framework with AnthropicClient.

Wraps our tool dispatchers as AF @tool functions for automatic function calling.
Manages conversation history via AF sessions.
"""

import asyncio
import json
import logging
import queue
import threading
from typing import Any, Generator

from agent_framework import tool as af_tool
from agent_framework.anthropic import AnthropicClient

from app.config import settings
from app.services.message_store import message_store

logger = logging.getLogger(__name__)


def _store_message(thread_id: str, role: str, content: str, images: list[dict] | None = None):
    message_store.store_message(thread_id, role, content, images=images)


def get_messages(thread_id: str) -> list[dict]:
    return message_store.get_messages(thread_id)


def _create_af_tool_wrapper(
    tool_name: str,
    tool_def: dict,
    execute_tool_fn,
    agent_id_ref: list,
    thread_id_ref: list,
    model_ref: list,
    event_queue: queue.Queue,
    trigger_tool_names: set,
):
    """Create a Python function that wraps our tool dispatcher and
    is compatible with AF's @tool decorator."""

    params = tool_def.get("parameters", {}).get("properties", {})
    required = tool_def.get("parameters", {}).get("required", [])

    def wrapper(**kwargs) -> str:
        event_queue.put(json.dumps({
            "type": "tool_call", "content": "",
            "data": {"name": tool_name, "arguments": kwargs},
        }))

        result = execute_tool_fn(
            tool_name, json.dumps(kwargs),
            agent_id_ref[0], thread_id_ref[0], model_ref[0],
        )

        if tool_name in trigger_tool_names:
            event_queue.put(json.dumps({"type": "trigger_update", "data": result}))

        event_queue.put(json.dumps({
            "type": "tool_result", "content": "",
            "data": {"name": tool_name, "result": result},
        }))

        # Strip large image data before returning to the model
        from app.services.agent_service import strip_image_from_result
        img_dict = strip_image_from_result(result, thread_id_ref[0])
        if img_dict:
            event_queue.put(json.dumps({"type": "image", "content": "", "data": img_dict}))

        return json.dumps(result)

    wrapper.__name__ = tool_name
    wrapper.__qualname__ = tool_name
    wrapper.__doc__ = tool_def.get("description", "")

    from typing import Annotated
    from pydantic import Field
    annotations: dict[str, Any] = {}
    for pname, pdef in params.items():
        ptype = str
        if pdef.get("type") == "integer":
            ptype = int
        elif pdef.get("type") == "number":
            ptype = float
        elif pdef.get("type") == "boolean":
            ptype = bool
        elif pdef.get("type") == "array":
            ptype = list

        desc = pdef.get("description", pname)
        if pname in required:
            annotations[pname] = Annotated[ptype, Field(description=desc)]
        else:
            annotations[pname] = Annotated[ptype | None, Field(default=None, description=desc)]

    annotations["return"] = str
    wrapper.__annotations__ = annotations

    return af_tool(approval_mode="never_require")(wrapper)


def stream_response(
    *,
    thread_id: str,
    agent_id: str,
    model: str,
    content: str,
    instructions: str,
    tool_defs: list[dict],
    execute_tool_fn,
    trigger_tool_names: set,
    images: list[dict] | None = None,
) -> Generator[str, None, None]:
    """Stream a response using Agent Framework's AnthropicClient."""
    api_key = settings.anthropic_api_key
    if not api_key:
        yield json.dumps({"type": "error", "content": "Anthropic API key not configured. Set it in Settings."})
        return

    model_name = model or settings.anthropic_model
    event_q: queue.Queue = queue.Queue()

    agent_id_ref = [agent_id]
    thread_id_ref = [thread_id]
    model_ref = [model]

    af_tools = []
    for td in tool_defs:
        try:
            wrapped = _create_af_tool_wrapper(
                td["name"], td, execute_tool_fn,
                agent_id_ref, thread_id_ref, model_ref,
                event_q, trigger_tool_names,
            )
            af_tools.append(wrapped)
        except Exception as e:
            logger.warning("Failed to create AF tool wrapper for %s: %s", td["name"], e)

    # Store user message (with images if any)
    user_images = [{"data": img["data"], "media_type": img["media_type"]} for img in images] if images else None
    _store_message(thread_id, "user", content, images=user_images)

    # Merge any cached tool images (e.g. from a previous Twitch capture)
    from app.services.agent_service import pop_tool_images
    cached_imgs = pop_tool_images(thread_id)
    if cached_imgs:
        if images is None:
            images = []
        images.extend(cached_imgs)

    # Build prompt with conversation history
    history_messages = get_messages(thread_id)
    if len(history_messages) > 1:
        history_context = ""
        for msg in history_messages[:-1]:
            history_context += f"\n{msg['role'].upper()}: {msg['content']}"
        prompt = f"Previous conversation:{history_context}\n\nUSER: {content}"
    else:
        prompt = content

    # Build prompt — multimodal if images attached
    if images:
        import base64
        from agent_framework._types import Content
        prompt_parts = [Content.from_text(prompt)]
        for img in images:
            img_bytes = base64.b64decode(img["data"])
            prompt_parts.append(Content.from_data(img_bytes, img["media_type"]))
        run_input = prompt_parts
    else:
        run_input = prompt

    full_response = ""
    error_msg = ""

    async def _run_agent():
        nonlocal full_response, error_msg
        try:
            client = AnthropicClient(api_key=api_key, model_id=model_name)
            agent = client.as_agent(
                name="Cronosaurus-Agent",
                instructions=instructions,
                tools=af_tools if af_tools else None,
            )

            async for chunk in agent.run(run_input, stream=True):
                if chunk.text:
                    full_response += chunk.text
                    event_q.put(json.dumps({"type": "delta", "content": chunk.text}))
        except Exception as e:
            logger.error("AF Anthropic agent error: %s", e, exc_info=True)
            error_msg = str(e)
        finally:
            event_q.put(None)

    def _thread_target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_run_agent())
        finally:
            loop.close()

    t = threading.Thread(target=_thread_target, daemon=True)
    t.start()

    while True:
        try:
            event = event_q.get(timeout=120)
        except queue.Empty:
            yield json.dumps({"type": "error", "content": "Response timed out"})
            break
        if event is None:
            break
        yield event

    if error_msg:
        yield json.dumps({"type": "error", "content": f"Anthropic error: {error_msg}"})

    # Store assistant response (with any tool-generated images)
    if full_response:
        from app.services.agent_service import pop_tool_images
        assistant_images = pop_tool_images(thread_id) or None
        _store_message(thread_id, "assistant", full_response, images=assistant_images)

    yield json.dumps({"type": "done", "content": full_response})
