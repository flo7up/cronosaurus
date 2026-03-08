import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import api
from app.routers import agents as agents_router
from app.routers import user
from app.routers import notification as notification_router
from app.routers import settings as settings_router
from app.config import settings
from app.services.agent_service import agent_service
from app.services.agent_store import agent_store
from app.services.user_service import user_service
from app.services.message_store import message_store
from app.services.notification_service import notification_service
from app.services.trigger_scheduler import trigger_scheduler
from app.services.gmail_push_service import gmail_push_service

# ── Auto-discover custom trigger services ───────────────────────
_custom_trigger_services: list = []

def _load_custom_triggers():
    import importlib
    import pathlib
    custom_dir = pathlib.Path(__file__).resolve().parent / "services" / "custom_triggers"
    if not custom_dir.is_dir():
        return
    for path in sorted(custom_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module_name = f"app.services.custom_triggers.{path.stem}"
        try:
            mod = importlib.import_module(module_name)
            meta = getattr(mod, "TRIGGER_META", None)
            svc_cls = getattr(mod, "TriggerService", None)
            if not meta or not svc_cls:
                continue
            svc = svc_cls()
            _custom_trigger_services.append((meta, svc))
            logging.getLogger(__name__).info(
                "Discovered custom trigger: %s", meta.get("id", path.stem)
            )
        except Exception:
            logging.getLogger(__name__).exception(
                "Failed to load custom trigger %s", path.name
            )

_load_custom_triggers()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Silence noisy Azure SDK HTTP loggers — only show warnings+
for _quiet in (
    "azure.cosmos",
    "azure.identity",
    "azure.core.pipeline.policies.http_logging_policy",
    "azure.cosmos._cosmos_http_logging_policy",
):
    logging.getLogger(_quiet).setLevel(logging.WARNING)

_init_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="init")
INIT_TIMEOUT = 30  # seconds per service


async def _init_service(fn, name: str):
    """Run a blocking service initializer in a thread with a timeout."""
    logger.info("Initializing %s …", name)
    try:
        loop = asyncio.get_running_loop()
        await asyncio.wait_for(
            loop.run_in_executor(_init_pool, fn), timeout=INIT_TIMEOUT
        )
        logger.info("%s initialized successfully", name)
    except asyncio.TimeoutError:
        logger.warning("%s timed out after %ds — skipping", name, INIT_TIMEOUT)
    except Exception as e:
        logger.warning("%s not available: %s", name, e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Apply saved settings to runtime config before initializing services
    logger.info("Lifespan startup: loading saved settings …")
    from app.services.settings_service import settings_service as _ss
    _raw = _ss.get_raw()
    if _raw.get("project_endpoint"):
        object.__setattr__(settings, "project_endpoint", _raw["project_endpoint"])
    if _raw.get("model_deployment_name"):
        object.__setattr__(settings, "model_deployment_name", _raw["model_deployment_name"])
    if _raw.get("model_provider"):
        object.__setattr__(settings, "model_provider", _raw["model_provider"])
    if _raw.get("openai_api_key"):
        object.__setattr__(settings, "openai_api_key", _raw["openai_api_key"])
    if _raw.get("openai_model"):
        object.__setattr__(settings, "openai_model", _raw["openai_model"])
    if _raw.get("anthropic_api_key"):
        object.__setattr__(settings, "anthropic_api_key", _raw["anthropic_api_key"])
    if _raw.get("anthropic_model"):
        object.__setattr__(settings, "anthropic_model", _raw["anthropic_model"])
    if _raw.get("cosmos_url"):
        object.__setattr__(settings, "cosmos_url", _raw["cosmos_url"])
    if _raw.get("cosmos_key"):
        object.__setattr__(settings, "cosmos_key", _raw["cosmos_key"])
    if _raw.get("cosmos_db"):
        object.__setattr__(settings, "cosmos_db", _raw["cosmos_db"])
    if _raw.get("available_models"):
        from app.models.chat import AVAILABLE_MODELS
        AVAILABLE_MODELS.clear()
        AVAILABLE_MODELS.extend(_raw["available_models"])
    logger.info("Settings applied — starting service initialization")

    # Startup — run blocking SDK calls in a thread so they can be timed out
    await _init_service(user_service.initialize, "user_service")
    await _init_service(message_store.initialize, "message_store")
    await _init_service(agent_store.initialize, "agent_store")
    await _init_service(agent_service.initialize, "agent_service")
    await _init_service(notification_service.initialize, "notification_service")

    # Start async background services
    if agent_store.is_ready and agent_service.is_ready:
        await trigger_scheduler.start()
        logger.info("Trigger scheduler started")
        await gmail_push_service.start()
        logger.info("Gmail push service started")
        # Start custom trigger services
        for meta, svc in _custom_trigger_services:
            try:
                await svc.start()
                logger.info("Custom trigger '%s' started", meta.get("id"))
            except Exception as e:
                logger.warning("Custom trigger '%s' failed to start: %s", meta.get("id"), e)

    logger.info("Lifespan startup complete — server ready")
    try:
        yield
    finally:
        # Shutdown custom triggers
        for meta, svc in _custom_trigger_services:
            try:
                await svc.stop()
            except Exception:
                pass
        # Shutdown
        try:
            await gmail_push_service.stop()
        except Exception:
            pass
        try:
            await trigger_scheduler.stop()
        except Exception:
            pass
        try:
            agent_service.cleanup()
        except Exception:
            pass
        _init_pool.shutdown(wait=False)


app = FastAPI(title="Cronosaurus API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(api.router, prefix="/api")
app.include_router(agents_router.router, prefix="/api")
app.include_router(user.router, prefix="/api")
app.include_router(notification_router.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "agent_ready": agent_service.is_ready,
        "store_ready": agent_store.is_ready,
        "user_service_ready": user_service.is_ready,
    }
