"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge, Card, Empty, ErrorBox, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { stage, when } from "@/lib/debug";

// D168: the owner's console. Every switch as it applies to this account (on or off, working or
// not, and why), the owner's recorded permissions with their own words, the rules that always
// apply, and each step NoEfforts took across this account's jobs. It only reads: nothing here
// turns a switch or runs a step, and no secret is ever shown (only whether one is set).
export default function DebuggerPage() {
  const [system, setSystem] = useState(null);
  const [activity, setActivity] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api("/debug/system")
      .then(setSystem)
      .catch(setError);
    api("/debug/activity?limit=200")
      .then((r) => setActivity(r.items))
      .catch((e) => {
        setError(e);
        setActivity([]);
      });
  }, []);

  return (
    <>
      <h1 className="text-xl font-semibold">Debugger</h1>
      <p className="text-sm text-ink-muted">
        The whole automatic application process for this account, start to finish: every switch and why it is on or off, your recorded
        permissions, and each step NoEfforts took. Read-only: nothing here changes a setting or runs a step.
      </p>
      <ErrorBox error={error} />
      {system === null && !error ? (
        <Loading />
      ) : system ? (
        <>
          <Card title="This account">
            <ul className="space-y-1 text-sm" aria-label="This account">
              <li>
                Signed in as <span className="font-medium text-ink">{system.account.email}</span>{" "}
                <Badge tone={system.account.owner ? "green" : "slate"}>{system.account.owner ? "Owner" : "Not the owner"}</Badge>
              </li>
              <li>
                Sole-owner mode (every account is the owner&apos;s):{" "}
                <Badge tone={system.account.sole_owner ? "green" : "slate"}>{system.account.sole_owner ? "On" : "Off"}</Badge>
              </li>
              <li>
                Every account served: <Badge tone={system.account.all_accounts ? "green" : "slate"}>{system.account.all_accounts ? "On" : "Off"}</Badge>
              </li>
              <li className="text-ink-muted">
                Environment: {system.environment.env} · browser isolation: {system.environment.browser_isolation}
              </li>
            </ul>
          </Card>

          {system.warnings.length > 0 && (
            <section aria-label="Warnings" className="space-y-2">
              {system.warnings.map((w) => (
                <p key={w} className="rounded-[var(--r-md)] border border-caution/30 bg-caution-weak p-3 text-sm text-caution-ink">
                  {w}
                </p>
              ))}
            </section>
          )}

          <Card title="Features">
            <ul aria-label="Features" className="divide-y divide-hairline">
              {system.features.map((f) => (
                <li key={f.key} className="py-3">
                  <p className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-ink">{f.name}</span>
                    <Badge tone={f.on ? "green" : "slate"}>{f.on ? "On" : "Off"}</Badge>
                    {f.on && <Badge tone={f.ready ? "green" : "amber"}>{f.ready ? "Working" : "Not working yet"}</Badge>}
                  </p>
                  {f.switch && (
                    <p className="mt-1 text-xs text-ink-faint">
                      Switch: <code className="break-all">{f.switch}</code>
                    </p>
                  )}
                  {f.why && <p className="mt-1 text-sm text-ink-muted">Why: {f.why}</p>}
                  {f.needs.length > 0 && <p className="mt-1 text-sm text-ink-muted">Still needs: {f.needs.join(", ")}</p>}
                  {f.note && <p className="mt-1 text-xs text-ink-faint">{f.note}</p>}
                </li>
              ))}
            </ul>
          </Card>

          <Card title="Recorded permissions">
            <p className="mb-2 text-xs text-ink-faint">
              Steps on real employer sites, and reading a real mailbox, run only within a permission you recorded in your own words, with its
              steps, end date and limit. A switch being on is not a permission.
            </p>
            {system.permissions.length === 0 ? (
              <Empty>No permission is recorded.</Empty>
            ) : (
              <ul aria-label="Recorded permissions" className="divide-y divide-hairline">
                {system.permissions.map((p, i) => (
                  <li key={`${p.decision}-${p.what}-${i}`} className="py-3 text-sm">
                    <p className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-ink">{p.what}</span>
                      <Badge tone={p.active ? "green" : "red"}>{p.active ? "Active" : `Ended ${p.ends_on}`}</Badge>
                    </p>
                    <p className="mt-1 text-xs text-ink-faint">
                      Recorded in {p.decision}, given on {p.given_on}
                      {p.ends_on ? `, ends ${p.ends_on}` : ""} · steps: {p.actions.join(", ")}
                    </p>
                    <blockquote className="mt-2 border-l-2 border-hairline-strong pl-3 text-ink-muted">“{p.words}”</blockquote>
                    {p.data && <p className="mt-1 text-xs text-ink-faint">Data: {p.data}</p>}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Rules that always apply">
            <ul aria-label="Rules that always apply" className="list-disc space-y-1 pl-5 text-sm text-ink-muted">
              {system.safety.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          </Card>
        </>
      ) : null}

      <Card title="Activity">
        <p className="mb-2 text-xs text-ink-faint">What happened across your jobs, newest first. Open a trace to see one application from start to finish.</p>
        {activity === null ? (
          <Loading />
        ) : activity.length === 0 ? (
          <Empty>Nothing yet. Jobs found, forms read, approvals, attempts, pauses and emails will show here.</Empty>
        ) : (
          <ol aria-label="Activity" className="divide-y divide-hairline">
            {activity.map((a, i) => {
              const s = stage(a.stage);
              return (
                <li key={`${a.at}-${i}`} className="flex flex-col gap-1 py-2 sm:flex-row sm:items-center sm:justify-between">
                  <p className="flex min-w-0 flex-wrap items-center gap-2 text-sm">
                    <Badge tone={s.tone}>{s.label}</Badge>
                    <span className="break-words text-ink">{a.what}</span>
                  </p>
                  <p className="flex shrink-0 items-center gap-3 text-xs text-ink-faint">
                    <time dateTime={a.at}>{when(a.at)}</time>
                    {a.application_id && (
                      <Link href={`/applications/${a.application_id}/debug`} className="text-brand underline">
                        Open trace
                      </Link>
                    )}
                  </p>
                </li>
              );
            })}
          </ol>
        )}
      </Card>
    </>
  );
}
