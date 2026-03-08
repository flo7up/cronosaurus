from pydantic import BaseModel
from typing import Optional


class MCPServerCreate(BaseModel):
    name: str
    url: str
    api_key: str = ""
    description: str = ""
    active: bool = True


class MCPServerUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    api_key: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None


class MCPServerResponse(BaseModel):
    id: str
    name: str
    url: str
    api_key: str = ""
    description: str = ""
    active: bool = True


class SelectedModelRequest(BaseModel):
    model: str


class ToolPreference(BaseModel):
    """Enabled/disabled state for a single tool."""
    id: str          # e.g. "web_search", "triggers", or an MCP server id
    enabled: bool


class ToolPreferencesUpdate(BaseModel):
    """Update request for a single tool toggle."""
    tool_id: str
    enabled: bool


# ── Email Account ────────────────────────────────────────────────

class EmailAccountCreate(BaseModel):
    label: str = ""
    smtp_host: str
    smtp_port: int = 587
    username: str
    password: str
    from_email: str
    from_name: str = ""
    use_tls: bool = True
    imap_host: str = ""
    imap_port: int = 993
    is_default: bool = False


class EmailAccountUpdate(BaseModel):
    label: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    use_tls: Optional[bool] = None
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    is_default: Optional[bool] = None


class EmailAccountResponse(BaseModel):
    id: str
    label: str = ""
    smtp_host: str
    smtp_port: int
    username: str
    from_email: str
    from_name: str = ""
    use_tls: bool = True
    imap_host: str = ""
    imap_port: int = 993
    is_default: bool = False
    configured: bool = True
    has_password: bool = True


class ToolCatalogEntry(BaseModel):
    """Describes one available tool for the frontend."""
    id: str
    label: str
    description: str
    category: str  # "built-in", "configurable", "mcp"
    in_library: bool = False
    available: bool = True  # False when config/test required but not done
    requires_config: bool = False
    provider_only: str = ""  # empty = all providers, or "azure_foundry" etc.


class ToolLibraryUpdate(BaseModel):
    """Add or remove a tool from the user's library."""
    tool_id: str
    action: str  # "add" or "remove"


class ToolLibraryBatchUpdate(BaseModel):
    """Batch add/remove tools from the user's library."""
    updates: list[ToolLibraryUpdate]


class NotificationPreferencesUpdate(BaseModel):
    delivery: str = "all"  # "all" | "in_app" | "none"


class UserPreferencesResponse(BaseModel):
    selected_model: str
    mcp_servers: list[MCPServerResponse]
    tool_preferences: list[ToolPreference] = []
    tool_library: list[str] = []
    email_configured: bool = False
    email_tested: bool = False
    notification_preferences: dict = {"delivery": "all"}
