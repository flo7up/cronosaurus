const BASE = "/api/notifications";

export interface NotificationData {
  id: string;
  user_id: string;
  title: string;
  body: string;
  level: "info" | "success" | "warning" | "error";
  agent_id?: string;
  agent_name?: string;
  read: boolean;
  created_at: string;
}

export async function fetchNotifications(
  limit = 50,
  unreadOnly = false
): Promise<NotificationData[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (unreadOnly) params.set("unread_only", "true");
  const res = await fetch(`${BASE}?${params}`);
  if (!res.ok) throw new Error("Failed to fetch notifications");
  return res.json();
}

export async function fetchUnreadCount(): Promise<number> {
  const res = await fetch(`${BASE}/unread-count`);
  if (!res.ok) return 0;
  const data = await res.json();
  return data.count ?? 0;
}

export async function markNotificationRead(id: string): Promise<void> {
  await fetch(`${BASE}/${id}/read`, { method: "PUT" });
}

export async function markAllNotificationsRead(): Promise<void> {
  await fetch(`${BASE}/read-all`, { method: "PUT" });
}

export async function deleteNotification(id: string): Promise<void> {
  await fetch(`${BASE}/${id}`, { method: "DELETE" });
}

export async function clearAllNotifications(): Promise<void> {
  await fetch(BASE, { method: "DELETE" });
}

// ── Notification preferences ────────────────────────────────

export interface NotificationPreferences {
  delivery: "all" | "in_app" | "none";
}

export async function fetchNotificationPreferences(): Promise<NotificationPreferences> {
  const res = await fetch("/api/user/notification-preferences");
  if (!res.ok) return { delivery: "all" };
  return res.json();
}

export async function updateNotificationPreferences(
  prefs: NotificationPreferences
): Promise<NotificationPreferences> {
  const res = await fetch("/api/user/notification-preferences", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(prefs),
  });
  if (!res.ok) throw new Error("Failed to update notification preferences");
  return res.json();
}
