"use client";

import { useCallback, useEffect, useState } from "react";

import { Button, Card, ErrorBox, Notice } from "@/components/ui";
import { api } from "@/lib/api";

// D128: connect the owner's Gmail from the app with a browser OAuth flow. The connect control is a
// top-level navigation to the backend, which redirects to Google's own consent page in this same
// browser (the system browser, never an embedded credential view). Connecting enables nothing on
// its own — reading application emails still needs the authorization and tracking controls below
// (InboxCard). Pausing or disconnecting here does not touch verification-code reading, which is a
// separate setting.
const RESULT = {
  connected: "Gmail connected.",
  denied: "Connecting was cancelled, so nothing changed.",
  unexpected_scope:
    "Google offered a different access than read-only mail, so nothing was connected.",
  exchange_failed: "Google did not finish the connection. Please try again.",
  unreachable: "Google could not be reached. Please try again.",
  invalid_state: "That connect link had expired or did not match. Please start again.",
  not_owner: "Connecting Gmail is set up for the server owner’s account only.",
};

function whyText(why) {
  return why === "not_configured"
    ? "Connecting Gmail from the app is not configured on this server yet."
    : "Connecting Gmail from the app is switched off on this server.";
}

function ConnectLink({ children }) {
  // A real navigation (not fetch): the OAuth flow must leave the app to Google and come back.
  return (
    <a
      href="/api/connections/gmail/start"
      data-testid="gmail-connect"
      className="focus-ring inline-block min-h-10 rounded-[var(--r-md)] brand-grad px-4 py-2 text-sm font-medium text-brand-contrast shadow-[var(--shadow-sm)] hover:brightness-[1.06]"
    >
      {children}
    </a>
  );
}

export default function GmailConnection() {
  const [v, setV] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api("/connections")
      .then((r) => setV(r.gmail))
      .catch(setError);
  }, []);
  useEffect(load, [load]);

  // The OAuth callback redirects back with ?connections=gmail&result=…; show it once, then clean
  // the address bar so a refresh doesn't repeat it.
  useEffect(() => {
    try {
      const p = new URLSearchParams(window.location.search);
      if (p.get("connections") === "gmail" && p.get("result")) {
        setNotice(RESULT[p.get("result")] ?? "");
        window.history.replaceState({}, "", window.location.pathname);
      }
    } catch {
      /* no-op: the address bar is a convenience, not required */
    }
  }, []);

  const act = async (promise, msg) => {
    setBusy(true);
    setError(null);
    try {
      setV((await promise).gmail);
      if (msg) setNotice(msg);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  const disconnect = () =>
    act(api("/connections/gmail/disconnect", { method: "POST" }), "Disconnected.");

  if (!v)
    return (
      <Card title="Gmail">
        <ErrorBox error={error} />
      </Card>
    );

  return (
    <Card title="Gmail">
      {notice && <Notice>{notice}</Notice>}
      <ErrorBox error={error} />
      {!v.available ? (
        <p className="text-sm text-ink-muted" data-testid="gmail-unavailable">
          {whyText(v.why_not)}
        </p>
      ) : !v.is_owner ? (
        <p className="text-sm text-ink-muted" data-testid="gmail-not-owner">
          Connecting Gmail is set up for the server owner’s account only.
        </p>
      ) : v.state === "connected" ? (
        <div className="space-y-2 text-sm" data-testid="gmail-connected">
          <p className="text-ink">
            Connected: <span className="font-medium">{v.email}</span>
          </p>
          <p className="text-xs text-ink-muted">{v.scope_label}</p>
          <p className="text-xs text-ink-faint">
            Connecting enables nothing on its own — reading application emails still needs your
            authorization and the tracking setting below.
          </p>
          <Button variant="danger" disabled={busy} onClick={disconnect}>
            Disconnect Google access
          </Button>
          <p className="text-xs text-ink-faint">
            This deletes the access stored on this server. To also remove NoEfforts at Google, use
            your Google account’s Security settings (&ldquo;Third-party access&rdquo;).
          </p>
        </div>
      ) : v.state === "reconnect_required" ? (
        <div className="space-y-2 text-sm" data-testid="gmail-reconnect">
          <p className="text-danger-ink">The connection stopped working and needs reconnecting.</p>
          <ConnectLink>Reconnect Gmail</ConnectLink>
          <Button variant="secondary" disabled={busy} onClick={disconnect}>
            Disconnect
          </Button>
        </div>
      ) : (
        <div className="space-y-2 text-sm" data-testid="gmail-not-connected">
          <p className="text-ink-muted">
            Connect your Gmail (read-only) so NoEfforts can recognise recruitment emails. {v.scope_label}
          </p>
          <ConnectLink>Connect Gmail</ConnectLink>
          <p className="text-xs text-ink-faint">
            You sign in on Google’s own page in your browser; NoEfforts never sees your password.
            Connecting enables nothing until you authorize tracking below.
          </p>
        </div>
      )}
    </Card>
  );
}
