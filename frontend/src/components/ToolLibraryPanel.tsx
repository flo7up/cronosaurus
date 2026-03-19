import { useState, useEffect } from "react";
import type { ToolCatalogEntry, EmailAccount } from "../types/chat";
import { fetchToolCatalog, updateToolLibrary, batchUpdateToolLibrary } from "../api/user";
import ToggleSwitch from "./ToggleSwitch";

interface ToolLibraryPanelProps {
  onClose: () => void;
  onOpenEmailConfig: () => void;
  emailAccounts: EmailAccount[];
  onToolLibraryChange: (library: string[]) => void;
}

// Icons for each tool category
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
  _mcp: (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.737 5.1a3.375 3.375 0 012.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 01.9 2.7m0 0a3 3 0 01-3 3m0 3h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008zm-3 6h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008z" />
    </svg>
  ),
  weather: (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M2.25 15a4.5 4.5 0 004.5 4.5H18a3.75 3.75 0 001.332-7.257 3 3 0 00-3.758-3.848 5.25 5.25 0 00-10.233 2.33A4.502 4.502 0 002.25 15z" />
    </svg>
  ),
};

export default function ToolLibraryPanel({
  onClose,
  onOpenEmailConfig,
  emailAccounts,
  onToolLibraryChange,
}: ToolLibraryPanelProps) {
  const defaultAccount = emailAccounts.find((a) => a.is_default) ?? emailAccounts[0] ?? null;
  const accountCount = emailAccounts.length;
  const [catalog, setCatalog] = useState<ToolCatalogEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchToolCatalog()
      .then(setCatalog)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // Refetch catalog when emailAccounts changes (to update available state)
  useEffect(() => {
    if (!loading) {
      fetchToolCatalog()
        .then(setCatalog)
        .catch(() => {});
    }
  }, [emailAccounts]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleToggle = async (toolId: string, currentlyInLibrary: boolean) => {
    const action = currentlyInLibrary ? "remove" : "add";
    // Optimistic update — flip UI immediately
    setCatalog((prev) =>
      prev.map((t) => (t.id === toolId ? { ...t, in_library: !currentlyInLibrary } : t))
    );
    try {
      const newLibrary = await updateToolLibrary(toolId, action);
      onToolLibraryChange(newLibrary);
    } catch (e) {
      // Revert on failure
      setCatalog((prev) =>
        prev.map((t) => (t.id === toolId ? { ...t, in_library: currentlyInLibrary } : t))
      );
      console.error("Failed to update tool library", e);
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
      const latestLibrary = await batchUpdateToolLibrary(
        toChange.map((t) => ({ tool_id: t.id, action: action as "add" | "remove" }))
      );
      onToolLibraryChange(latestLibrary);
    } catch {
      // Revert all on failure
      setCatalog((prev) =>
        prev.map((t) => (changeIds.has(t.id) ? { ...t, in_library: !enable } : t))
      );
    }
  };

  const [search, setSearch] = useState("");

  const filtered = search.trim()
    ? catalog.filter(
        (t) =>
          t.label.toLowerCase().includes(search.toLowerCase()) ||
          t.description.toLowerCase().includes(search.toLowerCase()) ||
          t.id.toLowerCase().includes(search.toLowerCase())
      )
    : catalog;

  // Group tools by category, preserving a defined order
  const CATEGORY_ORDER = ["Finance", "Research", "Communication", "Social", "Automation", "Media", "Cloud", "Utilities", "Agent", "Custom", "MCP Servers"];
  const grouped = new Map<string, ToolCatalogEntry[]>();
  for (const tool of filtered) {
    const cat = tool.category === "mcp" ? "MCP Servers" : (tool.category || "Other");
    if (!grouped.has(cat)) grouped.set(cat, []);
    grouped.get(cat)!.push(tool);
  }
  const sortedCategories = [...grouped.keys()].sort(
    (a, b) => (CATEGORY_ORDER.indexOf(a) === -1 ? 99 : CATEGORY_ORDER.indexOf(a)) - (CATEGORY_ORDER.indexOf(b) === -1 ? 99 : CATEGORY_ORDER.indexOf(b))
  );

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-gray-900 rounded-2xl border border-gray-700 w-full max-w-lg max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M11.42 15.17l-5.1-3.56a1 1 0 00-.86-.08l-2.86.94a1 1 0 01-1.28-.7l-.54-2.26a1 1 0 01.7-1.19l2.89-.78a1 1 0 00.65-.54l1.35-2.88a1 1 0 011.56-.35l2.18 1.9a1 1 0 00.88.2l2.92-.62a1 1 0 011.13.76l.54 2.26a1 1 0 01-.44 1.08l-2.44 1.56a1 1 0 00-.46.76l-.16 2.97a1 1 0 01-1.14.92l-2.26-.42a1 1 0 00-.68.12z" />
            </svg>
            <h2 className="text-lg font-semibold text-white">Tool Library</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-gray-400 hover:text-white transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="flex items-center justify-center py-12 text-gray-500">
              Loading tools...
            </div>
          ) : (
            <div className="space-y-5">
              {/* Description */}
              <p className="text-sm text-gray-400">
                Manage the tools available when building agents. Only tools in your library
                will appear in the agent configuration.
              </p>

              {/* Search */}
              <div className="relative">
                <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
                </svg>
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search tools..."
                  className="w-full pl-9 pr-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:border-teal-500"
                />
              </div>

              {/* Build Your Own Tool link */}
              <button
                onClick={() => window.open("https://github.com/AiondaDotCom/cronosaurus/blob/main/docs/CUSTOM_TOOLS.md", "_blank")}
                className="text-xs text-teal-400 hover:text-teal-300 transition-colors flex items-center gap-1"
              >
                <span>+</span> BUILD YOUR OWN TOOL
              </button>

              {/* Category groups */}
              {sortedCategories.map((category) => {
                const tools = grouped.get(category) || [];
                return (
                  <div key={category}>
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                        {category}
                      </h3>
                      <div className="flex gap-1.5">
                        <button
                          onClick={() => handleBatchToggle(tools, true)}
                          disabled={tools.every((t) => t.in_library)}
                          className="px-2 py-0.5 text-[10px] rounded bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                        >
                          Enable all
                        </button>
                        <button
                          onClick={() => handleBatchToggle(tools, false)}
                          disabled={tools.every((t) => !t.in_library)}
                          className="px-2 py-0.5 text-[10px] rounded bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                        >
                          Disable all
                        </button>
                      </div>
                    </div>
                    <div className="space-y-1">
                      {tools.map((tool) => (
                        <ToolRow
                          key={tool.id}
                          tool={tool}
                          onToggle={() => handleToggle(tool.id, tool.in_library)}
                        />
                      ))}
                    </div>

                    {/* Email config status for Communication category */}
                    {category === "Communication" && tools.some((t) => t.id === "email_send" || t.id === "email_read") && (
                      <div className="mt-3 rounded-lg bg-gray-800/50 border border-gray-700/50 p-3">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            {defaultAccount ? (
                              <>
                                <span className="w-2 h-2 rounded-full bg-green-400" />
                                <span className="text-xs text-gray-300">
                                  {defaultAccount.label || defaultAccount.from_email}
                                </span>
                                {accountCount > 1 && (
                                  <span className="text-[10px] bg-blue-900/40 text-blue-400 px-1.5 py-0.5 rounded-full">
                                    +{accountCount - 1} more
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
                                <span className="text-xs text-gray-500">
                                  No email accounts configured
                                </span>
                              </>
                            )}
                          </div>
                          <button
                            onClick={onOpenEmailConfig}
                            className="px-3 py-1 text-xs rounded-lg bg-gray-700 text-gray-300
                              hover:bg-gray-600 hover:text-white transition-colors"
                          >
                            {defaultAccount ? "Manage" : "Set Up"}
                          </button>
                        </div>
                        {!defaultAccount && (
                          <p className="text-xs text-gray-600 mt-2">
                            Configure an email account to enable Send Email and Read Email tools.
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-800">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-800 text-gray-300 text-sm rounded-lg
              hover:bg-gray-700 transition-colors"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Single tool row ─────────────────────────────────────────── */

function ToolRow({
  tool,
  onToggle,
}: {
  tool: ToolCatalogEntry;
  onToggle: () => void;
}) {
  const [showInfo, setShowInfo] = useState(false);
  const icon = TOOL_ICONS[tool.id] || (tool.category === "mcp" ? TOOL_ICONS._mcp : undefined);
  const needsConfig = tool.requires_config && !tool.available;
  const hasFunctions = tool.tools && tool.tools.length > 0;

  return (
    <div>
      <div className="flex items-center gap-3 px-3 py-3 rounded-xl hover:bg-gray-800/60 transition-colors">
        <button
          onClick={onToggle}
          className="flex items-center gap-3 flex-1 min-w-0"
        >
          <span className={tool.in_library ? "text-purple-400" : "text-gray-600"}>
            {icon || (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M4.5 12a7.5 7.5 0 0015 0m-15 0a7.5 7.5 0 1115 0m-15 0H3m16.5 0H21" />
              </svg>
            )}
          </span>
          <div className="flex-1 text-left min-w-0">
            <div className="flex items-center gap-2">
              <span className={`text-sm font-medium ${tool.in_library ? "text-white" : "text-gray-400"}`}>
                {tool.label}
              </span>
              {needsConfig && (
                <span className="text-[10px] bg-yellow-900/40 text-yellow-400 px-1.5 py-0.5 rounded-full">
                  Needs setup
                </span>
              )}
            </div>
            <div className="text-xs text-gray-500 mt-0.5">{tool.description}</div>
          </div>
        </button>
        {hasFunctions && (
          <button
            onClick={(e) => { e.stopPropagation(); setShowInfo(!showInfo); }}
            title="View tool functions & parameters"
            className={`p-1 rounded-md transition-colors flex-shrink-0 ${
              showInfo
                ? "text-purple-400 bg-purple-900/30"
                : "text-gray-500 hover:text-gray-300 hover:bg-gray-800"
            }`}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </button>
        )}
        <button
          onClick={onToggle}
          className="flex-shrink-0"
        >
          <ToggleSwitch checked={tool.in_library} accent="purple" className="pointer-events-none" />
        </button>
      </div>

      {/* Expanded parameter info */}
      {showInfo && hasFunctions && (
        <div className="mx-3 mb-2 px-3 py-2.5 rounded-lg bg-gray-800/80 border border-gray-700/50">
          <div className="space-y-2.5">
            {tool.tools.map((fn) => (
              <div key={fn.name}>
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] font-mono text-purple-300">{fn.name}</span>
                </div>
                {fn.parameters.length > 0 ? (
                  <div className="mt-1 space-y-0.5">
                    {fn.parameters.map((p) => (
                      <div key={p.name} className="flex items-start gap-1.5 text-[11px] pl-2">
                        <span className="font-mono text-gray-300">{p.name}</span>
                        <span className="text-gray-600">:</span>
                        <span className="text-blue-400">{p.type}</span>
                        {p.required && (
                          <span className="text-red-400 text-[9px] mt-px">*</span>
                        )}
                        {p.description && (
                          <span className="text-gray-500 truncate" title={p.description}>
                            — {p.description}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-[11px] text-gray-600 pl-2 mt-0.5">No parameters</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
