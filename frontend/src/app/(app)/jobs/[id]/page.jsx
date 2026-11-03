"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Fragment, useCallback, useEffect, useState } from "react";

import { Badge, Button, Card, Credit, ErrorBox, Field, inputCls, Loading } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { cx } from "@/ui/cx";
import { Reveal, Stagger } from "@/ui/motion";

const RESULT = {
  met: { tone: "green", label: "met" },
  not_met: { tone: "amber", label: "not met" },
  not_stated: { tone: "slate", label: "not stated" },
  not_set: { tone: "slate", label: "not set" },
};

function yoursLine(y, what) {
  return what === "sponsorship"
    ? `${y.country}: you need sponsorship now: ${y.sponsorship_now}; later: ${y.sponsorship_later}`
    : `${y.country}: you are authorized to work: ${y.authorized}`;
}

// ── D126: the complete, structured, sanitized job detail (content.py → GET /jobs/{id}.content) ──
// Blocks are rendered as React elements, never as raw HTML, so the sanitizer's guarantee holds
// all the way to the DOM: no script runs and no embedded asset is ever fetched.

function renderText(text) {
  // A span's text may carry soft line breaks ("\n", from <br>). Render them, nothing else.
  return String(text ?? "")
    .split("\n")
    .map((part, j) => (
      <Fragment key={j}>
        {j > 0 && <br />}
        {part}
      </Fragment>
    ));
}

function Span({ s }) {
  const inner = renderText(s.text);
  if (s.href) {
    return (
      <a href={s.href} target="_blank" rel="noopener noreferrer nofollow" className="text-brand underline">
        {inner}
      </a>
    );
  }
  if (s.bold) return <strong>{s.italic ? <em>{inner}</em> : inner}</strong>;
  if (s.italic) return <em>{inner}</em>;
  return <>{inner}</>;
}

function Spans({ spans }) {
  return (spans || []).map((s, i) => <Span key={i} s={s} />);
}

function Block({ b }) {
  if (b.type === "heading") {
    return (
      <h4 className="mt-4 text-sm font-semibold text-ink first:mt-0">
        <Spans spans={b.spans} />
      </h4>
    );
  }
  if (b.type === "list") {
    const Tag = b.ordered ? "ol" : "ul";
    return (
      <Tag className={cx("mt-2 space-y-1 pl-5 text-sm text-ink-muted", b.ordered ? "list-decimal" : "list-disc")}>
        {(b.items || []).map((item, i) => (
          <li key={i}>
            <Spans spans={item} />
          </li>
        ))}
      </Tag>
    );
  }
  return (
    <p className="mt-2 text-sm leading-relaxed text-ink-muted first:mt-0">
      <Spans spans={b.spans} />
    </p>
  );
}

function Blocks({ blocks }) {
  return (blocks || []).map((b, i) => <Block key={i} b={b} />);
}

const SAL_PROVENANCE = {
  structured: "From the posting’s structured data",
  enrichment: "Estimated by the discovery source",
  extracted: "Found in the description text",
};
const SAL_KIND = { base: "base pay", bonus: "bonus", equity: "equity", ote: "on-target earnings", total: "total" };

function salaryDisplay(s) {
  if (s.text) return s.text; // extracted: the original snippet, exactly as written
  const sym = s.currency_symbol || "";
  const code = !s.currency_symbol && s.currency ? ` ${s.currency}` : "";
  const amount = s.min && s.max ? `${sym}${s.min}–${sym}${s.max}` : `${sym}${s.amount || s.min || s.max || ""}`;
  const per = s.period ? ` / ${s.period}` : s.period_raw ? ` (${s.period_raw})` : "";
  return `${amount}${code}${per}`.trim();
}

function Salary({ salary }) {
  // The owner sees the original figures as given; nothing here annualizes or converts (D126).
  if (!salary) return <p className="text-sm text-ink-muted">Salary not provided.</p>;
  const kind = SAL_KIND[salary.kind];
  return (
    <div>
      <p className="text-lg font-semibold tracking-tight text-ink">
        {salaryDisplay(salary)}
        {kind && <span className="ml-1.5 text-sm font-normal text-ink-muted">({kind})</span>}
      </p>
      <p className="mt-0.5 text-xs text-ink-faint">
        {SAL_PROVENANCE[salary.source] || "Stated pay"} · shown as given; not annualized or currency-converted.
      </p>
    </div>
  );
}

function Facts({ facts }) {
  const chips = [];
  if (facts.employment_type) chips.push(["Employment", facts.employment_type]);
  if (facts.seniority) chips.push(["Seniority", facts.seniority]);
  if (facts.department) chips.push(["Department", facts.department]);
  const locations = facts.locations || [];
  if (!chips.length && !locations.length) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {chips.map(([k, v]) => (
        <Badge key={k} tone="slate">
          {k}: {v}
        </Badge>
      ))}
      {locations.map((l) => (
        <Badge key={l} tone="slate">
          {l}
        </Badge>
      ))}
    </div>
  );
}

// The body of the posting: salary with provenance, the facts the source gave, the full
// (sanitized) description and the source's own sections. Rendered only when a source actually
// gave something — a bare job shows no empty card. Availability-dependent, never invented.
function JobBody({ content }) {
  const c = content || {};
  const desc = c.description || {};
  const blocks = desc.blocks || [];
  const sections = desc.sections || [];
  const facts = c.facts || {};
  const hasFacts = !!(facts.employment_type || facts.seniority || facts.department || (facts.locations || []).length);
  if (!blocks.length && !sections.length && !c.salary && !hasFacts) return null;
  return (
    <Reveal>
      <Card title="About this role">
        <div className="space-y-4">
          <Salary salary={c.salary ?? null} />
          {hasFacts && <Facts facts={facts} />}
          {blocks.length > 0 && (
            <div data-testid="job-description">
              <Blocks blocks={blocks} />
            </div>
          )}
          {sections.length > 0 && (
            <Stagger className="space-y-4">
              {sections.map((sec, i) => (
                <section key={i}>
                  {sec.heading && <h3 className="text-sm font-semibold text-ink">{sec.heading}</h3>}
                  <Blocks blocks={sec.blocks} />
                </section>
              ))}
            </Stagger>
          )}
          {c.origin === "your_entry" && (
            <p className="text-xs text-ink-faint">From your own saved text for this job.</p>
          )}
        </div>
      </Card>
    </Reveal>
  );
}

// Priority D (D79): three components, never mixed. The only number counts your own preferences
// that could be checked; eligibility is shown side by side and never decided here.
function FitCard({ fit }) {
  const [skills, licences] = fit.qualifications;
  return (
    <Card title="Why this job matches (or doesn't)">
      <p className="text-sm font-medium text-ink">
        Your preferences: {fit.preference_fit.label}
        <span className="block text-xs font-normal text-ink-faint">
          A count of your own targets this job could be checked against: not a prediction and not an application-system score.
        </span>
      </p>
      <ul aria-label="Your preferences" className="mt-2 space-y-2">
        {fit.preferences.map((p) => (
          <li key={p.what} className="flex items-start gap-2 text-sm">
            <Badge tone={RESULT[p.result].tone}>{RESULT[p.result].label}</Badge>
            <span>{p.text}</span>
          </li>
        ))}
      </ul>
      <h3 className="mt-4 text-sm font-medium text-ink">Eligibility, side by side (advisory)</h3>
      <p className="text-xs text-ink-faint">
        What a source says next to what you recorded. NoEfforts does not decide eligibility; each question is answered from your facts when you prepare.
      </p>
      <ul aria-label="Eligibility" className="mt-1 space-y-2 text-sm">
        {fit.eligibility.map((e) => (
          <li key={e.what}>
            <span className="font-medium">{e.what === "sponsorship" ? "Sponsorship offered" : "Job's country"}</span>: source says{" "}
            {e.source_says}
            {e.stated_by ? ` (${e.stated_by}${e.basis ? `, ${e.basis}` : ""})` : ""}
            {e.note ? `. ${e.note}` : ""}
            <ul className="ml-4 list-disc text-xs text-ink-muted">
              {e.yours.length === 0 ? <li>You have recorded nothing for this.</li> : e.yours.map((y) => <li key={y.country}>{yoursLine(y, e.what)}</li>)}
            </ul>
          </li>
        ))}
      </ul>
      {skills && (
        <>
          <h3 className="mt-4 text-sm font-medium text-ink">Your approved qualifications the job names</h3>
          <ul aria-label="Qualifications" className="mt-1 space-y-1 text-sm">
            <li>
              Skills: {skills.mentioned.length ? skills.mentioned.join(", ") : "none of yours named"} ({skills.mentioned.length} of {skills.of} you listed)
            </li>
            <li>
              Licences: {licences.mentioned.length ? licences.mentioned.join(", ") : "none of yours named"} ({licences.mentioned.length} of {licences.of} valid)
            </li>
          </ul>
        </>
      )}
      {fit.missing.length > 0 && (
        <>
          <h3 className="mt-4 text-sm font-medium text-ink">Not known, so not checked</h3>
          <ul aria-label="Missing information" className="mt-1 list-disc space-y-1 pl-5 text-sm text-ink-muted">
            {fit.missing.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}

export default function JobPage() {
  const { id } = useParams();
  const router = useRouter();
  const [job, setJob] = useState(null);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState(null);
  const [missing, setMissing] = useState(false);
  // The route depends on the captured form: it is read again whenever a form is captured.
  const [route, setRoute] = useState(null);
  const [formVersion, setFormVersion] = useState(0);

  const load = useCallback(() => {
    api(`/jobs/${id}`)
      .then((j) => {
        setJob(j);
        setNotes(j.notes ?? "");
      })
      .catch((e) => (e instanceof ApiError && e.status === 404 ? setMissing(true) : setError(e)));
  }, [id]);

  useEffect(load, [load]);

  // The jobs list links to /jobs/{id}#match: scroll there once the job (and the card) is shown.
  const loaded = job !== null;
  useEffect(() => {
    if (loaded && window.location.hash === "#match") document.getElementById("match")?.scrollIntoView();
  }, [loaded]);

  async function patch(body) {
    setError(null);
    try {
      await api(`/jobs/${id}`, { method: "PATCH", json: body });
      load();
    } catch (e) {
      setError(e);
    }
  }

  async function prepare() {
    try {
      const app = await api("/applications", { json: { job_id: id } });
      router.push(`/applications/${app.id}`);
    } catch (e) {
      setError(e);
    }
  }

  async function track() {
    try {
      const app = await api("/applications", { json: { job_id: id } });
      router.push(`/tracker?highlight=${app.id}`);
    } catch (e) {
      setError(e);
    }
  }

  if (missing)
    return (
      <Card>
        <p>
          This job does not exist or is not yours.{" "}
          <Link className="text-brand underline" href="/jobs">
            Back to jobs
          </Link>
        </p>
      </Card>
    );
  if (!job) return <><ErrorBox error={error} /><Loading /></>;

  return (
    <>
      <Link href="/jobs" className="text-sm text-brand underline">← All jobs</Link>
      <Card
        title={job.title ?? "Untitled role"}
        actions={<Badge tone={job.status === "excluded" ? "red" : "indigo"}>{job.status}</Badge>}
      >
        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          <Row k="Employer" v={job.employer} />
          <Row k="Location" v={job.location} />
          <Row k="Application system" v={job.ats_provider === "unknown" ? "Not recognised" : job.ats_provider} />
          <Row k="Requisition" v={job.requisition_id} />
          <Row k="Posted" v={job.posted_on} />
          <Row k="First seen" v={new Date(job.first_seen_at).toLocaleString()} />
          <Row k="Times seen" v={String(job.seen_count)} />
          <Row k="Source" v={job.source} />
        </dl>
        {job.discovered_from.length > 0 && (
          <div className="mt-3 rounded-lg bg-surface-2 p-3 text-sm text-ink-muted">
            <p className="font-medium">Found through a discovery source</p>
            <ul className="mt-1 space-y-1">
              {job.discovered_from.map((d, i) => (
                <li key={i}>
                  <Badge>{d.label}</Badge> <Credit a={d.attribution} /> last seen {new Date(d.last_seen_at).toLocaleString()}
                  {d.stale && <> · <span className="text-caution-ink">{d.stale_reason}</span></>}
                  {d.changed_fields.length > 0 && <> · changed at the source: {d.changed_fields.join(", ")} (not applied here)</>}
                  {(d.signal_lines?.length ?? 0) > 0 && (
                    <span className="block text-xs text-ink-muted" data-testid="source-signals">
                      {d.label} says: {d.signal_lines.join(" · ")} (display only: not used to match, approve or apply)
                    </span>
                  )}
                </li>
              ))}
            </ul>
            <p className="mt-1 text-xs text-ink-faint">A source listing is not verified, and says nothing about eligibility or sponsorship.</p>
          </div>
        )}
        {job.url && (
          <p className="mt-3 break-all text-sm">
            <a className="text-brand underline" href={job.url} target="_blank" rel="noopener noreferrer nofollow">
              Open original posting
            </a>
          </p>
        )}
        <div className="mt-4 flex flex-wrap gap-2">
          <Button onClick={track}>Track application</Button>
          {job.status !== "shortlisted" && <Button variant="secondary" onClick={() => patch({ status: "shortlisted" })}>Shortlist</Button>}
          {job.status !== "excluded" && (
            <Button variant="secondary" onClick={() => patch({ status: "excluded", exclusion_reason: "Excluded manually" })}>Exclude</Button>
          )}
          {job.status !== "new" && <Button variant="secondary" onClick={() => patch({ status: "new" })}>Reset to new</Button>}
        </div>
      </Card>
      <JobBody content={job.content} />
      <SignalsCard job={job} onChange={load} onError={setError} />
      <RouteCard jobId={id} refresh={formVersion} onRoute={setRoute} />
      <FormCard
        jobId={id}
        onPrepare={prepare}
        onCaptured={() => setFormVersion((v) => v + 1)}
        realDestination={route?.reason === "real_destination_disabled"}
        greenhousePilot={job.ats_provider === "greenhouse" && route?.reason === "no_form_captured"}
      />
      <div id="match" className="scroll-mt-4">
        <FitCard fit={job.fit} />
      </div>
      <Card title="Notes">
        <Field label="Private notes">
          <textarea className={inputCls} rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>
        <Button className="mt-2" variant="secondary" onClick={() => patch({ notes })}>Save notes</Button>
        <div className="mt-2"><ErrorBox error={error} /></div>
      </Card>
    </>
  );
}

function RouteCard({ jobId, refresh, onRoute }) {
  const [route, setRoute] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(() => {
    setError(null);
    api(`/jobs/${jobId}/route`)
      .then((r) => {
        setRoute(r);
        onRoute(r);
      })
      .catch(setError);
  }, [jobId, onRoute]);
  useEffect(() => {
    load();
  }, [load, refresh]);
  return (
    <Card
      title="How NoEfforts could apply"
      actions={
        <Button variant="secondary" onClick={load}>
          Check again
        </Button>
      }
    >
      <ErrorBox error={error} />
      {route && (
        <div className="space-y-1 text-sm">
          <p>
            <Badge tone={route.route === "browser" || route.route === "api" ? "indigo" : "amber"}>{route.label}</Badge>
          </p>
          {route.message && <p className="text-ink-muted">{route.message}</p>}
          {(route.route === "api" || route.route === "browser") && (
            <p className="text-xs text-ink-faint">
              Provider: {route.provider} — {route.provider_support}
            </p>
          )}
          <p className="text-xs text-ink-faint">Reason code: {route.reason}</p>
        </div>
      )}
    </Card>
  );
}

function FormCard({ jobId, onPrepare, onCaptured, realDestination, greenhousePilot }) {
  const [form, setForm] = useState(undefined);
  const [fixtures, setFixtures] = useState({});
  const [pick, setPick] = useState("basic");
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    api(`/jobs/${jobId}/form`)
      .then(setForm)
      .catch((e) => (e instanceof ApiError && e.status === 404 ? setForm(null) : setError(e)));
  }, [jobId]);

  useEffect(() => {
    load();
    api("/fixtures/forms")
      .then((r) => setFixtures(r.fixtures))
      .catch(() => undefined);
  }, [load]);

  async function read(kind) {
    setError(null);
    try {
      setForm(await api(`/jobs/${jobId}/form/${kind}`, { method: "POST" }));
      onCaptured();
    } catch (e) {
      setError(e);
    }
  }

  async function attach() {
    setError(null);
    try {
      setForm(await api(`/jobs/${jobId}/form`, { json: { fixture: pick } }));
      onCaptured();
    } catch (e) {
      setError(e);
    }
  }

  return (
    <Card title="Application form">
      <ErrorBox error={error} />
      {form === undefined ? (
        <Loading />
      ) : form === null && realDestination ? (
        // A real employer's site: the test-only controls below could not change that.
        <p className="text-sm">
          This posting is on a real employer&apos;s site. NoEfforts reads and fills a real employer&apos;s form only through the
          Greenhouse pilot, for a Greenhouse job post on a server where it is switched on (“How NoEfforts could apply” above says
          why not here). Otherwise apply there, then record it with “Track application”.
        </p>
      ) : form === null && greenhousePilot ? (
        <div className="space-y-2 text-sm" data-testid="greenhouse-pilot">
          <p>
            This is a Greenhouse job post, and the Greenhouse pilot is on for your account. NoEfforts can read its questions
            from Greenhouse&apos;s public job data and its page (nothing of yours is sent). Every application still needs your
            approval, and the first one to this employer is a rehearsal that never submits.
          </p>
          <Button variant="secondary" onClick={() => read("greenhouse")}>
            Read the Greenhouse form
          </Button>
        </div>
      ) : form === null ? (
        <div className="space-y-2 text-sm">
          <p>
            No form captured yet. Reading forms from employer sites is not available in this version; for now you can attach a
            local test form (fictional employer) to try the preparation workflow.
          </p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <select aria-label="Test form" className={inputCls} value={pick} onChange={(e) => setPick(e.target.value)}>
              {Object.entries(fixtures).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
            <Button variant="secondary" onClick={attach}>
              Attach test form
            </Button>
          </div>
          <p>
            For a Greenhouse-style job post on the local test receiver, NoEfforts can read the questions from the job data and
            the application page and check that they agree. Real Greenhouse posts are not read in this version.
          </p>
          <Button variant="secondary" onClick={() => read("greenhouse")}>
            Read Greenhouse-style test form
          </Button>
          <p>
            For a Lever-style posting on the local test receiver, NoEfforts can read its application page. Real Lever
            postings are not read in this version.
          </p>
          <Button variant="secondary" onClick={() => read("lever")}>
            Read Lever-style test form
          </Button>
          <p>
            For an Ashby-style posting on the local test receiver, NoEfforts can read its application page. Real Ashby
            postings are not read in this version.
          </p>
          <Button variant="secondary" onClick={() => read("ashby")}>
            Read Ashby-style test form
          </Button>
          <p>
            For a Workday-style posting on the local test receiver, NoEfforts can read a single-page application. Accounts,
            several pages, prefilled answers and location lists stay yours. Real Workday postings are not read in this
            version.
          </p>
          <Button variant="secondary" onClick={() => read("workday")}>
            Read Workday-style test form
          </Button>
        </div>
      ) : (
        <div className="space-y-3 text-sm">
          <p>
            Form v{form.version} · {form.schema.fields.length} questions · source: {form.source}
            {form.source_label && (
              <>
                {" "}
                <Badge tone="amber">{form.source_label}</Badge>
              </>
            )}
          </p>
          <Button onClick={onPrepare}>Prepare application</Button>
        </div>
      )}
    </Card>
  );
}

function Row({ k, v }) {
  return (
    <div>
      <dt className="text-ink-faint">{k}</dt>
      <dd className="text-ink">{v || "—"}</dd>
    </div>
  );
}

// S3: what about this job holds an approval back, with the statements that answer it. All
// messages come from the API (backend jobs/signals.py).
function SignalsCard({ job, onChange, onError }) {
  const s = job.signals;
  if (!s.approval_blocked && !s.source_closed && s.possible_duplicates.length === 0) return null;
  async function state(path) {
    try {
      await api(`/jobs/${job.id}/${path}`, { method: "POST" });
      onChange();
    } catch (e) {
      onError(e);
    }
  }
  return (
    <Card title="Before you apply">
      {s.approval_blocked && <p className="text-sm text-caution-ink">{s.approval_blocked.message}</p>}
      {s.source_closed && (
        <div className="mt-3 text-sm">
          <p>
            <Badge tone="amber">{s.source_closed.provider_label}</Badge> says this posting is {s.source_closed.reason} (since{" "}
            {new Date(s.source_closed.since).toLocaleString()}).
          </p>
          <Button className="mt-2" variant="secondary" onClick={() => state("still-open")}>It is still open</Button>
        </div>
      )}
      {s.possible_duplicates.length > 0 && (
        <div className="mt-3 text-sm">
          <p className="font-medium">Looks like a role you already have an application for</p>
          <ul className="mt-1 space-y-1">
            {s.possible_duplicates.map((d) => (
              <li key={d.application_id}>
                <Link className="text-brand underline" href={`/jobs/${d.job_id}`}>
                  {d.title ?? "Untitled role"} · {d.employer}
                  {d.location ? ` · ${d.location}` : ""}
                </Link>{" "}
                <Badge>{d.state}</Badge> {d.outcome !== "none" && <Badge tone="indigo">{d.outcome}</Badge>}
              </li>
            ))}
          </ul>
          <Button className="mt-2" variant="secondary" onClick={() => state("different-role")}>This is a different role</Button>
        </div>
      )}
    </Card>
  );
}
