import { useState } from "react";
import type { AgentTrigger } from "../types/chat";
import ToggleSwitch from "./ToggleSwitch";

interface TriggerPanelProps {
  trigger: AgentTrigger | null;
  onClose: () => void;
  onCreate: (data: {
    type?: string;
    interval_minutes?: number;
    prompt: string;
    description?: string;
    filter_from?: string;
    filter_subject?: string;
    filter_body?: string;
    filter_header?: string;
    max_age_minutes?: number;
    filter_after_date?: string;
  }) => void;
  onUpdate: (
    data: Partial<{
      interval_minutes: number;
      prompt: string;
      description: string;
      filter_from: string;
      filter_subject: string;
      filter_body: string;
      filter_header: string;
      max_age_minutes: number;
      filter_after_date: string;
    }>
  ) => void;
  onToggle: (active: boolean) => void;
  onDelete: () => void;
}

const INTERVAL_PRESETS = [
  { label: "10 min", value: 10 },
  { label: "15 min", value: 15 },
  { label: "30 min", value: 30 },
  { label: "1 hour", value: 60 },
  { label: "6 hours", value: 360 },
  { label: "Daily", value: 1440 },
];

export default function TriggerPanel({
  trigger,
  onClose,
  onCreate,
  onUpdate,
  onToggle,
  onDelete,
}: TriggerPanelProps) {
  const [editing, setEditing] = useState(!trigger);
  const [triggerType, setTriggerType] = useState<"regular" | "gmail_push">(
    (trigger?.type as "regular" | "gmail_push") ?? "regular"
  );
  const [interval, setInterval] = useState(trigger?.interval_minutes ?? 60);
  const [customInterval, setCustomInterval] = useState("");
  const [prompt, setPrompt] = useState(trigger?.prompt ?? "");
  const [description, setDescription] = useState(trigger?.description ?? "");
  const [filterFrom, setFilterFrom] = useState(trigger?.filter_from ?? "");
  const [filterSubject, setFilterSubject] = useState(trigger?.filter_subject ?? "");
  const [filterBody, setFilterBody] = useState(trigger?.filter_body ?? "");
  const [filterHeader, setFilterHeader] = useState(trigger?.filter_header ?? "");
  const [maxAgeMinutes, setMaxAgeMinutes] = useState(trigger?.max_age_minutes ?? 0);
  const [filterAfterDate, setFilterAfterDate] = useState(trigger?.filter_after_date ?? "");
  const [confirmDelete, setConfirmDelete] = useState(false);

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
        data.filter_after_date = filterAfterDate.trim();
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
          filter_after_date: filterAfterDate.trim(),
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

  const formatTime = (iso: string | null) => {
    if (!iso) return "-";
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-gray-900 rounded-2xl border border-gray-700 w-full max-w-lg flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
          <div className="flex items-center gap-2">
            {trigger?.type === "gmail_push" ? (
              <svg
                className="w-5 h-5 text-red-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
                />
              </svg>
            ) : (
              <svg
                className="w-5 h-5 text-amber-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            )}
            <h2 className="text-lg font-semibold text-white">
              {trigger
                ? trigger.type === "gmail_push"
                  ? "Gmail Push Trigger"
                  : "Trigger Settings"
                : "Create Trigger"}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-gray-400 hover:text-white transition-colors"
          >
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        <div className="p-6 space-y-5 overflow-y-auto max-h-[70vh]">
          {/* Status display for existing trigger */}
          {trigger && !editing && (
            <>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-400">Status</span>
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full ${
                        trigger.active
                          ? "bg-green-900/40 text-green-400"
                          : "bg-gray-800 text-gray-500"
                      }`}
                    >
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
                  <span className="text-sm text-white">
                    {trigger.type === "gmail_push" ? (
                      <span className="flex items-center gap-1.5">
                        <svg className="w-4 h-4 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                        </svg>
                        Gmail Push
                      </span>
                    ) : (
                      <span className="flex items-center gap-1.5">
                        <svg className="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        Scheduled
                      </span>
                    )}
                  </span>
                </div>

                {trigger.type === "regular" && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-400">Interval</span>
                    <span className="text-sm text-white">
                      Every {trigger.interval_minutes} min
                    </span>
                  </div>
                )}

                {trigger.type === "gmail_push" && trigger.filter_from && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-400">Filter from</span>
                    <span className="text-sm text-white font-mono text-xs">
                      {trigger.filter_from}
                    </span>
                  </div>
                )}

                {trigger.type === "gmail_push" && trigger.filter_subject && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-400">Filter subject</span>
                    <span className="text-sm text-white">
                      {trigger.filter_subject}
                    </span>
                  </div>
                )}

                {trigger.type === "gmail_push" && trigger.filter_body && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-400">Filter body</span>
                    <span className="text-sm text-white">
                      {trigger.filter_body}
                    </span>
                  </div>
                )}

                {trigger.type === "gmail_push" && trigger.filter_header && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-400">Filter header</span>
                    <span className="text-sm text-white">
                      {trigger.filter_header}
                    </span>
                  </div>
                )}

                {trigger.type === "gmail_push" && (trigger.max_age_minutes ?? 0) > 0 && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-400">Max age</span>
                    <span className="text-sm text-white">
                      {trigger.max_age_minutes} min
                    </span>
                  </div>
                )}

                {trigger.type === "gmail_push" && trigger.filter_after_date && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-400">Only after</span>
                    <span className="text-sm text-white">
                      {trigger.filter_after_date}
                    </span>
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
                    <span className="text-sm text-white">
                      {trigger.description}
                    </span>
                  </div>
                )}

                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-400">Last run</span>
                  <span className="text-sm text-white">
                    {formatTime(trigger.last_run)}
                  </span>
                </div>

                {trigger.type === "regular" && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-400">Next run</span>
                    <span className="text-sm text-white">
                      {formatTime(trigger.next_run)}
                    </span>
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
                      ) : (
                        "Paused"
                      )}
                    </span>
                  </div>
                )}

                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-400">Total runs</span>
                  <span className="text-sm text-white">
                    {trigger.run_count}
                  </span>
                </div>
              </div>

              {/* Action buttons */}
              <div className="flex gap-2 pt-2">
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
                      onClick={() => {
                        onDelete();
                        onClose();
                      }}
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
            </>
          )}

          {/* Edit / Create form */}
          {editing && (
            <div className="space-y-4">
              {/* Trigger type selector — only shown when creating */}
              {!trigger && (
                <div>
                  <label className="block text-xs text-gray-400 mb-2">
                    Trigger Type
                  </label>
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
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
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
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                      </svg>
                      Gmail Push
                    </button>
                  </div>
                </div>
              )}

              {/* Description */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">
                  Description
                </label>
                <input
                  type="text"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder={
                    triggerType === "gmail_push"
                      ? "e.g. Auto-respond to support emails"
                      : "e.g. Daily email summary"
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
                />
              </div>

              {/* Interval — only for regular triggers */}
              {triggerType === "regular" && (
                <div>
                  <label className="block text-xs text-gray-400 mb-2">
                    Interval
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {INTERVAL_PRESETS.map((p) => (
                      <button
                        key={p.value}
                        onClick={() => {
                          setInterval(p.value);
                          setCustomInterval("");
                        }}
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
                    <div className="flex items-center gap-2 mb-2">
                      <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <span className="text-xs text-blue-400">
                        Fires when new emails arrive. Requires email account setup in Tools.
                      </span>
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">
                      Filter by sender (optional)
                    </label>
                    <input
                      type="text"
                      value={filterFrom}
                      onChange={(e) => setFilterFrom(e.target.value)}
                      placeholder="e.g. notifications@github.com"
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">
                      Filter by subject keyword (optional)
                    </label>
                    <input
                      type="text"
                      value={filterSubject}
                      onChange={(e) => setFilterSubject(e.target.value)}
                      placeholder="e.g. urgent, invoice, alert"
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">
                      Filter by body keyword (optional)
                    </label>
                    <input
                      type="text"
                      value={filterBody}
                      onChange={(e) => setFilterBody(e.target.value)}
                      placeholder="e.g. payment, confirmation code"
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">
                      Filter by header keyword (optional)
                    </label>
                    <input
                      type="text"
                      value={filterHeader}
                      onChange={(e) => setFilterHeader(e.target.value)}
                      placeholder="e.g. mailing-list name, X-header value"
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">
                      Max email age in minutes (0 = no limit)
                    </label>
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
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">
                      Only process emails after date (optional)
                    </label>
                    <input
                      type="date"
                      value={filterAfterDate}
                      onChange={(e) => setFilterAfterDate(e.target.value)}
                      className="w-52 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
                    />
                    <p className="text-[10px] text-gray-500 mt-1">Emails before this date will be skipped. Format: YYYY-MM-DD.</p>
                  </div>
                </div>
              )}

              {/* Prompt */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">
                  Trigger prompt *
                </label>
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder={
                    triggerType === "gmail_push"
                      ? "What should the agent do with each new email? e.g. Summarize the email and decide if it needs a reply"
                      : "What should the agent do each time this trigger fires?"
                  }
                  rows={3}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500 resize-none"
                  required
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
        </div>
      </div>
    </div>
  );
}
