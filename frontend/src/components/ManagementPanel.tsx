import { useState, useEffect, useCallback } from "react";
import ToggleSwitch from "./ToggleSwitch";
import type {
  Agent,
  MCPServer,
  EmailAccount,
  EmailAccountCreate,
  ToolCatalogEntry,
  AppSettings,
} from "../types/chat";
import { fetchToolCatalog, updateToolLibrary, batchUpdateToolLibrary } from "../api/user";
import { updateAgentTrigger, testAgentTrigger } from "../api/agent";
import { fetchSettings, updateSettings, testFoundryConnection, testCosmosConnection, fetchDeployments, fetchProviderModels } from "../api/settings";
import type { FoundryDeployment } from "../api/settings";
import type { NotificationChannel, DistributionGroup } from "../api/notification";
import {
  fetchNotificationChannels,
  addNotificationChannel,
  updateNotificationChannel,
  deleteNotificationChannel,
  testNotificationChannel,
  fetchDistributionGroups,
  addDistributionGroup,
  updateDistributionGroup,
  deleteDistributionGroup,
} from "../api/notification";

// ── Types ──────────────────────────────────────────────────

type Tab = "tools" | "triggers" | "email" | "mcp" | "notifications" | "appearance" | "settings";

interface ManagementPanelProps {
  defaultTab?: Tab;
  onClose: () => void;
  // Tools
  emailAccounts: EmailAccount[];
  onToolLibraryChange: (library: string[]) => void;
  // Triggers
  agents: Agent[];
  activeAgent: Agent | null;
  onSelectAgent: (agentId: string) => void;
  onAgentsChange: (agents: Agent[]) => void;
  onCreateTrigger: (data: {
    type?: string;
    interval_minutes?: number;
    prompt: string;
    description?: string;
    filter_from?: string;
    filter_subject?: string;
    filter_body?: string;
    filter_header?: string;
    max_age_minutes?: number;
  }) => void;
  onUpdateTrigger: (
    data: Partial<{
      interval_minutes: number;
      prompt: string;
      description: string;
      filter_from: string;
      filter_subject: string;
      filter_body: string;
      filter_header: string;
      max_age_minutes: number;
    }>
  ) => void;
  onToggleTrigger: (active: boolean) => void;
  onDeleteTrigger: () => void;
  // Email
  onAddEmail: (data: EmailAccountCreate) => Promise<void>;
  onUpdateEmail: (
    id: string,
    data: Partial<EmailAccountCreate>
  ) => Promise<void>;
  onDeleteEmail: (id: string) => Promise<void>;
  onTestEmail: (
    id: string
  ) => Promise<{ success: boolean; message?: string; error?: string }>;
  // MCP
  mcpServers: MCPServer[];
  onAddMCP: (server: Omit<MCPServer, "id">) => void;
  onDeleteMCP: (id: string) => void;
  onToggleMCP: (id: string, active: boolean) => void;
  onUpdateMCP: (
    id: string,
    data: Partial<Omit<MCPServer, "id">>
  ) => void;
}

// ── Tab metadata ───────────────────────────────────────────

const TABS: { id: Tab; label: string; description: string }[] = [
  { id: "tools", label: "Tools", description: "Manage available tools" },
  { id: "triggers", label: "Triggers", description: "Agent automations" },
  { id: "email", label: "Email", description: "Account settings" },
  { id: "mcp", label: "MCP Servers", description: "External tool servers" },
  { id: "notifications", label: "Notifications", description: "Channels & groups" },
  { id: "appearance", label: "Appearance", description: "Theme & display" },
  { id: "settings", label: "Connections", description: "Foundry & models" },
];

// ── Main component ─────────────────────────────────────────

export default function ManagementPanel({
  defaultTab = "tools",
  onClose,
  emailAccounts,
  onToolLibraryChange,
  agents,
  activeAgent,
  onSelectAgent,
  onAgentsChange,
  onCreateTrigger,
  onUpdateTrigger,
  onToggleTrigger,
  onDeleteTrigger,
  onAddEmail,
  onUpdateEmail,
  onDeleteEmail,
  onTestEmail,
  mcpServers,
  onAddMCP,
  onDeleteMCP,
  onToggleMCP,
  onUpdateMCP,
}: ManagementPanelProps) {
  const [activeTab, setActiveTab] = useState<Tab>(defaultTab);
  useEffect(() => setActiveTab(defaultTab), [defaultTab]);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  const activeTriggers = agents.filter((a) => a.trigger?.active).length;
  const emailCount = emailAccounts.length;
  const mcpCount = mcpServers.filter((s) => s.active).length;

  // Toggle trigger for any agent (used by overview)
  const handleToggleAnyTrigger = useCallback(async (agentId: string, active: boolean) => {
    try {
      const updated = await updateAgentTrigger(agentId, { active });
      onAgentsChange(agents.map((a) => (a.id === updated.id ? updated : a)));
    } catch (e) {
      console.error("Failed to toggle trigger", e);
    }
  }, [agents, onAgentsChange]);



  return (
    <div
      className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="app-modal w-full max-w-5xl h-[85vh] flex flex-col rounded-2xl overflow-hidden">
        <div className="terminal-titlebar px-6">cronosaurus :: control panel</div>
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#3dd8c5]/10">
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-teal-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z"
              />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <h2 className="text-lg font-semibold text-[#b0f0e8] uppercase tracking-[0.12em]">Settings</h2>
          </div>
          <button
            onClick={onClose}
            className="terminal-control p-1.5 text-[#78adb8] hover:text-[#b0f0e8] transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex flex-1 overflow-hidden">
          {/* Tab sidebar */}
          <nav className="w-52 border-r border-[#3dd8c5]/10 p-3 space-y-1 shrink-0">
            {TABS.map((tab) => {
              const badge =
                tab.id === "triggers" && activeTriggers > 0 ? activeTriggers
                : tab.id === "email" && emailCount > 0 ? emailCount
                : tab.id === "mcp" && mcpCount > 0 ? mcpCount
                : 0;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left text-sm transition-colors ${
                    activeTab === tab.id
                      ? "bg-[#241b10] text-[#b0f0e8] ring-1 ring-teal-200/10"
                      : "text-[#78adb8] hover:bg-[#0f161b]/75 hover:text-[#c9f6ef]"
                  }`}
                >
                  <TabIcon tab={tab.id} active={activeTab === tab.id} />
                  <div className="flex-1 min-w-0">
                    <div className="font-medium">{tab.label}</div>
                    <div className="text-[11px] text-[#426d6d] truncate">{tab.description}</div>
                  </div>
                  {badge > 0 && (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full shrink-0 ${
                      tab.id === "triggers"
                        ? "bg-amber-900/40 text-amber-400"
                        : tab.id === "email"
                          ? "bg-[#0f1812] text-[#97ff8a]"
                          : "bg-[#25150b] text-[#ffcf67]"
                    }`}>
                      {badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-6">
            {activeTab === "tools" && (
              <ToolsTab
                emailAccounts={emailAccounts}
                onToolLibraryChange={onToolLibraryChange}
                onSwitchToEmail={() => setActiveTab("email")}
              />
            )}
            {activeTab === "triggers" && (
              <TriggersTab
                agents={agents}
                activeAgent={activeAgent}
                onCreate={onCreateTrigger}
                onUpdate={onUpdateTrigger}
                onToggle={onToggleTrigger}
                onDelete={onDeleteTrigger}
                onSelectAgent={(id) => { onSelectAgent(id); }}
                onToggleAnyTrigger={handleToggleAnyTrigger}
              />
            )}
            {activeTab === "email" && (
              <EmailTab
                accounts={emailAccounts}
                onAdd={onAddEmail}
                onUpdate={onUpdateEmail}
                onDelete={onDeleteEmail}
                onTest={onTestEmail}
              />
            )}
            {activeTab === "mcp" && (
              <MCPTab
                servers={mcpServers}
                onAdd={onAddMCP}
                onDelete={onDeleteMCP}
                onToggle={onToggleMCP}
                onUpdate={onUpdateMCP}
              />
            )}
            {activeTab === "settings" && <SettingsTab />}
            {activeTab === "notifications" && <NotificationsTab />}
            {activeTab === "appearance" && <AppearanceTab />}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Tab icon ───────────────────────────────────────────────

function TabIcon({ tab, active }: { tab: Tab; active: boolean }) {
  const cls = `w-5 h-5 ${active ? "text-teal-300" : ""}`;
  switch (tab) {
    case "tools":
      return (
        <svg className={cls} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M21.75 6.75a4.5 4.5 0 01-4.884 4.484c-1.076-.091-2.264.071-2.95.904l-7.152 8.684a2.548 2.548 0 11-3.586-3.586l8.684-7.152c.833-.686.995-1.874.904-2.95a4.5 4.5 0 016.336-4.486l-3.276 3.276a3.004 3.004 0 002.25 2.25l3.276-3.276c.256.565.398 1.192.398 1.852z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4.867 19.125h.008v.008h-.008v-.008z" />
        </svg>
      );
    case "triggers":
      return (
        <svg className={cls} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      );
    case "email":
      return (
        <svg className={cls} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
        </svg>
      );
    case "mcp":
      return (
        <svg className={cls} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
        </svg>
      );
    case "settings":
      return (
        <svg className={cls} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M10.343 3.94c.09-.542.56-.94 1.11-.94h1.093c.55 0 1.02.398 1.11.94l.149.894c.07.424.384.764.78.93.398.164.855.142 1.205-.108l.737-.527a1.125 1.125 0 011.45.12l.773.774c.39.389.44 1.002.12 1.45l-.527.737c-.25.35-.272.806-.107 1.204.165.397.505.71.93.78l.893.15c.543.09.94.56.94 1.109v1.094c0 .55-.397 1.02-.94 1.11l-.893.149c-.425.07-.765.383-.93.78-.165.398-.143.854.107 1.204l.527.738c.32.447.269 1.06-.12 1.45l-.774.773a1.125 1.125 0 01-1.449.12l-.738-.527c-.35-.25-.806-.272-1.204-.107-.397.165-.71.505-.78.929l-.15.894c-.09.542-.56.94-1.11.94h-1.094c-.55 0-1.019-.398-1.11-.94l-.148-.894c-.071-.424-.384-.764-.781-.93-.398-.164-.854-.142-1.204.108l-.738.527c-.447.32-1.06.269-1.45-.12l-.773-.774a1.125 1.125 0 01-.12-1.45l.527-.737c.25-.35.273-.806.108-1.204-.165-.397-.506-.71-.93-.78l-.894-.15c-.542-.09-.94-.56-.94-1.109v-1.094c0-.55.398-1.02.94-1.11l.894-.149c.424-.07.765-.383.93-.78.165-.398.143-.854-.107-1.204l-.527-.738a1.125 1.125 0 01.12-1.45l.773-.773a1.125 1.125 0 011.45-.12l.737.527c.35.25.807.272 1.204.107.397-.165.71-.505.78-.929l.15-.894z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      );
    case "notifications":
      return (
        <svg className={cls} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
        </svg>
      );
    case "appearance":
      return (
        <svg className={cls} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M4.098 19.902a3.75 3.75 0 005.304 0l6.401-6.402M6.75 21A3.75 3.75 0 013 17.25V4.125C3 3.504 3.504 3 4.125 3h5.25c.621 0 1.125.504 1.125 1.125v4.072M6.75 21a3.75 3.75 0 003.75-3.75V8.197M6.75 21h13.125c.621 0 1.125-.504 1.125-1.125v-5.25c0-.621-.504-1.125-1.125-1.125h-4.072M10.5 8.197l2.88-2.88c.438-.439 1.15-.439 1.59 0l3.712 3.713c.44.44.44 1.152 0 1.59l-2.879 2.88M6.75 17.25h.008v.008H6.75v-.008z" />
        </svg>
      );
  }
}

// ══════════════════════════════════════════════════════════
//  TOOLS TAB
// ══════════════════════════════════════════════════════════

const TOOL_ICONS: Record<string, React.ReactNode> = {
  crypto: (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  stock: (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
    </svg>
  ),
  email_send: (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
    </svg>
  ),
  email_read: (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
    </svg>
  ),
  triggers: (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
};

function ToolRow({ tool, onToggle }: { tool: ToolCatalogEntry; onToggle: () => void }) {
  const icon = TOOL_ICONS[tool.id];
  const needsConfig = tool.requires_config && !tool.available;
  return (
    <button
      onClick={onToggle}
      className="w-full flex items-center gap-3 px-3 py-3 hover:bg-[#0f161b] transition-colors"
    >
      <span className={tool.in_library ? "text-[#97ff8a]" : "text-[#486d78]"}>
        {icon || (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M4.5 12a7.5 7.5 0 0015 0m-15 0a7.5 7.5 0 1115 0m-15 0H3m16.5 0H21" />
          </svg>
        )}
      </span>
      <div className="flex-1 text-left">
        <div className="flex items-center gap-2">
          <span className={`text-sm font-medium ${tool.in_library ? "text-[#c9f6ef]" : "text-[#649b8f]"}`}>
            {tool.label}
          </span>
          {needsConfig && (
            <span className="terminal-chip text-[10px] px-1.5 py-0.5 text-yellow-300">
              Needs setup
            </span>
          )}
        </div>
        <div className="text-xs text-[#486d78] mt-0.5">{tool.description}</div>
      </div>
      <ToggleSwitch
        checked={tool.in_library}
        accent="teal"
        className="pointer-events-none"
      />
    </button>
  );
}

function ToolsTab({
  emailAccounts,
  onToolLibraryChange,
  onSwitchToEmail,
}: {
  emailAccounts: EmailAccount[];
  onToolLibraryChange: (library: string[]) => void;
  onSwitchToEmail: () => void;
}) {
  const [catalog, setCatalog] = useState<ToolCatalogEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchToolCatalog()
      .then(setCatalog)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!loading) {
      fetchToolCatalog().then(setCatalog).catch(() => {});
    }
  }, [emailAccounts]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleToggle = async (toolId: string, inLibrary: boolean) => {
    // Optimistic update — flip UI immediately
    setCatalog((prev) =>
      prev.map((t) => (t.id === toolId ? { ...t, in_library: !inLibrary } : t))
    );
    try {
      const newLib = await updateToolLibrary(toolId, inLibrary ? "remove" : "add");
      onToolLibraryChange(newLib);
    } catch {
      // Revert on failure
      setCatalog((prev) =>
        prev.map((t) => (t.id === toolId ? { ...t, in_library: inLibrary } : t))
      );
    }
  };

  const handleBatchToggle = async (tools: ToolCatalogEntry[], enable: boolean) => {
    const toChange = tools.filter((t) => t.in_library !== enable);
    if (toChange.length === 0) return;
    const changeIds = new Set(toChange.map((t) => t.id));
    // Optimistic update — flip all immediately
    setCatalog((prev) =>
      prev.map((t) => (changeIds.has(t.id) ? { ...t, in_library: enable } : t))
    );
    try {
      const action = enable ? "add" : "remove";
      const latestLib = await batchUpdateToolLibrary(
        toChange.map((t) => ({ tool_id: t.id, action: action as "add" | "remove" }))
      );
      onToolLibraryChange(latestLib);
    } catch {
      // Revert all on failure
      setCatalog((prev) =>
        prev.map((t) => (changeIds.has(t.id) ? { ...t, in_library: !enable } : t))
      );
    }
  };

  const emailToolIds = ["email_send", "email_read"];
  const [toolSearch, setToolSearch] = useState("");
  const searchLower = toolSearch.toLowerCase();
  const filteredCatalog = toolSearch
    ? catalog.filter(t => t.label.toLowerCase().includes(searchLower) || t.description.toLowerCase().includes(searchLower) || t.id.toLowerCase().includes(searchLower))
    : catalog;
  const builtIn = filteredCatalog.filter((t) => !emailToolIds.includes(t.id) && t.category !== "mcp");
  const emailEntries = filteredCatalog.filter((t) => emailToolIds.includes(t.id));
  const mcpEntries = filteredCatalog.filter((t) => t.category === "mcp");
  const defaultAccount = emailAccounts.find((a) => a.is_default) ?? emailAccounts[0] ?? null;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-gray-500">
        Loading tools...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <p className="text-sm text-gray-400">
        Manage the tools available when building agents. Only tools in your
        library will appear in the agent configuration.
      </p>

      {/* Search bar */}
      <div className="relative">
        <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#486d78]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
        </svg>
        <input
          type="text"
          value={toolSearch}
          onChange={(e) => setToolSearch(e.target.value)}
          placeholder="Search tools..."
          className="terminal-control w-full pl-9 pr-3 py-2 text-sm"
        />
        {toolSearch && (
          <button onClick={() => setToolSearch("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-[#486d78] hover:text-[#8adcca]">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        )}
      </div>

      {toolSearch && filteredCatalog.length === 0 && (
        <p className="text-sm text-[#486d78] text-center py-8">No tools matching "{toolSearch}"</p>
      )}

      {/* Built-in tools */}
      {builtIn.length > 0 && (
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            {toolSearch ? `Built-in Tools (${builtIn.length})` : "Built-in Tools"}
          </h3>
          {!toolSearch && (
          <div className="flex gap-1.5">
            <button
              onClick={() => handleBatchToggle(catalog.filter((t) => !emailToolIds.includes(t.id) && t.category !== "mcp"), true)}
              disabled={catalog.filter((t) => !emailToolIds.includes(t.id) && t.category !== "mcp").every((t) => t.in_library)}
              className="px-2 py-0.5 text-[10px] rounded bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            >
              Enable all
            </button>
            <button
              onClick={() => handleBatchToggle(catalog.filter((t) => !emailToolIds.includes(t.id) && t.category !== "mcp"), false)}
              disabled={catalog.filter((t) => !emailToolIds.includes(t.id) && t.category !== "mcp").every((t) => !t.in_library)}
              className="px-2 py-0.5 text-[10px] rounded bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            >
              Disable all
            </button>
          </div>
          )}
        </div>
        <div className="space-y-1">
          {builtIn.map((tool) => (
            <ToolRow
              key={tool.id}
              tool={tool}
              onToggle={() => handleToggle(tool.id, tool.in_library)}
            />
          ))}
        </div>
      </div>
      )}

      {/* Email tools */}
      {emailEntries.length > 0 && (
      <div>
        <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">
          Email Tools
        </h3>
        <div className="space-y-1">
          {emailEntries.map((tool) => (
            <ToolRow
              key={tool.id}
              tool={tool}
              onToggle={() => handleToggle(tool.id, tool.in_library)}
            />
          ))}
        </div>
        <div className="mt-3 rounded-lg bg-gray-800/50 border border-gray-700/50 p-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {defaultAccount ? (
                <>
                  <span className="w-2 h-2 rounded-full bg-green-400" />
                  <span className="text-xs text-gray-300">
                    {defaultAccount.label || defaultAccount.from_email}
                  </span>
                  {emailAccounts.length > 1 && (
                    <span className="text-[10px] bg-blue-900/40 text-blue-400 px-1.5 py-0.5 rounded-full">
                      +{emailAccounts.length - 1} more
                    </span>
                  )}
                  {defaultAccount.imap_host ? (
                    <span className="text-[10px] bg-green-900/40 text-green-400 px-1.5 py-0.5 rounded-full">
                      SMTP + IMAP
                    </span>
                  ) : (
                    <span className="text-[10px] bg-yellow-900/40 text-yellow-400 px-1.5 py-0.5 rounded-full">
                      SMTP only
                    </span>
                  )}
                </>
              ) : (
                <>
                  <span className="w-2 h-2 rounded-full bg-gray-600" />
                  <span className="text-xs text-gray-500">No email accounts configured</span>
                </>
              )}
            </div>
            <button
              onClick={onSwitchToEmail}
              className="px-3 py-1 text-xs rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 hover:text-white transition-colors"
            >
              {defaultAccount ? "Manage" : "Set Up"}
            </button>
          </div>
        </div>
      </div>
      )}

      {/* MCP Server tools */}
      {mcpEntries.length > 0 && (
        <div>
          <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">
            MCP Servers
          </h3>
          <div className="space-y-1">
            {mcpEntries.map((tool) => (
              <ToolRow
                key={tool.id}
                tool={tool}
                onToggle={() => handleToggle(tool.id, tool.in_library)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Build Your Own Tool */}
      <details className="group mt-2">
        <summary className="flex items-center gap-2 cursor-pointer text-xs font-medium text-gray-500 uppercase tracking-wider select-none">
          <svg className="w-4 h-4 text-amber-500 transition-transform group-open:rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
          Build Your Own Tool
        </summary>
        <div className="mt-3 p-4 bg-gray-800/60 border border-gray-700 rounded-lg text-sm text-gray-300 space-y-3">
          <p>Drop a single Python file into the <code className="text-amber-400 bg-gray-900 px-1 rounded">backend/app/tools/custom/</code> folder and restart — it auto-registers.</p>
          <ol className="list-decimal list-inside space-y-2 text-gray-400">
            <li>
              Copy the template: <code className="text-amber-400 bg-gray-900 px-1 rounded">_template.py</code> → <code className="text-amber-400 bg-gray-900 px-1 rounded">my_tools.py</code>
            </li>
            <li>
              Edit <code className="text-amber-400 bg-gray-900 px-1 rounded">TOOL_META</code>, <code className="text-amber-400 bg-gray-900 px-1 rounded">TOOL_DEFINITIONS</code>, and <code className="text-amber-400 bg-gray-900 px-1 rounded">execute_tool()</code>
            </li>
            <li>
              Restart the backend — your tool appears here automatically
            </li>
          </ol>
          <p className="text-gray-500 text-xs mt-1">
            No other files need editing. The auto-loader handles catalog registration and dispatch.
          </p>
          <p className="text-gray-500 text-xs">
            Full guide →{" "}
            <a href="https://github.com/ffollonier/cronosaurus/blob/main/CONTRIBUTING.md" target="_blank" rel="noopener noreferrer" className="text-amber-500 hover:text-amber-400 underline">
              CONTRIBUTING.md
            </a>
          </p>
        </div>
      </details>
    </div>
  );
}

// ══════════════════════════════════════════════════════════
//  TRIGGERS TAB
// ══════════════════════════════════════════════════════════

const INTERVAL_PRESETS = [
  { label: "10 min", value: 10 },
  { label: "15 min", value: 15 },
  { label: "30 min", value: 30 },
  { label: "1 hour", value: 60 },
  { label: "6 hours", value: 360 },
  { label: "Daily", value: 1440 },
];

function TriggersTab({
  agents,
  activeAgent,
  onCreate,
  onUpdate,
  onToggle,
  onDelete,
  onSelectAgent,
  onToggleAnyTrigger,
}: {
  agents: Agent[];
  activeAgent: Agent | null;
  onCreate: ManagementPanelProps["onCreateTrigger"];
  onUpdate: ManagementPanelProps["onUpdateTrigger"];
  onToggle: (active: boolean) => void;
  onDelete: () => void;
  onSelectAgent: (agentId: string) => void;
  onToggleAnyTrigger: (agentId: string, active: boolean) => void;
}) {
  const agentsWithTriggers = agents.filter((a) => a.trigger != null);
  const trigger = activeAgent?.trigger ?? null;
  const [editing, setEditing] = useState(!trigger);
  const [testResult, setTestResult] = useState<import("../api/agent").TriggerTestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [triggerType, setTriggerType] = useState<"regular" | "gmail_push">(
    (trigger?.type as "regular" | "gmail_push") ?? "regular"
  );
  const [interval, setIntervalVal] = useState(trigger?.interval_minutes ?? 60);
  const [customInterval, setCustomInterval] = useState("");
  const [prompt, setPrompt] = useState(trigger?.prompt ?? "");
  const [description, setDescription] = useState(trigger?.description ?? "");
  const [filterFrom, setFilterFrom] = useState(trigger?.filter_from ?? "");
  const [filterSubject, setFilterSubject] = useState(trigger?.filter_subject ?? "");
  const [filterBody, setFilterBody] = useState(trigger?.filter_body ?? "");
  const [filterHeader, setFilterHeader] = useState(trigger?.filter_header ?? "");
  const [maxAgeMinutes, setMaxAgeMinutes] = useState(trigger?.max_age_minutes ?? 0);
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Sync state when agent or trigger changes
  useEffect(() => {
    setEditing(!trigger);
    setTriggerType((trigger?.type as "regular" | "gmail_push") ?? "regular");
    setIntervalVal(trigger?.interval_minutes ?? 60);
    setCustomInterval("");
    setPrompt(trigger?.prompt ?? "");
    setDescription(trigger?.description ?? "");
    setFilterFrom(trigger?.filter_from ?? "");
    setFilterSubject(trigger?.filter_subject ?? "");
    setFilterBody(trigger?.filter_body ?? "");
    setFilterHeader(trigger?.filter_header ?? "");
    setMaxAgeMinutes(trigger?.max_age_minutes ?? 0);
    setConfirmDelete(false);
  }, [activeAgent?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Re-sync display fields when trigger data updates from server
  useEffect(() => {
    if (trigger && !editing) {
      setTriggerType((trigger.type as "regular" | "gmail_push") ?? "regular");
      setIntervalVal(trigger.interval_minutes ?? 60);
      setPrompt(trigger.prompt ?? "");
      setDescription(trigger.description ?? "");
      setFilterFrom(trigger.filter_from ?? "");
      setFilterSubject(trigger.filter_subject ?? "");
      setFilterBody(trigger.filter_body ?? "");
      setFilterHeader(trigger.filter_header ?? "");
      setMaxAgeMinutes(trigger.max_age_minutes ?? 0);
    }
    if (!trigger) setEditing(true);
  }, [trigger]); // eslint-disable-line react-hooks/exhaustive-deps

  const fmtOverview = (iso: string | null) => {
    if (!iso) return "-";
    try { return new Date(iso).toLocaleString(); } catch { return iso; }
  };

  // ── All triggers overview (always shown) ──
  const overviewSection = (
    <div className="space-y-4 mb-8">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">All Triggers</h3>
        <span className="text-xs text-gray-500">
          {agentsWithTriggers.length} trigger{agentsWithTriggers.length !== 1 ? "s" : ""} configured
        </span>
      </div>

      {agentsWithTriggers.length === 0 ? (
        <div className="text-center py-8 text-gray-500">
          <svg className="w-10 h-10 mx-auto mb-2 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-sm">No triggers configured on any agent</p>
          <p className="text-xs text-gray-600 mt-1">Select an agent below to create one</p>
        </div>
      ) : (
        <div className="space-y-2">
          {agentsWithTriggers.map((agent) => {
            const t = agent.trigger!;
            const isCurrentAgent = agent.id === activeAgent?.id;
            return (
              <div
                key={agent.id}
                className={`bg-gray-800/60 border rounded-lg p-3 transition-colors ${
                  isCurrentAgent ? "border-purple-500/50" : "border-gray-700/50 hover:border-gray-600"
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2 min-w-0">
                    {t.type === "gmail_push" ? (
                      <svg className={`w-4 h-4 shrink-0 ${t.active ? "text-red-400" : "text-gray-600"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                          d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                      </svg>
                    ) : (
                      <svg className={`w-4 h-4 shrink-0 ${t.active ? "text-amber-400" : "text-gray-600"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                          d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    )}
                    <button
                      onClick={() => onSelectAgent(agent.id)}
                      className="text-sm font-medium text-white truncate hover:text-purple-300 transition-colors text-left"
                      title={`Switch to ${agent.name}`}
                    >
                      {agent.name}
                    </button>
                    {isCurrentAgent && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-purple-900/40 text-purple-400 shrink-0">
                        current
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                      t.active ? "bg-green-900/40 text-green-400" : "bg-gray-700 text-gray-500"
                    }`}>
                      {t.active ? "Active" : "Paused"}
                    </span>
                    <ToggleSwitch
                      checked={t.active}
                      onToggle={() => onToggleAnyTrigger(agent.id, !t.active)}
                      accent="green"
                      size="sm"
                      title={t.active ? "Pause trigger" : "Activate trigger"}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-gray-400">
                  <div>
                    <span className="text-gray-500">Type: </span>
                    {t.type === "gmail_push" ? "Gmail Push" : `Scheduled (${t.interval_minutes}m)`}
                  </div>
                  <div>
                    <span className="text-gray-500">Runs: </span>
                    {t.run_count}
                  </div>
                  {t.description && (
                    <div className="col-span-2 truncate">
                      <span className="text-gray-500">Desc: </span>
                      {t.description}
                    </div>
                  )}
                  <div>
                    <span className="text-gray-500">Last: </span>
                    {fmtOverview(t.last_run)}
                  </div>
                  {t.type === "regular" && (
                    <div>
                      <span className="text-gray-500">Next: </span>
                      {fmtOverview(t.next_run)}
                    </div>
                  )}
                  {t.type === "gmail_push" && t.active && (
                    <div className="flex items-center gap-1">
                      <span className="relative flex h-1.5 w-1.5">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                        <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-green-500" />
                      </span>
                      Watching inbox
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );

  if (!activeAgent) {
    return (
      <div className="max-w-xl">
        {overviewSection}
        <div className="border-t border-gray-800 pt-6">
          <div className="flex flex-col items-center justify-center py-8 text-gray-500">
            <svg className="w-10 h-10 mb-2 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="text-sm">Select an agent to configure its trigger</p>
          </div>
        </div>
      </div>
    );
  }

  const effectiveInterval =
    customInterval && parseInt(customInterval, 10) >= 1
      ? parseInt(customInterval, 10)
      : interval;

  const handleSave = () => {
    if (!prompt.trim()) return;
    if (trigger) {
      const data: Record<string, unknown> = {
        prompt: prompt.trim(),
        description: description.trim(),
      };
      if (triggerType === "regular") {
        data.interval_minutes = effectiveInterval;
      } else {
        data.filter_from = filterFrom.trim();
        data.filter_subject = filterSubject.trim();
        data.filter_body = filterBody.trim();
        data.filter_header = filterHeader.trim();
        data.max_age_minutes = maxAgeMinutes;
      }
      onUpdate(data as Parameters<typeof onUpdate>[0]);
    } else {
      if (triggerType === "gmail_push") {
        onCreate({
          type: "gmail_push",
          prompt: prompt.trim(),
          description: description.trim(),
          filter_from: filterFrom.trim(),
          filter_subject: filterSubject.trim(),
          filter_body: filterBody.trim(),
          filter_header: filterHeader.trim(),
          max_age_minutes: maxAgeMinutes,
        });
      } else {
        onCreate({
          type: "regular",
          interval_minutes: effectiveInterval,
          prompt: prompt.trim(),
          description: description.trim(),
        });
      }
    }
    setEditing(false);
  };

  const fmt = (iso: string | null) => {
    if (!iso) return "-";
    try { return new Date(iso).toLocaleString(); } catch { return iso; }
  };

  return (
    <div className="space-y-5 max-w-xl">
      {/* All triggers overview */}
      {overviewSection}

      {/* Divider between overview and current agent detail */}
      <div className="border-t border-gray-800 pt-5">

      {/* Agent context */}
      <div className="flex items-center gap-2 text-sm text-gray-400">
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714a2.25 2.25 0 00.659 1.591L19 14.5M14.25 3.104c.251.023.501.05.75.082M19 14.5l-2.47 2.47" />
        </svg>
        Trigger for <strong className="text-white ml-1">{activeAgent.name}</strong>
      </div>

      {/* ── Status display ── */}
      {trigger && !editing && (
        <>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400">Status</span>
              <div className="flex items-center gap-2">
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  trigger.active ? "bg-green-900/40 text-green-400" : "bg-gray-800 text-gray-500"
                }`}>
                  {trigger.active ? "Active" : "Paused"}
                </span>
                <ToggleSwitch
                  checked={trigger.active}
                  onToggle={() => onToggle(!trigger.active)}
                  accent="green"
                  title={trigger.active ? "Pause trigger" : "Activate trigger"}
                />
              </div>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400">Type</span>
              <span className="text-sm text-white flex items-center gap-1.5">
                {trigger.type === "gmail_push" ? (
                  <>
                    <svg className="w-4 h-4 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                    </svg>
                    Gmail Push
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    Scheduled
                  </>
                )}
              </span>
            </div>

            {trigger.type === "regular" && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">Interval</span>
                <span className="text-sm text-white">Every {trigger.interval_minutes} min</span>
              </div>
            )}

            {trigger.type === "gmail_push" && trigger.filter_from && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">Filter from</span>
                <span className="text-sm text-white font-mono text-xs">{trigger.filter_from}</span>
              </div>
            )}
            {trigger.type === "gmail_push" && trigger.filter_subject && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">Filter subject</span>
                <span className="text-sm text-white">{trigger.filter_subject}</span>
              </div>
            )}
            {trigger.type === "gmail_push" && trigger.filter_body && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">Filter body</span>
                <span className="text-sm text-white">{trigger.filter_body}</span>
              </div>
            )}
            {trigger.type === "gmail_push" && trigger.filter_header && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">Filter header</span>
                <span className="text-sm text-white">{trigger.filter_header}</span>
              </div>
            )}
            {trigger.type === "gmail_push" && (trigger.max_age_minutes ?? 0) > 0 && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">Max age</span>
                <span className="text-sm text-white">{trigger.max_age_minutes} min</span>
              </div>
            )}

            <div>
              <span className="text-sm text-gray-400">Prompt</span>
              <p className="text-sm text-white mt-1 bg-gray-800/50 rounded-lg px-3 py-2">
                {trigger.prompt}
              </p>
            </div>

            {trigger.description && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">Description</span>
                <span className="text-sm text-white">{trigger.description}</span>
              </div>
            )}

            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400">Last run</span>
              <span className="text-sm text-white">{fmt(trigger.last_run)}</span>
            </div>
            {trigger.type === "regular" && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">Next run</span>
                <span className="text-sm text-white">{fmt(trigger.next_run)}</span>
              </div>
            )}
            {trigger.type === "gmail_push" && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">Mode</span>
                <span className="text-sm text-white flex items-center gap-1.5">
                  {trigger.active ? (
                    <>
                      <span className="relative flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
                      </span>
                      Watching inbox
                    </>
                  ) : "Paused"}
                </span>
              </div>
            )}
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400">Total runs</span>
              <span className="text-sm text-white">{trigger.run_count}</span>
            </div>
          </div>

          <div className="flex gap-2 pt-2">
            <button
              onClick={async () => {
                if (!activeAgent) return;
                setTesting(true);
                setTestResult(null);
                try {
                  const result = await testAgentTrigger(activeAgent.id);
                  setTestResult(result);
                } catch (e) {
                  setTestResult({ type: "error", error: String(e) });
                } finally {
                  setTesting(false);
                }
              }}
              disabled={testing}
              className="px-4 py-2 bg-gray-800 text-white text-sm rounded-lg hover:bg-gray-700 transition-colors flex items-center gap-1.5 disabled:opacity-50"
            >
              {testing ? (
                <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
              ) : (
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
              )}
              Test
            </button>
            <button
              onClick={() => setEditing(true)}
              className="px-4 py-2 bg-gray-800 text-white text-sm rounded-lg hover:bg-gray-700 transition-colors"
            >
              Edit
            </button>
            {!confirmDelete ? (
              <button
                onClick={() => setConfirmDelete(true)}
                className="px-4 py-2 bg-gray-800 text-red-400 text-sm rounded-lg hover:bg-red-900/30 transition-colors"
              >
                Delete
              </button>
            ) : (
              <div className="flex items-center gap-2">
                <span className="text-xs text-red-400">Are you sure?</span>
                <button
                  onClick={() => { onDelete(); setConfirmDelete(false); }}
                  className="px-3 py-1.5 bg-red-600 text-white text-xs rounded-lg hover:bg-red-700 transition-colors"
                >
                  Yes, delete
                </button>
                <button
                  onClick={() => setConfirmDelete(false)}
                  className="px-3 py-1.5 bg-gray-800 text-gray-300 text-xs rounded-lg hover:bg-gray-700 transition-colors"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>

          {/* Test result preview */}
          {testResult && (
            <div className="terminal-panel mt-3 overflow-hidden">
              <div className="terminal-titlebar">trigger test result</div>
              <div className="p-3 space-y-3 text-sm">
                {testResult.error ? (
                  <div className="text-red-400 text-xs">{testResult.error}</div>
                ) : testResult.type === "regular" ? (
                  <div className="space-y-2">
                    <div className="terminal-label text-[#97ff8a] mb-1">prompt that will be sent every {testResult.interval_minutes} minutes:</div>
                    <div className="terminal-bubble px-3 py-2 text-xs text-[#e0f5d0] whitespace-pre-wrap">{testResult.preview}</div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="terminal-label text-[#97ff8a] mb-1">
                      {testResult.total_matches ?? 0} matching email(s) found
                    </div>
                    <div className="text-xs text-[#597f8b]">{testResult.explanation || ""}</div>
                    {(testResult.matching_emails || []).map((em, i) => (
                      <details key={i} className="group">
                        <summary className="terminal-control flex items-center gap-2 px-2.5 py-2 text-xs cursor-pointer select-none">
                          <svg className="w-3 h-3 transition-transform group-open:rotate-90 text-[#97ff8a]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
                          <span className="text-[#8adcca] truncate flex-1">{em.subject}</span>
                          <span className="text-[#486d78] shrink-0">{em.from}</span>
                        </summary>
                        <div className="terminal-bubble mt-1 px-3 py-2 text-[10px] text-[#e0f5d0] whitespace-pre-wrap font-mono max-h-48 overflow-auto">
                          {em.agent_input_preview}
                        </div>
                      </details>
                    ))}
                  </div>
                )}
                <button onClick={() => setTestResult(null)} className="terminal-control px-3 py-1 text-xs text-[#78adb8] hover:text-[#b0f0e8]">
                  Dismiss
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* ── Edit / Create form ── */}
      {editing && (
        <div className="space-y-4">
          {/* Trigger type selector (only for new triggers) */}
          {!trigger && (
            <div>
              <label className="block text-xs text-gray-400 mb-2">Trigger Type</label>
              <div className="flex gap-2">
                <button
                  onClick={() => setTriggerType("regular")}
                  className={`flex-1 flex items-center gap-2 px-3 py-2.5 rounded-lg border text-sm transition-colors ${
                    triggerType === "regular"
                      ? "border-amber-500 bg-amber-900/30 text-teal-300"
                      : "border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600"
                  }`}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Scheduled
                </button>
                <button
                  onClick={() => setTriggerType("gmail_push")}
                  className={`flex-1 flex items-center gap-2 px-3 py-2.5 rounded-lg border text-sm transition-colors ${
                    triggerType === "gmail_push"
                      ? "border-red-500 bg-red-900/30 text-red-300"
                      : "border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600"
                  }`}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                  Gmail Push
                </button>
              </div>
            </div>
          )}

          {/* Description */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Description</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={triggerType === "gmail_push" ? "e.g. Auto-respond to support emails" : "e.g. Daily email summary"}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
            />
          </div>

          {/* Interval (scheduled only) */}
          {triggerType === "regular" && (
            <div>
              <label className="block text-xs text-gray-400 mb-2">Interval</label>
              <div className="flex flex-wrap gap-2">
                {INTERVAL_PRESETS.map((p) => (
                  <button
                    key={p.value}
                    onClick={() => { setIntervalVal(p.value); setCustomInterval(""); }}
                    className={`px-3 py-1.5 text-xs rounded-lg border transition-colors ${
                      interval === p.value && !customInterval
                        ? "border-amber-500 bg-amber-900/30 text-teal-300"
                        : "border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600"
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-2 mt-2">
                <input
                  type="number"
                  min={10}
                  value={customInterval}
                  onChange={(e) => setCustomInterval(e.target.value)}
                  placeholder="Custom (min 10)"
                  className="w-40 bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
                />
                <span className="text-xs text-gray-500">minutes</span>
              </div>
            </div>
          )}

          {/* Gmail push filters */}
          {triggerType === "gmail_push" && (
            <div className="space-y-3">
              <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-3">
                <div className="flex items-center gap-2">
                  <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span className="text-xs text-blue-400">
                    Fires when new emails arrive. Requires email account with IMAP.
                  </span>
                </div>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Filter by sender (optional)</label>
                <input
                  type="text"
                  value={filterFrom}
                  onChange={(e) => setFilterFrom(e.target.value)}
                  placeholder="e.g. notifications@github.com"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Filter by subject keyword (optional)</label>
                <input
                  type="text"
                  value={filterSubject}
                  onChange={(e) => setFilterSubject(e.target.value)}
                  placeholder="e.g. urgent, invoice, alert"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Filter by body keyword (optional)</label>
                <input
                  type="text"
                  value={filterBody}
                  onChange={(e) => setFilterBody(e.target.value)}
                  placeholder="e.g. payment, confirmation code"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Filter by header keyword (optional)</label>
                <input
                  type="text"
                  value={filterHeader}
                  onChange={(e) => setFilterHeader(e.target.value)}
                  placeholder="e.g. mailing-list name, X-header value"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Max email age in minutes (0 = no limit)</label>
                <input
                  type="number"
                  min={0}
                  value={maxAgeMinutes}
                  onChange={(e) => setMaxAgeMinutes(Math.max(0, parseInt(e.target.value) || 0))}
                  placeholder="e.g. 60"
                  className="w-40 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
                />
                <p className="text-[10px] text-gray-500 mt-1">Ignore emails older than this. Useful to skip old unread emails on first run.</p>
              </div>
            </div>
          )}

          {/* Prompt */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Trigger prompt *</label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={
                triggerType === "gmail_push"
                  ? "What should the agent do with each new email?"
                  : "What should the agent do each time this trigger fires?"
              }
              rows={3}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500 resize-none"
            />
          </div>

          <div className="flex gap-2 pt-1">
            <button
              onClick={handleSave}
              disabled={!prompt.trim()}
              className="px-4 py-2 bg-amber-600 text-white text-sm rounded-lg font-medium hover:bg-amber-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              {trigger ? "Save Changes" : "Create Trigger"}
            </button>
            {trigger && (
              <button
                onClick={() => setEditing(false)}
                className="px-4 py-2 bg-gray-800 text-gray-300 text-sm rounded-lg hover:bg-gray-700 transition-colors"
              >
                Cancel
              </button>
            )}
          </div>
        </div>
      )}
      </div>{/* close divider section */}

      {/* Build Your Own Trigger */}
      <details className="group mt-2">
        <summary className="flex items-center gap-2 cursor-pointer text-xs font-medium text-gray-500 uppercase tracking-wider select-none">
          <svg className="w-4 h-4 text-amber-500 transition-transform group-open:rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
          Build Your Own Trigger
        </summary>
        <div className="mt-3 p-4 bg-gray-800/60 border border-gray-700 rounded-lg text-sm text-gray-300 space-y-3">
          <p>Drop a Python file into <code className="text-amber-400 bg-gray-900 px-1 rounded">backend/app/services/custom_triggers/</code> and restart — it auto-starts.</p>
          <div className="space-y-2 text-gray-400">
            <div>
              <span className="text-white font-medium">Interval-based</span> — already built-in, no code needed. Just enable the Triggers tool on an agent.
            </div>
            <div>
              <span className="text-white font-medium">Event-driven (custom)</span> — for new event sources (webhook, RSS, file watcher, etc.):
            </div>
          </div>
          <ol className="list-decimal list-inside space-y-2 text-gray-400">
            <li>
              Copy the template: <code className="text-amber-400 bg-gray-900 px-1 rounded">_template.py</code> → <code className="text-amber-400 bg-gray-900 px-1 rounded">my_trigger.py</code>
            </li>
            <li>
              Edit <code className="text-amber-400 bg-gray-900 px-1 rounded">TRIGGER_META</code> and the <code className="text-amber-400 bg-gray-900 px-1 rounded">TriggerService</code> class
            </li>
            <li>
              Restart the backend — your trigger service starts automatically
            </li>
          </ol>
          <p className="text-gray-500 text-xs mt-1">
            No other files need editing. The app lifespan auto-discovers and manages the lifecycle.
          </p>
          <p className="text-gray-500 text-xs">
            Full guide →{" "}
            <a href="https://github.com/ffollonier/cronosaurus/blob/main/CONTRIBUTING.md" target="_blank" rel="noopener noreferrer" className="text-amber-500 hover:text-amber-400 underline">
              CONTRIBUTING.md
            </a>
          </p>
        </div>
      </details>
    </div>
  );
}

// ══════════════════════════════════════════════════════════
//  EMAIL TAB
// ══════════════════════════════════════════════════════════

const COMMON_PROVIDERS = [
  { label: "Gmail", host: "smtp.gmail.com", port: 587, tls: true, imap_host: "imap.gmail.com", imap_port: 993 },
  { label: "Outlook", host: "smtp.office365.com", port: 587, tls: true, imap_host: "outlook.office365.com", imap_port: 993 },
  { label: "Yahoo", host: "smtp.mail.yahoo.com", port: 587, tls: true, imap_host: "imap.mail.yahoo.com", imap_port: 993 },
  { label: "iCloud", host: "smtp.mail.me.com", port: 587, tls: true, imap_host: "imap.mail.me.com", imap_port: 993 },
  { label: "Custom", host: "", port: 587, tls: true, imap_host: "", imap_port: 993 },
];

const EMPTY_EMAIL_FORM: EmailAccountCreate = {
  label: "",
  smtp_host: "",
  smtp_port: 587,
  username: "",
  password: "",
  from_email: "",
  from_name: "",
  use_tls: true,
  imap_host: "",
  imap_port: 993,
  is_default: false,
};

function EmailTab({
  accounts,
  onAdd,
  onUpdate,
  onDelete,
  onTest,
}: {
  accounts: EmailAccount[];
  onAdd: (data: EmailAccountCreate) => Promise<void>;
  onUpdate: (id: string, data: Partial<EmailAccountCreate>) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onTest: (id: string) => Promise<{ success: boolean; message?: string; error?: string }>;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [form, setForm] = useState<EmailAccountCreate>({ ...EMPTY_EMAIL_FORM });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ success: boolean; message?: string; error?: string } | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  useEffect(() => {
    if (editing && editing !== "new") {
      const acct = accounts.find((a) => a.id === editing);
      if (acct) {
        setForm({
          label: acct.label,
          smtp_host: acct.smtp_host,
          smtp_port: acct.smtp_port,
          username: acct.username,
          password: "",
          from_email: acct.from_email,
          from_name: acct.from_name,
          use_tls: acct.use_tls,
          imap_host: acct.imap_host || "",
          imap_port: acct.imap_port || 993,
          is_default: acct.is_default,
        });
      }
    } else if (editing === "new") {
      setForm({ ...EMPTY_EMAIL_FORM, is_default: accounts.length === 0 });
    }
    setTestResult(null);
    setShowPassword(false);
  }, [editing, accounts]);

  const handleProviderSelect = (p: (typeof COMMON_PROVIDERS)[number]) => {
    setForm((prev) => ({
      ...prev,
      smtp_host: p.host,
      smtp_port: p.port,
      use_tls: p.tls,
      imap_host: p.imap_host,
      imap_port: p.imap_port,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.smtp_host || !form.username || !form.from_email) return;
    if (editing === "new" && !form.password) return;
    setSaving(true);
    setTestResult(null);
    try {
      if (editing === "new") {
        await onAdd(form);
      } else if (editing) {
        const updates: Partial<EmailAccountCreate> = { ...form };
        if (!updates.password) delete updates.password;
        await onUpdate(editing, updates);
      }
      setEditing(null);
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async (id: string) => {
    setTesting(id);
    setTestResult(null);
    try {
      const result = await onTest(id);
      setTestResult(result);
    } catch {
      setTestResult({ success: false, error: "Test request failed" });
    } finally {
      setTesting(null);
    }
  };

  const handleDelete = async (id: string) => {
    if (confirmDelete !== id) {
      setConfirmDelete(id);
      return;
    }
    await onDelete(id);
    setConfirmDelete(null);
  };

  const editingAccount = editing && editing !== "new" ? accounts.find((a) => a.id === editing) : null;

  // ── List view ──
  if (!editing) {
    return (
      <div className="space-y-4">
        {accounts.length === 0 && (
          <p className="text-gray-500 text-sm text-center py-8">
            No email accounts configured yet.
          </p>
        )}
        {accounts.map((acct) => (
          <div
            key={acct.id}
            className="bg-gray-800/60 border border-gray-700 rounded-xl p-4 flex items-start gap-3"
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-white font-medium text-sm truncate">
                  {acct.label || acct.from_email}
                </span>
                {acct.is_default && (
                  <span className="px-1.5 py-0.5 text-[10px] font-semibold rounded bg-blue-600/30 text-blue-300 border border-blue-700 uppercase">
                    Default
                  </span>
                )}
                {!acct.has_password && (
                  <span className="px-1.5 py-0.5 text-[10px] font-semibold rounded bg-amber-600/30 text-teal-300 border border-amber-700">
                    No Password
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-400 mt-0.5 truncate">{acct.from_email}</p>
              <p className="text-xs text-gray-500 mt-0.5">
                SMTP: {acct.smtp_host}:{acct.smtp_port}
                {acct.imap_host && ` · IMAP: ${acct.imap_host}:${acct.imap_port}`}
              </p>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <button
                onClick={() => handleTest(acct.id)}
                disabled={testing === acct.id}
                className="p-1.5 text-gray-400 hover:text-blue-400 transition-colors disabled:opacity-50"
                title="Test connection"
              >
                {testing === acct.id ? (
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                ) : (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                )}
              </button>
              <button
                onClick={() => setEditing(acct.id)}
                className="p-1.5 text-gray-400 hover:text-white transition-colors"
                title="Edit"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
              </button>
              <button
                onClick={() => handleDelete(acct.id)}
                className={`p-1.5 transition-colors ${
                  confirmDelete === acct.id ? "text-red-400 hover:text-red-300" : "text-gray-400 hover:text-red-400"
                }`}
                title={confirmDelete === acct.id ? "Click again to confirm" : "Delete"}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </div>
        ))}

        {testResult && (
          <div className={`rounded-lg px-4 py-3 text-sm ${
            testResult.success
              ? "bg-green-900/30 border border-green-800 text-green-300"
              : "bg-red-900/30 border border-red-800 text-red-300"
          }`}>
            {testResult.success
              ? testResult.message || "Connection successful!"
              : testResult.error || "Connection failed."}
          </div>
        )}

        <button
          onClick={() => setEditing("new")}
          className="flex items-center gap-2 px-4 py-2 bg-white text-black text-sm rounded-lg font-medium hover:bg-gray-200 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Add Account
        </button>
      </div>
    );
  }

  // ── Form view ──
  return (
    <div className="space-y-4 max-w-xl">
      {/* Back + Title */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => setEditing(null)}
          className="p-1 text-gray-400 hover:text-white transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <h3 className="text-sm font-semibold text-white">
          {editing === "new" ? "Add Email Account" : "Edit Email Account"}
        </h3>
      </div>

      {/* Password warning */}
      {editingAccount && !editingAccount.has_password && (
        <div className="p-3 rounded-lg bg-amber-900/30 border border-amber-700 text-teal-300 text-sm flex items-start gap-2">
          <svg className="w-5 h-5 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
          </svg>
          <span><strong>Password missing!</strong> Please re-enter your email password below and save.</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Label */}
        <div>
          <label className="block text-xs text-gray-400 mb-1">Account Label</label>
          <input
            type="text"
            value={form.label}
            onChange={(e) => setForm({ ...form, label: e.target.value })}
            placeholder="e.g. Work, Personal"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
          />
        </div>

        {/* Provider quick-select */}
        <div>
          <label className="block text-xs text-gray-400 mb-2">Quick Setup</label>
          <div className="flex flex-wrap gap-2">
            {COMMON_PROVIDERS.map((p) => (
              <button
                key={p.label}
                type="button"
                onClick={() => handleProviderSelect(p)}
                className={`px-3 py-1.5 text-xs rounded-lg border transition-colors ${
                  form.smtp_host === p.host
                    ? "border-blue-500 bg-blue-900/30 text-blue-300"
                    : "border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* SMTP Host + Port */}
        <div className="grid grid-cols-3 gap-3">
          <div className="col-span-2">
            <label className="block text-xs text-gray-400 mb-1">SMTP Host *</label>
            <input
              type="text"
              value={form.smtp_host}
              onChange={(e) => setForm({ ...form, smtp_host: e.target.value })}
              placeholder="smtp.gmail.com"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
              required
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Port</label>
            <input
              type="number"
              value={form.smtp_port}
              onChange={(e) => setForm({ ...form, smtp_port: parseInt(e.target.value) || 587 })}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-gray-500"
            />
          </div>
        </div>

        {/* Username */}
        <div>
          <label className="block text-xs text-gray-400 mb-1">Username / Email *</label>
          <input
            type="text"
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
            placeholder="you@gmail.com"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
            required
          />
        </div>

        {/* Password */}
        <div>
          <label className="block text-xs text-gray-400 mb-1">
            Password / App Password {editing !== "new" ? "(leave blank to keep current)" : "*"}
          </label>
          <div className="relative">
            <input
              type={showPassword ? "text" : "password"}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              placeholder={editing !== "new" ? "••••••••" : "App-specific password recommended"}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 pr-10 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
              required={editing === "new"}
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-gray-300"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                {showPassword ? (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M3 3l18 18" />
                ) : (
                  <>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                  </>
                )}
              </svg>
            </button>
          </div>
          <p className="text-xs text-gray-600 mt-1">
            For Gmail, use an{" "}
            <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:text-blue-400">
              App Password
            </a>. Your password is encrypted before storage.
          </p>
        </div>

        {/* From Email + Name */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-gray-400 mb-1">From Email *</label>
            <input
              type="email"
              value={form.from_email}
              onChange={(e) => setForm({ ...form, from_email: e.target.value })}
              placeholder="you@gmail.com"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
              required
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Display Name</label>
            <input
              type="text"
              value={form.from_name}
              onChange={(e) => setForm({ ...form, from_name: e.target.value })}
              placeholder="Your Name"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
            />
          </div>
        </div>

        {/* TLS + Default */}
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-3">
            <ToggleSwitch
              checked={form.use_tls}
              onToggle={() => setForm({ ...form, use_tls: !form.use_tls })}
              accent="green"
              title={form.use_tls ? "Disable TLS" : "Enable TLS"}
            />
            <span className="text-sm text-gray-300">Use TLS</span>
          </div>
          <div className="flex items-center gap-3">
            <ToggleSwitch
              checked={form.is_default}
              onToggle={() => setForm({ ...form, is_default: !form.is_default })}
              accent="blue"
              title={form.is_default ? "Unset as default account" : "Set as default account"}
            />
            <span className="text-sm text-gray-300">Default account</span>
          </div>
        </div>

        {/* IMAP Settings */}
        <div className="pt-2 border-t border-gray-800">
          <label className="block text-xs text-gray-400 mb-2">IMAP Settings (for reading emails)</label>
          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2">
              <label className="block text-xs text-gray-500 mb-1">IMAP Host</label>
              <input
                type="text"
                value={form.imap_host}
                onChange={(e) => setForm({ ...form, imap_host: e.target.value })}
                placeholder="imap.gmail.com"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Port</label>
              <input
                type="number"
                value={form.imap_port}
                onChange={(e) => setForm({ ...form, imap_port: parseInt(e.target.value) || 993 })}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-gray-500"
              />
            </div>
          </div>
          <p className="text-xs text-gray-600 mt-1">
            Leave empty if you only need to send emails. IMAP uses the same username/password.
          </p>
        </div>

        {/* Test result */}
        {testResult && (
          <div className={`rounded-lg px-4 py-3 text-sm ${
            testResult.success
              ? "bg-green-900/30 border border-green-800 text-green-300"
              : "bg-red-900/30 border border-red-800 text-red-300"
          }`}>
            {testResult.success
              ? testResult.message || "Connection successful!"
              : testResult.error || "Connection failed."}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2 pt-2">
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 bg-white text-black text-sm rounded-lg font-medium hover:bg-gray-200 transition-colors disabled:opacity-50"
          >
            {saving ? "Saving..." : editing === "new" ? "Add Account" : "Update Account"}
          </button>
          {editing !== "new" && (
            <button
              type="button"
              onClick={() => handleTest(editing!)}
              disabled={!!testing}
              className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg font-medium hover:bg-blue-500 transition-colors disabled:opacity-50"
            >
              {testing ? "Testing..." : "Test Connection"}
            </button>
          )}
          <button
            type="button"
            onClick={() => setEditing(null)}
            className="px-4 py-2 bg-gray-800 text-gray-300 text-sm rounded-lg hover:bg-gray-700 transition-colors ml-auto"
          >
            Back
          </button>
        </div>
      </form>
    </div>
  );
}

// ══════════════════════════════════════════════════════════
//  MCP TAB
// ══════════════════════════════════════════════════════════

function MCPTab({
  servers,
  onAdd,
  onDelete,
  onToggle,
  onUpdate,
}: {
  servers: MCPServer[];
  onAdd: (server: Omit<MCPServer, "id">) => void;
  onDelete: (id: string) => void;
  onToggle: (id: string, active: boolean) => void;
  onUpdate: (id: string, data: Partial<Omit<MCPServer, "id">>) => void;
}) {
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", url: "", api_key: "", description: "" });

  const resetForm = () => {
    setForm({ name: "", url: "", api_key: "", description: "" });
    setShowForm(false);
    setEditId(null);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim() || !form.url.trim()) return;
    if (editId) {
      onUpdate(editId, {
        name: form.name.trim(),
        url: form.url.trim(),
        api_key: form.api_key.trim(),
        description: form.description.trim(),
      });
    } else {
      onAdd({
        name: form.name.trim(),
        url: form.url.trim(),
        api_key: form.api_key.trim(),
        description: form.description.trim(),
        active: true,
      });
    }
    resetForm();
  };

  const startEdit = (srv: MCPServer) => {
    setEditId(srv.id);
    setForm({ name: srv.name, url: srv.url, api_key: srv.api_key, description: srv.description });
    setShowForm(true);
  };

  return (
    <div className="space-y-4">
      {servers.length === 0 && !showForm && (
        <p className="text-gray-500 text-sm text-center py-8">
          No MCP servers configured yet.
        </p>
      )}

      {servers.map((srv) => (
        <div
          key={srv.id}
          className={`rounded-xl border p-4 transition-colors ${
            srv.active ? "border-gray-700 bg-gray-800/50" : "border-gray-800 bg-gray-900/50 opacity-60"
          }`}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-medium text-white truncate">{srv.name}</h3>
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  srv.active ? "bg-green-900/40 text-green-400" : "bg-gray-800 text-gray-500"
                }`}>
                  {srv.active ? "Active" : "Inactive"}
                </span>
              </div>
              <p className="text-xs text-gray-400 mt-1 truncate">{srv.url}</p>
              {srv.description && <p className="text-xs text-gray-500 mt-1">{srv.description}</p>}
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <ToggleSwitch
                checked={srv.active}
                onToggle={() => onToggle(srv.id, !srv.active)}
                accent="green"
                title={srv.active ? "Deactivate" : "Activate"}
              />
              <button onClick={() => startEdit(srv)} className="p-1.5 text-gray-400 hover:text-blue-400 transition-colors" title="Edit">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
              </button>
              <button onClick={() => onDelete(srv.id)} className="p-1.5 text-gray-400 hover:text-red-400 transition-colors" title="Delete">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      ))}

      {/* Add/Edit form */}
      {showForm && (
        <form onSubmit={handleSubmit} className="rounded-xl border border-gray-700 bg-gray-800/50 p-4 space-y-3">
          <h3 className="text-sm font-medium text-white">
            {editId ? "Edit MCP Server" : "Add MCP Server"}
          </h3>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Name *</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="e.g. My Tool Server"
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
              required
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">URL *</label>
            <input
              type="url"
              value={form.url}
              onChange={(e) => setForm({ ...form, url: e.target.value })}
              placeholder="https://mcp-server.example.com"
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
              required
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">API Key</label>
            <input
              type="password"
              value={form.api_key}
              onChange={(e) => setForm({ ...form, api_key: e.target.value })}
              placeholder="Optional"
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Description</label>
            <input
              type="text"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="What does this server do?"
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
            />
          </div>
          <div className="flex gap-2 pt-1">
            <button
              type="submit"
              className="px-4 py-2 bg-white text-black text-sm rounded-lg font-medium hover:bg-gray-200 transition-colors"
            >
              {editId ? "Save Changes" : "Add Server"}
            </button>
            <button
              type="button"
              onClick={resetForm}
              className="px-4 py-2 bg-gray-800 text-gray-300 text-sm rounded-lg hover:bg-gray-700 transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {!showForm && (
        <button
          onClick={() => { resetForm(); setShowForm(true); }}
          className="flex items-center gap-2 px-4 py-2 bg-gray-800 text-white text-sm rounded-lg hover:bg-gray-700 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Add MCP Server
        </button>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════
//  SETTINGS TAB
// ══════════════════════════════════════════════════════════

const ALL_MODELS = [
  "gpt-4.1",
  "gpt-4.1-mini",
  "gpt-4.1-nano",
  "gpt-4o",
  "gpt-5",
  "gpt-5-mini",
  "gpt-5-nano",
  "model-router",
];

function SettingsTab() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [foundryTest, setFoundryTest] = useState<{ status: "idle" | "testing" | "success" | "error"; message: string }>({ status: "idle", message: "" });
  const [cosmosTest, setCosmosTest] = useState<{ status: "idle" | "testing" | "success" | "error"; message: string }>({ status: "idle", message: "" });
  const [deploymentsLoading, setDeploymentsLoading] = useState(false);
  const [deploymentsError, setDeploymentsError] = useState("");
  const [foundryDeployments, setFoundryDeployments] = useState<FoundryDeployment[]>([]);
  const [providerModels, setProviderModels] = useState<{ id: string; owned_by: string }[]>([]);
  const [providerModelsLoading, setProviderModelsLoading] = useState(false);
  const [providerModelsError, setProviderModelsError] = useState("");

  // Local form state
  const [provider, setProvider] = useState("azure_foundry");
  const [endpoint, setEndpoint] = useState("");
  const [deployment, setDeployment] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [openaiKey, setOpenaiKey] = useState("");
  const [openaiModel, setOpenaiModel] = useState("gpt-4.1-mini");
  const [anthropicKey, setAnthropicKey] = useState("");
  const [anthropicModel, setAnthropicModel] = useState("claude-sonnet-4-20250514");
  const [cUrl, setCUrl] = useState("");
  const [cKey, setCKey] = useState("");
  const [cDb, setCDb] = useState("");

  // Google Search config
  const [gsKey, setGsKey] = useState("");
  const [gsEngineId, setGsEngineId] = useState("");

  // Calendar config
  const [calProvider, setCalProvider] = useState("google");
  const [calUrl, setCalUrl] = useState("");
  const [calUsername, setCalUsername] = useState("");
  const [calPassword, setCalPassword] = useState("");
  const [calConfigured, setCalConfigured] = useState(false);
  const [calSaving, setCalSaving] = useState(false);

  useEffect(() => {
    fetchSettings()
      .then((s) => {
        setSettings(s);
        setProvider(s.model_provider || "azure_foundry");
        setEndpoint(s.project_endpoint);
        setDeployment(s.model_deployment_name);
        setModels(s.available_models);
        setOpenaiModel(s.openai_model || "gpt-4.1-mini");
        setAnthropicModel(s.anthropic_model || "claude-sonnet-4-20250514");
        setCUrl(s.cosmos_url);
        setCKey(s.cosmos_key_set ? "" : "");
        setCDb(s.cosmos_db);
        setGsEngineId(s.google_search_engine_id || "");
      })
      .catch(() => {})
      .finally(() => setLoading(false));

    // Load calendar config
    fetch("/api/user/calendar-config")
      .then(r => r.json())
      .then(c => {
        if (c.configured) {
          setCalProvider(c.provider || "google");
          setCalUrl(c.caldav_url || "");
          setCalUsername(c.username || "");
          setCalConfigured(true);
        }
      })
      .catch(() => {});
  }, []);

  const toggleModel = (model: string) => {
    setModels((prev) =>
      prev.includes(model) ? prev.filter((m) => m !== model) : [...prev, model]
    );
  };

  const handleLoadDeployments = async () => {
    setDeploymentsLoading(true);
    setDeploymentsError("");
    try {
      const r = await fetchDeployments();
      if (r.success) {
        setFoundryDeployments(r.deployments);
        const names = r.deployments.map((d) => d.name);
        setModels((prev) => {
          const merged = new Set([...prev, ...names]);
          return Array.from(merged);
        });
      } else {
        setDeploymentsError(r.error || "Failed to load deployments");
      }
    } catch {
      setDeploymentsError("Failed to load deployments");
    } finally {
      setDeploymentsLoading(false);
    }
  };

  const handleLoadProviderModels = async () => {
    setProviderModelsLoading(true);
    setProviderModelsError("");
    try {
      const r = await fetchProviderModels();
      if (r.success && r.models) {
        setProviderModels(r.models);
        const names = r.models.map((m) => m.id);
        setModels((prev) => {
          const merged = new Set([...prev, ...names]);
          return Array.from(merged);
        });
      } else {
        setProviderModelsError(r.error || "Failed to load models");
      }
    } catch {
      setProviderModelsError("Failed to load models");
    } finally {
      setProviderModelsLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    try {
      const payload: Record<string, unknown> = {
        model_provider: provider,
        project_endpoint: endpoint,
        model_deployment_name: deployment,
        available_models: models,
        openai_model: openaiModel,
        anthropic_model: anthropicModel,
        cosmos_url: cUrl,
        cosmos_db: cDb,
        google_search_engine_id: gsEngineId,
      };
      if (cKey) payload.cosmos_key = cKey;
      if (openaiKey) payload.openai_api_key = openaiKey;
      if (anthropicKey) payload.anthropic_api_key = anthropicKey;
      if (gsKey) payload.google_search_api_key = gsKey;
      const result = await updateSettings(payload as Partial<AppSettings>);
      setSettings(result);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch {
      // ignore
    } finally {
      setSaving(false);
    }
  };

  const handleTestFoundry = async () => {
    setFoundryTest({ status: "testing", message: "Testing..." });
    try {
      const r = await testFoundryConnection();
      setFoundryTest({ status: r.success ? "success" : "error", message: r.message || r.error || "" });
    } catch { setFoundryTest({ status: "error", message: "Test failed" }); }
  };

  const handleTestCosmos = async () => {
    setCosmosTest({ status: "testing", message: "Testing..." });
    try {
      const r = await testCosmosConnection();
      setCosmosTest({ status: r.success ? "success" : "error", message: r.message || r.error || "" });
    } catch { setCosmosTest({ status: "error", message: "Test failed" }); }
  };

  if (loading) return <div className="text-gray-500 text-sm">Loading settings...</div>;

  return (
    <div className="space-y-8 max-w-2xl">
      <div>
        <h3 className="text-[#c9f6ef] font-semibold mb-1 uppercase tracking-[0.08em]">Settings</h3>
        <p className="text-xs text-[#597f8b]">Configure your model provider, API keys, and database connection.</p>
      </div>

      {/* Provider selection */}
      <section className="space-y-3">
        <h4 className="text-sm font-medium text-gray-300 flex items-center gap-2">
          <span className="w-2 h-2 bg-[#3dd8c5]" />
          Model Provider
        </h4>
        <div className="grid grid-cols-3 gap-2">
          {([
            { id: "azure_foundry", label: "Azure AI Foundry", desc: "Microsoft Foundry Agent Service" },
            { id: "openai", label: "OpenAI", desc: "Direct OpenAI API" },
            { id: "anthropic", label: "Anthropic", desc: "Claude models" },
          ] as const).map((p) => (
            <button
              key={p.id}
              onClick={() => setProvider(p.id)}
              className={`terminal-control flex flex-col items-start gap-1 px-3 py-2.5 text-left transition-colors ${
                provider === p.id
                  ? "bg-[#0e1922] border-[#3dd8c5]/30 text-[#b0f0e8]"
                  : "text-[#78adb8] hover:bg-[#0f161b]"
              }`}
            >
              <span className="text-xs font-medium">{p.label}</span>
              <span className="text-[10px] opacity-60">{p.desc}</span>
            </button>
          ))}
        </div>
      </section>

      {/* OpenAI API Key */}
      {provider === "openai" && (
        <section className="space-y-3">
          <h4 className="text-sm font-medium text-gray-300 flex items-center gap-2">
            <span className="w-2 h-2 bg-[#97ff8a]" />
            OpenAI Configuration
          </h4>
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              API Key
              {settings?.openai_api_key_set && <span className="text-green-400 ml-2">(key is set)</span>}
            </label>
            <input
              type="password"
              value={openaiKey}
              onChange={(e) => setOpenaiKey(e.target.value)}
              placeholder={settings?.openai_api_key_set ? "Leave blank to keep current key" : "sk-..."}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-green-500"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Default Model</label>
            <input
              type="text"
              value={openaiModel}
              onChange={(e) => setOpenaiModel(e.target.value)}
              placeholder="gpt-4.1-mini"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-green-500"
            />
          </div>
        </section>
      )}

      {/* Anthropic API Key */}
      {provider === "anthropic" && (
        <section className="space-y-3">
          <h4 className="text-sm font-medium text-gray-300 flex items-center gap-2">
            <span className="w-2 h-2 bg-[#3dd8c5]" />
            Anthropic Configuration
          </h4>
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              API Key
              {settings?.anthropic_api_key_set && <span className="text-green-400 ml-2">(key is set)</span>}
            </label>
            <input
              type="password"
              value={anthropicKey}
              onChange={(e) => setAnthropicKey(e.target.value)}
              placeholder={settings?.anthropic_api_key_set ? "Leave blank to keep current key" : "sk-ant-..."}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-amber-500"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Default Model</label>
            <input
              type="text"
              value={anthropicModel}
              onChange={(e) => setAnthropicModel(e.target.value)}
              placeholder="claude-sonnet-4-20250514"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-amber-500"
            />
          </div>
        </section>
      )}

      {/* Foundry (only show when azure_foundry is selected) */}
      {provider === "azure_foundry" && (
      <section className="space-y-3">
        <h4 className="text-sm font-medium text-gray-300 flex items-center gap-2">
          <span className="w-2 h-2 bg-[#3dd8c5]" />
          Azure AI Foundry
        </h4>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Project Endpoint</label>
          <input
            type="text"
            value={endpoint}
            onChange={(e) => setEndpoint(e.target.value)}
            placeholder="https://<resource>.services.ai.azure.com/api/projects/<project>"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Default Model Deployment</label>
          <select
            value={deployment}
            onChange={(e) => setDeployment(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-blue-500"
          >
            {!models.includes(deployment) && deployment && (
              <option value={deployment}>{deployment}</option>
            )}
            {models.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={handleTestFoundry} disabled={foundryTest.status === "testing" || !endpoint}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-gray-800 border border-gray-700 text-gray-300 hover:border-gray-600 disabled:opacity-40 transition-colors">
            {foundryTest.status === "testing" ? <span className="w-3 h-3 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" /> : null}
            Test Connection
          </button>
          {foundryTest.status !== "idle" && foundryTest.status !== "testing" && (
            <span className={`text-xs ${foundryTest.status === "success" ? "text-green-400" : "text-red-400"}`}>{foundryTest.message}</span>
          )}
        </div>

        {/* Role guidance */}
        <details className="group">
          <summary className="text-[11px] text-gray-500 hover:text-gray-300 cursor-pointer select-none transition-colors flex items-center gap-1">
            <svg className="w-3 h-3 transition-transform group-open:rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
            Required Azure role assignments
          </summary>
          <div className="mt-2 p-3 bg-gray-800/60 rounded-lg border border-gray-700/50 text-[11px] text-gray-400 space-y-2">
            <p>The identity running this app needs these roles on your <strong className="text-gray-300">AI Foundry project</strong> resource:</p>
            <table className="w-full text-left">
              <thead><tr className="text-gray-500"><th className="pr-3 pb-1 font-medium">Role</th><th className="pb-1 font-medium">Purpose</th></tr></thead>
              <tbody className="text-gray-400">
                <tr><td className="pr-3 py-0.5"><code className="text-blue-400">Azure AI Developer</code></td><td>Invoke models, manage agents, list deployments</td></tr>
                <tr><td className="pr-3 py-0.5"><code className="text-blue-400">Azure AI Inference Deployment Operator</code></td><td>List model deployments ("Load from Foundry")</td></tr>
              </tbody>
            </table>
            <p className="text-gray-500">For local dev, run <code className="text-gray-400">az login</code> first — the app uses <code className="text-gray-400">DefaultAzureCredential</code> automatically.</p>
            <a href="https://learn.microsoft.com/azure/ai-studio/concepts/rbac-ai-studio" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-blue-400 hover:text-blue-300 transition-colors">
              Azure AI Foundry RBAC docs
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
            </a>
          </div>
        </details>
      </section>
      )}

      {/* Models */}
      <section className="space-y-3">
        <h4 className="text-sm font-medium text-gray-300 flex items-center gap-2">
          <span className="w-2 h-2 bg-[#97ff8a]" />
          Available Models
        </h4>
        <p className="text-xs text-[#597f8b]">Select which models appear in the model selector dropdown.</p>

        {/* Load models — provider-aware */}
        <div className="flex items-center gap-2">
          {provider === "azure_foundry" ? (
            <button
              onClick={handleLoadDeployments}
              disabled={deploymentsLoading || !endpoint}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-purple-900/30 border border-purple-700 text-purple-300 hover:bg-purple-900/50 disabled:opacity-40 transition-colors"
            >
              {deploymentsLoading ? <span className="w-3 h-3 border-2 border-purple-400 border-t-transparent rounded-full animate-spin" /> : (
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
              )}
              Load from Foundry
            </button>
          ) : (
            <button
              onClick={handleLoadProviderModels}
              disabled={providerModelsLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-purple-900/30 border border-purple-700 text-purple-300 hover:bg-purple-900/50 disabled:opacity-40 transition-colors"
            >
              {providerModelsLoading ? <span className="w-3 h-3 border-2 border-purple-400 border-t-transparent rounded-full animate-spin" /> : (
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
              )}
              Load from {provider === "openai" ? "OpenAI" : "Anthropic"}
            </button>
          )}
          {deploymentsError && provider === "azure_foundry" && <span className="text-xs text-red-400">{deploymentsError}</span>}
          {providerModelsError && provider !== "azure_foundry" && <span className="text-xs text-red-400">{providerModelsError}</span>}
          {foundryDeployments.length > 0 && provider === "azure_foundry" && !deploymentsError && (
            <span className="text-xs text-green-400">{foundryDeployments.length} deployment{foundryDeployments.length !== 1 ? "s" : ""} found</span>
          )}
          {providerModels.length > 0 && provider !== "azure_foundry" && !providerModelsError && (
            <span className="text-xs text-green-400">{providerModels.length} model{providerModels.length !== 1 ? "s" : ""} found</span>
          )}
        </div>

        {/* Foundry deployments list */}
        {provider === "azure_foundry" && foundryDeployments.length > 0 && (
          <div className="bg-gray-800/50 rounded-lg border border-gray-700 divide-y divide-gray-700">
            {foundryDeployments.map((d) => (
              <div key={d.name} className="flex items-center gap-3 px-3 py-2">
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-gray-200">{d.name}</div>
                  <div className="text-[10px] text-gray-500">{d.model_publisher} / {d.model_name} v{d.model_version}</div>
                </div>
                <button
                  onClick={() => { setDeployment(d.name); }}
                  className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${
                    deployment === d.name
                      ? "bg-blue-600 border-blue-600 text-white"
                      : "border-gray-600 text-gray-400 hover:border-blue-500 hover:text-blue-400"
                  }`}
                >
                  {deployment === d.name ? "Default" : "Set as default"}
                </button>
                <button
                  onClick={() => toggleModel(d.name)}
                  className={`w-3.5 h-3.5 rounded border flex items-center justify-center text-[10px] flex-shrink-0 ${
                    models.includes(d.name) ? "bg-purple-600 border-purple-600 text-white" : "border-gray-600"
                  }`}
                >
                  {models.includes(d.name) && "✓"}
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Provider models list (OpenAI / Anthropic) */}
        {provider !== "azure_foundry" && providerModels.length > 0 && (
          <div className="bg-gray-800/50 rounded-lg border border-gray-700 max-h-48 overflow-y-auto divide-y divide-gray-700">
            {providerModels.map((m) => (
              <div key={m.id} className="flex items-center gap-3 px-3 py-2">
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-gray-200">{m.id}</div>
                </div>
                <button
                  onClick={() => {
                    if (provider === "openai") setOpenaiModel(m.id);
                    else setAnthropicModel(m.id);
                    setDeployment(m.id);
                  }}
                  className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${
                    (provider === "openai" ? openaiModel : anthropicModel) === m.id
                      ? "bg-blue-600 border-blue-600 text-white"
                      : "border-gray-600 text-gray-400 hover:border-blue-500 hover:text-blue-400"
                  }`}
                >
                  {(provider === "openai" ? openaiModel : anthropicModel) === m.id ? "Default" : "Set as default"}
                </button>
                <button
                  onClick={() => toggleModel(m.id)}
                  className={`w-3.5 h-3.5 rounded border flex items-center justify-center text-[10px] flex-shrink-0 ${
                    models.includes(m.id) ? "bg-purple-600 border-purple-600 text-white" : "border-gray-600"
                  }`}
                >
                  {models.includes(m.id) && "✓"}
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Static model grid — hide models already shown in the Foundry/provider list */}
        <div className="grid grid-cols-2 gap-2">
          {ALL_MODELS.filter((m) => !foundryDeployments.some((d) => d.name === m) && !providerModels.some((p) => p.id === m)).map((model) => (
            <div
              key={model}
              onClick={() => toggleModel(model)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs text-left transition-colors cursor-pointer ${
                models.includes(model)
                  ? "bg-purple-900/20 border-purple-700 text-purple-300"
                  : "bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-600"
              }`}
            >
              <div className={`w-3.5 h-3.5 rounded border flex items-center justify-center text-[10px] ${
                models.includes(model) ? "bg-purple-600 border-purple-600 text-white" : "border-gray-600"
              }`}>
                {models.includes(model) && "✓"}
              </div>
              <span className="flex-1">{model}</span>
              {models.includes(model) && (
                <button
                  onClick={(e) => { e.stopPropagation(); setDeployment(model); }}
                  className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${
                    deployment === model
                      ? "bg-blue-600 border-blue-600 text-white"
                      : "border-gray-600 text-gray-400 hover:border-blue-500 hover:text-blue-400"
                  }`}
                >
                  {deployment === model ? "Default" : "Set as default"}
                </button>
              )}
            </div>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Add custom model name"
            className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-xs text-gray-200 placeholder-gray-500 focus:outline-none focus:border-purple-500"
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                const val = (e.target as HTMLInputElement).value.trim();
                if (val && !models.includes(val)) {
                  setModels((prev) => [...prev, val]);
                  (e.target as HTMLInputElement).value = "";
                }
              }
            }}
          />
          <span className="text-[10px] text-gray-500 self-center whitespace-nowrap">Press Enter</span>
        </div>
      </section>

      {/* Calendar */}
      <section className="space-y-3">
        <h4 className="text-sm font-medium text-gray-300 flex items-center gap-2">
          <span className={`w-2 h-2 ${calConfigured ? "bg-[#97ff8a]" : "bg-gray-600"}`} />
          Calendar (CalDAV)
        </h4>
        <p className="text-xs text-gray-500">
          Connect a calendar to let agents read your schedule and create events. Supports Google Calendar, Apple iCloud, Nextcloud, and any CalDAV server.
        </p>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Provider</label>
          <select
            value={calProvider}
            onChange={(e) => {
              const p = e.target.value;
              setCalProvider(p);
              if (p === "google") setCalUrl("https://www.googleapis.com/caldav/v2/");
              else if (p === "icloud") setCalUrl("https://caldav.icloud.com/");
              else if (p === "custom") setCalUrl("");
            }}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-blue-500"
          >
            <option value="google">Google Calendar</option>
            <option value="icloud">Apple iCloud</option>
            <option value="nextcloud">Nextcloud</option>
            <option value="custom">Custom CalDAV</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">CalDAV URL</label>
          <input
            type="text"
            value={calUrl}
            onChange={(e) => setCalUrl(e.target.value)}
            placeholder={calProvider === "google" ? "https://www.googleapis.com/caldav/v2/" : calProvider === "icloud" ? "https://caldav.icloud.com/" : "https://your-server.com/remote.php/dav/"}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Username / Email</label>
          <input
            type="text"
            value={calUsername}
            onChange={(e) => setCalUsername(e.target.value)}
            placeholder="your@email.com"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">
            Password / App Password
            {calConfigured && <span className="text-green-400 ml-2">(configured)</span>}
          </label>
          <input
            type="password"
            value={calPassword}
            onChange={(e) => setCalPassword(e.target.value)}
            placeholder={calConfigured ? "Leave blank to keep current" : "App-specific password"}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />
          <p className="text-[10px] text-gray-600 mt-1">
            {calProvider === "google" && "Generate at myaccount.google.com/apppasswords"}
            {calProvider === "icloud" && "Generate at appleid.apple.com → Sign-In and Security → App-Specific Passwords"}
            {calProvider === "nextcloud" && "Use your Nextcloud credentials"}
            {calProvider === "custom" && "Your CalDAV server credentials"}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={async () => {
              if (!calUrl) return;
              setCalSaving(true);
              try {
                await fetch("/api/user/calendar-config", {
                  method: "PUT",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ provider: calProvider, caldav_url: calUrl, username: calUsername, password: calPassword }),
                });
                setCalConfigured(true);
                setCalPassword("");
              } catch { /* silent */ }
              setCalSaving(false);
            }}
            disabled={!calUrl || calSaving}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-gray-800 border border-gray-700 text-gray-300 hover:border-gray-600 disabled:opacity-40 transition-colors"
          >
            {calSaving ? <span className="w-3 h-3 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" /> : null}
            {calConfigured ? "Update" : "Save"}
          </button>
          {calConfigured && (
            <button
              onClick={async () => {
                await fetch("/api/user/calendar-config", { method: "DELETE" });
                setCalConfigured(false);
                setCalUrl("");
                setCalUsername("");
                setCalPassword("");
              }}
              className="px-3 py-1.5 text-xs rounded-lg bg-gray-800 border border-gray-700 text-red-400 hover:border-red-600 transition-colors"
            >
              Remove
            </button>
          )}
        </div>
      </section>

      {/* Storage / Cosmos DB */}
      <section className="space-y-3">
        <h4 className="text-sm font-medium text-gray-300 flex items-center gap-2">
          <span className={`w-2 h-2 ${settings?.storage_mode === "cosmos" ? "bg-[#97ff8a]" : "bg-teal-400"}`} />
          Data Storage
        </h4>
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-800/50 border border-gray-700/50">
          <span className="text-xs text-gray-400">Mode:</span>
          <span className={`text-xs font-medium ${settings?.storage_mode === "cosmos" ? "text-[#97ff8a]" : "text-teal-400"}`}>
            {settings?.storage_mode === "cosmos" ? "Azure Cosmos DB" : "Local (SQLite)"}
          </span>
          {settings?.storage_mode === "local" && (
            <span className="text-[10px] text-gray-500 ml-auto">Add Cosmos DB credentials below to switch to cloud storage</span>
          )}
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Cosmos DB URL</label>
          <input
            type="text"
            value={cUrl}
            onChange={(e) => setCUrl(e.target.value)}
            placeholder="https://<account>.documents.azure.com:443/"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">
            Cosmos DB Key
            {settings?.cosmos_key_set && <span className="text-green-400 ml-2">(key is set)</span>}
          </label>
          <input
            type="password"
            value={cKey}
            onChange={(e) => setCKey(e.target.value)}
            placeholder={settings?.cosmos_key_set ? "Leave blank to keep current key" : "Your primary key"}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Database Name</label>
          <input
            type="text"
            value={cDb}
            onChange={(e) => setCDb(e.target.value)}
            placeholder="cronosaurus"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />
        </div>
        <div className="flex items-center gap-2">
          <button onClick={handleTestCosmos} disabled={cosmosTest.status === "testing" || !cUrl}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-gray-800 border border-gray-700 text-gray-300 hover:border-gray-600 disabled:opacity-40 transition-colors">
            {cosmosTest.status === "testing" ? <span className="w-3 h-3 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" /> : null}
            Test Connection
          </button>
          {cosmosTest.status !== "idle" && cosmosTest.status !== "testing" && (
            <span className={`text-xs ${cosmosTest.status === "success" ? "text-green-400" : "text-red-400"}`}>{cosmosTest.message}</span>
          )}
        </div>
      </section>

      {/* Google Search (Deep Search) */}
      <section className="space-y-3">
        <h4 className="text-sm font-medium text-gray-300 flex items-center gap-2">
          <span className={`w-2 h-2 ${settings?.google_search_api_key_set ? "bg-[#97ff8a]" : "bg-gray-600"}`} />
          Google Search (Deep Search)
        </h4>
        <p className="text-[10px] text-gray-500">Required for the deep_search tool. Uses Google Programmable Search Engine.</p>
        <div>
          <label className="block text-xs text-gray-400 mb-1">
            API Key
            {settings?.google_search_api_key_set && <span className="text-green-400 ml-2">(key is set)</span>}
          </label>
          <input
            type="password"
            value={gsKey}
            onChange={(e) => setGsKey(e.target.value)}
            placeholder={settings?.google_search_api_key_set ? "Leave blank to keep current key" : "Google Custom Search API key"}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Search Engine ID</label>
          <input
            type="text"
            value={gsEngineId}
            onChange={(e) => setGsEngineId(e.target.value)}
            placeholder="Programmable Search Engine ID (cx)"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />
        </div>
      </section>

      {/* Save */}
      <div className="flex items-center gap-3 pt-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="brand-button-primary px-5 py-2 text-sm font-semibold disabled:opacity-50 transition-all flex items-center gap-2"
        >
          {saving && <span className="w-3.5 h-3.5 border-2 border-[#071210] border-t-transparent rounded-full animate-spin" />}
          save settings
        </button>
        {saved && <span className="text-sm text-[#97ff8a]">Settings saved!</span>}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════
//  APPEARANCE TAB
// ══════════════════════════════════════════════════════════

function AppearanceTab() {
  const [lightMode, setLightMode] = useState(() => document.documentElement.classList.contains("light"));

  const toggleTheme = () => {
    const next = !lightMode;
    setLightMode(next);
    if (next) {
      document.documentElement.classList.add("light");
      localStorage.setItem("theme", "light");
    } else {
      document.documentElement.classList.remove("light");
      localStorage.setItem("theme", "dark");
    }
  };

  return (
    <div className="space-y-6">
      <section>
        <h3 className="text-sm font-semibold text-gray-200 mb-1">Theme</h3>
        <p className="text-xs text-gray-500 mb-3">Choose how Cronosaurus looks.</p>
        <div className="flex gap-3">
          <button
            onClick={() => { if (lightMode) toggleTheme(); }}
            className={`flex-1 flex flex-col items-center gap-2 px-4 py-4 rounded-lg border transition-colors ${
              !lightMode
                ? "bg-gray-800 border-green-600 text-gray-200"
                : "bg-gray-800/50 border-gray-700 text-gray-400 hover:border-gray-600"
            }`}
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z" />
            </svg>
            <span className="text-xs font-medium">Dark</span>
          </button>
          <button
            onClick={() => { if (!lightMode) toggleTheme(); }}
            className={`flex-1 flex flex-col items-center gap-2 px-4 py-4 rounded-lg border transition-colors ${
              lightMode
                ? "bg-gray-800 border-green-600 text-gray-200"
                : "bg-gray-800/50 border-gray-700 text-gray-400 hover:border-gray-600"
            }`}
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z" />
            </svg>
            <span className="text-xs font-medium">Light</span>
          </button>
        </div>
      </section>
    </div>
  );
}

// ══════════════════════════════════════════════════════════
//  NOTIFICATIONS TAB
// ══════════════════════════════════════════════════════════

function NotificationsTab() {
  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [newEmail, setNewEmail] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [addingChannel, setAddingChannel] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ id: string; ok: boolean; msg: string } | null>(null);
  const [groups, setGroups] = useState<DistributionGroup[]>([]);
  const [editingGroupId, setEditingGroupId] = useState<string | null>(null);
  const [addingGroup, setAddingGroup] = useState(false);

  useEffect(() => {
    fetchNotificationChannels().then(setChannels).catch(() => {});
    fetchDistributionGroups().then(setGroups).catch(() => {});
  }, []);

  async function handleAddChannel() {
    if (!newEmail.trim()) return;
    setAddingChannel(true);
    try {
      const ch = await addNotificationChannel({
        type: "email",
        address: newEmail.trim(),
        label: newLabel.trim() || undefined,
      });
      setChannels((prev) => [...prev, ch]);
      setNewEmail("");
      setNewLabel("");
    } catch { /* silent */ }
    setAddingChannel(false);
  }

  async function handleToggleChannel(id: string, enabled: boolean) {
    try {
      const updated = await updateNotificationChannel(id, { enabled });
      setChannels((prev) => prev.map((c) => (c.id === id ? updated : c)));
    } catch { /* silent */ }
  }

  async function handleDeleteChannel(id: string) {
    await deleteNotificationChannel(id);
    setChannels((prev) => prev.filter((c) => c.id !== id));
  }

  async function handleTestChannel(id: string) {
    setTestingId(id);
    setTestResult(null);
    try {
      const result = await testNotificationChannel(id);
      setTestResult({ id, ok: result.success, msg: result.message });
    } catch {
      setTestResult({ id, ok: false, msg: "Failed to test" });
    }
    setTestingId(null);
  }

  async function handleAddGroup() {
    setAddingGroup(true);
    try {
      const nextNum = groups.length + 1;
      const name = `Group ${nextNum}`;
      const g = await addDistributionGroup({ name, description: "", emails: [] });
      setGroups((prev) => [...prev, g]);
      setEditingGroupId(g.id);
    } catch { /* silent */ }
    setAddingGroup(false);
  }

  async function handleUpdateGroup(id: string, updates: { name?: string; description?: string; emails?: string[] }) {
    try {
      const updated = await updateDistributionGroup(id, updates);
      setGroups((prev) => prev.map((g) => (g.id === id ? updated : g)));
    } catch { /* silent */ }
    setEditingGroupId(null);
  }

  async function handleDeleteGroup(id: string) {
    await deleteDistributionGroup(id);
    setGroups((prev) => prev.filter((g) => g.id !== id));
  }

  return (
    <div className="space-y-6">
      {/* Notification channels */}
      <section>
        <h3 className="text-sm font-semibold text-gray-200 mb-1">Notification Channels</h3>
        <p className="text-xs text-gray-500 mb-3">
          Email addresses that receive notifications from your agents.
        </p>

        {channels.length > 0 && (
          <div className="space-y-2 mb-3">
            {channels.map((ch) => (
              <div
                key={ch.id}
                className="flex items-center gap-2 px-3 py-2 bg-gray-800/50 border border-gray-700/50 rounded-lg"
              >
                <svg className="w-4 h-4 text-gray-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
                </svg>
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-gray-200 truncate">{ch.address}</div>
                  {ch.label && ch.label !== ch.address && (
                    <div className="text-[10px] text-gray-500">{ch.label}</div>
                  )}
                </div>
                {testResult?.id === ch.id && (
                  <span className={`text-[10px] ${testResult.ok ? "text-green-400" : "text-red-400"}`}>
                    {testResult.ok ? "Sent!" : testResult.msg}
                  </span>
                )}
                <button
                  onClick={() => handleTestChannel(ch.id)}
                  disabled={testingId === ch.id}
                  className="text-[10px] text-gray-400 hover:text-white transition-colors px-1"
                  title="Send test notification"
                >
                  {testingId === ch.id ? (
                    <div className="w-3 h-3 border border-gray-500 border-t-white rounded-full animate-spin" />
                  ) : (
                    "Test"
                  )}
                </button>
                <ToggleSwitch
                  checked={ch.enabled}
                  onToggle={() => handleToggleChannel(ch.id, !ch.enabled)}
                  accent="green"
                  size="sm"
                  title={ch.enabled ? "Disable channel" : "Enable channel"}
                />
                <button
                  onClick={() => handleDeleteChannel(ch.id)}
                  className="p-0.5 text-gray-500 hover:text-red-400 transition-colors"
                  title="Remove channel"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="space-y-2">
          <div className="flex gap-2">
            <input
              type="email"
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              placeholder="email@example.com"
              className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500"
              onKeyDown={(e) => e.key === "Enter" && handleAddChannel()}
            />
            <input
              type="text"
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              placeholder="Label (optional)"
              className="w-32 bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500"
              onKeyDown={(e) => e.key === "Enter" && handleAddChannel()}
            />
          </div>
          <button
            onClick={handleAddChannel}
            disabled={!newEmail.trim() || addingChannel}
            className="w-full py-1.5 text-xs rounded-lg bg-gray-800 border border-gray-700 text-gray-400 hover:border-gray-600 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {addingChannel ? "Adding..." : "+ Add email channel"}
          </button>
        </div>

        {channels.length === 0 && (
          <p className="text-xs text-gray-600 text-center py-2 mt-2">
            No channels configured. Add an email to receive notification reports.
          </p>
        )}
      </section>

      {/* Distribution groups */}
      <section>
        <h3 className="text-sm font-semibold text-gray-200 mb-1">Distribution Groups</h3>
        <p className="text-xs text-gray-500 mb-3">
          Group email addresses together. Assign a group to an agent so notifications go to the right people. Max 10 groups.
        </p>

        {groups.length > 0 && (
          <div className="space-y-2 mb-3">
            {groups.map((g) => {
              const isEditing = editingGroupId === g.id;
              return (
                <div key={g.id} className="px-3 py-2 bg-gray-800/50 border border-gray-700/50 rounded-lg">
                  {isEditing ? (
                    <NotifGroupEditForm
                      group={g}
                      onSave={(updates) => handleUpdateGroup(g.id, updates)}
                      onCancel={() => setEditingGroupId(null)}
                    />
                  ) : (
                    <div className="flex items-start gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-gray-200 font-medium">{g.name}</div>
                        {g.description && (
                          <div className="text-[10px] text-gray-500 mt-0.5">{g.description}</div>
                        )}
                        <div className="text-[10px] text-gray-600 mt-0.5 truncate">
                          {g.emails.length > 0 ? g.emails.join(", ") : "No emails"}
                        </div>
                      </div>
                      <button
                        onClick={() => setEditingGroupId(g.id)}
                        className="p-0.5 text-gray-500 hover:text-gray-200 transition-colors shrink-0"
                        title="Edit group"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                        </svg>
                      </button>
                      <button
                        onClick={() => handleDeleteGroup(g.id)}
                        className="p-0.5 text-gray-500 hover:text-red-400 transition-colors shrink-0"
                        title="Delete group"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {groups.length < 10 && (
          <button
            onClick={handleAddGroup}
            disabled={addingGroup}
            className="w-full py-1.5 text-xs rounded-lg bg-gray-800 border border-gray-700 text-gray-400 hover:border-gray-600 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {addingGroup ? "Adding..." : "+ Add distribution group"}
          </button>
        )}

        {groups.length === 0 && (
          <p className="text-xs text-gray-600 text-center py-2">
            No distribution groups yet. Create one to target specific recipients.
          </p>
        )}
      </section>
    </div>
  );
}

function NotifGroupEditForm({
  group,
  onSave,
  onCancel,
}: {
  group: DistributionGroup;
  onSave: (updates: { name?: string; description?: string; emails?: string[] }) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(group.name);
  const [desc, setDesc] = useState(group.description);
  const [emails, setEmails] = useState(group.emails.join(", "));

  return (
    <div className="space-y-2">
      <input
        type="text"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Group name"
        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-2 py-1 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500"
        maxLength={100}
      />
      <input
        type="text"
        value={desc}
        onChange={(e) => setDesc(e.target.value)}
        placeholder="Description"
        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-2 py-1 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500"
        maxLength={300}
      />
      <textarea
        value={emails}
        onChange={(e) => setEmails(e.target.value)}
        placeholder="Emails (comma or newline separated)"
        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-2 py-1 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500 min-h-[40px] resize-y"
        rows={2}
      />
      <div className="flex gap-2 justify-end">
        <button onClick={onCancel} className="text-[10px] text-gray-500 hover:text-gray-200 transition-colors px-2 py-1">
          Cancel
        </button>
        <button
          onClick={() => {
            const parsed = emails.split(/[,;\n]/).map((e) => e.trim()).filter(Boolean);
            onSave({ name: name.trim() || undefined, description: desc.trim(), emails: parsed });
          }}
          disabled={!name.trim()}
          className="text-[10px] text-green-400 hover:text-green-300 transition-colors px-2 py-1 disabled:opacity-40"
        >
          Save
        </button>
      </div>
    </div>
  );
}
