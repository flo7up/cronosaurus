import { useState, useRef, useEffect } from "react";
import ToggleSwitch from "./ToggleSwitch";
import type { MCPServer, ToolPreference } from "../types/chat";

/** Built-in tools that always appear in the menu */
const BUILT_IN_TOOLS = [
  {
    id: "web_search",
    label: "Web search",
    description: "Search the web for real-time information",
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
      </svg>
    ),
  },
  {
    id: "triggers",
    label: "Triggers",
    description: "Schedule recurring tasks on a timer",
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  {
    id: "crypto_prices",
    label: "Crypto prices",
    description: "Get live crypto market data from Hyperliquid",
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  {
    id: "stock_prices",
    label: "Stock prices",
    description: "Get stock market data, history & company info from Yahoo Finance",
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
      </svg>
    ),
  },
] as const;

interface ToolMenuProps {
  mcpServers: MCPServer[];
  toolPreferences: ToolPreference[];
  onToggleTool: (toolId: string, enabled: boolean) => void;
  onOpenMCPPanel: () => void;
}

export default function ToolMenu({
  mcpServers,
  toolPreferences,
  onToggleTool,
  onOpenMCPPanel,
}: ToolMenuProps) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  // Close on click outside
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (
        menuRef.current &&
        !menuRef.current.contains(e.target as Node) &&
        buttonRef.current &&
        !buttonRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  const isToolEnabled = (id: string) => {
    const pref = toolPreferences.find((p) => p.id === id);
    return pref ? pref.enabled : true; // default to enabled
  };

  const enabledCount =
    BUILT_IN_TOOLS.filter((t) => isToolEnabled(t.id)).length +
    mcpServers.filter((s) => s.active && isToolEnabled(`mcp_${s.id}`)).length;

  return (
    <div className="relative">
      {/* Trigger button — matches ChatGPT "+" style */}
      <button
        ref={buttonRef}
        onClick={() => setOpen(!open)}
        className={`
          p-2 rounded-lg transition-colors
          ${open
            ? "bg-gray-700 text-white"
            : "text-gray-400 hover:text-white hover:bg-gray-800"
          }
        `}
        title="Tools & integrations"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
      </button>

      {/* Badge showing active tool count */}
      {enabledCount > 0 && !open && (
        <span className="absolute -top-1 -right-1 w-4 h-4 text-[10px] font-bold flex items-center justify-center rounded-full bg-purple-600 text-white pointer-events-none">
          {enabledCount}
        </span>
      )}

      {/* Popup menu */}
      {open && (
        <div
          ref={menuRef}
          className="absolute bottom-full left-0 mb-2 w-72 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl z-50 overflow-hidden"
        >
          {/* Built-in tools */}
          <div className="p-2">
            <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
              Built-in tools
            </p>
            {BUILT_IN_TOOLS.map((tool) => {
              const enabled = isToolEnabled(tool.id);
              return (
                <button
                  key={tool.id}
                  onClick={() => onToggleTool(tool.id, !enabled)}
                  className={`
                    w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors
                    ${enabled
                      ? "text-white hover:bg-gray-800"
                      : "text-gray-500 hover:bg-gray-800/50"
                    }
                  `}
                >
                  <span className={`shrink-0 ${enabled ? "text-purple-400" : "text-gray-600"}`}>
                    {tool.icon}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{tool.label}</p>
                    <p className="text-[11px] text-gray-500 truncate">{tool.description}</p>
                  </div>
                  {/* Toggle switch */}
                  <ToggleSwitch
                    checked={enabled}
                    accent="purple"
                    size="sm"
                    className="shrink-0 pointer-events-none"
                  />
                </button>
              );
            })}
          </div>

          {/* Divider */}
          <div className="border-t border-gray-800" />

          {/* MCP servers */}
          <div className="p-2">
            <div className="flex items-center justify-between px-2 py-1">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                MCP Servers
              </p>
              <button
                onClick={() => {
                  setOpen(false);
                  onOpenMCPPanel();
                }}
                className="text-[10px] text-purple-400 hover:text-purple-300 transition-colors"
              >
                Configure
              </button>
            </div>

            {mcpServers.length === 0 ? (
              <div className="px-3 py-3 text-center">
                <p className="text-xs text-gray-500 mb-2">No MCP servers configured</p>
                <button
                  onClick={() => {
                    setOpen(false);
                    onOpenMCPPanel();
                  }}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs bg-gray-800 text-gray-300 rounded-lg hover:bg-gray-700 hover:text-white transition-colors"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  Add MCP Server
                </button>
              </div>
            ) : (
              <>
                {mcpServers.map((srv) => {
                  const toolId = `mcp_${srv.id}`;
                  const enabled = srv.active && isToolEnabled(toolId);
                  return (
                    <button
                      key={srv.id}
                      onClick={() => onToggleTool(toolId, !enabled)}
                      className={`
                        w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors
                        ${enabled
                          ? "text-white hover:bg-gray-800"
                          : "text-gray-500 hover:bg-gray-800/50"
                        }
                      `}
                      disabled={!srv.active}
                      title={!srv.active ? "Server is inactive — enable it in MCP settings" : ""}
                    >
                      {/* Server icon */}
                      <span className={`shrink-0 ${enabled ? "text-green-400" : "text-gray-600"}`}>
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                            d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
                        </svg>
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{srv.name}</p>
                        <p className="text-[11px] text-gray-500 truncate">
                          {srv.description || srv.url}
                        </p>
                      </div>
                      {/* Toggle switch */}
                      {srv.active ? (
                        <ToggleSwitch
                          checked={enabled}
                          accent="green"
                          size="sm"
                          className="shrink-0 pointer-events-none"
                        />
                      ) : (
                        <span className="text-[10px] text-gray-600 shrink-0">Inactive</span>
                      )}
                    </button>
                  );
                })}

                {/* Add more link */}
                <button
                  onClick={() => {
                    setOpen(false);
                    onOpenMCPPanel();
                  }}
                  className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left text-gray-500 hover:bg-gray-800/50 hover:text-gray-300 transition-colors"
                >
                  <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 4v16m8-8H4" />
                  </svg>
                  <span className="text-sm">Add MCP Server</span>
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
