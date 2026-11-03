"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge, Button, Card, ErrorBox, Field, inputCls, Notice } from "./ui";
import { api } from "@/lib/api";

// Priority D (D84, docs/api-tokens.md): personal access tokens for your own scripts, the CLI and
// an MCP client. Shown once, stored as a hash, always expiring, revocable here.
const SCOPE_TEXT = {
  read: "Read your jobs, applications and notifications",
  "import:jobs": "Add jobs (by link, or a CSV or XLSX file)",
};
const STATE_TONE = { active: "green", expired: "slate", revoked: "red" };

export default function ApiTokens() {
  const [tokens, setTokens] = useState(null);
  const [label, setLabel] = useState("");
  const [scopes, setScopes] = useState(["read"]);
  const [days, setDays] = useState(30);
  const [shown, setShown] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    api("/account/tokens")
      .then((r) => setTokens(r.items))
      .catch(setError);
  }, []);
  useEffect(load, [load]);

  async function create(e) {
    e.preventDefault();
    setError(null);
    try {
      const r = await api("/account/tokens", { json: { label, scopes, expires_in_days: days } });
      setShown(r.token);
      setLabel("");
      load();
    } catch (err) {
      setError(err);
    }
  }

  async function revoke(t) {
    setError(null);
    try {
      await api(`/account/tokens/${t.id}/revoke`, { method: "POST" });
      load();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <Card title="API tokens">
      <p className="text-sm text-ink-muted">
        For your own scripts, the <code>noefforts</code> command line and an MCP client on this machine (docs/api-tokens.md). A token can
        read, and with the second scope add jobs. It can never answer, consent, approve or submit anything, read your profile facts,
        documents or saved answers, or manage tokens.
      </p>
      {shown && (
        <div role="status" className="mt-3 rounded-lg border border-caution/40 bg-caution-weak p-3 text-sm text-caution-ink">
          <p className="font-medium">Copy this token now: it is shown only once and NoEfforts cannot show it again.</p>
          <code aria-label="New API token" className="mt-2 block break-all rounded bg-surface p-2 text-xs text-ink">
            {shown}
          </code>
          <Button variant="secondary" className="mt-2" onClick={() => setShown(null)}>
            I have copied it
          </Button>
        </div>
      )}
      <form onSubmit={create} className="mt-3 space-y-3">
        <Field label="Label" hint="What it is for, e.g. “laptop CLI”.">
          <input className={inputCls} required maxLength={100} value={label} onChange={(e) => setLabel(e.target.value)} />
        </Field>
        <fieldset>
          <legend className="text-sm font-medium text-ink">Scopes</legend>
          {Object.entries(SCOPE_TEXT).map(([s, text]) => (
            <label key={s} className="mt-1 flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={scopes.includes(s)}
                onChange={(e) => setScopes(e.target.checked ? [...scopes, s] : scopes.filter((x) => x !== s))}
              />
              {text} (<code>{s}</code>)
            </label>
          ))}
        </fieldset>
        <Field label="Expires after (days)" hint="1 to 90. Every token expires.">
          <input className={`${inputCls} sm:w-32`} type="number" min={1} max={90} required value={days} onChange={(e) => setDays(Number(e.target.value))} />
        </Field>
        <ErrorBox error={error} />
        <Button type="submit" disabled={!label.trim() || scopes.length === 0}>
          Make a token
        </Button>
      </form>
      {tokens && tokens.length > 0 && (
        <ul aria-label="Your API tokens" className="mt-4 divide-y divide-hairline">
          {tokens.map((t) => (
            <li key={t.id} className="flex flex-col gap-2 py-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="text-sm">
                <p className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{t.label}</span>
                  <code className="text-xs text-ink-faint">ne_{t.public_id}_…</code>
                  <Badge tone={STATE_TONE[t.state]}>{t.state}</Badge>
                </p>
                <p className="text-xs text-ink-faint">
                  {t.scopes.join(", ")} · expires {new Date(t.expires_at).toLocaleDateString()} · last used{" "}
                  {t.last_used_at ? new Date(t.last_used_at).toLocaleString() : "never"}
                </p>
              </div>
              {t.state === "active" && (
                <Button variant="danger" onClick={() => revoke(t)}>
                  Revoke
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {tokens && tokens.length === 0 && <Notice>No tokens yet.</Notice>}
    </Card>
  );
}
