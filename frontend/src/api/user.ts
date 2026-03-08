import type { MCPServer, UserPreferences, ToolPreference, ToolCatalogEntry, EmailAccount, EmailAccountCreate } from "../types/chat";

const BASE = "/api/user";

export async function fetchPreferences(): Promise<UserPreferences> {
  const res = await fetch(`${BASE}/preferences`);
  if (!res.ok) throw new Error("Failed to fetch preferences");
  return res.json();
}

export async function updateSelectedModel(model: string): Promise<void> {
  await fetch(`${BASE}/preferences/model`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model }),
  });
}

export async function fetchToolPreferences(): Promise<ToolPreference[]> {
  const res = await fetch(`${BASE}/tools`);
  if (!res.ok) throw new Error("Failed to fetch tool preferences");
  return res.json();
}

export async function updateToolPreference(
  toolId: string,
  enabled: boolean
): Promise<ToolPreference[]> {
  const res = await fetch(`${BASE}/tools`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tool_id: toolId, enabled }),
  });
  if (!res.ok) throw new Error("Failed to update tool preference");
  return res.json();
}

export async function fetchMCPServers(): Promise<MCPServer[]> {
  const res = await fetch(`${BASE}/mcp-servers`);
  if (!res.ok) throw new Error("Failed to fetch MCP servers");
  return res.json();
}

export async function createMCPServer(
  data: Omit<MCPServer, "id">
): Promise<MCPServer> {
  const res = await fetch(`${BASE}/mcp-servers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create MCP server");
  return res.json();
}

export async function updateMCPServer(
  id: string,
  data: Partial<Omit<MCPServer, "id">>
): Promise<MCPServer> {
  const res = await fetch(`${BASE}/mcp-servers/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update MCP server");
  return res.json();
}

export async function deleteMCPServer(id: string): Promise<void> {
  await fetch(`${BASE}/mcp-servers/${id}`, { method: "DELETE" });
}

export async function toggleMCPServer(
  id: string,
  active: boolean
): Promise<MCPServer> {
  const res = await fetch(`${BASE}/mcp-servers/${id}/toggle`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ active }),
  });
  if (!res.ok) throw new Error("Failed to toggle MCP server");
  return res.json();
}

// ── Email Accounts (multi-account) ─────────────────────────────

export async function fetchEmailAccounts(): Promise<EmailAccount[]> {
  const res = await fetch(`${BASE}/email-accounts`);
  if (!res.ok) throw new Error("Failed to fetch email accounts");
  return res.json();
}

export async function createEmailAccount(
  data: EmailAccountCreate
): Promise<EmailAccount> {
  const res = await fetch(`${BASE}/email-accounts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create email account");
  return res.json();
}

export async function updateEmailAccount(
  id: string,
  data: Partial<EmailAccountCreate>
): Promise<EmailAccount> {
  const res = await fetch(`${BASE}/email-accounts/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update email account");
  return res.json();
}

export async function deleteEmailAccount(id: string): Promise<void> {
  await fetch(`${BASE}/email-accounts/${id}`, { method: "DELETE" });
}

export async function testEmailAccount(id: string): Promise<{
  success: boolean;
  message?: string;
  error?: string;
}> {
  const res = await fetch(`${BASE}/email-accounts/${id}/test`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to test email account");
  return res.json();
}

// ── Tool Catalog & Library ─────────────────────────────────────

export async function fetchToolCatalog(): Promise<ToolCatalogEntry[]> {
  const res = await fetch(`${BASE}/tool-catalog`);
  if (!res.ok) throw new Error("Failed to fetch tool catalog");
  return res.json();
}

export async function fetchToolLibrary(): Promise<string[]> {
  const res = await fetch(`${BASE}/tool-library`);
  if (!res.ok) throw new Error("Failed to fetch tool library");
  return res.json();
}

export async function updateToolLibrary(
  toolId: string,
  action: "add" | "remove"
): Promise<string[]> {
  const res = await fetch(`${BASE}/tool-library`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tool_id: toolId, action }),
  });
  if (!res.ok) throw new Error("Failed to update tool library");
  return res.json();
}

export async function batchUpdateToolLibrary(
  updates: { tool_id: string; action: "add" | "remove" }[]
): Promise<string[]> {
  const res = await fetch(`${BASE}/tool-library/batch`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ updates }),
  });
  if (!res.ok) throw new Error("Failed to batch update tool library");
  return res.json();
}
