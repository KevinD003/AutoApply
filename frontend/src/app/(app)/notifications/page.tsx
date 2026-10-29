"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Badge, Button, Card, Empty, ErrorBox, Loading } from "@/components/ui";
import { api, AppNotification, NOTIFICATIONS_CHANGED } from "@/lib/api";

// Priority C (D83): what happened to your applications, derived from the records themselves
// (backend notifications/service.py). Shown here only: nothing is emailed, texted or pushed.
const KIND = {
  checkpoint: { label: "Verification", tone: "amber" },
  approval_invalidated: { label: "Approval", tone: "amber" },
  rehearsal: { label: "Rehearsal", tone: "indigo" },
  receipt: { label: "Receipt", tone: "green" },
  failure: { label: "Stopped", tone: "red" },
} as const;

interface Feed {
  items: AppNotification[];
  total: number;
  unread: number;
}

export default function NotificationsPage() {
  const router = useRouter();
  const [feed, setFeed] = useState<Feed | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    api<Feed>("/notifications?limit=200")
      .then(setFeed)
      .catch((e) => {
        setError(e);
        setFeed({ items: [], total: 0, unread: 0 });
      });
  }, []);

  useEffect(load, [load]);

  async function mark(path: string, keys?: string[]) {
    setError(null);
    try {
      await api(`/notifications/${path}`, keys ? { json: { keys } } : { method: "POST" });
      window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED));
      load();
    } catch (e) {
      setError(e);
    }
  }

  async function open(n: AppNotification) {
    if (!n.read) {
      await api("/notifications/read", { json: { keys: [n.key] } }).catch(() => undefined);
      window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED));
    }
    router.push(n.link);
  }

  return (
    <>
      <h1 className="text-xl font-semibold">Notifications</h1>
      <Card
        title={feed ? `${feed.unread} unread of ${feed.total}` : "Notifications"}
        actions={
          feed && feed.unread > 0 ? (
            <Button variant="secondary" onClick={() => mark("read-all")}>
              Mark all as read
            </Button>
          ) : undefined
        }
      >
        <p className="mb-3 text-xs text-slate-500">
          Shown here only: NoEfforts sends no email, text message or push notification. Each one says what its record says now.
        </p>
        <ErrorBox error={error} />
        {feed === null ? (
          <Loading />
        ) : feed.items.length === 0 ? (
          <Empty>Nothing yet. Verification requests, approvals that stop applying, rehearsals, receipts and stops will show here.</Empty>
        ) : (
          <ul aria-label="Notifications" className="divide-y divide-slate-100">
            {feed.items.map((n) => (
              <li key={n.key} className={`flex flex-col gap-2 py-3 sm:flex-row sm:items-start sm:justify-between ${n.read ? "" : "bg-indigo-50/40"}`}>
                <div className="min-w-0 sm:px-2">
                  <p className="flex flex-wrap items-center gap-2">
                    <Badge tone={KIND[n.kind].tone}>{KIND[n.kind].label}</Badge>
                    {!n.read && <Badge tone="indigo">Unread</Badge>}
                    {n.needs_action && <Badge tone="amber">Needs you</Badge>}
                    <span className="font-medium text-slate-900">{n.title}</span>
                  </p>
                  <p className="mt-1 text-sm text-slate-700">{n.text}</p>
                  {n.evidence_label && <p className="mt-1 text-xs text-slate-500">{n.evidence_label}</p>}
                  <p className="mt-1 text-xs text-slate-500">
                    {n.job} · {new Date(n.at).toLocaleString()}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2 sm:px-2">
                  <Link
                    href={n.link}
                    onClick={(e) => {
                      e.preventDefault();
                      open(n);
                    }}
                    className="min-h-10 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
                  >
                    Open application
                  </Link>
                  <Button variant="secondary" onClick={() => mark(n.read ? "unread" : "read", [n.key])}>
                    {n.read ? "Mark as unread" : "Mark as read"}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
