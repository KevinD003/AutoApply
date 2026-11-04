"use client";

import { useState } from "react";

import EmailUpdateRow from "@/components/EmailUpdateRow";
import { Button, Card, Empty, ErrorBox, Notice, inputCls } from "@/components/ui";
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

// D103: reading application emails needs the owner's own recorded authorization — turning the
// toggle on is not one. The owner grants that here (their own authenticated, auditable consent),
// which covers reading application emails only — never verification codes, sending or submission —
// and can be withdrawn here at any time. A server-wide authorization recorded in reviewed source
// also satisfies it (shown, but not revocable here). This is separate from connecting Gmail and
// from the Google permission itself; revoking in your Google account is the stronger step.
function AuthorizeTracking({ v, busy, act }) {
  const [text, setText] = useState("");
  const [endsOn, setEndsOn] = useState("");
  const authz = v.authorization;

  if (v.tracking_authorized) {
    if (authz?.source === "in_app") {
      const granted = authz.granted_at ? new Date(authz.granted_at).toLocaleDateString() : null;
      return (
        <div className="rounded-[var(--r-md)] border border-hairline bg-surface-2 p-2 text-xs" data-testid="tracking-authorized">
          <p className="text-ink-muted">
            You authorized reading your application emails{granted ? ` on ${granted}` : ""}
            {authz.ends_on ? `, until ${new Date(authz.ends_on).toLocaleDateString()}` : ""}. This
            covers reading application emails only — never verification codes, sending or submitting.
          </p>
          {v.is_inbox_owner && (
            <Button
              variant="danger"
              className="mt-2"
              disabled={busy}
              onClick={() =>
                act(api("/inbox/authorize/revoke", { method: "POST" }), {
                  notice: "Authorization withdrawn; reading application emails is gated again.",
                })
              }
            >
              Revoke authorization
            </Button>
          )}
        </div>
      );
    }
    // Authorized server-wide in reviewed source code (D103) — not revocable from the app.
    return (
      <p className="text-xs text-ink-muted" data-testid="tracking-authorized">
        Reading application emails is authorized in this server&rsquo;s reviewed source
        configuration. Managing that is a change to the server, not a setting here.
      </p>
    );
  }

  if (!v.is_inbox_owner)
    return (
      <p className="text-xs text-ink-muted" data-testid="tracking-needs-auth">
        Reading application emails needs the server owner&rsquo;s own recorded authorization.
      </p>
    );

  // Owner, not yet authorized: record their own authenticated, auditable consent (no code change).
  return (
    <details className="rounded-[var(--r-md)] border border-hairline bg-surface-2 p-2" data-testid="authorize-tracking">
      <summary className="cursor-pointer text-xs font-medium text-ink">
        Authorize reading my application emails
      </summary>
      <div className="mt-2 space-y-2 text-xs text-ink-muted">
        <p>
          This records your own consent to read your application emails. It covers reading those
          emails only — never verification codes, sending, replying, or submitting applications —
          is scoped to your own mailbox, and you can withdraw it here at any time.
        </p>
        <label className="block">
          <span className="mb-1 block font-medium text-ink">Your consent, in your own words</span>
          <textarea
            className={inputCls}
            rows={2}
            value={text}
            disabled={busy}
            placeholder="e.g. I authorize NoEfforts to read my own application emails to track my applications."
            onChange={(e) => setText(e.target.value)}
            data-testid="attestation"
          />
        </label>
        <label className="block">
          <span className="mb-1 block font-medium text-ink">Ends on (optional)</span>
          <input
            type="date"
            className={inputCls}
            value={endsOn}
            disabled={busy}
            onChange={(e) => setEndsOn(e.target.value)}
            data-testid="ends-on"
          />
        </label>
        <Button
          disabled={busy || !text.trim()}
          onClick={() =>
            act(
              api("/inbox/authorize", {
                method: "POST",
                json: { attestation: text, ends_on: endsOn || null },
              }),
              { notice: "Authorization recorded. You can now turn on application-email tracking." },
            ).then((ok) => ok && (setText(""), setEndsOn("")))
          }
        >
          Authorize tracking
        </Button>
      </div>
    </details>
  );
}

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
          <AuthorizeTracking v={v} busy={busy} act={act} />
          <label className="flex items-start gap-2">
            <input
              type="checkbox"
              checked={v.tracking_enabled}
              disabled={busy || !v.tracking_authorized}
              onChange={(e) => set(v.codes_enabled, e.target.checked, v.auto_apply)}
            />
            <span>
              Read emails about my applications and propose what they say (rejected, interview, assessment, offer) for me to confirm.
              {v.first_read_days != null && (
                <span className="text-ink-faint">
                  {" "}
                  The first read reaches back {v.first_read_days} days and no further; after that only new mail is read.
                </span>
              )}
            </span>
          </label>
          <p className="text-xs text-ink-faint">
            Turning this off stops reading application emails. Verification-code reading is a
            separate setting above and is not affected by it.
          </p>
          <label className="flex items-start gap-2">
            <input type="checkbox" checked={Boolean(v.auto_apply)} disabled={busy || !v.tracking_enabled} onChange={(e) => set(v.codes_enabled, v.tracking_enabled, e.target.checked)} />
            <span>
              Automatically update an application&rsquo;s status from email (this records a status only &mdash; it never submits an application):
              when an update is clear and clearly about one application, record it for me. You can still review or undo it on the tracker;
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
