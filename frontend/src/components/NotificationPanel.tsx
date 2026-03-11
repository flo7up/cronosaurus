import { useState, useEffect, useRef } from "react";
import type { NotificationData } from "../api/notification";
import {
  fetchNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  deleteNotification,
  clearAllNotifications,
} from "../api/notification";

/* ── Level styling ─────────────────────────────────────────── */
const LEVEL_CONFIG: Record<
  string,
  { icon: string; bg: string; border: string; text: string }
> = {
  info: {
    icon: "ℹ️",
    bg: "bg-blue-900/30",
    border: "border-blue-700/40",
    text: "text-blue-300",
  },
  success: {
    icon: "✅",
    bg: "bg-emerald-900/30",
    border: "border-emerald-700/40",
    text: "text-emerald-300",
  },
  warning: {
    icon: "⚠️",
    bg: "bg-amber-900/30",
    border: "border-amber-700/40",
    text: "text-teal-300",
  },
  error: {
    icon: "❌",
    bg: "bg-red-900/30",
    border: "border-red-700/40",
    text: "text-red-300",
  },
};

/* ── Bell icon with badge ──────────────────────────────────── */
export function NotificationBell({
  onClick,
  unreadCount,
}: {
  onClick: () => void;
  unreadCount: number;
}) {
  return (
    <button
      onClick={onClick}
      className="relative p-2 rounded-lg text-gray-400 hover:bg-gray-800 hover:text-white transition-colors"
      aria-label="Notifications"
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
          strokeWidth={1.5}
          d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0"
        />
      </svg>
      {unreadCount > 0 && (
        <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] flex items-center justify-center px-1 text-[10px] font-bold text-white bg-red-500 rounded-full animate-pulse">
          {unreadCount > 99 ? "99+" : unreadCount}
        </span>
      )}
    </button>
  );
}

/* ── Notification panel (slide-over) ───────────────────────── */
export default function NotificationPanel({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) {
  const [notifications, setNotifications] = useState<NotificationData[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"all" | "unread">("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // Load notifications when panel opens
  useEffect(() => {
    if (!isOpen) return;
    loadNotifications();
  }, [isOpen, tab]);

  // Close on click outside
  useEffect(() => {
    if (!isOpen) return;
    function handleClick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [isOpen, onClose]);

  async function loadNotifications() {
    setLoading(true);
    try {
      const data = await fetchNotifications(50, tab === "unread");
      setNotifications(data);
    } catch {
      // silent
    }
    setLoading(false);
  }

  async function handleMarkRead(id: string) {
    await markNotificationRead(id);
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n))
    );
  }

  async function handleMarkAllRead() {
    await markAllNotificationsRead();
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  }

  async function handleDelete(id: string) {
    await deleteNotification(id);
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  }

  async function handleClearAll() {
    await clearAllNotifications();
    setNotifications([]);
  }

  function timeAgo(iso: string): string {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  }

  if (!isOpen) return null;

  const unreadCount = notifications.filter((n) => !n.read).length;

  return (
    <div className="fixed inset-0 z-50">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" />

      {/* Panel */}
      <div
        ref={panelRef}
        className="absolute right-0 top-0 h-full w-full max-w-md app-sidebar border-l border-[#3dd8c5]/18 shadow-2xl flex flex-col animate-slide-in-right"
      >
        <div className="terminal-titlebar px-5">cronosaurus :: notifications</div>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#3dd8c5]/10">
          <div className="flex items-center gap-3">
            <svg className="w-5 h-5 text-[#78adb8]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
            </svg>
            <h2 className="text-lg font-semibold text-[#b0f0e8] uppercase tracking-[0.1em]">Notifications</h2>
            {unreadCount > 0 && (
              <span className="terminal-chip text-xs px-2 py-0.5 text-[#97ff8a]">
                {unreadCount} unread
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            {/* Close */}
            <button
              onClick={onClose}
              className="terminal-control p-1.5 text-[#78adb8] hover:bg-[#0f161b] hover:text-[#b0f0e8] transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Tabs + actions */}
        <div className="flex items-center justify-between px-5 py-2.5 border-b border-[#3dd8c5]/10">
          <div className="flex gap-1">
            {(["all", "unread"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`terminal-control px-3 py-1 text-xs font-medium transition-colors uppercase tracking-[0.08em] ${
                  tab === t
                    ? "bg-[#0e1922] text-[#b0f0e8] border-[#3dd8c5]/30"
                    : "text-[#78adb8] hover:text-[#c9f6ef]"
                }`}
              >
                {t === "all" ? "All" : "Unread"}
              </button>
            ))}
          </div>
          <div className="flex gap-1">
            {unreadCount > 0 && (
              <button
                onClick={handleMarkAllRead}
                className="terminal-control text-xs text-[#78adb8] hover:text-[#b0f0e8] px-2 py-1 transition-colors"
              >
                Mark all read
              </button>
            )}
            {notifications.length > 0 && (
              <button
                onClick={handleClearAll}
                className="terminal-control text-xs text-[#486d78] hover:text-red-400 px-2 py-1 transition-colors"
              >
                Clear all
              </button>
            )}
          </div>
        </div>

        {/* Notification list */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-5 h-5 border-2 border-[#486d78] border-t-[#3dd8c5] rounded-full animate-spin" />
            </div>
          ) : notifications.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-[#486d78]">
              <svg className="w-12 h-12 mb-3 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
              </svg>
              <p className="text-sm">
                {tab === "unread" ? "No unread notifications" : "No notifications yet"}
              </p>
              <p className="text-xs mt-1 text-[#305a5a]">
                Agents will send alerts here
              </p>
            </div>
          ) : (
            <div className="divide-y divide-[#3dd8c5]/10">
              {notifications.map((n) => {
                const cfg = LEVEL_CONFIG[n.level] || LEVEL_CONFIG.info;
                const isExpanded = expandedId === n.id;
                const hasContent = !!(n.content && n.content !== n.body);
                return (
                  <div
                    key={n.id}
                    className={`group px-5 py-3.5 transition-colors hover:bg-[#0f161b] cursor-pointer ${
                      !n.read ? "bg-[#0d1318]/60" : ""
                    }`}
                    onClick={() => {
                      const next = isExpanded ? null : n.id;
                      setExpandedId(next);
                      if (next && !n.read) handleMarkRead(n.id);
                    }}
                  >
                    <div className="flex items-start gap-3">
                      {/* Unread dot */}
                      <div className="mt-1.5 shrink-0 w-2">
                        {!n.read && (
                          <div className="w-2 h-2 rounded-full bg-[#97ff8a]" />
                        )}
                      </div>

                      {/* Level icon */}
                      <div
                        className={`shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-sm border ${cfg.bg} ${cfg.border}`}
                      >
                        {cfg.icon}
                      </div>

                      {/* Content */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className={`text-sm font-medium ${!n.read ? "text-[#b0f0e8]" : "text-[#8adcca]"}`}>
                            {n.title}
                          </span>
                          <svg
                            className={`w-3.5 h-3.5 text-[#486d78] transition-transform shrink-0 ${isExpanded ? "rotate-180" : ""}`}
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                          </svg>
                        </div>
                        <p className={`text-xs text-[#78adb8] mt-0.5 ${isExpanded ? "whitespace-pre-wrap" : "line-clamp-2"}`}>
                          {n.body}
                        </p>
                        {/* Expanded content */}
                        {isExpanded && (
                          <>
                            {hasContent && (
                              <div className="mt-2 p-3 rounded-lg bg-[#070c0e]/60 border border-[#3dd8c5]/10">
                                <p className="text-xs text-[#78adb8] whitespace-pre-wrap leading-relaxed">
                                  {n.content}
                                </p>
                              </div>
                            )}
                            {/* Notification images */}
                            {n.images && n.images.length > 0 && (
                              <div className="flex gap-2 flex-wrap mt-2">
                                {n.images.map((img, i) => (
                                  <img
                                    key={i}
                                    src={`data:${img.media_type};base64,${img.data}`}
                                    alt={`Notification image ${i + 1}`}
                                    className="max-h-40 max-w-full rounded-lg border border-[#3dd8c5]/15 object-contain"
                                  />
                                ))}
                              </div>
                            )}
                          </>
                        )}
                        <div className="flex items-center gap-2 mt-1.5">
                          {n.agent_name && (
                            <span className="terminal-chip text-[10px] px-1.5 py-0.5">
                              {n.agent_name}
                            </span>
                          )}
                          <span className="text-[10px] text-[#486d78]">
                            {timeAgo(n.created_at)}
                          </span>
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                        {!n.read && (
                          <button
                            onClick={(e) => { e.stopPropagation(); handleMarkRead(n.id); }}
                            className="p-1 rounded text-gray-500 hover:text-white hover:bg-gray-700 transition-colors"
                            title="Mark as read"
                          >
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                            </svg>
                          </button>
                        )}
                        <button
                          onClick={(e) => { e.stopPropagation(); handleDelete(n.id); }}
                          className="p-1 rounded text-gray-500 hover:text-red-400 hover:bg-gray-700 transition-colors"
                          title="Delete"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Animation */}
      <style>{`
        @keyframes slide-in-right {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
        .animate-slide-in-right {
          animation: slide-in-right 0.2s ease-out;
        }
      `}</style>
    </div>
  );
}
