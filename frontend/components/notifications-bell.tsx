"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { useState } from "react";

import type { NotificationResponse } from "@eminidatabase/sdk";

async function fetchNotifications(): Promise<NotificationResponse[]> {
  const res = await fetch("/api/notifications");
  if (!res.ok) throw new Error("Failed to load notifications");
  return res.json();
}

export function NotificationsBell() {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();
  const { data: notifications = [] } = useQuery({
    queryKey: ["notifications"],
    queryFn: fetchNotifications,
    refetchInterval: 30_000,
  });

  const unreadCount = notifications.filter((n) => !n.read_at).length;

  async function markRead(id: string) {
    await fetch(`/api/notifications/${id}/read`, { method: "POST" });
    queryClient.invalidateQueries({ queryKey: ["notifications"] });
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="relative rounded-md p-2 text-slate-500 hover:bg-slate-100"
        aria-label="Notifications"
      >
        <Bell className="h-5 w-5" />
        {unreadCount > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-medium text-white">
            {unreadCount}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-10 mt-2 w-80 rounded-md border border-slate-200 bg-white shadow-lg">
          <div className="max-h-96 overflow-y-auto">
            {notifications.length === 0 ? (
              <p className="px-4 py-6 text-center text-sm text-slate-400">No notifications yet.</p>
            ) : (
              notifications.map((n) => (
                <button
                  key={n.id}
                  onClick={() => markRead(n.id)}
                  className={`block w-full border-b border-slate-100 px-4 py-3 text-left text-sm last:border-0 hover:bg-slate-50 ${
                    n.read_at ? "text-slate-400" : "text-slate-900"
                  }`}
                >
                  <p className="font-medium">{n.title}</p>
                  <p className="mt-0.5 text-slate-500">{n.body}</p>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
