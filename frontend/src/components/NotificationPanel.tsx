import { useState, useEffect, useRef } from "react";
import type { NotificationData, NotificationPreferences } from "../api/notification";
import {
  fetchNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  deleteNotification,
  clearAllNotifications,
  fetchNotificationPreferences,
  updateNotificationPreferences,
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
    text: "text-amber-300",
  },
  error: {
    icon: "❌",
    bg: "bg-red-900/30",
    border: "border-red-700/40",
    text: "text-red-300",
  },
};

const DELIVERY_OPTIONS = [
  {
    value: "all" as const,
    label: "In-app + Email",
    desc: "Show in bell and send email",
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
      </svg>
    ),
  },
  {
    value: "in_app" as const,
    label: "In-app only",
    desc: "Show in bell, no email",
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
      </svg>
    ),
  },
  {
    value: "none" as const,
    label: "Muted",
    desc: "No notifications at all",
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.143 17.082a24.248 24.248 0 005.714 0m-5.714 0a3 3 0 115.714 0M3.124 13.772A8.967 8.967 0 005.75 9.75V9a6 6 0 0112 0v.75c0 2.123.8 4.057 2.118 5.52M3.124 13.772a23.91 23.91 0 007.019 2.26M3.124 13.772L2 15m18.876-1.228L22 15M3 3l18 18" />
      </svg>
    ),
  },
];

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
  const [showSettings, setShowSettings] = useState(false);
  const [prefs, setPrefs] = useState<NotificationPreferences>({ delivery: "all" });
  const [savingPrefs, setSavingPrefs] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  // Load notifications when panel opens
  useEffect(() => {
    if (!isOpen) return;
    loadNotifications();
    loadPrefs();
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

  async function loadPrefs() {
    try {
      const p = await fetchNotificationPreferences();
      setPrefs(p);
    } catch {
      // silent
    }
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

  async function handleUpdatePrefs(delivery: NotificationPreferences["delivery"]) {
    setSavingPrefs(true);
    try {
      const updated = await updateNotificationPreferences({ delivery });
      setPrefs(updated);
    } catch {
      // silent
    }
    setSavingPrefs(false);
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
        className="absolute right-0 top-0 h-full w-full max-w-md app-sidebar border-l border-[#f2c230]/18 shadow-2xl flex flex-col animate-slide-in-right"
      >
        <div className="terminal-titlebar px-5">cronosaurus :: notifications</div>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#f2c230]/10">
          <div className="flex items-center gap-3">
            <svg className="w-5 h-5 text-[#b8ad78]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
            </svg>
            <h2 className="text-lg font-semibold text-[#fff0b0] uppercase tracking-[0.1em]">Notifications</h2>
            {unreadCount > 0 && (
              <span className="terminal-chip text-xs px-2 py-0.5 text-[#97ff8a]">
                {unreadCount} unread
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            {/* Settings toggle */}
            <button
              onClick={() => setShowSettings(!showSettings)}
              className={`terminal-control p-1.5 transition-colors ${
                showSettings
                  ? "bg-[#22190e] text-[#fff0b0]"
                  : "text-[#b8ad78] hover:bg-[#1b160f] hover:text-[#fff0b0]"
              }`}
              title="Notification settings"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </button>
            {/* Close */}
            <button
              onClick={onClose}
              className="terminal-control p-1.5 text-[#b8ad78] hover:bg-[#1b160f] hover:text-[#fff0b0] transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Settings panel (collapsible) */}
        {showSettings && (
          <div className="px-5 py-4 border-b border-[#f2c230]/10 bg-[#0e0c07]/80 space-y-3">
            <p className="terminal-label text-[#97ff8a]">
              delivery method
            </p>
            <div className="space-y-2">
              {DELIVERY_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => handleUpdatePrefs(opt.value)}
                  disabled={savingPrefs}
                  className={`terminal-control w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors ${
                    prefs.delivery === opt.value
                      ? "bg-[#22190e] border-[#f2c230]/30 text-[#fff0b0]"
                      : "text-[#b8ad78] hover:bg-[#1b160f]"
                  }`}
                >
                  <span className={prefs.delivery === opt.value ? "text-[#97ff8a]" : "text-[#786d48]"}>
                    {opt.icon}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium">{opt.label}</div>
                    <div className="text-xs text-[#786d48]">{opt.desc}</div>
                  </div>
                  {prefs.delivery === opt.value && (
                    <svg className="w-4 h-4 text-[#97ff8a] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </button>
              ))}
            </div>
            {prefs.delivery === "all" && (
              <p className="text-xs text-[#786d48]">
                Emails are sent to your configured email account.
              </p>
            )}
          </div>
        )}

        {/* Tabs + actions */}
        <div className="flex items-center justify-between px-5 py-2.5 border-b border-[#f2c230]/10">
          <div className="flex gap-1">
            {(["all", "unread"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`terminal-control px-3 py-1 text-xs font-medium transition-colors uppercase tracking-[0.08em] ${
                  tab === t
                    ? "bg-[#22190e] text-[#fff0b0] border-[#f2c230]/30"
                    : "text-[#b8ad78] hover:text-[#f6efc9]"
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
                className="terminal-control text-xs text-[#b8ad78] hover:text-[#fff0b0] px-2 py-1 transition-colors"
              >
                Mark all read
              </button>
            )}
            {notifications.length > 0 && (
              <button
                onClick={handleClearAll}
                className="terminal-control text-xs text-[#786d48] hover:text-red-400 px-2 py-1 transition-colors"
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
              <div className="w-5 h-5 border-2 border-[#786d48] border-t-[#f2c230] rounded-full animate-spin" />
            </div>
          ) : notifications.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-[#786d48]">
              <svg className="w-12 h-12 mb-3 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
              </svg>
              <p className="text-sm">
                {tab === "unread" ? "No unread notifications" : "No notifications yet"}
              </p>
              <p className="text-xs mt-1 text-[#5a5130]">
                Agents will send alerts here
              </p>
            </div>
          ) : (
            <div className="divide-y divide-[#f2c230]/10">
              {notifications.map((n) => {
                const cfg = LEVEL_CONFIG[n.level] || LEVEL_CONFIG.info;
                return (
                  <div
                    key={n.id}
                    className={`group px-5 py-3.5 transition-colors hover:bg-[#1b160f] ${
                      !n.read ? "bg-[#18130d]/60" : ""
                    }`}
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
                          <span className={`text-sm font-medium ${!n.read ? "text-[#fff0b0]" : "text-[#dcca8a]"}`}>
                            {n.title}
                          </span>
                        </div>
                        <p className="text-xs text-[#b8ad78] mt-0.5 line-clamp-2">
                          {n.body}
                        </p>
                        <div className="flex items-center gap-2 mt-1.5">
                          {n.agent_name && (
                            <span className="terminal-chip text-[10px] px-1.5 py-0.5">
                              {n.agent_name}
                            </span>
                          )}
                          <span className="text-[10px] text-[#786d48]">
                            {timeAgo(n.created_at)}
                          </span>
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                        {!n.read && (
                          <button
                            onClick={() => handleMarkRead(n.id)}
                            className="p-1 rounded text-gray-500 hover:text-white hover:bg-gray-700 transition-colors"
                            title="Mark as read"
                          >
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                            </svg>
                          </button>
                        )}
                        <button
                          onClick={() => handleDelete(n.id)}
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
