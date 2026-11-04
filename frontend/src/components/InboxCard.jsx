"use client";

import EmailUpdateRow from "@/components/EmailUpdateRow";
import { Button, Card, Empty, ErrorBox, Notice } from "@/components/ui";
import { api } from "@/lib/api";
import { useInbox } from "@/lib/useInbox";

// D101 / email status tracking: your own Gmail, read-only, when the server's owner connected it.
// Verification codes are entered for you only while an application waits for one and exactly one
// code arrives from its application system; application emails are matched to an application and
// proposed as outcomes you confirm, correct, or undo. Settings and privacy live here; the day-to-
// day Confirm/Correct/Undo surface is also on the tracker (EmailUpdates).
const SCOPE_FALLBACK =
  "NoEfforts can read your own Gmail, read-only: it never sends, replies, deletes, marks read or " +
  "changes labels, and stores no message text — only a keyed reference, the sender's domain, the " +
  "recognised event and the application.";

export default function InboxCard() {
  const { v, error, notice, busy, apps, loadApps, act } = useInbox();
  if (!v) return <ErrorBox error={error} />;

  const set = (codes, tracking, auto) =>
    act(api("/inbox", { method: "PUT", json: { codes_enabled: codes, tracking_enabled: tracking, auto_apply: auto } }));

  return (
    <Card title="Email (your Gmail, read-only)">
      <p className="text-sm text-ink-muted">{v.scope_note ?? SCOPE_FALLBACK}</p>
      <ErrorBox error={error} />
      {notice && <Notice>{notice}</Notice>}
      {!v.available ? (
        <p className="mt-2 text-sm text-ink-muted" data-testid="inbox-unavailable">
          {v.why_not} Connecting it is a step on the server owner&rsquo;s machine (docs/inbox.md).
        </p>
      ) : (
        <div className="mt-2 space-y-2 text-sm">
          <label className="flex items-start gap-2">
            <input type="checkbox" checked={v.codes_enabled} disabled={busy} onChange={(e) => set(e.target.checked, v.tracking_enabled, v.auto_apply)} />
            <span>
              Enter verification codes for me: only while one of my applications waits for a code, and only when exactly one code arrives from its
              application system. Otherwise I type it.
            </span>
          </label>
          <label className="flex items-start gap-2">
            <input type="checkbox" checked={v.tracking_enabled} disabled={busy} onChange={(e) => set(v.codes_enabled, e.target.checked, v.auto_apply)} />
            <span>Read emails about my applications and propose what they say (rejected, interview, assessment, offer) for me to confirm.</span>
          </label>
          <label className="flex items-start gap-2">
            <input type="checkbox" checked={Boolean(v.auto_apply)} disabled={busy || !v.tracking_enabled} onChange={(e) => set(v.codes_enabled, v.tracking_enabled, e.target.checked)} />
            <span>
              When an update is clear and clearly about one application, record it automatically. You can still review or undo it on the tracker;
              anything less clear I confirm myself.
            </span>
          </label>
          <p className="text-xs text-ink-faint">
            Last read: {v.last_checked_at ? new Date(v.last_checked_at).toLocaleString() : "never"}
            {v.last_error && <span className="text-danger-ink"> · {v.last_error}</span>}
          </p>
          <Button variant="secondary" disabled={busy || !v.tracking_enabled} onClick={() => act(api("/inbox/check", { method: "POST" }), { notice: "Read." })}>
            Read now
          </Button>
        </div>
      )}
      <h3 className="mt-4 text-sm font-semibold">Recent emails</h3>
      {v.events.length === 0 ? (
        <Empty>None read yet.</Empty>
      ) : (
        <ul className="mt-1 divide-y divide-hairline text-sm" data-testid="inbox-events">
          {v.events.map((e) => (
            <EmailUpdateRow key={e.id} e={e} act={act} busy={busy} apps={apps} loadApps={loadApps} />
          ))}
        </ul>
      )}
    </Card>
  );
}
