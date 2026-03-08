// ── Agent (first-class entity) ────────────────────────────────

export interface AgentTrigger {
  type: string;  // "regular" | "gmail_push"
  interval_minutes: number;
  prompt: string;
  description: string;
  active: boolean;
  last_run: string | null;
  next_run: string | null;
  run_count: number;
  created_at: string;
  // gmail_push fields
  filter_from?: string;
  filter_subject?: string;
  filter_body?: string;
  filter_header?: string;
  max_age_minutes?: number;
  filter_after_date?: string;
  last_seen_uid?: number;
}

export interface Agent {
  id: string;
  user_id: string;
  name: string;
  model: string;
  tools: string[];
  email_account_id: string | null;
  thread_id: string;
  foundry_agent_id: string;
  trigger: AgentTrigger | null;
  created_at: string;
  updated_at: string;
}

// ── Legacy Conversation (kept for type compat, mapped from Agent) ──

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  model: string;
}

export interface ToolStep {
  name: string;
  arguments: Record<string, unknown>;
  result?: Record<string, unknown>;
  status: "running" | "completed" | "error";
}

export interface TodoItem {
  id: number;
  title: string;
  status: "pending" | "in_progress" | "completed" | "failed";
  result?: string | null;
}

export interface Message {
  role: "user" | "assistant";
  content: string;
  toolSteps?: ToolStep[];
  created_at?: string;
  images?: Array<{ data: string; media_type: string }>;
}

export interface SSEEvent {
  type: "delta" | "done" | "error" | "trigger_update" | "tool_call" | "tool_result" | "name_update";
  content: string;
  data?: unknown;
}

export interface MCPServer {
  id: string;
  name: string;
  url: string;
  api_key: string;
  description: string;
  active: boolean;
}

// Trigger is now part of Agent (AgentTrigger)

export interface UserPreferences {
  selected_model: string;
  mcp_servers: MCPServer[];
  tool_preferences: ToolPreference[];
  tool_library: string[];
  email_configured: boolean;
}

export interface ToolPreference {
  id: string;
  enabled: boolean;
}

export interface ToolCatalogEntry {
  id: string;
  label: string;
  description: string;
  category: string;  // "built-in" | "configurable" | "mcp"
  in_library: boolean;
  available: boolean;
  requires_config: boolean;
  provider_only: string;  // "" = all providers, or "azure_foundry" etc.
}

export interface EmailAccount {
  id: string;
  label: string;
  smtp_host: string;
  smtp_port: number;
  username: string;
  from_email: string;
  from_name: string;
  use_tls: boolean;
  imap_host: string;
  imap_port: number;
  is_default: boolean;
  configured: boolean;
  has_password: boolean;
}

export interface EmailAccountCreate {
  label: string;
  smtp_host: string;
  smtp_port: number;
  username: string;
  password: string;
  from_email: string;
  from_name: string;
  use_tls: boolean;
  imap_host: string;
  imap_port: number;
  is_default: boolean;
}

// ── App Settings / Onboarding ────────────────────────────────

export interface AppSettings {
  onboarding_completed: boolean;
  model_provider: string;
  project_endpoint: string;
  model_deployment_name: string;
  available_models: string[];
  openai_api_key_set: boolean;
  openai_model: string;
  anthropic_api_key_set: boolean;
  anthropic_model: string;
  cosmos_url: string;
  cosmos_key: string;
  cosmos_key_set: boolean;
  cosmos_db: string;
  configure_email: boolean;
  configure_cosmos: boolean;
}
