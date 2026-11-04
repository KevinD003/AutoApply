"use client";

import EmailUpdateRow from "@/components/EmailUpdateRow";
import { Button, Card, Empty, ErrorBox, Notice } from "@/components/ui";
import { api } from "@/lib/api";
import { useInbox } from "@/lib/useInbox";

// Email updates on the tracker (spec §9): recruitment emails matched to your applications,
// proposed for you to confirm, correct, undo, or re-link to the right application. Timeline and
// settings live elsewhere (the application's own timeline; Account → Email); this is the one
// place to act on what the mailbox found. onApplied refreshes the tracker when an outcome changes.
const ACTIONABLE = ["proposed", "review", "unlinked", "auto_applied", "accepted"];

export default function EmailUpdates({ onApplied }) {
  const { v, error, notice, busy, apps, loadApps, act } = useInbox(onApplied);
  if (!v) return null;
  const updates = v.events.filter((e) => ACTIONABLE.includes(e.state));
  // Nothing to act on and tracking isn't on for this account: keep the tracker uncluttered.
  if (!v.tracking_enabled && updates.length === 0) return null;

  return (
    <Card title="Email updates">
      <p className="text-sm text-ink-muted">
        What recruitment emails in your connected mailbox say about your applications. NoEfforts
        proposes an update; you confirm, correct, undo, or point it at the right application. It
        reads your own mail only, stores no message text, and sends nothing. Manage access in
        Account.
      </p>
      <ErrorBox error={error} />
      {notice && <Notice>{notice}</Notice>}
      {v.tracking_enabled && (
        <div className="mt-3">
          <Button variant="secondary" disabled={busy} onClick={() => act(api("/inbox/check", { method: "POST" }), { notice: "Read." })}>
            Check email now
          </Button>
        </div>
      )}
      {updates.length === 0 ? (
        <Empty>No email updates right now. When a recruitment email matches an application, it appears here for you to confirm.</Empty>
      ) : (
        <ul className="mt-2 divide-y divide-hairline text-sm" data-testid="email-updates">
          {updates.map((e) => (
            <EmailUpdateRow key={e.id} e={e} act={act} busy={busy} apps={apps} loadApps={loadApps} />
          ))}
        </ul>
      )}
    </Card>
  );
}
