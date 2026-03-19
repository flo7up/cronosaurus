import json
import sys
import time

sys.path.insert(0, ".")

from app.config import settings
from app.services.agent_service import agent_service
from app.services.agent_store import agent_store
from app.services.message_store import message_store
from app.services.settings_service import settings_service


AGENT_ID = "2539d227-984c-4c57-b23e-f78a51618bce"
PROMPT = "check if workers are wearing their helmets"


def apply_saved_settings() -> None:
    raw = settings_service.get_raw()
    for key in (
        "project_endpoint",
        "model_deployment_name",
        "model_provider",
        "openai_api_key",
        "openai_model",
        "anthropic_api_key",
        "anthropic_model",
        "cosmos_url",
        "cosmos_key",
        "cosmos_db",
        "google_search_api_key",
        "google_search_engine_id",
    ):
        if key in raw:
            object.__setattr__(settings, key, raw[key])


def main() -> None:
    apply_saved_settings()
    message_store.initialize()
    agent_store.initialize()
    agent_service.initialize()

    agent = agent_store.get_agent(AGENT_ID)
    if not agent:
        print("Agent not found")
        return

    recent_images = agent.get("recent_images") or []
    print("AGENT", agent.get("name"))
    print("THREAD", agent.get("thread_id"))
    print("FOUNDRY_AGENT", agent.get("foundry_agent_id"))
    print("RECENT_IMAGES", len(recent_images))
    if recent_images:
        print("FIRST_IMAGE_META", {
            "media_type": recent_images[0].get("media_type"),
            "data_len": len(recent_images[0].get("data", "")),
            "data_prefix": recent_images[0].get("data", "")[:40],
        })

    if not recent_images:
        print("No recent images stored on agent")
        return

    fresh_thread_id = agent_service.create_foundry_thread()
    print("FRESH_THREAD", fresh_thread_id)

    try:
        uploaded_ids = agent_service._post_user_message(
            thread_id=fresh_thread_id,
            content=PROMPT,
            images=recent_images,
        )
        print("POST_USER_MESSAGE_OK", uploaded_ids)
    except Exception as exc:
        print("POST_USER_MESSAGE_ERROR", repr(exc))
        return

    try:
        foundry_agent = agent_service.ensure_foundry_agent(
            agent_id=agent["id"],
            foundry_agent_id=agent.get("foundry_agent_id", ""),
            model=agent.get("model", "gpt-4.1"),
            tools=agent.get("tools", []),
            custom_instructions=agent.get("custom_instructions", ""),
        )
        run = agent_service.client.runs.create(
            thread_id=fresh_thread_id,
            agent_id=foundry_agent.id,
        )
        print("RUN_CREATED", run.id, run.status)
        for _ in range(90):
            if run.status in ("completed", "failed", "cancelled", "expired", "requires_action"):
                break
            time.sleep(1)
            run = agent_service.client.runs.get(thread_id=fresh_thread_id, run_id=run.id)
        print("RUN_FINAL", run.id, run.status)
        if getattr(run, "last_error", None):
            print("RUN_LAST_ERROR", getattr(run.last_error, "code", None), getattr(run.last_error, "message", None))

        messages = list(agent_service.client.messages.list(thread_id=fresh_thread_id))
        summary = []
        for msg in messages:
            summary.append({
                "role": msg.role,
                "created_at": str(getattr(msg, "created_at", "")),
                "text": [tm.text.value for tm in getattr(msg, "text_messages", [])],
            })
        print("THREAD_MESSAGES")
        print(json.dumps(summary, indent=2)[:12000])
    except Exception as exc:
        print("RUN_ERROR", repr(exc))

    print("\nMINIMAL_PROBES")
    for label, model, tools, custom_instructions in [
        ("same-model-no-tools", agent.get("model", "gpt-4.1"), [], ""),
        ("same-model-same-tools", agent.get("model", "gpt-4.1"), agent.get("tools", []), agent.get("custom_instructions", "")),
        ("settings-default-no-tools", settings.model_deployment_name or "gpt-5.2-chat", [], ""),
        ("settings-default-same-tools", settings.model_deployment_name or "gpt-5.2-chat", agent.get("tools", []), agent.get("custom_instructions", "")),
    ]:
        temp_agent = None
        temp_thread = None
        uploaded_ids: list[str] = []
        try:
            temp_agent = agent_service.create_foundry_agent(model, tools, custom_instructions)
            temp_thread = agent_service.create_foundry_thread()
            uploaded_ids = agent_service._post_user_message(
                thread_id=temp_thread,
                content=PROMPT,
                images=recent_images,
            )
            run = agent_service.client.runs.create(thread_id=temp_thread, agent_id=temp_agent.id)
            for _ in range(90):
                if run.status in ("completed", "failed", "cancelled", "expired", "requires_action"):
                    break
                time.sleep(1)
                run = agent_service.client.runs.get(thread_id=temp_thread, run_id=run.id)
            print(label, "STATUS", run.status)
            if getattr(run, "last_error", None):
                print(label, "ERROR", getattr(run.last_error, "code", None), getattr(run.last_error, "message", None))
            messages = list(agent_service.client.messages.list(thread_id=temp_thread))
            summary = []
            for msg in messages:
                summary.append({
                    "role": msg.role,
                    "text": [tm.text.value for tm in getattr(msg, "text_messages", [])],
                })
            print(label, "MESSAGES", json.dumps(summary, indent=2)[:4000])
        except Exception as exc:
            print(label, "EXC", repr(exc))
        finally:
            try:
                agent_service._delete_uploaded_files(uploaded_ids)
            except Exception:
                pass
            try:
                if temp_agent:
                    agent_service.delete_foundry_agent(temp_agent.id)
            except Exception:
                pass
            try:
                if temp_thread:
                    agent_service.delete_foundry_thread(temp_thread)
            except Exception:
                pass

    print("\nSERVICE_LEVEL_PROBES")
    for label, use_stream in [
        ("service-run-non-streaming", False),
        ("service-run-streaming", True),
    ]:
        temp_doc = None
        temp_threads: set[str] = set()
        created_agent_ids: set[str] = set()
        try:
            initial_thread_id = agent_service.create_foundry_thread()
            temp_threads.add(initial_thread_id)
            initial_foundry_agent = agent_service.create_foundry_agent(
                agent.get("model", "gpt-4.1"),
                agent.get("tools", []),
                agent.get("custom_instructions", ""),
            )
            created_agent_ids.add(initial_foundry_agent.id)
            temp_doc = agent_store.create_agent(
                name=f"{label}-{int(time.time())}",
                model=agent.get("model", "gpt-4.1"),
                tools=agent.get("tools", []),
                thread_id=initial_thread_id,
                provider=agent.get("provider", "azure_foundry"),
                foundry_agent_id=initial_foundry_agent.id,
                custom_instructions=agent.get("custom_instructions", ""),
            )

            if use_stream:
                chunks = list(
                    agent_service.stream_response(
                        agent_id=temp_doc["id"],
                        foundry_agent_id=temp_doc.get("foundry_agent_id", ""),
                        thread_id=temp_doc["thread_id"],
                        model=temp_doc["model"],
                        content=PROMPT,
                        tools=temp_doc.get("tools", []),
                        provider=temp_doc.get("provider", "azure_foundry"),
                        images=recent_images,
                        custom_instructions=temp_doc.get("custom_instructions", ""),
                    )
                )
                parsed_chunks = []
                for chunk in chunks:
                    try:
                        parsed_chunks.append(json.loads(chunk))
                    except Exception:
                        parsed_chunks.append({"type": "raw", "content": chunk})
                done_chunk = next((chunk for chunk in parsed_chunks if chunk.get("type") == "done"), None)
                print(label, "DONE", bool(done_chunk))
                if done_chunk:
                    print(label, "DONE_PREVIEW", (done_chunk.get("content", "") or "")[:500])
                else:
                    print(label, "CHUNKS", json.dumps(parsed_chunks, indent=2)[:4000])
            else:
                response = agent_service.run_non_streaming(
                    agent_id=temp_doc["id"],
                    foundry_agent_id=temp_doc.get("foundry_agent_id", ""),
                    thread_id=temp_doc["thread_id"],
                    model=temp_doc["model"],
                    content=PROMPT,
                    tools=temp_doc.get("tools", []),
                    provider=temp_doc.get("provider", "azure_foundry"),
                    images=recent_images,
                    custom_instructions=temp_doc.get("custom_instructions", ""),
                )
                print(label, "RESPONSE_LEN", len(response or ""))
                print(label, "RESPONSE_PREVIEW", (response or "")[:500])

            refreshed = agent_store.get_agent(temp_doc["id"])
            if refreshed:
                if refreshed.get("thread_id"):
                    temp_threads.add(refreshed["thread_id"])
                print(label, "REFRESHED_AGENT", {
                    "thread_id": refreshed.get("thread_id"),
                    "foundry_agent_id": refreshed.get("foundry_agent_id"),
                    "model": refreshed.get("model"),
                })
        except Exception as exc:
            print(label, "EXC", repr(exc))
        finally:
            try:
                if temp_doc:
                    refreshed = agent_store.get_agent(temp_doc["id"])
                    if refreshed and refreshed.get("foundry_agent_id"):
                        created_agent_ids.add(refreshed["foundry_agent_id"])
                    agent_store.delete_agent(temp_doc["id"])
            except Exception:
                pass
            for foundry_agent_id in created_agent_ids:
                try:
                    agent_service.delete_foundry_agent(foundry_agent_id)
                except Exception:
                    pass
            for temp_thread in temp_threads:
                try:
                    agent_service.delete_foundry_thread(temp_thread)
                except Exception:
                    pass


if __name__ == "__main__":
    main()