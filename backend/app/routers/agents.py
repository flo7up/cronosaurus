"""
REST endpoints for multi-agent management.

Replaces the old chat.py and trigger.py routers with a unified
agent-centric API.
"""

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.agent import (
    AgentCreate,
    AgentUpdate,
    AgentTriggerCreate,
    AgentTriggerUpdate,
    SendAgentMessageRequest,
    InvokeAgentRequest,
    InvokeAgentResponse,
    AgentResponse,
    AgentTriggerResponse,
    MessageResponse,
)
from app.models.chat import AVAILABLE_MODELS
from app.services.agent_store import agent_store
from app.services.agent_service import agent_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


def _require_ready():
    if not agent_store.is_ready:
        raise HTTPException(503, "Agent store not initialized (Cosmos DB)")
    if not agent_service.is_ready:
        raise HTTPException(503, "Agent service not initialized (Foundry)")


def _agent_to_response(doc: dict) -> AgentResponse:
    """Convert a Cosmos document to an AgentResponse."""
    trigger = doc.get("trigger")
    trigger_resp = AgentTriggerResponse(**trigger) if trigger else None
    return AgentResponse(
        id=doc["id"],
        user_id=doc.get("user_id", "1"),
        name=doc["name"],
        model=doc["model"],
        tools=doc.get("tools", []),
        email_account_id=doc.get("email_account_id"),
        custom_instructions=doc.get("custom_instructions", ""),
        notification_group_id=doc.get("notification_group_id"),
        role=doc.get("role", "agent"),
        managed_by=doc.get("managed_by"),
        thread_id=doc.get("thread_id", ""),
        foundry_agent_id=doc.get("foundry_agent_id", ""),
        trigger=trigger_resp,
        created_at=doc.get("created_at", ""),
        updated_at=doc.get("updated_at", ""),
    )


# ── Status & models ─────────────────────────────────────────────

@router.get("/status")
def agents_status():
    return {
        "ready": agent_store.is_ready and agent_service.is_ready,
        "store_ready": agent_store.is_ready,
        "service_ready": agent_service.is_ready,
    }


@router.get("/models")
def list_models():
    return {"models": AVAILABLE_MODELS}


@router.get("/delegations/active-agents")
def active_delegation_agents():
    """Return agent IDs that have active (pending/running) delegations."""
    from app.services.delegation_store import delegation_store
    if not delegation_store.is_ready:
        return {"agent_ids": []}
    try:
        pending = delegation_store.get_pending_delegations()
        running = delegation_store.get_running_delegations()
        active = pending + running
        agent_ids = list({d["sub_agent_id"] for d in active})
        return {"agent_ids": agent_ids}
    except Exception:
        return {"agent_ids": []}


@router.get("/api-catalog")
def api_catalog():
    """List all agents with their API invoke endpoints."""
    _require_ready()
    docs = agent_store.list_agents()
    catalog = []
    for d in docs:
        catalog.append({
            "agent_id": d["id"],
            "name": d["name"],
            "model": d.get("model", ""),
            "tools": d.get("tools", []),
            "role": d.get("role", "agent"),
            "endpoint": f"/api/agents/{d['id']}/invoke",
            "method": "POST",
            "request_body": {
                "message": "string (required)",
                "images": "[{data: base64, media_type: string}] (optional)",
            },
        })
    return {"agents": catalog}


# ── Agent CRUD ───────────────────────────────────────────────────

@router.get("", response_model=list[AgentResponse])
def list_agents():
    _require_ready()
    docs = agent_store.list_agents()
    return [_agent_to_response(d) for d in docs]


@router.post("", response_model=AgentResponse, status_code=201)
def create_agent(body: AgentCreate = AgentCreate()):
    _require_ready()

    # Enforce single master agent
    if body.role == "master":
        existing = agent_store.list_agents()
        if any(a.get("role") == "master" for a in existing):
            raise HTTPException(409, "A master agent already exists. Only one master agent is allowed.")

    provider = agent_service.provider
    thread_id = ""

    if provider != "azure_foundry":
        # OpenAI / Anthropic — generate a pseudo thread_id for conversation keying
        import uuid
        thread_id = f"{provider}-{uuid.uuid4().hex[:12]}"

    # Auto-assign: if creating a regular agent, assign to existing master;
    # if creating a master, adopt all unassigned agents.
    managed_by = body.managed_by
    if body.role != "master" and not managed_by:
        existing = agent_store.list_agents()
        masters = [a for a in existing if a.get("role") == "master"]
        if len(masters) == 1:
            managed_by = masters[0]["id"]

    # Persist to Cosmos immediately — Foundry resources are created lazily
    # on first message send so the UI opens instantly.
    doc = agent_store.create_agent(
        name=body.name,
        model=body.model,
        tools=body.tools,
        custom_instructions=body.custom_instructions,
        thread_id=thread_id,
        provider=provider,
        foundry_agent_id="",
        role=body.role,
        managed_by=managed_by,
    )

    # If we just created a master, adopt all existing unassigned agents
    if body.role == "master":
        for a in agent_store.list_agents():
            if a["id"] != doc["id"] and a.get("role") != "master" and not a.get("managed_by"):
                agent_store.update_agent(a["id"], {"managed_by": doc["id"]})

    return _agent_to_response(doc)


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(agent_id: str):
    _require_ready()
    doc = agent_store.get_agent(agent_id)
    if not doc:
        raise HTTPException(404, "Agent not found")
    return _agent_to_response(doc)


@router.patch("/{agent_id}", response_model=AgentResponse)
def update_agent(agent_id: str, body: AgentUpdate):
    _require_ready()
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")

    doc = agent_store.get_agent(agent_id)
    if not doc:
        raise HTTPException(404, "Agent not found")

    doc_provider = (doc.get("provider") or agent_service.provider or "azure_foundry").strip().lower()

    # If model changed, we need to recreate the Foundry agent (different deployment)
    model_changed = "model" in updates and updates["model"] != doc["model"]
    tools_changed = "tools" in updates and set(updates["tools"]) != set(doc.get("tools", []))
    instructions_changed = "custom_instructions" in updates and updates["custom_instructions"] != doc.get("custom_instructions", "")

    if doc_provider == "azure_foundry":
        if model_changed:
            new_model = updates.get("model", doc["model"])
            new_tools = updates.get("tools", doc.get("tools", []))
            new_custom = updates.get("custom_instructions", doc.get("custom_instructions", ""))
            try:
                if doc.get("foundry_agent_id"):
                    agent_service.delete_foundry_agent(doc["foundry_agent_id"])
                foundry_agent = agent_service.create_foundry_agent(new_model, new_tools, custom_instructions=new_custom)
                updates["foundry_agent_id"] = foundry_agent.id
            except Exception as e:
                logger.error("Failed to recreate Foundry agent: %s", e)
                raise HTTPException(500, f"Failed to update agent: {e}")
        elif tools_changed or instructions_changed:
            new_tools = updates.get("tools", doc.get("tools", []))
            new_custom = updates.get("custom_instructions", doc.get("custom_instructions", ""))
            foundry_agent_id = doc.get("foundry_agent_id", "")
            if foundry_agent_id:
                try:
                    agent_service.ensure_foundry_agent(
                        agent_id=agent_id,
                        foundry_agent_id=foundry_agent_id,
                        model=doc["model"],
                        tools=new_tools,
                        custom_instructions=new_custom,
                    )
                except Exception as e:
                    logger.warning("Failed to update Foundry agent in place: %s", e)

    # If role changed to master, auto-assign all unassigned agents
    role_became_master = (
        updates.get("role") == "master" and doc.get("role") != "master"
    )

    doc = agent_store.update_agent(agent_id, updates)
    if not doc:
        raise HTTPException(404, "Agent not found")

    if role_became_master:
        for a in agent_store.list_agents():
            if a["id"] != agent_id and a.get("role") != "master" and not a.get("managed_by"):
                agent_store.update_agent(a["id"], {"managed_by": agent_id})

    return _agent_to_response(doc)


@router.delete("/{agent_id}", status_code=204)
def delete_agent(agent_id: str):
    _require_ready()
    doc = agent_store.get_agent(agent_id)
    if not doc:
        raise HTTPException(404, "Agent not found")

    if doc.get("role") == "master":
        raise HTTPException(400, "The master agent cannot be deleted.")

    doc_provider = (doc.get("provider") or agent_service.provider or "azure_foundry").strip().lower()

    # Clean up Foundry resources (only for azure_foundry provider)
    if doc_provider == "azure_foundry":
        fns = []
        if doc.get("foundry_agent_id"):
            fns.append(lambda: agent_service.delete_foundry_agent(doc["foundry_agent_id"]))
        if doc.get("thread_id"):
            fns.append(lambda: agent_service.delete_foundry_thread(doc["thread_id"]))
        if fns:
            with ThreadPoolExecutor(max_workers=len(fns)) as pool:
                list(pool.map(lambda f: f(), fns))

    agent_store.delete_agent(agent_id)


# ── Thread busy check ────────────────────────────────────────────

@router.get("/{agent_id}/busy")
def check_busy(agent_id: str):
    """Return whether the agent's thread has an active run."""
    _require_ready()
    doc = agent_store.get_agent(agent_id)
    if not doc:
        raise HTTPException(404, "Agent not found")
    doc_provider = (doc.get("provider") or agent_service.provider or "azure_foundry").strip().lower()
    if doc_provider != "azure_foundry":
        return {"busy": False, "reason": None}
    thread_id = doc.get("thread_id", "")
    trigger_running = agent_service.is_trigger_run_active(agent_id)
    thread_busy = agent_service.is_thread_busy(thread_id) if thread_id else False
    busy = trigger_running or thread_busy
    reason = "trigger" if trigger_running else ("run" if thread_busy else None)
    return {"busy": busy, "reason": reason}


# ── Messages ─────────────────────────────────────────────────────

@router.get("/{agent_id}/messages", response_model=list[MessageResponse])
def get_messages(agent_id: str):
    _require_ready()
    doc = agent_store.get_agent(agent_id)
    if not doc:
        raise HTTPException(404, "Agent not found")
    if not doc.get("thread_id"):
        return []
    doc_provider = (doc.get("provider") or agent_service.provider or "azure_foundry").strip().lower()
    messages = agent_service.get_messages(doc["thread_id"], provider=doc_provider)
    return [MessageResponse(**m) for m in messages]


@router.get("/{agent_id}/token-count")
def get_token_count(agent_id: str):
    """Return approximate token usage for the agent's conversation."""
    _require_ready()
    doc = agent_store.get_agent(agent_id)
    if not doc:
        raise HTTPException(404, "Agent not found")
    if not doc.get("thread_id"):
        return {"token_count": 0, "context_limit": 0}

    model = doc.get("model", "gpt-4.1-mini")

    # Context window limits by model family
    context_limits = {
        "gpt-4.1": 1_048_576,
        "gpt-4.1-mini": 1_048_576,
        "gpt-4.1-nano": 1_048_576,
        "gpt-5-mini": 1_048_576,
        "gpt-5-chat": 1_048_576,
        "gpt-5-nano": 1_048_576,
        "model-router": 1_048_576,
    }
    context_limit = context_limits.get(model, 128_000)

    try:
        import tiktoken
        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("o200k_base")

        doc_provider = (doc.get("provider") or agent_service.provider or "azure_foundry").strip().lower()
        messages = agent_service.get_messages(doc["thread_id"], provider=doc_provider)

        token_count = 0
        for msg in messages:
            token_count += 4  # ~4 tokens overhead per message
            content = msg.get("content") or ""
            if content:
                token_count += len(enc.encode(content))
    except Exception as e:
        logger.warning("Token count failed for agent %s: %s", agent_id, e)
        return {"token_count": 0, "context_limit": context_limit}

    return {"token_count": token_count, "context_limit": context_limit}


@router.post("/{agent_id}/messages")
def send_message(agent_id: str, body: SendAgentMessageRequest):
    """Send a user message and stream the agent response as SSE."""
    _require_ready()
    doc = agent_store.get_agent(agent_id)
    if not doc:
        raise HTTPException(404, "Agent not found")

    foundry_agent_id = doc.get("foundry_agent_id", "")
    thread_id = doc.get("thread_id", "")
    model = doc.get("model", "gpt-4.1-mini")
    doc_provider = (doc.get("provider") or agent_service.provider or "azure_foundry").strip().lower()
    is_first_message = doc.get("name", "New Agent") == "New Agent"

    # Lazy-init Foundry resources on first message (deferred from create_agent for speed)
    if doc_provider == "azure_foundry" and (not foundry_agent_id or not thread_id):
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = {}
                if not foundry_agent_id:
                    futures["agent"] = pool.submit(
                        agent_service.create_foundry_agent, model,
                        doc.get("tools", []), doc.get("custom_instructions", ""),
                    )
                if not thread_id:
                    futures["thread"] = pool.submit(agent_service.create_foundry_thread)

                if "agent" in futures:
                    foundry_agent_id = futures["agent"].result().id
                if "thread" in futures:
                    thread_id = futures["thread"].result()

            agent_store.update_agent(agent_id, {
                "foundry_agent_id": foundry_agent_id,
                "thread_id": thread_id,
            })
        except Exception as e:
            logger.error("Lazy Foundry init failed for agent %s: %s", agent_id, e)
            raise HTTPException(500, f"Failed to initialize agent: {e}")
    elif doc_provider != "azure_foundry" and not thread_id:
        raise HTTPException(500, "Agent not properly initialized")

    # Convert images to data URIs for the provider
    image_data_uris = []
    for img in body.images:
        data_uri = f"data:{img.media_type};base64,{img.data}"
        image_data_uris.append({"data_uri": data_uri, "media_type": img.media_type, "data": img.data})

    def event_stream():
        for chunk in agent_service.stream_response(
            agent_id=agent_id,
            foundry_agent_id=foundry_agent_id,
            thread_id=thread_id,
            model=model,
            content=body.content,
            agent_name=doc.get("name", ""),
            tools=doc.get("tools", []),
            provider=doc_provider,
            images=image_data_uris if image_data_uris else None,
            custom_instructions=doc.get("custom_instructions", ""),
        ):
            yield f"data: {chunk}\n\n"

        # Auto-name the agent on the first message — run in background
        # so the SSE stream closes immediately after the response.
        if is_first_message:
            def _auto_name():
                try:
                    name = agent_service.generate_agent_name(body.content, provider=doc_provider)
                    if name:
                        agent_store.update_agent(agent_id, {"name": name})
                        logger.info("Auto-named agent %s → %s", agent_id, name)
                except Exception as e:
                    logger.warning("Auto-naming failed: %s", e)
            threading.Thread(target=_auto_name, daemon=True).start()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Agent API (synchronous invoke) ──────────────────────────────

@router.post("/{agent_id}/invoke", response_model=InvokeAgentResponse)
def invoke_agent(agent_id: str, body: InvokeAgentRequest):
    """Invoke an agent synchronously — send a message, get the full response."""
    _require_ready()
    doc = agent_store.get_agent(agent_id)
    if not doc:
        raise HTTPException(404, "Agent not found")

    foundry_agent_id = doc.get("foundry_agent_id", "")
    thread_id = doc.get("thread_id", "")
    model = doc.get("model", "gpt-4.1-mini")
    doc_provider = (doc.get("provider") or agent_service.provider or "azure_foundry").strip().lower()

    # Lazy-init Foundry resources if needed
    if doc_provider == "azure_foundry" and (not foundry_agent_id or not thread_id):
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = {}
                if not foundry_agent_id:
                    futures["agent"] = pool.submit(
                        agent_service.create_foundry_agent, model,
                        doc.get("tools", []), doc.get("custom_instructions", ""),
                    )
                if not thread_id:
                    futures["thread"] = pool.submit(agent_service.create_foundry_thread)

                if "agent" in futures:
                    foundry_agent_id = futures["agent"].result().id
                if "thread" in futures:
                    thread_id = futures["thread"].result()

            agent_store.update_agent(agent_id, {
                "foundry_agent_id": foundry_agent_id,
                "thread_id": thread_id,
            })
        except Exception as e:
            logger.error("Lazy Foundry init failed for agent %s: %s", agent_id, e)
            raise HTTPException(500, f"Failed to initialize agent: {e}")
    elif doc_provider != "azure_foundry" and not thread_id:
        raise HTTPException(500, "Agent not properly initialized")

    # Convert images
    image_data = None
    if body.images:
        image_data = [
            {"data_uri": f"data:{img.media_type};base64,{img.data}", "media_type": img.media_type, "data": img.data}
            for img in body.images
        ]

    try:
        response = agent_service.run_non_streaming(
            agent_id=agent_id,
            foundry_agent_id=foundry_agent_id,
            thread_id=thread_id,
            model=model,
            content=body.message,
            tools=doc.get("tools", []),
            provider=doc_provider,
            images=image_data,
            custom_instructions=doc.get("custom_instructions", ""),
        )
    except Exception as e:
        logger.error("invoke_agent error for %s: %s", agent_id, e, exc_info=True)
        raise HTTPException(500, f"Agent invocation failed: {e}")

    return InvokeAgentResponse(
        agent_id=agent_id,
        agent_name=doc.get("name", ""),
        response=response or "",
        model=model,
    )


# ── Trigger management ───────────────────────────────────────────

@router.get("/{agent_id}/trigger", response_model=AgentTriggerResponse | None)
def get_trigger(agent_id: str):
    _require_ready()
    doc = agent_store.get_agent(agent_id)
    if not doc:
        raise HTTPException(404, "Agent not found")
    trigger = doc.get("trigger")
    if not trigger:
        return None
    return AgentTriggerResponse(**trigger)


@router.post("/{agent_id}/trigger", response_model=AgentResponse, status_code=201)
def create_trigger(agent_id: str, body: AgentTriggerCreate):
    _require_ready()
    doc = agent_store.get_agent(agent_id)
    if not doc:
        raise HTTPException(404, "Agent not found")
    if doc.get("trigger"):
        raise HTTPException(400, "Agent already has a trigger. Update or remove it first.")

    doc = agent_store.set_trigger(
        agent_id,
        trigger_type=body.type,
        interval_minutes=body.interval_minutes,
        prompt=body.prompt,
        description=body.description,
        filter_from=body.filter_from,
        filter_subject=body.filter_subject,
        filter_body=body.filter_body,
        filter_header=body.filter_header,
        max_age_minutes=body.max_age_minutes,
        filter_after_date=body.filter_after_date,
    )
    return _agent_to_response(doc)


@router.patch("/{agent_id}/trigger", response_model=AgentResponse)
def update_trigger(agent_id: str, body: AgentTriggerUpdate):
    _require_ready()
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")

    # Handle active toggle separately
    if "active" in updates:
        active = updates.pop("active")
        agent_store.toggle_trigger(agent_id, active=active)

    if updates:
        doc = agent_store.update_trigger(agent_id, updates)
    else:
        doc = agent_store.get_agent(agent_id)

    if not doc:
        raise HTTPException(404, "Agent or trigger not found")
    return _agent_to_response(doc)


@router.delete("/{agent_id}/trigger", status_code=204)
def delete_trigger(agent_id: str):
    _require_ready()
    doc = agent_store.remove_trigger(agent_id)
    if not doc:
        raise HTTPException(404, "Agent not found")


@router.post("/{agent_id}/trigger/test")
def test_trigger(agent_id: str):
    """Dry-run a trigger to preview what data it would send to the agent.

    For scheduled triggers: shows the prompt that would be sent.
    For gmail_push triggers: connects to IMAP, finds matching emails,
    and shows what the agent would receive — without actually running it.
    """
    _require_ready()
    doc = agent_store.get_agent(agent_id)
    if not doc:
        raise HTTPException(404, "Agent not found")
    trigger = doc.get("trigger")
    if not trigger:
        raise HTTPException(400, "Agent has no trigger configured")

    trigger_type = trigger.get("type", "regular")
    prompt = trigger.get("prompt", "")
    description = trigger.get("description", "")

    if trigger_type == "regular":
        return {
            "type": "regular",
            "interval_minutes": trigger.get("interval_minutes", 60),
            "prompt": prompt,
            "description": description,
            "preview": prompt,
            "explanation": "This exact prompt will be sent to the agent every time the trigger fires.",
        }

    # Gmail push — do a read-only IMAP check
    from app.services.user_service import user_service
    from app.tools.email_encryption import decrypt
    import imaplib

    account = user_service.get_email_account("1")
    if not account:
        return {
            "type": "gmail_push",
            "error": "No email account configured. Set up email in Settings first.",
            "matching_emails": [],
        }

    imap_host = account.get("imap_host")
    if not imap_host:
        return {
            "type": "gmail_push",
            "error": "No IMAP host configured on your email account.",
            "matching_emails": [],
        }

    try:
        password = decrypt(account["password_encrypted"])
    except Exception:
        return {
            "type": "gmail_push",
            "error": "Failed to decrypt email credentials.",
            "matching_emails": [],
        }

    try:
        conn = imaplib.IMAP4_SSL(imap_host, account.get("imap_port", 993), timeout=15)
        conn.login(account["username"], password)
        conn.select("INBOX", readonly=True)
    except Exception as e:
        return {
            "type": "gmail_push",
            "error": f"IMAP connection failed: {e}",
            "matching_emails": [],
        }

    try:
        from app.services.gmail_push_service import _fetch_new_emails

        filter_from = trigger.get("filter_from", "")
        filter_subject = trigger.get("filter_subject", "")
        filter_body = trigger.get("filter_body", "")
        filter_header = trigger.get("filter_header", "")
        max_age_minutes = trigger.get("max_age_minutes", 0)
        filter_after_date = trigger.get("filter_after_date", "")

        if not filter_after_date:
            created_at = trigger.get("created_at", "")
            if created_at:
                filter_after_date = created_at[:10]

        emails = _fetch_new_emails(
            conn,
            last_seen_uid=0,
            filter_from=filter_from,
            filter_subject=filter_subject,
            filter_body=filter_body,
            filter_header=filter_header,
            max_age_minutes=max_age_minutes,
            filter_after_date=filter_after_date,
            limit=5,
        )
        conn.logout()
    except TypeError:
        # _fetch_new_emails may not have limit param — fallback
        try:
            emails = _fetch_new_emails(
                conn,
                last_seen_uid=0,
                filter_from=trigger.get("filter_from", ""),
                filter_subject=trigger.get("filter_subject", ""),
                filter_body=trigger.get("filter_body", ""),
                filter_header=trigger.get("filter_header", ""),
                max_age_minutes=trigger.get("max_age_minutes", 0),
                filter_after_date=filter_after_date,
            )[:5]
            conn.logout()
        except Exception as e:
            try:
                conn.logout()
            except Exception:
                pass
            return {
                "type": "gmail_push",
                "error": f"IMAP fetch error: {e}",
                "matching_emails": [],
            }
    except Exception as e:
        try:
            conn.logout()
        except Exception:
            pass
        return {
            "type": "gmail_push",
            "error": f"IMAP fetch error: {e}",
            "matching_emails": [],
        }

    # Build preview of what the agent would receive
    matching = []
    for em in emails:
        agent_input = (
            f"[Gmail Push Notification — New Email]\n"
            f"From: {em['from']}\n"
            f"Subject: {em['subject']}\n"
            f"Date: {em['date']}\n"
            f"Email UID: {em['uid']}\n\n"
            f"(Use the read_trigger_email tool with this UID to read the full email body if needed.)\n\n"
            f"---\n"
            f"Trigger instruction: {prompt}"
        )
        matching.append({
            "uid": em["uid"],
            "from": em["from"],
            "subject": em["subject"],
            "date": em["date"],
            "agent_input_preview": agent_input,
        })

    return {
        "type": "gmail_push",
        "filters": {
            "filter_from": trigger.get("filter_from", ""),
            "filter_subject": trigger.get("filter_subject", ""),
            "filter_body": trigger.get("filter_body", ""),
            "filter_header": trigger.get("filter_header", ""),
            "max_age_minutes": trigger.get("max_age_minutes", 0),
        },
        "matching_emails": matching,
        "total_matches": len(matching),
        "explanation": f"Found {len(matching)} email(s) that match your filters. Each would generate the agent input shown in 'agent_input_preview'.",
    }


# ── Delegations ──────────────────────────────────────────────────

@router.get("/{agent_id}/delegations")
def list_delegations(agent_id: str, status: str | None = None, limit: int = 20):
    """List delegations for a master agent."""
    _require_ready()
    doc = agent_store.get_agent(agent_id)
    if not doc:
        raise HTTPException(404, "Agent not found")
    if doc.get("role") != "master":
        raise HTTPException(400, "Only master agents have delegations")

    from app.services.delegation_store import delegation_store
    if not delegation_store.is_ready:
        raise HTTPException(503, "Delegation store not initialized")

    docs = delegation_store.list_delegations(agent_id, status=status, limit=min(limit, 50))

    # Resolve sub-agent names
    agents_cache: dict[str, str] = {}
    result = []
    for d in docs:
        sub_id = d["sub_agent_id"]
        if sub_id not in agents_cache:
            sub = agent_store.get_agent(sub_id)
            agents_cache[sub_id] = sub["name"] if sub else "Unknown"
        result.append({
            "id": d["id"],
            "sub_agent_id": sub_id,
            "sub_agent_name": agents_cache[sub_id],
            "task": d["task"],
            "status": d["status"],
            "priority": d.get("priority", "normal"),
            "result_summary": d.get("result_summary"),
            "error": d.get("error"),
            "created_at": d["created_at"],
            "started_at": d.get("started_at"),
            "completed_at": d.get("completed_at"),
        })
    return result
