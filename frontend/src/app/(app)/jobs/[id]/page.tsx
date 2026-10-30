"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Badge, Button, Card, Credit, ErrorBox, Field, inputCls, Loading } from "@/components/ui";
import { api, ApiError, Application, FitYours, JobDetail, JobFit, JobSignals } from "@/lib/api";

const RESULT = {
  met: { tone: "green", label: "met" },
  not_met: { tone: "amber", label: "not met" },
  not_stated: { tone: "slate", label: "not stated" },
  not_set: { tone: "slate", label: "not set" },
} as const;

function yoursLine(y: FitYours, what: string): string {
  return what === "sponsorship"
    ? `${y.country}: you need sponsorship now: ${y.sponsorship_now}; later: ${y.sponsorship_later}`
    : `${y.country}: you are authorized to work: ${y.authorized}`;
}

// Priority D (D79): three components, never mixed. The only number counts your own preferences
// that could be checked; eligibility is shown side by side and never decided here.
function FitCard({ fit }: { fit: JobFit }) {
  const [skills, licences] = fit.qualifications;
  return (
    <Card title="Why this job matches (or doesn't)">
      <p className="text-sm font-medium text-slate-800">
        Your preferences: {fit.preference_fit.label}
        <span className="block text-xs font-normal text-slate-500">
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
      <h3 className="mt-4 text-sm font-medium text-slate-800">Eligibility, side by side (advisory)</h3>
      <p className="text-xs text-slate-500">
        What a source says next to what you recorded. NoEfforts does not decide eligibility; each question is answered from your facts when you prepare.
      </p>
      <ul aria-label="Eligibility" className="mt-1 space-y-2 text-sm">
        {fit.eligibility.map((e) => (
          <li key={e.what}>
            <span className="font-medium">{e.what === "sponsorship" ? "Sponsorship offered" : "Job's country"}</span>: source says{" "}
            {e.source_says}
            {e.stated_by ? ` (${e.stated_by}${e.basis ? `, ${e.basis}` : ""})` : ""}
            {e.note ? `. ${e.note}` : ""}
            <ul className="ml-4 list-disc text-xs text-slate-600">
              {e.yours.length === 0 ? <li>You have recorded nothing for this.</li> : e.yours.map((y) => <li key={y.country}>{yoursLine(y, e.what)}</li>)}
            </ul>
          </li>
        ))}
      </ul>
      {skills && (
        <>
          <h3 className="mt-4 text-sm font-medium text-slate-800">Your approved qualifications the job names</h3>
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
          <h3 className="mt-4 text-sm font-medium text-slate-800">Not known, so not checked</h3>
          <ul aria-label="Missing information" className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-600">
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
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [job, setJob] = useState<JobDetail | null>(null);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [missing, setMissing] = useState(false);
  // The route depends on the captured form: it is read again whenever a form is captured.
  const [route, setRoute] = useState<Route | null>(null);
  const [formVersion, setFormVersion] = useState(0);

  const load = useCallback(() => {
    api<JobDetail>(`/jobs/${id}`)
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

  async function patch(body: object) {
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
      const app = await api<Application>("/applications", { json: { job_id: id } });
      router.push(`/applications/${app.id}`);
    } catch (e) {
      setError(e);
    }
  }

  async function track() {
    try {
      const app = await api<Application>("/applications", { json: { job_id: id } });
      router.push(`/tracker?highlight=${app.id}`);
    } catch (e) {
      setError(e);
    }
  }

  if (missing) return <Card><p>This job does not exist or is not yours. <Link className="text-indigo-700 underline" href="/jobs">Back to jobs</Link></p></Card>;
  if (!job) return <><ErrorBox error={error} /><Loading /></>;

  return (
    <>
      <Link href="/jobs" className="text-sm text-indigo-700 underline">← All jobs</Link>
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
          <div className="mt-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-700">
            <p className="font-medium">Found through a discovery source</p>
            <ul className="mt-1 space-y-1">
              {job.discovered_from.map((d, i) => (
                <li key={i}>
                  <Badge>{d.label}</Badge> <Credit a={d.attribution} /> last seen {new Date(d.last_seen_at).toLocaleString()}
                  {d.stale && <> · <span className="text-amber-800">{d.stale_reason}</span></>}
                  {d.changed_fields.length > 0 && <> · changed at the source: {d.changed_fields.join(", ")} (not applied here)</>}
                  {(d.signal_lines?.length ?? 0) > 0 && (
                    <span className="block text-xs text-slate-600" data-testid="source-signals">
                      {d.label} says: {d.signal_lines!.join(" · ")} (display only: not used to match, approve or apply)
                    </span>
                  )}
                </li>
              ))}
            </ul>
            <p className="mt-1 text-xs text-slate-500">A source listing is not verified, and says nothing about eligibility or sponsorship.</p>
          </div>
        )}
        {job.url && (
          <p className="mt-3 break-all text-sm">
            <a className="text-indigo-700 underline" href={job.url} target="_blank" rel="noopener noreferrer nofollow">
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
      <SignalsCard job={job} onChange={load} onError={setError} />
      <RouteCard jobId={id} refresh={formVersion} onRoute={setRoute} />
      <FormCard
        jobId={id}
        onPrepare={prepare}
        onCaptured={() => setFormVersion((v) => v + 1)}
        realDestination={route?.reason === "real_destination_disabled"}
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
      {job.description && (
        <Card title="Description">
          <p className="whitespace-pre-wrap text-sm text-slate-700">{job.description}</p>
        </Card>
      )}
    </>
  );
}

// Support wording (labels) comes from the API (backend providers/wording.py), derived from
// evidence; this page writes none of its own.
interface FormInfo {
  version: number;
  source: string;
  source_label: string | null; // set for a local test source, which says so
  source_ref: string | null;
  schema: { title: string | null; fields: unknown[] };
}

// GET /api/jobs/{id}/route.
type Route = {
  route: string;
  provider: string;
  message: string;
  reason: string;
  evidence: string; // the evidence level behind an API or browser route ("fixture" today)
  label: string; // the route and the evidence behind it
  provider_support: string | null; // the provider's support state, worded
};

function RouteCard({ jobId, refresh, onRoute }: { jobId: string; refresh: number; onRoute: (r: Route) => void }) {
  const [route, setRoute] = useState<Route | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(() => {
    setError(null);
    api<Route>(`/jobs/${jobId}/route`)
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
          {route.message && <p className="text-slate-700">{route.message}</p>}
          {(route.route === "api" || route.route === "browser") && (
            <p className="text-xs text-slate-500">
              Provider: {route.provider} — {route.provider_support}
            </p>
          )}
          <p className="text-xs text-slate-500">Reason code: {route.reason}</p>
        </div>
      )}
    </Card>
  );
}

function FormCard({
  jobId,
  onPrepare,
  onCaptured,
  realDestination,
}: {
  jobId: string;
  onPrepare: () => void;
  onCaptured: () => void;
  realDestination: boolean;
}) {
  const [form, setForm] = useState<FormInfo | null | undefined>(undefined);
  const [fixtures, setFixtures] = useState<Record<string, string>>({});
  const [pick, setPick] = useState("basic");
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    api<FormInfo>(`/jobs/${jobId}/form`)
      .then(setForm)
      .catch((e) => (e instanceof ApiError && e.status === 404 ? setForm(null) : setError(e)));
  }, [jobId]);

  useEffect(() => {
    load();
    api<{ fixtures: Record<string, string> }>("/fixtures/forms")
      .then((r) => setFixtures(r.fixtures))
      .catch(() => undefined);
  }, [load]);

  async function read(kind: "greenhouse" | "lever" | "ashby" | "workday") {
    setError(null);
    try {
      setForm(await api<FormInfo>(`/jobs/${jobId}/form/${kind}`, { method: "POST" }));
      onCaptured();
    } catch (e) {
      setError(e);
    }
  }

  async function attach() {
    setError(null);
    try {
      setForm(await api<FormInfo>(`/jobs/${jobId}/form`, { json: { fixture: pick } }));
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
          This posting is on a real employer&apos;s site. NoEfforts does not read or fill real employer forms in this version: apply
          there, then record it with “Track application”.
        </p>
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

function Row({ k, v }: { k: string; v: string | null }) {
  return (
    <div>
      <dt className="text-slate-500">{k}</dt>
      <dd className="text-slate-900">{v || "—"}</dd>
    </div>
  );
}

// S3: what about this job holds an approval back, with the statements that answer it. All
// messages come from the API (backend jobs/signals.py).
function SignalsCard({ job, onChange, onError }: { job: JobDetail; onChange: () => void; onError: (e: unknown) => void }) {
  const s: JobSignals = job.signals;
  if (!s.approval_blocked && !s.source_closed && s.possible_duplicates.length === 0) return null;
  async function state(path: string) {
    try {
      await api(`/jobs/${job.id}/${path}`, { method: "POST" });
      onChange();
    } catch (e) {
      onError(e);
    }
  }
  return (
    <Card title="Before you apply">
      {s.approval_blocked && <p className="text-sm text-amber-800">{s.approval_blocked.message}</p>}
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
                <Link className="text-indigo-700 underline" href={`/jobs/${d.job_id}`}>
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
