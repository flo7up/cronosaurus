import type { Agent, AgentTrigger, Message, SSEEvent, ToolStep } from "../types/chat";

const BASE = "/api/agents";

// ── Status & models ───────────────────────────────────────────

export async function checkStatus(): Promise<{ ready: boolean }> {
  const res = await fetch(`${BASE}/status`);
  const data = await res.json();
  return { ready: data.ready };
}

export async function fetchModels(): Promise<string[]> {
  const res = await fetch(`${BASE}/models`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.models;
}

// ── Agent CRUD ────────────────────────────────────────────────

export async function fetchAgents(): Promise<Agent[]> {
  const res = await fetch(BASE);
  if (!res.ok) throw new Error("Failed to fetch agents");
  return res.json();
}

export async function createAgent(data?: {
  name?: string;
  model?: string;
  tools?: string[];
}): Promise<Agent> {
  const res = await fetch(BASE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data || {}),
  });
  if (!res.ok) throw new Error("Failed to create agent");
  return res.json();
}

export async function getAgent(agentId: string): Promise<Agent> {
  const res = await fetch(`${BASE}/${agentId}`);
  if (!res.ok) throw new Error("Agent not found");
  return res.json();
}

export async function updateAgent(
  agentId: string,
  data: Partial<{ name: string; model: string; tools: string[]; email_account_id: string | null; custom_instructions: string; notification_group_id: string | null }>
): Promise<Agent> {
  const res = await fetch(`${BASE}/${agentId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update agent");
  return res.json();
}

export async function deleteAgent(agentId: string): Promise<void> {
  await fetch(`${BASE}/${agentId}`, { method: "DELETE" });
}

// ── Token count ───────────────────────────────────────────────

export async function fetchTokenCount(agentId: string): Promise<{ token_count: number; context_limit: number }> {
  const res = await fetch(`${BASE}/${agentId}/token-count`);
  if (!res.ok) return { token_count: 0, context_limit: 0 };
  return res.json();
}

// ── Messages ──────────────────────────────────────────────────

export async function fetchMessages(agentId: string): Promise<Message[]> {
  const res = await fetch(`${BASE}/${agentId}/messages`);
  if (!res.ok) throw new Error("Failed to fetch messages");
  const raw = await res.json();
  // Map snake_case tool_steps from API to camelCase toolSteps
  return raw.map((m: Record<string, unknown>) => {
    const msg: Message = {
      role: m.role as "user" | "assistant",
      content: m.content as string,
      created_at: m.created_at as string | undefined,
    };
    if (m.tool_steps && Array.isArray(m.tool_steps) && m.tool_steps.length > 0) {
      msg.toolSteps = m.tool_steps as ToolStep[];
    }
    if (m.images && Array.isArray(m.images) && m.images.length > 0) {
      msg.images = m.images as Array<{ data: string; media_type: string }>;
    }
    return msg;
  });
}

export async function sendMessageStream(
  agentId: string,
  content: string,
  onDelta: (text: string) => void,
  onDone: (fullText: string) => void,
  onError: (error: string) => void,
  signal?: AbortSignal,
  onTriggerUpdate?: () => void,
  onToolCall?: (step: ToolStep) => void,
  onToolResult?: (name: string, result: Record<string, unknown>) => void,
  onNameUpdate?: (name: string) => void,
  images?: Array<{ data: string; media_type: string }>,
  onImage?: (img: { data: string; media_type: string }) => void
): Promise<void> {
  const body: Record<string, unknown> = { content };
  if (images && images.length > 0) {
    body.images = images;
  }
  const res = await fetch(`${BASE}/${agentId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) {
    onError("Failed to send message");
    return;
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          const event: SSEEvent = JSON.parse(line.slice(6));
          switch (event.type) {
            case "delta":
              onDelta(event.content);
              break;
            case "done":
              onDone(event.content);
              break;
            case "error":
              onError(event.content);
              break;
            case "trigger_update":
              onTriggerUpdate?.();
              break;
            case "name_update":
              onNameUpdate?.(event.content);
              break;
            case "tool_call": {
              const tcData = event.data as {
                name: string;
                arguments: Record<string, unknown>;
              };
              onToolCall?.({
                name: tcData.name,
                arguments: tcData.arguments ?? {},
                status: "running",
              });
              break;
            }
            case "tool_result": {
              const trData = event.data as {
                name: string;
                result: Record<string, unknown>;
              };
              onToolResult?.(trData.name, trData.result ?? {});
              break;
            }
            case "image": {
              const imgData = event.data as { data: string; media_type: string };
              if (imgData?.data) onImage?.(imgData);
              break;
            }
          }
        } catch {
          // skip malformed events
        }
      }
    }
  }
}

// ── Thread busy check ─────────────────────────────────────────

export async function checkAgentBusy(
  agentId: string
): Promise<boolean> {
  try {
    const res = await fetch(`${BASE}/${agentId}/busy`);
    if (!res.ok) return false;
    const data = await res.json();
    return data.busy === true;
  } catch {
    return false;
  }
}

// ── Trigger management ────────────────────────────────────────

export async function getAgentTrigger(
  agentId: string
): Promise<AgentTrigger | null> {
  const res = await fetch(`${BASE}/${agentId}/trigger`);
  if (!res.ok) return null;
  return res.json();
}

export async function createAgentTrigger(
  agentId: string,
  data: {
    type?: string;
    interval_minutes?: number;
    prompt: string;
    description?: string;
    filter_from?: string;
    filter_subject?: string;
    filter_body?: string;
    filter_header?: string;
    max_age_minutes?: number;
  }
): Promise<Agent> {
  const res = await fetch(`${BASE}/${agentId}/trigger`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to create trigger");
  }
  return res.json();
}

export async function updateAgentTrigger(
  agentId: string,
  data: Partial<{
    interval_minutes: number;
    prompt: string;
    description: string;
    active: boolean;
    filter_from: string;
    filter_subject: string;
    filter_body: string;
    filter_header: string;
    max_age_minutes: number;
  }>
): Promise<Agent> {
  const res = await fetch(`${BASE}/${agentId}/trigger`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update trigger");
  return res.json();
}

export async function deleteAgentTrigger(agentId: string): Promise<void> {
  await fetch(`${BASE}/${agentId}/trigger`, { method: "DELETE" });
}

export interface TriggerTestResult {
  type: string;
  error?: string;
  prompt?: string;
  description?: string;
  preview?: string;
  explanation?: string;
  interval_minutes?: number;
  filters?: Record<string, unknown>;
  matching_emails?: Array<{
    uid: number;
    from: string;
    subject: string;
    date: string;
    agent_input_preview: string;
  }>;
  total_matches?: number;
}

export async function testAgentTrigger(agentId: string): Promise<TriggerTestResult> {
  const res = await fetch(`${BASE}/${agentId}/trigger/test`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to test trigger");
  }
  return res.json();
}
