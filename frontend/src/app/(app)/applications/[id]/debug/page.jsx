"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Badge, Card, ErrorBox, Loading } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { safeHref, stage, when } from "@/lib/debug";

// D168: one application from the moment its job was found to its outcome, as NoEfforts kept it
// (backend debug/service.trace): every step in order, then each part in detail. Read-only, and
// never a secret: no verification code, token or keyed reference, and an answer is shown as the
// review page shows it, never its stored value.

function show(v) {
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (Array.isArray(v)) return v.map((x) => (typeof x === "object" ? JSON.stringify(x) : String(x))).join(", ");
  if (v && typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function Facts({ items }) {
  const shown = items.filter(([, v]) => v !== null && v !== undefined && v !== "" && !(Array.isArray(v) && v.length === 0));
  if (shown.length === 0) return null;
  return (
    <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-[max-content_1fr]">
      {shown.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-ink-faint">{k}</dt>
          <dd className="min-w-0 break-words text-ink">{show(v)}</dd>
        </div>
      ))}
    </dl>
  );
}

function Data({ value }) {
  if (value === null || value === undefined || (typeof value === "object" && Object.keys(value).length === 0)) return null;
  return (
    <pre className="mt-1 max-w-full overflow-x-auto whitespace-pre-wrap break-words rounded-[var(--r-md)] bg-surface-3 p-2 text-xs text-ink-muted">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function Section({ title, count, children }) {
  return (
    <details className="rounded-[var(--r-lg)] border border-hairline bg-surface p-4 shadow-[var(--shadow-sm)] sm:p-5">
      <summary className="cursor-pointer text-base font-semibold tracking-tight text-ink">
        {title} <span className="text-sm font-normal text-ink-muted">({count})</span>
      </summary>
      <div className="mt-3 space-y-4">{count === 0 ? <p className="text-sm text-ink-muted">Nothing recorded.</p> : children}</div>
    </details>
  );
}

function Rows({ label, items, render }) {
  if (!items || items.length === 0) return null;
  return (
    <div>
      <h4 className="text-sm font-medium text-ink">{label}</h4>
      <ul className="mt-1 space-y-1 text-sm text-ink-muted">
        {items.map((x, i) => (
          <li key={i} className="break-words">
            {render(x)}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function ApplicationDebugPage() {
  const { id } = useParams();
  const [t, setT] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api(`/debug/applications/${id}`)
      .then(setT)
      .catch((e) =>
        setError(e instanceof ApiError && e.status === 404 ? new Error("No application of yours has this address.") : e),
      );
  }, [id]);

  if (error)
    return (
      <>
        <Link href="/debug" className="text-sm text-brand underline">
          ← Debugger
        </Link>
        <ErrorBox error={error} />
      </>
    );
  if (!t) return <Loading />;

  const job = t.job;
  const href = safeHref(job.url);
  return (
    <>
      <p className="flex flex-wrap gap-4 text-sm">
        <Link href="/debug" className="text-brand underline">
          ← Debugger
        </Link>
        <Link href={`/applications/${t.application.id}`} className="text-brand underline">
          Review page
        </Link>
      </p>
      <h1 className="text-xl font-semibold">Process trace</h1>
      <Card title={job.title ?? "Untitled role"}>
        <p className="text-ink-muted">{job.employer}</p>
        <p className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <Badge tone="indigo">{t.application.state}</Badge>
          {t.application.outcome && t.application.outcome !== "none" && <Badge tone="green">{t.application.outcome}</Badge>}
          <span className="text-ink-faint">since {when(t.application.state_changed_at)}</span>
        </p>
        <div className="mt-3">
          <Facts
            items={[
              ["Where it applies", job.ats_provider],
              ["Source", job.source],
              ["Job status", job.status],
              ["Excluded because", job.exclusion_reason],
              ["Location", job.location],
              ["Posted on", job.posted_on],
              ["First seen", job.first_seen_at && when(job.first_seen_at)],
              ["Confirmed open", job.open_confirmed_at && when(job.open_confirmed_at)],
            ]}
          />
          {href ? (
            <a className="mt-2 inline-block break-all text-sm text-brand underline" href={href} target="_blank" rel="noopener noreferrer nofollow">
              {job.url}
            </a>
          ) : (
            job.url && <p className="mt-2 break-all text-sm text-ink-muted">{job.url}</p>
          )}
        </div>
      </Card>

      <Card title="Timeline">
        <ol aria-label="Timeline" className="divide-y divide-hairline">
          {t.timeline.map((s, i) => {
            const st = stage(s.stage);
            return (
              <li key={`${s.at}-${i}`} className="flex flex-col gap-1 py-2 sm:flex-row sm:items-start sm:gap-3">
                <time dateTime={s.at} className="shrink-0 text-xs text-ink-faint sm:w-44">
                  {when(s.at)}
                </time>
                <p className="flex min-w-0 flex-wrap items-center gap-2 text-sm">
                  <Badge tone={st.tone}>{st.label}</Badge>
                  <span className="break-words text-ink">{s.what}</span>
                </p>
              </li>
            );
          })}
        </ol>
      </Card>

      <Section title="Where it was found" count={t.discovery.length}>
        {t.discovery.map((d, i) => (
          <Facts
            key={i}
            items={[
              ["Provider", d.provider],
              ["Status", d.status],
              ["Linked by", d.link_basis],
              ["First seen", when(d.first_seen_at)],
              ["Last seen", when(d.last_seen_at)],
              ["Stale", d.stale ? d.stale_reason || true : null],
              ["Changed", d.changed_fields],
              ["Filter", d.filter_result],
            ]}
          />
        ))}
      </Section>

      <Section title="Form reads" count={t.captures.length}>
        {t.captures.map((c) => (
          <div key={c.version} className="space-y-2">
            <h3 className="text-sm font-semibold text-ink">Version {c.version}</h3>
            <Facts
              items={[
                ["Read at", when(c.captured_at)],
                ["Read from", c.source],
                ["Reader version", c.extraction_version],
                ["Fingerprint", c.fingerprint],
                ["Questions", c.fields],
                ["Required", c.required],
                ["Wizard pages", c.wizard_pages],
              ]}
            />
            <Rows
              label="Stops for you (a required control NoEfforts cannot fill)"
              items={c.checkpoints}
              render={(x) => `${x.label ?? x.key}: ${x.reason ?? "not supported"}`}
            />
            <Rows
              label="Set by the page (a location search's value: checked after it, never filled)"
              items={c.set_by_the_page}
              render={(x) => `${x.label ?? x.key}: ${x.reason ?? "set by the page"}`}
            />
            <Rows
              label="Left empty (an optional control NoEfforts does not operate)"
              items={c.left_empty}
              render={(x) => `${x.label ?? x.key}: ${x.reason ?? "not supported"}`}
            />
            <Rows
              label="Sections"
              items={c.sections}
              render={(x) => `${x.kind}${x.step ? ` (step ${x.step})` : ""}${x.required ? ", required" : ""}`}
            />
          </div>
        ))}
      </Section>

      <Section title="Packages" count={t.packages.length}>
        {t.packages.map((p) => (
          <div key={p.version} className="space-y-2">
            <h3 className="text-sm font-semibold text-ink">Version {p.version}</h3>
            <Facts
              items={[
                ["Built", when(p.created_at)],
                ["Hash", p.content_hash],
                ["What changed", p.change_summary],
                ["Sent to", p.destination?.submit_url ?? p.destination?.origin],
                ["Form version", p.destination?.form_version],
              ]}
            />
            <Rows
              label="Documents"
              items={p.documents}
              render={(d) => `${d.display ?? d.field} (version ${d.version}, ${d.content_type ?? "file"}${d.origin ? `, ${d.origin}` : ""})`}
            />
            <Rows
              label="Consents"
              items={Object.entries(p.consents ?? {})}
              render={([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`}
            />
            <Rows label="Waiting for you" items={p.unresolved} render={(x) => show(x)} />
            <Rows label="Checks that failed" items={p.validation_errors} render={(x) => show(x)} />
            <Rows
              label="Sections"
              items={p.sections}
              render={(x) => `${x.kind}: ${x.rows} row${x.rows === 1 ? "" : "s"}`}
            />
            {p.answers.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[32rem] text-left text-sm">
                  <caption className="sr-only">Answers in package version {p.version}</caption>
                  <thead className="text-xs text-ink-faint">
                    <tr>
                      <th className="py-1 pr-3 font-medium">Question</th>
                      <th className="py-1 pr-3 font-medium">Status</th>
                      <th className="py-1 pr-3 font-medium">From</th>
                      <th className="py-1 font-medium">What is sent</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-hairline">
                    {p.answers.map((a) => (
                      <tr key={a.key}>
                        <td className="py-1 pr-3 align-top text-ink">
                          {a.label ?? a.key}
                          {a.required ? " *" : ""}
                        </td>
                        <td className="py-1 pr-3 align-top">{a.status}</td>
                        <td className="py-1 pr-3 align-top">{a.source}</td>
                        <td className="break-words py-1 align-top text-ink-muted">{a.sensitive ? "(sensitive: see the review page)" : (a.display ?? "—")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ))}
      </Section>

      <Section title="AI drafts" count={t.drafts.length}>
        <Rows
          label="Long answers drafted (their text is on the review page, where you accept them or not)"
          items={t.drafts}
          render={(d) => `${when(d.at)} · ${d.provider}${d.model ? ` (${d.model})` : ""}: ${d.status}`}
        />
      </Section>

      <Section title="Approvals" count={t.approvals.length}>
        {t.approvals.map((a) => (
          <Facts
            key={a.id}
            items={[
              ["Approved", when(a.approved_at)],
              ["By", a.by_rule ? "your standing rule" : "you"],
              ["Scope", a.scope],
              ["Package version", a.package_version],
              ["Hash", a.content_hash],
              ["Adapter", a.adapter && `${a.adapter} ${a.adapter_version ?? ""}`],
              ["Expires", a.expires_at && when(a.expires_at)],
              ["Retired", a.invalidated_at && `${when(a.invalidated_at)}: ${a.invalidation_reason}`],
            ]}
          />
        ))}
      </Section>

      <Section title="Standing rule" count={t.rule.length}>
        <Rows
          label="What your standing rule decided"
          items={t.rule}
          render={(r) => `${when(r.at)} · ${r.action} (${r.reason})${r.words ? `: ${r.words}` : ""}`}
        />
      </Section>

      <Section title="Status changes" count={t.state_changes.length}>
        <Rows
          label="Each change, by whom"
          items={t.state_changes}
          render={(s) =>
            `${when(s.at)} · ${
              s.to_state ? `${s.from_state ?? "—"} → ${s.to_state}` : `outcome ${s.from_outcome ?? "—"} → ${s.to_outcome}`
            } (${s.actor}${s.source ? `, ${s.source}` : ""})${s.reason ? `: ${s.reason}` : ""}`
          }
        />
      </Section>

      <Section title="Attempts" count={t.attempts.length}>
        {t.attempts.map((a) => (
          <div key={a.id} className="space-y-2">
            <h3 className="flex flex-wrap items-center gap-2 text-sm font-semibold text-ink">
              {a.rehearsal ? "Rehearsal" : "Attempt"} <Badge tone="indigo">{a.state}</Badge>
            </h3>
            <Facts
              items={[
                ["Queued", when(a.created_at)],
                ["Adapter", a.adapter],
                ["Package version", a.package_version],
                ["Package hash", a.package_hash],
                ["Queued by your standing rule", a.queued_by_rule],
                ["Destination", a.destination_class],
                ["Rehearsal first", a.rehearsal_prerequisite],
                ["Generation", a.generation],
                ["Retries", a.retry_count],
                ["Stop asked", a.cancel_requested],
                ["Worker", a.worker],
                ["Last heartbeat", a.heartbeat_at && when(a.heartbeat_at)],
                ["Filling started", a.disclosure_started_at && when(a.disclosure_started_at)],
                ["Final click started", a.send_started_at && when(a.send_started_at)],
                ["Ended", a.finished_at && when(a.finished_at)],
                ["Detail", a.outcome_detail],
              ]}
            />
            {a.events.length > 0 && (
              <div>
                <h4 className="text-sm font-medium text-ink">Events</h4>
                <ol className="mt-1 space-y-2 text-sm text-ink-muted">
                  {a.events.map((e, i) => (
                    <li key={i}>
                      {when(e.at)} · {e.kind} (generation {e.generation})
                      <Data value={e.detail} />
                    </li>
                  ))}
                </ol>
              </div>
            )}
            {a.evidence.length > 0 && (
              <div>
                <h4 className="text-sm font-medium text-ink">Evidence</h4>
                <ol className="mt-1 space-y-2 text-sm text-ink-muted">
                  {a.evidence.map((e, i) => (
                    <li key={i}>
                      {when(e.at)} · {e.kind} ({e.strength})
                      <Data value={e.data} />
                    </li>
                  ))}
                </ol>
              </div>
            )}
            <Rows
              label="Waits for you (the code itself is never kept or shown)"
              items={a.checkpoints}
              render={(c) =>
                `${when(c.at)} · ${c.kind}: ${c.status}, round ${c.round}, ${c.wrong_attempts} wrong of ${c.max_attempts ?? "—"}, until ${when(c.expires_at)}`
              }
            />
            <Rows
              label="Queue messages"
              items={a.outbox}
              render={(m) =>
                `${when(m.at)} · ${m.topic}: ${m.dispatched_at ? `sent ${when(m.dispatched_at)}` : "not sent"}, ${m.publish_attempts} tries${
                  m.last_error ? `, last error ${m.last_error}` : ""
                }`
              }
            />
            {a.rehearsal_record && (
              <div>
                <h4 className="text-sm font-medium text-ink">Rehearsal record</h4>
                <Facts
                  items={[
                    ["Recorded", when(a.rehearsal_record.recorded_at)],
                    ["Still holds", a.rehearsal_record.status === "valid" ? "yes" : a.rehearsal_record.status],
                    ["Withdrawn", a.rehearsal_record.revoked_at && `${when(a.rehearsal_record.revoked_at)}: ${a.rehearsal_record.revoked_reason}`],
                    ["Destination", a.rehearsal_record.destination_class],
                    ["Route", a.rehearsal_record.route],
                    ["Adapter version", a.rehearsal_record.adapter_version],
                    ["Uploads expected", a.rehearsal_record.uploads_expected],
                    ["Uploads acknowledged", a.rehearsal_record.uploads_acknowledged],
                    ["Read back differently", a.rehearsal_record.readback_mismatched],
                    ["Re-check matched", a.rehearsal_record.recheck_matched],
                    ["Blocked by the egress proxy", a.rehearsal_record.egress_proxy_denied],
                  ]}
                />
              </div>
            )}
          </div>
        ))}
      </Section>

      <Section title="Pauses" count={t.pauses.length}>
        {t.pauses.map((p, i) => (
          <div key={i}>
            <Facts
              items={[
                ["Paused", when(p.at)],
                ["Why", p.kind],
                ["Status", p.status],
                ["Resolved", p.resolved_at && `${when(p.resolved_at)}: ${p.resolution}`],
                ["Package version", p.package_version],
                ["Form version", p.form_version],
                ["Read again as version", p.recaptured_version],
              ]}
            />
            <Data value={p.detail} />
          </div>
        ))}
      </Section>

      <Section title="Emails" count={t.emails.length}>
        <Rows
          label="Emails read for this application (never their text)"
          items={t.emails}
          render={(e) =>
            `${when(e.at)} · ${e.sender_domain}: ${e.kind}, ${e.state}${e.proposed_outcome ? `, proposed ${e.proposed_outcome}` : ""}${
              e.applied_outcome ? `, applied ${e.applied_outcome}` : ""
            }`
          }
        />
      </Section>

      <Section title="Audit log" count={t.audit.length}>
        <ol className="space-y-2 text-sm text-ink-muted">
          {t.audit.map((e, i) => (
            <li key={i}>
              {when(e.at)} · {e.action} ({e.entity_type})
              <Data value={e.meta} />
            </li>
          ))}
        </ol>
      </Section>
    </>
  );
}
