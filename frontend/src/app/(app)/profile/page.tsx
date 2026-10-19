"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { Badge, Button, Card, Empty, ErrorBox, Field, inputCls, Loading, Notice, splitList, TriSelect } from "@/components/ui";
import { api, TriState } from "@/lib/api";

interface Meta {
  id: string;
  version: number;
  approval_status: string;
  provenance: string;
  updated_at: string;
}
interface Profile extends Partial<Meta> {
  full_name: string | null;
  given_name: string | null;
  family_name: string | null;
  preferred_name: string | null;
  contact_email: string | null;
  phone: string | null;
  residence_country: string | null;
  residence_region: string | null;
  residence_city: string | null;
  links: string[];
  skills: string[];
  summary: string | null;
}
interface WorkAuth extends Meta {
  country_code: string;
  authorized: TriState;
  sponsorship_needed_now: TriState;
  sponsorship_needed_future: TriState;
}
interface Employment extends Meta {
  employer: string;
  title: string;
  location: string | null;
  start_date: string | null;
  end_date: string | null;
  is_current: boolean;
  description: string | null;
}
interface Education extends Meta {
  institution: string;
  degree: string | null;
  field_of_study: string | null;
  start_date: string | null;
  end_date: string | null;
}

const EMPTY: Profile = {
  full_name: "", given_name: "", family_name: "", preferred_name: "", contact_email: "", phone: "", residence_country: "", residence_region: "", residence_city: "",
  links: [], skills: [], summary: "",
};

function MetaLine({ m }: { m?: Partial<Meta> }) {
  if (!m?.version) return null;
  return (
    <p className="text-xs text-slate-500">
      Version {m.version} · {m.provenance?.replace("_", " ")} · updated {new Date(m.updated_at!).toLocaleString()}{" "}
      <Badge tone={m.approval_status === "approved" ? "green" : "amber"}>{m.approval_status}</Badge>
    </p>
  );
}

export default function ProfilePage() {
  return (
    <>
      <h1 className="text-xl font-semibold">Your profile</h1>
      <p className="text-sm text-slate-600">
        These are facts about you. They are used to answer application questions exactly as written here. Anything you leave blank stays
        unanswered — NoEfforts will ask you rather than guess.
      </p>
      <ContactCard />
      <WorkAuthCard />
      <EmploymentCard />
      <EducationCard />
    </>
  );
}

function ContactCard() {
  const [p, setP] = useState<Profile | null>(null);
  const [skills, setSkills] = useState("");
  const [links, setLinks] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api<Profile | null>("/profile")
      .then((r) => {
        const v = r ?? EMPTY;
        setP(v);
        setSkills(v.skills.join(", "));
        setLinks(v.links.join("\n"));
      })
      .catch(setError);
  }, []);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!p) return;
    setError(null);
    setSaved(false);
    const nullify = (v: string | null) => (v && v.trim() ? v.trim() : null);
    try {
      const r = await api<Profile>("/profile", {
        method: "PUT",
        json: {
          full_name: nullify(p.full_name), given_name: nullify(p.given_name),
          family_name: nullify(p.family_name), preferred_name: nullify(p.preferred_name),
          contact_email: nullify(p.contact_email), phone: nullify(p.phone),
          residence_country: nullify(p.residence_country), residence_region: nullify(p.residence_region),
          residence_city: nullify(p.residence_city), summary: nullify(p.summary),
          skills: splitList(skills), links: splitList(links),
        },
      });
      setP(r);
      setSaved(true);
    } catch (err) {
      setError(err);
    }
  }

  if (!p) return <Card title="Contact and residence"><ErrorBox error={error} /><Loading /></Card>;
  const set = (k: keyof Profile) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setP({ ...p, [k]: e.target.value });
  return (
    <Card title="Contact and residence">
      <MetaLine m={p} />
      <form onSubmit={save} className="mt-3 grid gap-3 sm:grid-cols-2">
        <Field label="Full name"><input className={inputCls} value={p.full_name ?? ""} onChange={set("full_name")} autoComplete="name" /></Field>
        <Field label="First (given) name" hint="Kept separate: NoEfforts never splits your full name."><input className={inputCls} value={p.given_name ?? ""} onChange={set("given_name")} autoComplete="given-name" /></Field>
        <Field label="Last (family) name"><input className={inputCls} value={p.family_name ?? ""} onChange={set("family_name")} autoComplete="family-name" /></Field>
        <Field label="Preferred name (optional)"><input className={inputCls} value={p.preferred_name ?? ""} onChange={set("preferred_name")} /></Field>
        <Field label="Contact email"><input className={inputCls} type="email" value={p.contact_email ?? ""} onChange={set("contact_email")} autoComplete="email" /></Field>
        <Field label="Phone"><input className={inputCls} type="tel" value={p.phone ?? ""} onChange={set("phone")} autoComplete="tel" /></Field>
        <Field label="Country you currently live in" hint="Two-letter code, e.g. US, GB, IN. Leave blank if you prefer not to say.">
          <input className={inputCls} maxLength={2} value={p.residence_country ?? ""} onChange={set("residence_country")} />
        </Field>
        <Field label="State / region"><input className={inputCls} value={p.residence_region ?? ""} onChange={set("residence_region")} /></Field>
        <Field label="City"><input className={inputCls} value={p.residence_city ?? ""} onChange={set("residence_city")} /></Field>
        <Field label="Skills" hint="Comma-separated."><input className={inputCls} value={skills} onChange={(e) => setSkills(e.target.value)} /></Field>
        <Field label="Links" hint="One per line (portfolio, LinkedIn…)."><textarea className={inputCls} rows={2} value={links} onChange={(e) => setLinks(e.target.value)} /></Field>
        <div className="sm:col-span-2">
          <Field label="Professional summary"><textarea className={inputCls} rows={3} value={p.summary ?? ""} onChange={set("summary")} /></Field>
        </div>
        <div className="space-y-2 sm:col-span-2">
          <ErrorBox error={error} />
          {saved && <Notice>Saved.</Notice>}
          <Button type="submit">Save</Button>
        </div>
      </form>
    </Card>
  );
}

function useList<T>(path: string) {
  const [items, setItems] = useState<T[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(() => {
    api<T[]>(path).then(setItems).catch((e) => {
      setError(e);
      setItems([]);
    });
  }, [path]);
  useEffect(load, [load]);
  return { items, error, setError, load };
}

function WorkAuthCard() {
  const { items, error, setError, load } = useList<WorkAuth>("/profile/work-authorizations");
  const [form, setForm] = useState({ country_code: "", authorized: "unknown", sponsorship_needed_now: "unknown", sponsorship_needed_future: "unknown" });

  async function add(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api("/profile/work-authorizations", { json: form });
      setForm({ country_code: "", authorized: "unknown", sponsorship_needed_now: "unknown", sponsorship_needed_future: "unknown" });
      load();
    } catch (err) {
      setError(err);
    }
  }

  async function update(w: WorkAuth, patch: Partial<WorkAuth>) {
    setError(null);
    try {
      const { country_code, authorized, sponsorship_needed_now, sponsorship_needed_future } = { ...w, ...patch };
      await api(`/profile/work-authorizations/${w.id}`, {
        method: "PUT",
        json: { country_code, authorized, sponsorship_needed_now, sponsorship_needed_future },
      });
      load();
    } catch (err) {
      setError(err);
    }
  }

  const label = (t: string) => ({ yes: "Yes", no: "No", unknown: "Not answered", not_applicable: "N/A" })[t] ?? t;

  return (
    <Card title="Work authorization and sponsorship">
      <p className="mb-3 text-sm text-slate-600">
        Answer per country. “Authorized to work” and “needs sponsorship” are separate questions, and sponsorship now and in the future are
        asked separately too.
      </p>
      <ErrorBox error={error} />
      {items === null ? (
        <Loading />
      ) : items.length === 0 ? (
        <Empty>No countries yet.</Empty>
      ) : (
        <div className="space-y-3">
          {items.map((w) => (
            <div key={w.id} className="rounded-lg border border-slate-200 p-3">
              <p className="mb-2 font-medium">{w.country_code}</p>
              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="Authorized to work"><TriSelect value={w.authorized} onChange={(v) => update(w, { authorized: v as TriState })} /></Field>
                <Field label="Needs sponsorship now"><TriSelect value={w.sponsorship_needed_now} onChange={(v) => update(w, { sponsorship_needed_now: v as TriState })} /></Field>
                <Field label="Will need sponsorship later"><TriSelect value={w.sponsorship_needed_future} onChange={(v) => update(w, { sponsorship_needed_future: v as TriState })} /></Field>
              </div>
              <p className="mt-2 text-xs text-slate-500">
                Summary: authorized {label(w.authorized)}, sponsorship now {label(w.sponsorship_needed_now)}, later {label(w.sponsorship_needed_future)} · v{w.version}
              </p>
            </div>
          ))}
        </div>
      )}
      <form onSubmit={add} className="mt-4 grid gap-3 border-t border-slate-100 pt-4 sm:grid-cols-4">
        <Field label="Country code"><input className={inputCls} required maxLength={2} value={form.country_code} onChange={(e) => setForm({ ...form, country_code: e.target.value })} placeholder="US" /></Field>
        <Field label="Authorized"><TriSelect value={form.authorized} onChange={(v) => setForm({ ...form, authorized: v })} /></Field>
        <Field label="Sponsorship now"><TriSelect value={form.sponsorship_needed_now} onChange={(v) => setForm({ ...form, sponsorship_needed_now: v })} /></Field>
        <Field label="Sponsorship later"><TriSelect value={form.sponsorship_needed_future} onChange={(v) => setForm({ ...form, sponsorship_needed_future: v })} /></Field>
        <div className="sm:col-span-4"><Button type="submit">Add country</Button></div>
      </form>
    </Card>
  );
}

function EmploymentCard() {
  const { items, error, setError, load } = useList<Employment>("/profile/employment");
  const blank = { employer: "", title: "", location: "", start_date: "", end_date: "", is_current: false, description: "" };
  const [form, setForm] = useState(blank);

  async function add(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api("/profile/employment", {
        json: { ...form, location: form.location || null, start_date: form.start_date || null, end_date: form.is_current ? null : form.end_date || null, description: form.description || null },
      });
      setForm(blank);
      load();
    } catch (err) {
      setError(err);
    }
  }

  async function remove(id: string) {
    await api(`/profile/employment/${id}`, { method: "DELETE" }).catch(setError);
    load();
  }

  return (
    <Card title="Work history">
      <ErrorBox error={error} />
      {items === null ? <Loading /> : items.length === 0 ? <Empty>No positions yet.</Empty> : (
        <ul className="divide-y divide-slate-100">
          {items.map((j) => (
            <li key={j.id} className="flex items-start justify-between gap-3 py-2 text-sm">
              <div>
                <p className="font-medium">{j.title} — {j.employer}</p>
                <p className="text-slate-600">{j.start_date ?? "?"} → {j.is_current ? "present" : j.end_date ?? "?"}{j.location ? ` · ${j.location}` : ""}</p>
              </div>
              <Button variant="danger" className="!min-h-8 !px-2 !py-1" onClick={() => remove(j.id)}>Remove</Button>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={add} className="mt-4 grid gap-3 border-t border-slate-100 pt-4 sm:grid-cols-2">
        <Field label="Job title"><input className={inputCls} required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
        <Field label="Employer"><input className={inputCls} required value={form.employer} onChange={(e) => setForm({ ...form, employer: e.target.value })} /></Field>
        <Field label="Start date"><input className={inputCls} type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></Field>
        <Field label="End date"><input className={inputCls} type="date" disabled={form.is_current} value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></Field>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.is_current} onChange={(e) => setForm({ ...form, is_current: e.target.checked })} /> I currently work here</label>
        <Field label="Location"><input className={inputCls} value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></Field>
        <div className="sm:col-span-2"><Field label="What you did" hint="Facts only — tailoring later may rephrase these but never adds new claims."><textarea className={inputCls} rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field></div>
        <div className="sm:col-span-2"><Button type="submit">Add position</Button></div>
      </form>
    </Card>
  );
}

function EducationCard() {
  const { items, error, setError, load } = useList<Education>("/profile/education");
  const blank = { institution: "", degree: "", field_of_study: "", start_date: "", end_date: "", completed: "unknown" };
  const [form, setForm] = useState(blank);

  async function add(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api("/profile/education", {
        json: { ...form, degree: form.degree || null, field_of_study: form.field_of_study || null, start_date: form.start_date || null, end_date: form.end_date || null },
      });
      setForm(blank);
      load();
    } catch (err) {
      setError(err);
    }
  }

  async function remove(id: string) {
    await api(`/profile/education/${id}`, { method: "DELETE" }).catch(setError);
    load();
  }

  return (
    <Card title="Education">
      <ErrorBox error={error} />
      {items === null ? <Loading /> : items.length === 0 ? <Empty>No education entries yet.</Empty> : (
        <ul className="divide-y divide-slate-100">
          {items.map((ed) => (
            <li key={ed.id} className="flex items-start justify-between gap-3 py-2 text-sm">
              <div>
                <p className="font-medium">{[ed.degree, ed.field_of_study].filter(Boolean).join(", ") || "Studies"} — {ed.institution}</p>
                <p className="text-slate-600">{ed.start_date ?? "?"} → {ed.end_date ?? "?"}</p>
              </div>
              <Button variant="danger" className="!min-h-8 !px-2 !py-1" onClick={() => remove(ed.id)}>Remove</Button>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={add} className="mt-4 grid gap-3 border-t border-slate-100 pt-4 sm:grid-cols-2">
        <Field label="Institution"><input className={inputCls} required value={form.institution} onChange={(e) => setForm({ ...form, institution: e.target.value })} /></Field>
        <Field label="Degree / qualification"><input className={inputCls} value={form.degree} onChange={(e) => setForm({ ...form, degree: e.target.value })} /></Field>
        <Field label="Field of study"><input className={inputCls} value={form.field_of_study} onChange={(e) => setForm({ ...form, field_of_study: e.target.value })} /></Field>
        <Field label="Completed?"><TriSelect value={form.completed} onChange={(v) => setForm({ ...form, completed: v })} /></Field>
        <Field label="Start date"><input className={inputCls} type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></Field>
        <Field label="End date"><input className={inputCls} type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></Field>
        <div className="sm:col-span-2"><Button type="submit">Add education</Button></div>
      </form>
    </Card>
  );
}
