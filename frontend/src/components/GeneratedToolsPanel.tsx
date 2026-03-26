import { useState, useEffect } from "react";
import type { GeneratedTool } from "../types/chat";
import {
  fetchGeneratedTools,
  getGeneratedTool,
  toggleGeneratedTool,
  deleteGeneratedTool,
} from "../api/agent";
import ToggleSwitch from "./ToggleSwitch";

interface GeneratedToolsPanelProps {
  onClose: () => void;
}

export default function GeneratedToolsPanel({ onClose }: GeneratedToolsPanelProps) {
  const [tools, setTools] = useState<GeneratedTool[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [codeView, setCodeView] = useState<{ id: string; code: string } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  useEffect(() => {
    fetchGeneratedTools()
      .then(setTools)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleToggle = async (docId: string, currentActive: boolean) => {
    setTools((prev) =>
      prev.map((t) => (t.id === docId ? { ...t, active: !currentActive } : t))
    );
    try {
      await toggleGeneratedTool(docId, !currentActive);
    } catch {
      setTools((prev) =>
        prev.map((t) => (t.id === docId ? { ...t, active: currentActive } : t))
      );
    }
  };

  const handleDelete = async (docId: string) => {
    try {
      await deleteGeneratedTool(docId);
      setTools((prev) => prev.filter((t) => t.id !== docId));
      setConfirmDelete(null);
    } catch {
      // keep in list
    }
  };

  const handleViewCode = async (docId: string) => {
    if (codeView?.id === docId) {
      setCodeView(null);
      return;
    }
    try {
      const detail = await getGeneratedTool(docId);
      setCodeView({ id: docId, code: detail.code || "# No code available" });
    } catch {
      setCodeView({ id: docId, code: "# Failed to load code" });
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-gray-900 rounded-2xl border border-gray-700 w-full max-w-lg max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <span className="text-lg">🤖</span>
            <h2 className="text-lg font-semibold text-white">Agent-Created Tools</h2>
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
              Loading...
            </div>
          ) : tools.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-400 text-sm">No agent-created tools yet.</p>
              <p className="text-gray-600 text-xs mt-2">
                Enable the &ldquo;Self-Extension&rdquo; tool on an agent, then ask it to
                create a tool when it encounters a missing capability.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-sm text-gray-400 mb-4">
                These tools were created by agents at runtime. You can review their code,
                deactivate, or delete them.
              </p>

              {tools.map((tool) => (
                <div
                  key={tool.id}
                  className="rounded-xl border border-gray-700/60 bg-gray-800/40 overflow-hidden"
                >
                  {/* Tool row */}
                  <div className="flex items-center gap-3 px-4 py-3">
                    <button
                      onClick={() => setExpandedId(expandedId === tool.id ? null : tool.id)}
                      className="flex items-center gap-3 flex-1 min-w-0 text-left"
                    >
                      <span className="text-amber-400 text-lg flex-shrink-0">🤖</span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className={`text-sm font-medium ${tool.active ? "text-white" : "text-gray-500"}`}>
                            {tool.label}
                          </span>
                          <span className="text-[10px] bg-amber-900/40 text-amber-400 px-1.5 py-0.5 rounded-full">
                            Agent-created
                          </span>
                        </div>
                        <div className="text-xs text-gray-500 mt-0.5 truncate">{tool.description}</div>
                      </div>
                    </button>
                    <button
                      onClick={() => handleToggle(tool.id, tool.active)}
                      className="flex-shrink-0"
                    >
                      <ToggleSwitch checked={tool.active} accent="amber" className="pointer-events-none" />
                    </button>
                  </div>

                  {/* Expanded details */}
                  {expandedId === tool.id && (
                    <div className="px-4 pb-3 space-y-3 border-t border-gray-700/40 pt-3">
                      {/* Metadata */}
                      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                        <div className="text-gray-500">Tool ID</div>
                        <div className="text-gray-300 font-mono">{tool.tool_id}</div>
                        <div className="text-gray-500">Created by</div>
                        <div className="text-gray-300">
                          {tool.created_by_agent_name || tool.created_by_agent_id || "Unknown"}
                        </div>
                        <div className="text-gray-500">Created</div>
                        <div className="text-gray-300">
                          {new Date(tool.created_at).toLocaleDateString()}
                        </div>
                      </div>

                      {/* Functions */}
                      {tool.functions.length > 0 && (
                        <div>
                          <div className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">
                            Functions
                          </div>
                          <div className="space-y-1">
                            {tool.functions.map((fn) => (
                              <div key={fn.name} className="flex items-center gap-1.5">
                                <span className="text-[11px] font-mono text-purple-300">{fn.name}</span>
                                <span className="text-[10px] text-gray-600">— {fn.description}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Actions */}
                      <div className="flex items-center gap-2 pt-1">
                        <button
                          onClick={() => handleViewCode(tool.id)}
                          className={`px-3 py-1 text-xs rounded-lg transition-colors ${
                            codeView?.id === tool.id
                              ? "bg-purple-900/40 text-purple-300"
                              : "bg-gray-700 text-gray-300 hover:bg-gray-600"
                          }`}
                        >
                          {codeView?.id === tool.id ? "Hide Code" : "View Code"}
                        </button>
                        {confirmDelete === tool.id ? (
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-red-400">Delete permanently?</span>
                            <button
                              onClick={() => handleDelete(tool.id)}
                              className="px-2 py-1 text-xs rounded-lg bg-red-900/50 text-red-300 hover:bg-red-800/60"
                            >
                              Yes
                            </button>
                            <button
                              onClick={() => setConfirmDelete(null)}
                              className="px-2 py-1 text-xs rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600"
                            >
                              No
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => setConfirmDelete(tool.id)}
                            className="px-3 py-1 text-xs rounded-lg bg-gray-700 text-red-400 hover:bg-red-900/30 transition-colors"
                          >
                            Delete
                          </button>
                        )}
                      </div>

                      {/* Code viewer */}
                      {codeView?.id === tool.id && (
                        <div className="mt-2 rounded-lg bg-gray-950 border border-gray-700/50 p-3 overflow-x-auto">
                          <pre className="text-[11px] font-mono text-gray-300 whitespace-pre-wrap">
                            {codeView.code}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-800">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-800 text-gray-300 text-sm rounded-lg hover:bg-gray-700 transition-colors"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
