import logging
from fastapi import APIRouter, HTTPException

from app.models.user import (
    MCPServerCreate,
    MCPServerUpdate,
    MCPServerResponse,
    SelectedModelRequest,
    ToolPreference,
    ToolPreferencesUpdate,
    ToolCatalogEntry,
    ToolLibraryUpdate,
    ToolLibraryBatchUpdate,
    UserPreferencesResponse,
    EmailAccountCreate,
    EmailAccountUpdate,
    EmailAccountResponse,
    NotificationPreferencesUpdate,
)
from app.services.user_service import user_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user", tags=["user"])


def _require_ready():
    if not user_service.is_ready:
        raise HTTPException(503, "User service not initialized (Cosmos DB)")


# ── Preferences ──────────────────────────────────────────────────

@router.get("/preferences", response_model=UserPreferencesResponse)
def get_preferences():
    """Get user preferences (model + MCP servers + tool toggles + email status + tool library)."""
    _require_ready()
    model = user_service.get_selected_model()
    servers = user_service.list_mcp_servers()
    tool_prefs = user_service.get_tool_preferences()
    tool_library = user_service.get_tool_library()
    email_accounts = user_service.list_email_accounts_safe()
    return UserPreferencesResponse(
        selected_model=model,
        mcp_servers=[MCPServerResponse(**s) for s in servers],
        tool_preferences=[ToolPreference(**p) for p in tool_prefs],
        tool_library=tool_library,
        email_configured=len(email_accounts) > 0,
        notification_preferences=user_service.get_notification_preferences(),
    )


@router.put("/preferences/model")
def update_selected_model(body: SelectedModelRequest):
    """Persist the user's selected model."""
    _require_ready()
    user_service.set_selected_model(body.model)
    return {"selected_model": body.model}


# ── Notification preferences ────────────────────────────────────

@router.get("/notification-preferences")
def get_notification_preferences():
    """Get notification delivery preferences."""
    _require_ready()
    return user_service.get_notification_preferences()


@router.put("/notification-preferences")
def update_notification_preferences(body: NotificationPreferencesUpdate):
    """Update notification delivery preferences."""
    _require_ready()
    return user_service.update_notification_preferences({"delivery": body.delivery})


@router.get("/tools", response_model=list[ToolPreference])
def get_tool_preferences():
    """Get tool enabled/disabled preferences."""
    _require_ready()
    prefs = user_service.get_tool_preferences()
    return [ToolPreference(**p) for p in prefs]


@router.put("/tools", response_model=list[ToolPreference])
def update_tool_preference(body: ToolPreferencesUpdate):
    """Toggle a tool on or off."""
    _require_ready()
    prefs = user_service.set_tool_preference(body.tool_id, body.enabled)
    return [ToolPreference(**p) for p in prefs]


# ── Tool Catalog & Library ───────────────────────────────────────

@router.get("/tool-catalog", response_model=list[ToolCatalogEntry])
def get_tool_catalog():
    """Return all available tools with their metadata and library status."""
    _require_ready()
    from app.services.agent_service import TOOL_CATALOG_META

    library = user_service.get_tool_library()
    email_accounts = user_service.list_email_accounts_safe()
    email_configured = len(email_accounts) > 0
    imap_configured = email_configured and any(bool(a.get("imap_host")) for a in email_accounts)

    entries = []
    for tool_id, meta in TOOL_CATALOG_META.items():
        # Determine if the tool is ready to use
        available = True
        if tool_id == "email_send" and not email_configured:
            available = False
        elif tool_id == "email_read" and not imap_configured:
            available = False

        entries.append(ToolCatalogEntry(
            id=tool_id,
            label=meta["label"],
            description=meta["description"],
            category=meta["category"],
            in_library=tool_id in library,
            available=available,
            requires_config=meta.get("requires_config", False),
            provider_only=meta.get("provider_only", ""),
        ))

    # Inject active MCP servers as tool catalog entries
    try:
        mcp_servers = user_service.list_mcp_servers()
        for srv in mcp_servers:
            if not srv.get("active", False):
                continue
            mcp_id = f"mcp:{srv['id']}"
            entries.append(ToolCatalogEntry(
                id=mcp_id,
                label=srv.get("name", "MCP Server"),
                description=srv.get("description", "") or f"MCP server: {srv.get('name', '')}",
                category="mcp",
                in_library=mcp_id in library,
                available=True,
                requires_config=False,
            ))
    except Exception:
        logger.warning("Failed to load MCP servers for tool catalog", exc_info=True)

    return entries


@router.get("/debug/mcp-tools")
def debug_mcp_tools():
    """Diagnostic: show what MCP tools would be built for each active server."""
    _require_ready()
    from app.services import mcp_client
    result = []
    servers = user_service.list_mcp_servers()
    for srv in servers:
        entry = {
            "id": srv["id"],
            "name": srv["name"],
            "url": srv["url"],
            "active": srv.get("active", False),
            "tools": [],
        }
        if srv.get("active", False):
            try:
                raw_tools = mcp_client.discover_tools(srv["id"], srv["url"], srv.get("api_key", ""))
                fn_defs = mcp_client.mcp_tools_to_function_defs(srv["name"], raw_tools)
                entry["tools"] = [{"name": d["name"], "description": d["description"][:100]} for d in fn_defs]
                entry["raw_tool_count"] = len(raw_tools)
            except Exception as e:
                entry["error"] = str(e)
        result.append(entry)
    return result


@router.get("/tool-library", response_model=list[str])
def get_tool_library():
    """Return the user's tool library (list of enabled tool IDs)."""
    _require_ready()
    return user_service.get_tool_library()


@router.put("/tool-library", response_model=list[str])
def update_tool_library(body: ToolLibraryUpdate):
    """Add or remove a tool from the user's library."""
    _require_ready()
    if body.action not in ("add", "remove"):
        raise HTTPException(400, "action must be 'add' or 'remove'")
    return user_service.update_tool_library(body.tool_id, body.action)


@router.patch("/tool-library/batch", response_model=list[str])
def batch_update_tool_library(body: ToolLibraryBatchUpdate):
    """Apply multiple add/remove operations in a single Cosmos write."""
    _require_ready()
    for u in body.updates:
        if u.action not in ("add", "remove"):
            raise HTTPException(400, f"Invalid action '{u.action}' for tool '{u.tool_id}'")
    return user_service.batch_update_tool_library(body.updates)


# ── MCP Servers ──────────────────────────────────────────────────

@router.get("/mcp-servers", response_model=list[MCPServerResponse])
def list_mcp_servers():
    _require_ready()
    servers = user_service.list_mcp_servers()
    return [MCPServerResponse(**s) for s in servers]


@router.post("/mcp-servers", response_model=MCPServerResponse, status_code=201)
def create_mcp_server(body: MCPServerCreate):
    _require_ready()
    srv = user_service.add_mcp_server(
        name=body.name,
        url=body.url,
        api_key=body.api_key,
        description=body.description,
        active=body.active,
    )
    return MCPServerResponse(**srv)


@router.patch("/mcp-servers/{server_id}", response_model=MCPServerResponse)
def update_mcp_server(server_id: str, body: MCPServerUpdate):
    _require_ready()
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")
    srv = user_service.update_mcp_server(server_id, updates)
    if not srv:
        raise HTTPException(404, "MCP server not found")
    return MCPServerResponse(**srv)


@router.delete("/mcp-servers/{server_id}", status_code=204)
def delete_mcp_server(server_id: str):
    _require_ready()
    if not user_service.delete_mcp_server(server_id):
        raise HTTPException(404, "MCP server not found")


@router.put("/mcp-servers/{server_id}/toggle")
def toggle_mcp_server(server_id: str, body: MCPServerUpdate):
    """Activate or deactivate an MCP server."""
    _require_ready()
    if body.active is None:
        raise HTTPException(400, "active field is required")
    srv = user_service.toggle_mcp_server(server_id, body.active)
    if not srv:
        raise HTTPException(404, "MCP server not found")
    return MCPServerResponse(**srv)


# ── Email Accounts (multi-account) ───────────────────────────────

@router.get("/email-accounts", response_model=list[EmailAccountResponse])
def list_email_accounts():
    """Get all configured email accounts (without passwords)."""
    _require_ready()
    accounts = user_service.list_email_accounts_safe()
    return [EmailAccountResponse(**a) for a in accounts]


@router.post("/email-accounts", response_model=EmailAccountResponse, status_code=201)
def create_email_account(body: EmailAccountCreate):
    """Add a new email account."""
    _require_ready()
    result = user_service.add_email_account(
        label=body.label,
        smtp_host=body.smtp_host,
        smtp_port=body.smtp_port,
        username=body.username,
        password=body.password,
        from_email=body.from_email,
        from_name=body.from_name,
        use_tls=body.use_tls,
        imap_host=body.imap_host,
        imap_port=body.imap_port,
        is_default=body.is_default,
    )
    return EmailAccountResponse(**result)


@router.patch("/email-accounts/{account_id}", response_model=EmailAccountResponse)
def update_email_account(account_id: str, body: EmailAccountUpdate):
    """Partially update a specific email account."""
    _require_ready()
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")
    result = user_service.update_email_account(account_id, updates)
    if not result:
        raise HTTPException(404, "Email account not found")
    return EmailAccountResponse(**result)


@router.delete("/email-accounts/{account_id}", status_code=204)
def delete_email_account(account_id: str):
    """Remove a specific email account."""
    _require_ready()
    if not user_service.delete_email_account(account_id):
        raise HTTPException(404, "Email account not found")


@router.post("/email-accounts/{account_id}/test")
def test_email_account(account_id: str):
    """Test SMTP connection for a specific account."""
    _require_ready()
    return user_service.test_email_account(account_id)


@router.post("/email-accounts/{account_id}/test-send")
def test_send_email(account_id: str, to: str = "", port: int = 0):
    """Send a test email from a specific account."""
    _require_ready()
    if not to:
        account = user_service.get_email_account_safe(account_id=account_id)
        if not account:
            raise HTTPException(404, "Email account not found")
        to = account["from_email"]
    return user_service.send_test_email(to, account_id=account_id, use_port=port)


# ── Legacy single-account endpoints (backwards compat) ──────────

@router.get("/email-account", response_model=EmailAccountResponse | None)
def get_email_account():
    """Get the default email account (without password). Legacy endpoint."""
    _require_ready()
    account = user_service.get_email_account_safe()
    if not account:
        return None
    return EmailAccountResponse(**account)


@router.post("/email-account/test")
def test_default_email_account():
    """Test the default SMTP connection. Legacy endpoint."""
    _require_ready()
    return user_service.test_email_account()


@router.post("/email-account/test-send")
def test_send_default_email(to: str = "", port: int = 0):
    """Send a test email from the default account. Legacy endpoint."""
    _require_ready()
    if not to:
        account = user_service.get_email_account_safe()
        if not account:
            raise HTTPException(404, "No email account configured")
        to = account["from_email"]
    return user_service.send_test_email(to, use_port=port)
