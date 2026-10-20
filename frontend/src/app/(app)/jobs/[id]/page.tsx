"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Badge, Button, Card, ErrorBox, Field, inputCls, Loading } from "@/components/ui";
import { api, ApiError, Application, JobDetail } from "@/lib/api";

const KIND_TONE = { match: "green", mismatch: "amber", exclude: "red", info: "slate" } as const;

export default function JobPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [job, setJob] = useState<JobDetail | null>(null);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [missing, setMissing] = useState(false);

  const load = useCallback(() => {
    api<JobDetail>(`/jobs/${id}`)
      .then((j) => {
        setJob(j);
        setNotes(j.notes ?? "");
      })
      .catch((e) => (e instanceof ApiError && e.status === 404 ? setMissing(true) : setError(e)));
  }, [id]);

  useEffect(load, [load]);

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
      <FormCard jobId={id} onPrepare={prepare} />
      <Card title="Why this job matches (or doesn't)">
        <ul className="space-y-2">
          {job.explanations.map((e, i) => (
            <li key={i} className="flex items-start gap-2 text-sm">
              <Badge tone={KIND_TONE[e.kind]}>{e.kind}</Badge>
              <span>{e.text}</span>
            </li>
          ))}
        </ul>
      </Card>
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

interface FormInfo {
  version: number;
  source: string;
  source_ref: string | null;
  schema: { title: string | null; fields: unknown[] };
}

function FormCard({ jobId, onPrepare }: { jobId: string; onPrepare: () => void }) {
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

  async function readGreenhouse() {
    setError(null);
    try {
      setForm(await api<FormInfo>(`/jobs/${jobId}/form/greenhouse`, { method: "POST" }));
    } catch (e) {
      setError(e);
    }
  }

  async function attach() {
    setError(null);
    try {
      setForm(await api<FormInfo>(`/jobs/${jobId}/form`, { json: { fixture: pick } }));
    } catch (e) {
      setError(e);
    }
  }

  return (
    <Card title="Application form">
      <ErrorBox error={error} />
      {form === undefined ? (
        <Loading />
      ) : form === null ? (
        <div className="space-y-2 text-sm">
          <p>
            No form captured yet. Reading forms from live employer sites arrives later; for now you can attach a local test form
            (fictional employer) to try the preparation workflow.
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
          <Button variant="secondary" onClick={readGreenhouse}>
            Read Greenhouse form
          </Button>
        </div>
      ) : (
        <div className="space-y-3 text-sm">
          <p>
            Form v{form.version} · {form.schema.fields.length} questions · source: {form.source}
            {form.source === "fixture" && <> <Badge tone="amber">Local test fixture</Badge></>}
            {form.source === "greenhouse_api" && <> <Badge tone="amber">Greenhouse-style form (local test approximation)</Badge></>}
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
