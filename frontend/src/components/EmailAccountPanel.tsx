import { useState, useEffect } from "react";
import type { EmailAccount, EmailAccountCreate } from "../types/chat";

interface EmailAccountPanelProps {
  accounts: EmailAccount[];
  onAdd: (data: EmailAccountCreate) => Promise<void>;
  onUpdate: (id: string, data: Partial<EmailAccountCreate>) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onTest: (id: string) => Promise<{ success: boolean; message?: string; error?: string }>;
  onClose: () => void;
}

const COMMON_PROVIDERS = [
  { label: "Gmail", host: "smtp.gmail.com", port: 587, tls: true, imap_host: "imap.gmail.com", imap_port: 993 },
  { label: "Outlook / Microsoft 365", host: "smtp.office365.com", port: 587, tls: true, imap_host: "outlook.office365.com", imap_port: 993 },
  { label: "Yahoo", host: "smtp.mail.yahoo.com", port: 587, tls: true, imap_host: "imap.mail.yahoo.com", imap_port: 993 },
  { label: "iCloud", host: "smtp.mail.me.com", port: 587, tls: true, imap_host: "imap.mail.me.com", imap_port: 993 },
  { label: "Custom", host: "", port: 587, tls: true, imap_host: "", imap_port: 993 },
];

const EMPTY_FORM: EmailAccountCreate = {
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

export default function EmailAccountPanel({
  accounts,
  onAdd,
  onUpdate,
  onDelete,
  onTest,
  onClose,
}: EmailAccountPanelProps) {
  // null = list view, "new" = add form, string = editing that account's id
  const [editing, setEditing] = useState<string | null>(null);
  const [form, setForm] = useState<EmailAccountCreate>({ ...EMPTY_FORM });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    message?: string;
    error?: string;
  } | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  // When switching to edit mode, populate form
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
      setForm({ ...EMPTY_FORM, is_default: accounts.length === 0 });
    }
    setTestResult(null);
    setShowPassword(false);
  }, [editing, accounts]);

  const handleProviderSelect = (provider: (typeof COMMON_PROVIDERS)[number]) => {
    setForm((prev) => ({
      ...prev,
      smtp_host: provider.host,
      smtp_port: provider.port,
      use_tls: provider.tls,
      imap_host: provider.imap_host,
      imap_port: provider.imap_port,
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

  const handleTest = async (accountId: string) => {
    setTesting(accountId);
    setTestResult(null);
    try {
      const result = await onTest(accountId);
      setTestResult(result);
    } catch {
      setTestResult({ success: false, error: "Test request failed" });
    } finally {
      setTesting(null);
    }
  };

  const handleDelete = async (accountId: string) => {
    if (confirmDelete !== accountId) {
      setConfirmDelete(accountId);
      return;
    }
    await onDelete(accountId);
    setConfirmDelete(null);
  };

  const editingAccount = editing && editing !== "new" ? accounts.find((a) => a.id === editing) : null;

  // ── List View ──
  if (!editing) {
    return (
      <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
        <div className="bg-gray-900 rounded-2xl border border-gray-700 w-full max-w-lg max-h-[85vh] flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
            <div className="flex items-center gap-2">
              <svg className="w-5 h-5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75"
                />
              </svg>
              <h2 className="text-lg font-semibold text-white">Email Accounts</h2>
            </div>
            <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-white transition-colors">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Account list */}
          <div className="flex-1 overflow-y-auto p-4 space-y-2">
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
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                      </svg>
                    ) : (
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                          d="M13 10V3L4 14h7v7l9-11h-7z" />
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
                      confirmDelete === acct.id
                        ? "text-red-400 hover:text-red-300"
                        : "text-gray-400 hover:text-red-400"
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

            {/* Test result toast */}
            {testResult && (
              <div
                className={`rounded-lg px-4 py-3 text-sm ${
                  testResult.success
                    ? "bg-green-900/30 border border-green-800 text-green-300"
                    : "bg-red-900/30 border border-red-800 text-red-300"
                }`}
              >
                {testResult.success
                  ? testResult.message || "Connection successful!"
                  : testResult.error || "Connection failed."}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-4 py-3 border-t border-gray-800 flex justify-between">
            <button
              onClick={() => setEditing("new")}
              className="px-4 py-2 bg-white text-black text-sm rounded-lg font-medium
                hover:bg-gray-200 transition-colors flex items-center gap-1.5"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Add Account
            </button>
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-800 text-gray-300 text-sm rounded-lg
                hover:bg-gray-700 transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Edit / Add Form ──
  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-gray-900 rounded-2xl border border-gray-700 w-full max-w-lg max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setEditing(null)}
              className="p-1 text-gray-400 hover:text-white transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <h2 className="text-lg font-semibold text-white">
              {editing === "new" ? "Add Email Account" : "Edit Email Account"}
            </h2>
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
          {/* Warning if password is missing */}
          {editingAccount && !editingAccount.has_password && (
            <div className="mb-4 p-3 rounded-lg bg-amber-900/30 border border-amber-700 text-teal-300 text-sm flex items-start gap-2">
              <svg className="w-5 h-5 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"
                />
              </svg>
              <span>
                <strong>Password missing!</strong> Please re-enter your email password below and save.
              </span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Account Label */}
            <div>
              <label className="block text-xs text-gray-400 mb-1">Account Label</label>
              <input
                type="text"
                value={form.label}
                onChange={(e) => setForm({ ...form, label: e.target.value })}
                placeholder="e.g. Work, Personal, Newsletter"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white
                  placeholder-gray-500 focus:outline-none focus:border-gray-500"
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
                        : "border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600 hover:text-gray-300"
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
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white
                    placeholder-gray-500 focus:outline-none focus:border-gray-500"
                  required
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Port</label>
                <input
                  type="number"
                  value={form.smtp_port}
                  onChange={(e) => setForm({ ...form, smtp_port: parseInt(e.target.value) || 587 })}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white
                    focus:outline-none focus:border-gray-500"
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
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white
                  placeholder-gray-500 focus:outline-none focus:border-gray-500"
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
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 pr-10 text-sm text-white
                    placeholder-gray-500 focus:outline-none focus:border-gray-500"
                  required={editing === "new"}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-gray-300"
                >
                  {showPassword ? (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.878 9.878L6.59 6.59m7.532 7.532l3.29 3.29M3 3l18 18"
                      />
                    </svg>
                  ) : (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                      />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                      />
                    </svg>
                  )}
                </button>
              </div>
              <p className="text-xs text-gray-600 mt-1">
                For Gmail, use an <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:text-blue-400">App Password</a>.
                Your password is encrypted before storage.
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
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white
                    placeholder-gray-500 focus:outline-none focus:border-gray-500"
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
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white
                    placeholder-gray-500 focus:outline-none focus:border-gray-500"
                />
              </div>
            </div>

            {/* TLS + Default toggles */}
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setForm({ ...form, use_tls: !form.use_tls })}
                  className={`relative w-9 h-5 rounded-full transition-colors ${
                    form.use_tls ? "bg-green-600" : "bg-gray-600"
                  }`}
                >
                  <span
                    className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                      form.use_tls ? "left-[18px]" : "left-0.5"
                    }`}
                  />
                </button>
                <span className="text-sm text-gray-300">Use TLS</span>
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setForm({ ...form, is_default: !form.is_default })}
                  className={`relative w-9 h-5 rounded-full transition-colors ${
                    form.is_default ? "bg-blue-600" : "bg-gray-600"
                  }`}
                >
                  <span
                    className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                      form.is_default ? "left-[18px]" : "left-0.5"
                    }`}
                  />
                </button>
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
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white
                      placeholder-gray-500 focus:outline-none focus:border-gray-500"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Port</label>
                  <input
                    type="number"
                    value={form.imap_port}
                    onChange={(e) => setForm({ ...form, imap_port: parseInt(e.target.value) || 993 })}
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white
                      focus:outline-none focus:border-gray-500"
                  />
                </div>
              </div>
              <p className="text-xs text-gray-600 mt-1">
                Leave empty if you only need to send emails. IMAP uses the same username/password.
              </p>
            </div>

            {/* Test result */}
            {testResult && (
              <div
                className={`rounded-lg px-4 py-3 text-sm ${
                  testResult.success
                    ? "bg-green-900/30 border border-green-800 text-green-300"
                    : "bg-red-900/30 border border-red-800 text-red-300"
                }`}
              >
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
                className="px-4 py-2 bg-white text-black text-sm rounded-lg font-medium
                  hover:bg-gray-200 transition-colors disabled:opacity-50"
              >
                {saving ? "Saving..." : editing === "new" ? "Add Account" : "Update Account"}
              </button>

              {editing !== "new" && (
                <button
                  type="button"
                  onClick={() => handleTest(editing!)}
                  disabled={!!testing}
                  className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg font-medium
                    hover:bg-blue-500 transition-colors disabled:opacity-50"
                >
                  {testing ? "Testing..." : "Test Connection"}
                </button>
              )}

              <button
                type="button"
                onClick={() => setEditing(null)}
                className="px-4 py-2 bg-gray-800 text-gray-300 text-sm rounded-lg
                  hover:bg-gray-700 transition-colors ml-auto"
              >
                Back
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
