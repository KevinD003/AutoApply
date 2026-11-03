"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { Button, Card, EmptyState, ErrorText, Loading, Pill, SectionTitle } from "@/ui/primitives";
import { IconReview } from "@/ui/icons";

/*
  Review and approve (premium .jsx). D105: approve only the packages you tick, each
  with its own scope; nothing is queued or sent. Every user-facing string, the
  review-item testid, the scope checkbox labels and the approve-button wording are
  preserved verbatim from the previous implementation (review.spec).
*/

const SCOPE_LABEL = {
  disclose_only: "Rehearsal: fill and check, never submit",
  submit: "Submit once",
};

export default function ReviewPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [picked, setPicked] = useState({});
  const [results, setResults] = useState({});
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api("/review/packages")
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch(setError);
  }, []);
  useEffect(load, [load]);

  const chosen = Object.entries(picked).filter(([, s]) => s);

  async function approve() {
    if (!data || !chosen.length) return;
    setBusy(true);
    setError(null);
    try {
      const byId = Object.fromEntries(data.items.map((i) => [i.application_id, i]));
      const items = chosen.map(([id, scope]) => ({
        application_id: id,
        version: byId[id].version,
        content_hash: byId[id].content_hash,
        scope,
      }));
      const r = await api("/review/approve", { json: { items } });
      setResults(Object.fromEntries(r.results.map((x) => [x.application_id, x])));
      setPicked({});
      load();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  if (!data && !error) return <Loading />;
  return (
    <div className="space-y-4">
      <SectionTitle>Review and approve</SectionTitle>
      <p className="text-sm text-ink-muted">
        Tick the packages you have reviewed and choose what each approval allows. Each is approved on its own, for the version shown, its
        application and its destination only, and expires after {data?.approval_ttl_hours ?? "—"} hours. Approving sends nothing: you still
        start each application from its page. A package that changed after this list was loaded is refused, never replaced. Nothing here
        approves future applications.
      </p>
      <ErrorText error={error} />
      {data && data.items.length === 0 && (
        <EmptyState title="No package is waiting for your approval" icon={<IconReview size={28} />}>
          Prepare an application from Jobs or the Tracker, then come back to review and approve it here.
        </EmptyState>
      )}
      {data && data.items.length > 0 && (
        <Card
          title={`${data.items.length} package(s) you can review`}
          actions={
            <Button onClick={approve} disabled={busy || chosen.length === 0 || chosen.length > data.max_items}>
              {`Approve the ${chosen.length} ticked package(s)`}
            </Button>
          }
        >
          <ul className="divide-y divide-hairline">
            {data.items.map((i) => {
              const res = results[i.application_id];
              const scope = picked[i.application_id];
              const blocked = i.blocked.length > 0;
              const rehearseFirst = i.rehearsal_prerequisite.status === "unmet";
              return (
                <li key={i.application_id} className="py-3" data-testid="review-item">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <Link href={`/applications/${i.application_id}`} className="font-medium text-brand underline">
                        {i.title}
                      </Link>{" "}
                      <span className="text-sm text-ink-muted">at {i.employer}</span>
                      <p className="text-xs text-ink-faint">
                        Package v{i.version} · {i.answers} answer(s) · {i.documents} document(s) · {i.destination} · {i.form_source}
                      </p>
                      <p className="font-mono text-xs text-ink-faint" title="The package's content hash">
                        {i.content_hash.slice(0, 12)}
                      </p>
                    </div>
                    {i.approval && (
                      <Pill tone="positive">{i.approval.scope === "submit" ? "Approved to submit" : "Approved for a rehearsal"}</Pill>
                    )}
                  </div>
                  {blocked && (
                    <ul className="mt-1 list-disc pl-5 text-sm text-caution-ink">
                      {i.blocked.map((b) => (
                        <li key={b}>{b}</li>
                      ))}
                    </ul>
                  )}
                  {!blocked && !i.approval && (
                    <fieldset className="mt-2 flex flex-wrap gap-3 text-sm">
                      <legend className="sr-only">{`Approval for ${i.title}`}</legend>
                      {["disclose_only", "submit"].map((s) => (
                        <label key={s} className="flex items-center gap-1">
                          <input
                            type="checkbox"
                            checked={scope === s}
                            disabled={s === "submit" && rehearseFirst}
                            onChange={(e) => setPicked((p) => ({ ...p, [i.application_id]: e.target.checked ? s : undefined }))}
                          />
                          {SCOPE_LABEL[s]}
                        </label>
                      ))}
                      {rehearseFirst && <span className="text-xs text-ink-muted">{i.rehearsal_prerequisite.message}</span>}
                    </fieldset>
                  )}
                  {res && (
                    <p role="status" className={`mt-1 text-sm ${res.status === "approved" ? "text-positive-ink" : "text-danger-ink"}`}>
                      {res.status === "approved"
                        ? `Approved: ${SCOPE_LABEL[res.scope]}, until ${new Date(res.expires_at).toLocaleString()}`
                        : res.status === "not_found"
                          ? "Not found"
                          : `Not approved: ${res.reason}`}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        </Card>
      )}
    </div>
  );
}
