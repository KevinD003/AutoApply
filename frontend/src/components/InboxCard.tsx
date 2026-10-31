"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Badge, Button, Card, Empty, ErrorBox, Notice } from "./ui";
import { api } from "@/lib/api";

// D101: your own Gmail, read-only, when the server's owner connected it. Verification codes are
// entered for you only while an application waits for one and exactly one code arrives from its
// application system; application emails are proposed as outcomes you confirm or dismiss.
interface InboxEvent {
  id: string;
  received_at: string;
  sender_domain: string;
  kind:
    | "code"
    | "rejected"
    | "interview"
    | "assessment"
    | "received"
    | "unclear"
    | "other";
  state:
    | "proposed"
    | "accepted"
    | "dismissed"
    | "unlinked"
    | "code_used"
    | "code_unclear"
    | "noted";
  application_id: string | null;
}
interface InboxView {
  available: boolean;
  why_not: string | null;
  codes_enabled: boolean;
  tracking_enabled: boolean;
  last_checked_at: string | null;
  last_error: string | null;
  events: InboxEvent[];
}

const KIND: Record<InboxEvent["kind"], string> = {
  code: "verification code",
  rejected: "reads as a rejection",
  interview: "reads as an interview invitation",
  assessment: "reads as an assessment",
  received: "says your application was received",
  unclear: "unclear: it reads as more than one thing",
  other: "other",
};
const STATE: Record<InboxEvent["state"], string> = {
  proposed: "waiting for you",
  accepted: "recorded by you",
  dismissed: "dismissed",
  unlinked: "names none of your applications (or several)",
  code_used: "code entered for you",
  code_unclear: "not entered: more than one code, or none",
  noted: "noted",
};

export default function InboxCard() {
  const [v, setV] = useState<InboxView | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    api<InboxView>("/inbox").then(setV).catch(setError);
  }, []);
  useEffect(load, [load]);

  async function run(p: Promise<InboxView>, done?: string) {
    setBusy(true);
    setError(null);
    try {
      setV(await p);
      if (done) setNotice(done);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  if (!v) return <ErrorBox error={error} />;
  const set = (codes: boolean, tracking: boolean) =>
    run(
      api<InboxView>("/inbox", {
        method: "PUT",
        json: { codes_enabled: codes, tracking_enabled: tracking },
      }),
    );
  return (
    <Card title="Email (your Gmail, read-only)">
      <p className="text-sm text-slate-600">
        NoEfforts can read your own Gmail, read-only: it never sends, deletes,
        labels or marks anything. It keeps only what each email said (its kind,
        the sender&rsquo;s domain, the day), never the text. Turn on each use
        separately.
      </p>
      <ErrorBox error={error} />
      {notice && <Notice>{notice}</Notice>}
      {!v.available ? (
        <p
          className="mt-2 text-sm text-slate-600"
          data-testid="inbox-unavailable"
        >
          {v.why_not} Connecting it is a step on the server owner&rsquo;s
          machine (docs/inbox.md).
        </p>
      ) : (
        <div className="mt-2 space-y-2 text-sm">
          <label className="flex items-start gap-2">
            <input
              type="checkbox"
              checked={v.codes_enabled}
              disabled={busy}
              onChange={(e) => set(e.target.checked, v.tracking_enabled)}
            />
            <span>
              Enter verification codes for me: only while one of my applications
              waits for a code, and only when exactly one code arrives from its
              application system. Otherwise I type it.
            </span>
          </label>
          <label className="flex items-start gap-2">
            <input
              type="checkbox"
              checked={v.tracking_enabled}
              disabled={busy}
              onChange={(e) => set(v.codes_enabled, e.target.checked)}
            />
            <span>
              Read emails about my applications and propose what they say
              (rejected, interview, assessment) for me to confirm.
            </span>
          </label>
          <p className="text-xs text-slate-500">
            Last read:{" "}
            {v.last_checked_at
              ? new Date(v.last_checked_at).toLocaleString()
              : "never"}
            {v.last_error && (
              <span className="text-red-700"> · {v.last_error}</span>
            )}
          </p>
          <Button
            variant="secondary"
            disabled={busy || !v.tracking_enabled}
            onClick={() =>
              run(api<InboxView>("/inbox/check", { method: "POST" }), "Read.")
            }
          >
            Read now
          </Button>
        </div>
      )}
      <h3 className="mt-4 text-sm font-semibold">Recent emails</h3>
      {v.events.length === 0 ? (
        <Empty>None read yet.</Empty>
      ) : (
        <ul
          className="mt-1 divide-y divide-slate-100 text-sm"
          data-testid="inbox-events"
        >
          {v.events.map((e) => (
            <li
              key={e.id}
              className="flex flex-wrap items-center justify-between gap-2 py-2"
            >
              <span>
                {new Date(e.received_at).toLocaleDateString()} · from{" "}
                {e.sender_domain} · {KIND[e.kind]}{" "}
                <Badge tone={e.state === "proposed" ? "amber" : "slate"}>
                  {STATE[e.state]}
                </Badge>{" "}
                {e.application_id && (
                  <Link
                    className="text-indigo-700 underline"
                    href={`/applications/${e.application_id}`}
                  >
                    application
                  </Link>
                )}
              </span>
              {(e.state === "proposed" || e.state === "unlinked") && (
                <span className="flex gap-2">
                  {e.state === "proposed" && (
                    <Button
                      className="!min-h-8 !px-2 !py-1"
                      disabled={busy}
                      onClick={() =>
                        run(
                          api<InboxView>(`/inbox/events/${e.id}/accept`, {
                            method: "POST",
                          }),
                          "Recorded on the application.",
                        )
                      }
                    >
                      Confirm
                    </Button>
                  )}
                  <Button
                    variant="secondary"
                    className="!min-h-8 !px-2 !py-1"
                    disabled={busy}
                    onClick={() =>
                      run(
                        api<InboxView>(`/inbox/events/${e.id}/dismiss`, {
                          method: "POST",
                        }),
                      )
                    }
                  >
                    Dismiss
                  </Button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
