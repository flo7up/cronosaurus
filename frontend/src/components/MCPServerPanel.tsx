import { useState } from "react";
import type { MCPServer } from "../types/chat";
import ToggleSwitch from "./ToggleSwitch";

interface MCPServerPanelProps {
  servers: MCPServer[];
  onAdd: (server: Omit<MCPServer, "id">) => void;
  onDelete: (id: string) => void;
  onToggle: (id: string, active: boolean) => void;
  onUpdate: (id: string, data: Partial<Omit<MCPServer, "id">>) => void;
  onClose: () => void;
}

export default function MCPServerPanel({
  servers,
  onAdd,
  onDelete,
  onToggle,
  onUpdate,
  onClose,
}: MCPServerPanelProps) {
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: "",
    url: "",
    api_key: "",
    description: "",
  });

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
    setForm({
      name: srv.name,
      url: srv.url,
      api_key: srv.api_key,
      description: srv.description,
    });
    setShowForm(true);
  };

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-gray-900 rounded-2xl border border-gray-700 w-full max-w-2xl max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
          <h2 className="text-lg font-semibold text-white">MCP Servers</h2>
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
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {servers.length === 0 && !showForm && (
            <p className="text-gray-500 text-sm text-center py-8">
              No MCP servers configured yet.
            </p>
          )}

          {/* Server list */}
          {servers.map((srv) => (
            <div
              key={srv.id}
              className={`rounded-xl border p-4 transition-colors ${
                srv.active
                  ? "border-gray-700 bg-gray-800/50"
                  : "border-gray-800 bg-gray-900/50 opacity-60"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-medium text-white truncate">
                      {srv.name}
                    </h3>
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full ${
                        srv.active
                          ? "bg-green-900/40 text-green-400"
                          : "bg-gray-800 text-gray-500"
                      }`}
                    >
                      {srv.active ? "Active" : "Inactive"}
                    </span>
                  </div>
                  <p className="text-xs text-gray-400 mt-1 truncate">{srv.url}</p>
                  {srv.description && (
                    <p className="text-xs text-gray-500 mt-1">{srv.description}</p>
                  )}
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  {/* Toggle */}
                  <ToggleSwitch
                    checked={srv.active}
                    onToggle={() => onToggle(srv.id, !srv.active)}
                    accent="green"
                    title={srv.active ? "Deactivate" : "Activate"}
                  />
                  {/* Edit */}
                  <button
                    onClick={() => startEdit(srv)}
                    className="p-1.5 text-gray-400 hover:text-blue-400 transition-colors"
                    title="Edit"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                    </svg>
                  </button>
                  {/* Delete */}
                  <button
                    onClick={() => onDelete(srv.id)}
                    className="p-1.5 text-gray-400 hover:text-red-400 transition-colors"
                    title="Delete"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
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
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white
                    placeholder-gray-500 focus:outline-none focus:border-gray-500"
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
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white
                    placeholder-gray-500 focus:outline-none focus:border-gray-500"
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
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white
                    placeholder-gray-500 focus:outline-none focus:border-gray-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Description</label>
                <input
                  type="text"
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="What does this server do?"
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white
                    placeholder-gray-500 focus:outline-none focus:border-gray-500"
                />
              </div>
              <div className="flex gap-2 pt-1">
                <button
                  type="submit"
                  className="px-4 py-2 bg-white text-black text-sm rounded-lg font-medium
                    hover:bg-gray-200 transition-colors"
                >
                  {editId ? "Save Changes" : "Add Server"}
                </button>
                <button
                  type="button"
                  onClick={resetForm}
                  className="px-4 py-2 bg-gray-800 text-gray-300 text-sm rounded-lg
                    hover:bg-gray-700 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </form>
          )}
        </div>

        {/* Footer */}
        {!showForm && (
          <div className="px-6 py-4 border-t border-gray-800">
            <button
              onClick={() => {
                resetForm();
                setShowForm(true);
              }}
              className="flex items-center gap-2 px-4 py-2 bg-gray-800 text-white text-sm rounded-lg
                hover:bg-gray-700 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Add MCP Server
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
