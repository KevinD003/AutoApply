"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge, Button, Card, ErrorBox, Field, inputCls, Notice } from "./ui";
import { api } from "@/lib/api";

// D94: email reminders to you, the account owner, and nobody else. Off until you verify an
// address with a code you type here and turn them on. One daily digest at most; it names only
// the category and links to the tracker. The in-app notifications stay the source of truth.
interface Delivery {
  kind: "verification" | "digest";
  status: "pending" | "sending" | "sent" | "uncertain" | "failed" | "cancelled";
  outcome_code: string | null;
  item_count: number;
  created_at: string;
  sent_at: string | null;
}
interface EmailView {
  configured: boolean;
  address: string | null;
  verified: boolean;
  code_pending: boolean;
  enabled: boolean;
  attention: boolean;
  follow_ups: boolean;
  digest_hour_utc: number;
  recent: Delivery[];
}

const STATUS_TEXT: Record<Delivery["status"], string> = {
  pending: "waiting to be sent",
  sending: "being sent",
  sent: "accepted by the mail server",
  uncertain: "may or may not have been accepted (never sent again)",
  failed: "not sent",
  cancelled: "cancelled before sending",
};

export default function EmailReminders() {
  const [v, setV] = useState<EmailView | null>(null);
  const [address, setAddress] = useState("");
  const [code, setCode] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    api<EmailView>("/account/email")
      .then((r) => {
        setV(r);
        setAddress((a) => a || r.address || "");
      })
      .catch(setError);
  }, []);
  useEffect(load, [load]);

  async function call(path: string, method: string, json?: unknown, ok?: string) {
    setError(null);
    setNotice("");
    try {
      setV(await api<EmailView>(path, { method, json }));
      if (ok) setNotice(ok);
    } catch (e) {
      setError(e);
    }
  }

  if (!v) return <ErrorBox error={error} />;
  return (
    <Card title="Email reminders">
      <p className="text-sm text-slate-600">
        A daily email to you when applications need your attention or follow-ups are due. It names only the kind of reminder and
        links to your tracker: no job, employer, answer or document, and opening it changes nothing. NoEfforts never emails
        employers or recruiters for you. Off unless you turn it on.
      </p>
      {!v.configured && (
        <Notice>Email is not set up on this NoEfforts, so nothing can be sent. Reminders stay in the app.</Notice>
      )}
      <ErrorBox error={error} />
      {notice && <p className="mt-2 text-sm text-green-800" role="status">{notice}</p>}
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <Field label="Your email address">
          <input className={`${inputCls} sm:w-72`} type="email" value={address} onChange={(e) => setAddress(e.target.value)} />
        </Field>
        <Button variant="secondary" onClick={() => call("/account/email/address", "PUT", { address }, "Address saved. Verify it with a code.")}>
          Save address
        </Button>
      </div>
      {v.address && (
        <p className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <Badge tone={v.verified ? "green" : "amber"}>{v.verified ? "Verified" : "Not verified"}</Badge>
          <Badge tone={v.enabled ? "green" : "slate"}>{v.enabled ? "Reminders on" : "Reminders off"}</Badge>
        </p>
      )}
      {v.address && !v.verified && (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <Button variant="secondary" disabled={!v.configured} onClick={() => call("/account/email/code", "POST", undefined, "A code is on its way to that address.")}>
            Send me a code
          </Button>
          <Field label="Code from the email">
            <input className={`${inputCls} sm:w-32`} inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value)} />
          </Field>
          <Button disabled={!code} onClick={() => call("/account/email/verify", "POST", { code }, "Address verified.")}>
            Verify
          </Button>
        </div>
      )}
      {v.verified && (
        <fieldset className="mt-3 space-y-2 text-sm">
          <legend className="font-medium">What to email you about</legend>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={v.attention} onChange={(e) => call("/account/email/preferences", "PUT", { attention: e.target.checked, follow_ups: v.follow_ups, digest_hour_utc: v.digest_hour_utc })} />
            Applications that need your attention
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={v.follow_ups} onChange={(e) => call("/account/email/preferences", "PUT", { attention: v.attention, follow_ups: e.target.checked, digest_hour_utc: v.digest_hour_utc })} />
            Follow-ups that are due
          </label>
          <label className="flex flex-wrap items-center gap-2">
            Daily digest from
            <select
              aria-label="Digest hour (UTC)"
              className={`${inputCls} w-28`}
              value={v.digest_hour_utc}
              onChange={(e) => call("/account/email/preferences", "PUT", { attention: v.attention, follow_ups: v.follow_ups, digest_hour_utc: Number(e.target.value) })}
            >
              {Array.from({ length: 24 }, (_, h) => (
                <option key={h} value={h}>{`${String(h).padStart(2, "0")}:00 UTC`}</option>
              ))}
            </select>
          </label>
          <div className="flex flex-wrap gap-2 pt-1">
            {v.enabled ? (
              <Button variant="secondary" onClick={() => call("/account/email/disable", "POST", undefined, "Email reminders are off. Anything not yet sent was cancelled.")}>
                Turn email reminders off
              </Button>
            ) : (
              <Button disabled={!v.configured} onClick={() => call("/account/email/enable", "POST", undefined, "Email reminders are on.")}>
                Turn email reminders on
              </Button>
            )}
          </div>
        </fieldset>
      )}
      {v.address && (
        <div className="mt-3">
          <Button variant="danger" onClick={() => call("/account/email", "DELETE", undefined, "Your address was removed.")}>
            Remove my address
          </Button>
        </div>
      )}
      {v.recent.length > 0 && (
        <div className="mt-4 text-sm">
          <p className="font-medium">Recent emails</p>
          <ul className="mt-1 space-y-1 text-slate-600" aria-label="Recent emails">
            {v.recent.map((d, i) => (
              <li key={i} data-testid="email-delivery">
                {d.kind === "digest" ? `Daily digest (${d.item_count} item${d.item_count === 1 ? "" : "s"})` : "Verification code"}:{" "}
                {STATUS_TEXT[d.status]} · {new Date(d.created_at).toLocaleString()}
              </li>
            ))}
          </ul>
          <p className="mt-1 text-xs text-slate-500">
            &ldquo;Accepted&rdquo; means the mail server took it, not that it reached your inbox. A message already accepted cannot be recalled.
          </p>
        </div>
      )}
    </Card>
  );
}
