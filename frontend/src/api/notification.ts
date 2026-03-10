const BASE = "/api/notifications";

export interface NotificationData {
  id: string;
  user_id: string;
  title: string;
  body: string;
  content?: string;
  level: "info" | "success" | "warning" | "error";
  agent_id?: string;
  agent_name?: string;
  read: boolean;
  created_at: string;
  images?: Array<{ data: string; media_type: string }>;
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

// ── Notification channels ──────────────────────────────────

export interface NotificationChannel {
  id: string;
  type: string;
  address: string;
  label: string;
  enabled: boolean;
}

export async function fetchNotificationChannels(): Promise<NotificationChannel[]> {
  const res = await fetch("/api/user/notification-channels");
  if (!res.ok) return [];
  return res.json();
}

export async function addNotificationChannel(
  channel: { type: string; address: string; label?: string }
): Promise<NotificationChannel> {
  const res = await fetch("/api/user/notification-channels", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(channel),
  });
  if (!res.ok) throw new Error("Failed to add channel");
  return res.json();
}

export async function updateNotificationChannel(
  id: string,
  updates: { label?: string; address?: string; enabled?: boolean }
): Promise<NotificationChannel> {
  const res = await fetch(`/api/user/notification-channels/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error("Failed to update channel");
  return res.json();
}

export async function deleteNotificationChannel(id: string): Promise<void> {
  await fetch(`/api/user/notification-channels/${id}`, { method: "DELETE" });
}

export async function testNotificationChannel(
  id: string
): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`/api/user/notification-channels/${id}/test`, {
    method: "POST",
  });
  return res.json();
}
