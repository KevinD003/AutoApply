"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";

// Shared state + actions for the email card (Account) and the Email-updates card (Tracker).
// One place reads GET /inbox, runs an action (accept / correct / undo / relink / dismiss /
// check), and folds the returned view back in. `onApplied` lets a host refresh anything an
// outcome change affects (the tracker's application list and funnel).
export function useInbox(onApplied) {
  const [v, setV] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [apps, setApps] = useState(null);
  const [appsLoading, setAppsLoading] = useState(false);

  const reload = useCallback(() => {
    api("/inbox").then(setV).catch(setError);
  }, []);
  useEffect(reload, [reload]);

  // The applications offered when correcting the "wrong application"; fetched once, lazily, only
  // when a relink picker is first opened.
  const loadApps = useCallback(() => {
    if (apps !== null || appsLoading) return;
    setAppsLoading(true);
    api("/applications")
      .then((r) =>
        setApps(
          r.map((a) => ({ id: a.id, label: `${a.job.title ?? "Untitled"} — ${a.job.employer ?? ""}` })),
        ),
      )
      .catch(() => setApps([]))
      .finally(() => setAppsLoading(false));
  }, [apps, appsLoading]);

  const act = useCallback(
    async (promise, opts = {}) => {
      setBusy(true);
      setError(null);
      try {
        setV(await promise);
        if (opts.notice) setNotice(opts.notice);
        if (opts.applied && onApplied) onApplied();
        return true;
      } catch (e) {
        setError(e);
        return false;
      } finally {
        setBusy(false);
      }
    },
    [onApplied],
  );

  return { v, setV, error, notice, busy, apps, loadApps, act, reload };
}
