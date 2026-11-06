"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge, Button, Card, Empty, ErrorBox, Field, inputCls, Loading, Notice, splitList, TriSelect } from "@/components/ui";
import { api } from "@/lib/api";

/*
  Your profile (Slice C). Section navigation + a concise overview, then each section as a card:
  your saved records are shown as readable summaries; the "add" forms for Work history, Education
  and Licences are revealed on demand (not every empty form at once). The overview lists missing
  basics as actionable links — never a misleading "percent complete" score. Self-identification
  stays clearly optional and separately controlled, with its explanation tucked behind a
  disclosure so it never dominates the page. Facts are used exactly as written; anything blank
  stays unanswered.

  e2e contracts preserved: each section is a card whose heading names it (profile-edit locates
  "Work history"/"Licences and certifications"); records read "Title — Employer" / "Valid until …";
  per-record "Edit" opens the form with its field labels ("Job title", "Expires on") and a
  "Save changes" button; an "Add position" button is present once the form is closed; the Contact
  ("Full name"/"City"/"Save") and Work-authorization ("Country code"/"Add country") forms stay
  directly reachable (phase-a / phase-b / journey).
*/

const SECTIONS = [
  ["contact", "Contact"],
  ["work-auth", "Work authorization"],
  ["work-history", "Work history"],
  ["education", "Education"],
  ["licences", "Licences"],
  ["self-id", "Self-identification"],
  ["ai-drafting", "AI drafting"],
];

const EMPTY = {
  full_name: "", given_name: "", family_name: "", preferred_name: "", contact_email: "", phone: "", residence_country: "", residence_region: "", residence_city: "",
  links: [], skills: [], summary: "",
};

function MetaLine({ m }) {
  if (!m?.version) return null;
  return (
    <p className="text-xs text-ink-faint">
      Version {m.version} · {m.provenance?.replace("_", " ")} · updated {new Date(m.updated_at).toLocaleString()}{" "}
      <Badge tone={m.approval_status === "approved" ? "green" : "amber"}>{m.approval_status}</Badge>
    </p>
  );
}

export default function ProfilePage() {
  return (
    <>
      <h1 className="font-display text-[1.7rem] font-semibold leading-[1.1] text-ink">Your profile</h1>
      <OverviewCard />
      <div id="contact" className="scroll-mt-24">
        <ContactCard />
      </div>
      <div id="work-auth" className="scroll-mt-24">
        <WorkAuthCard />
      </div>
      <div id="work-history" className="scroll-mt-24">
        <EmploymentCard />
      </div>
      <div id="education" className="scroll-mt-24">
        <EducationCard />
      </div>
      <div id="licences" className="scroll-mt-24">
        <CredentialsCard />
      </div>
      <div id="self-id" className="scroll-mt-24">
        <SelfIdentificationCard />
      </div>
      <div id="ai-drafting" className="scroll-mt-24">
        <AiDraftingCard />
      </div>
    </>
  );
}

// A concise overview: a jump-nav to each section. Presentational only (no fetches of its own —
// each section loads and shows its own saved records and empty state), so landing on the profile
// and navigating away from it stay light.
function OverviewCard() {
  return (
    <Card title="Overview">
      <p className="text-sm text-ink-muted">
        These are facts about you, used to answer application questions exactly as written here. Anything you leave blank stays
        unanswered — NoEfforts asks you rather than guessing. Jump to a section to add or edit it; each one shows what you have
        saved and what is still missing.
      </p>
      <nav aria-label="Section navigation" className="mt-3 flex flex-wrap gap-2">
        {SECTIONS.map(([id, label]) => (
          <a
            key={id}
            href={`#${id}`}
            className="focus-ring rounded-full border border-hairline-strong bg-surface px-3 py-1 text-xs font-medium text-ink-muted hover:bg-surface-3 hover:text-ink"
          >
            {label}
          </a>
        ))}
      </nav>
    </Card>
  );
}

function ContactCard() {
  const [p, setP] = useState(null);
  const [skills, setSkills] = useState("");
  const [links, setLinks] = useState("");
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api("/profile")
      .then((r) => {
        const v = r ?? EMPTY;
        setP(v);
        setSkills(v.skills.join(", "));
        setLinks(v.links.join("\n"));
      })
      .catch(setError);
  }, []);

  async function save(e) {
    e.preventDefault();
    if (!p) return;
    setError(null);
    setSaved(false);
    const nullify = (v) => (v && v.trim() ? v.trim() : null);
    try {
      const r = await api("/profile", {
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
  const set = (k) => (e) => setP({ ...p, [k]: e.target.value });
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

// L1 (D72): a fact proposed from your resume is used by nothing until you approve it here.
function Proposed({ m, path, onDone, onError }) {
  if (m.approval_status === "approved") return null;
  return (
    <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-caution-ink">
      <Badge tone="amber">{m.provenance === "resume_parse" ? "Proposed from your resume" : m.approval_status}</Badge>
      Not used until you approve it.
      <button
        className="text-brand underline"
        onClick={() => api(`${path}/${m.id}/approve`, { method: "POST" }).then(onDone).catch(onError)}
      >
        Approve
      </button>
    </p>
  );
}

function useList(path) {
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(() => {
    api(path).then(setItems).catch((e) => {
      setError(e);
      setItems([]);
    });
  }, [path]);
  useEffect(load, [load]);
  return { items, error, setError, load };
}

function WorkAuthCard() {
  const { items, error, setError, load } = useList("/profile/work-authorizations");
  const [form, setForm] = useState({ country_code: "", authorized: "unknown", sponsorship_needed_now: "unknown", sponsorship_needed_future: "unknown" });

  async function add(e) {
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

  async function update(w, patch) {
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

  const label = (t) => ({ yes: "Yes", no: "No", unknown: "Not answered", not_applicable: "N/A" })[t] ?? t;

  return (
    <Card title="Work authorization and sponsorship">
      <p className="mb-3 text-sm text-ink-muted">
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
            <div key={w.id} className="rounded-lg border border-hairline p-3">
              <p className="mb-2 font-medium">{w.country_code}</p>
              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="Authorized to work"><TriSelect value={w.authorized} onChange={(v) => update(w, { authorized: v })} /></Field>
                <Field label="Needs sponsorship now"><TriSelect value={w.sponsorship_needed_now} onChange={(v) => update(w, { sponsorship_needed_now: v })} /></Field>
                <Field label="Will need sponsorship later"><TriSelect value={w.sponsorship_needed_future} onChange={(v) => update(w, { sponsorship_needed_future: v })} /></Field>
              </div>
              <p className="mt-2 text-xs text-ink-faint">
                Summary: authorized {label(w.authorized)}, sponsorship now {label(w.sponsorship_needed_now)}, later {label(w.sponsorship_needed_future)} · v{w.version}
              </p>
            </div>
          ))}
        </div>
      )}
      <form onSubmit={add} className="mt-4 grid gap-3 border-t border-hairline pt-4 sm:grid-cols-4">
        <Field label="Country code"><input className={inputCls} required maxLength={2} value={form.country_code} onChange={(e) => setForm({ ...form, country_code: e.target.value })} placeholder="US" /></Field>
        <Field label="Authorized"><TriSelect value={form.authorized} onChange={(v) => setForm({ ...form, authorized: v })} /></Field>
        <Field label="Sponsorship now"><TriSelect value={form.sponsorship_needed_now} onChange={(v) => setForm({ ...form, sponsorship_needed_now: v })} /></Field>
        <Field label="Sponsorship later"><TriSelect value={form.sponsorship_needed_future} onChange={(v) => setForm({ ...form, sponsorship_needed_future: v })} /></Field>
        <div className="sm:col-span-4"><Button type="submit">Add country</Button></div>
      </form>
    </Card>
  );
}

// A list section whose "add" form is revealed on demand; records stay readable summaries with a
// per-record Edit that opens the same form. `editing` holds the id being edited; `adding` opens an
// empty form. The "Add …" trigger shows whenever the form is closed (profile-edit relies on this).
function useRecordForm(blank) {
  const [form, setForm] = useState(blank);
  const [editing, setEditing] = useState(null);
  const [adding, setAdding] = useState(false);
  const open = adding || editing !== null;
  const startAdd = () => { setForm(blank); setEditing(null); setAdding(true); };
  const startEdit = (values, id) => { setForm(values); setEditing(id); setAdding(false); };
  const close = () => { setForm(blank); setEditing(null); setAdding(false); };
  return { form, setForm, editing, open, startAdd, startEdit, close };
}

function EmploymentCard() {
  const { items, error, setError, load } = useList("/profile/employment");
  const blank = { employer: "", title: "", location: "", start_date: "", end_date: "", is_current: false, description: "" };
  const { form, setForm, editing, open, startAdd, startEdit, close } = useRecordForm(blank);

  async function submit(e) {
    e.preventDefault();
    setError(null);
    try {
      await api(editing ? `/profile/employment/${editing}` : "/profile/employment", {
        method: editing ? "PUT" : "POST",
        json: { ...form, location: form.location || null, start_date: form.start_date || null, end_date: form.is_current ? null : form.end_date || null, description: form.description || null },
      });
      close();
      load();
    } catch (err) {
      setError(err);
    }
  }

  async function remove(id) {
    await api(`/profile/employment/${id}`, { method: "DELETE" }).catch(setError);
    load();
  }

  return (
    <Card title="Work history">
      <ErrorBox error={error} />
      {items === null ? <Loading /> : items.length === 0 ? <Empty>No positions yet.</Empty> : (
        <ul className="divide-y divide-hairline">
          {items.map((j) => (
            <li key={j.id} className="flex items-start justify-between gap-3 py-2 text-sm">
              <div>
                <p className="font-medium">{j.title} — {j.employer}</p>
                <p className="text-ink-muted">{j.start_date ?? "?"} → {j.is_current ? "present" : j.end_date ?? "?"}{j.location ? ` · ${j.location}` : ""}</p>
                {j.description && <p className="whitespace-pre-wrap text-xs text-ink-muted">{j.description}</p>}
                <Proposed m={j} path="/profile/employment" onDone={load} onError={setError} />
              </div>
              <div className="flex shrink-0 gap-2">
                <Button variant="secondary" className="!min-h-8 !px-2 !py-1" onClick={() => startEdit({ employer: j.employer, title: j.title, location: j.location ?? "", start_date: j.start_date ?? "", end_date: j.end_date ?? "", is_current: j.is_current, description: j.description ?? "" }, j.id)}>Edit</Button>
                <Button variant="danger" className="!min-h-8 !px-2 !py-1" onClick={() => remove(j.id)}>Remove</Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {!open ? (
        <Button variant="secondary" className="mt-4" onClick={startAdd}>Add position</Button>
      ) : (
        <form onSubmit={submit} className="mt-4 grid gap-3 border-t border-hairline pt-4 sm:grid-cols-2">
          <Field label="Job title"><input className={inputCls} required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
          <Field label="Employer"><input className={inputCls} required value={form.employer} onChange={(e) => setForm({ ...form, employer: e.target.value })} /></Field>
          <Field label="Start date"><input className={inputCls} type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></Field>
          <Field label="End date"><input className={inputCls} type="date" disabled={form.is_current} value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.is_current} onChange={(e) => setForm({ ...form, is_current: e.target.checked })} /> I currently work here</label>
          <Field label="Location"><input className={inputCls} value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></Field>
          <div className="sm:col-span-2"><Field label="What you did" hint="Facts only — tailoring later may rephrase these but never adds new claims."><textarea className={inputCls} rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field></div>
          <div className="flex gap-2 sm:col-span-2">
            <Button type="submit">{editing ? "Save changes" : "Save"}</Button>
            <Button type="button" variant="secondary" onClick={close}>Cancel</Button>
          </div>
        </form>
      )}
    </Card>
  );
}

function EducationCard() {
  const { items, error, setError, load } = useList("/profile/education");
  const blank = { institution: "", degree: "", field_of_study: "", start_date: "", end_date: "", completed: "unknown" };
  const { form, setForm, editing, open, startAdd, startEdit, close } = useRecordForm(blank);

  async function submit(e) {
    e.preventDefault();
    setError(null);
    try {
      await api(editing ? `/profile/education/${editing}` : "/profile/education", {
        method: editing ? "PUT" : "POST",
        json: { ...form, degree: form.degree || null, field_of_study: form.field_of_study || null, start_date: form.start_date || null, end_date: form.end_date || null },
      });
      close();
      load();
    } catch (err) {
      setError(err);
    }
  }

  async function remove(id) {
    await api(`/profile/education/${id}`, { method: "DELETE" }).catch(setError);
    load();
  }

  return (
    <Card title="Education">
      <ErrorBox error={error} />
      {items === null ? <Loading /> : items.length === 0 ? <Empty>No education entries yet.</Empty> : (
        <ul className="divide-y divide-hairline">
          {items.map((ed) => (
            <li key={ed.id} className="flex items-start justify-between gap-3 py-2 text-sm">
              <div>
                <p className="font-medium">{[ed.degree, ed.field_of_study].filter(Boolean).join(", ") || "Studies"} — {ed.institution}</p>
                <p className="text-ink-muted">{ed.start_date ?? "?"} → {ed.end_date ?? "?"}</p>
                <Proposed m={ed} path="/profile/education" onDone={load} onError={setError} />
              </div>
              <div className="flex shrink-0 gap-2">
                <Button variant="secondary" className="!min-h-8 !px-2 !py-1" onClick={() => startEdit({ institution: ed.institution, degree: ed.degree ?? "", field_of_study: ed.field_of_study ?? "", start_date: ed.start_date ?? "", end_date: ed.end_date ?? "", completed: ed.completed }, ed.id)}>Edit</Button>
                <Button variant="danger" className="!min-h-8 !px-2 !py-1" onClick={() => remove(ed.id)}>Remove</Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {!open ? (
        <Button variant="secondary" className="mt-4" onClick={startAdd}>Add education</Button>
      ) : (
        <form onSubmit={submit} className="mt-4 grid gap-3 border-t border-hairline pt-4 sm:grid-cols-2">
          <Field label="Institution"><input className={inputCls} required value={form.institution} onChange={(e) => setForm({ ...form, institution: e.target.value })} /></Field>
          <Field label="Degree / qualification"><input className={inputCls} value={form.degree} onChange={(e) => setForm({ ...form, degree: e.target.value })} /></Field>
          <Field label="Field of study"><input className={inputCls} value={form.field_of_study} onChange={(e) => setForm({ ...form, field_of_study: e.target.value })} /></Field>
          <Field label="Completed?"><TriSelect value={form.completed} onChange={(v) => setForm({ ...form, completed: v })} /></Field>
          <Field label="Start date"><input className={inputCls} type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></Field>
          <Field label="End date"><input className={inputCls} type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></Field>
          <div className="flex gap-2 sm:col-span-2">
            <Button type="submit">{editing ? "Save changes" : "Save"}</Button>
            <Button type="button" variant="secondary" onClick={close}>Cancel</Button>
          </div>
        </form>
      )}
    </Card>
  );
}

// C16 (D69): credentials ground a draft only when approved and not expired.
function CredentialsCard() {
  const { items, error, setError, load } = useList("/profile/credentials");
  const blank = { name: "", issuer: "", issued_on: "", expires_on: "" };
  const { form, setForm, editing, open, startAdd, startEdit, close } = useRecordForm(blank);

  async function submit(e) {
    e.preventDefault();
    setError(null);
    try {
      await api(editing ? `/profile/credentials/${editing}` : "/profile/credentials", {
        method: editing ? "PUT" : "POST",
        json: { name: form.name, issuer: form.issuer || null, issued_on: form.issued_on || null, expires_on: form.expires_on || null },
      });
      close();
      load();
    } catch (err) {
      setError(err);
    }
  }

  async function remove(id) {
    await api(`/profile/credentials/${id}`, { method: "DELETE" }).catch(setError);
    load();
  }

  const today = new Date().toISOString().slice(0, 10);
  return (
    <Card title="Licences and certifications">
      <ErrorBox error={error} />
      {items === null ? <Loading /> : items.length === 0 ? <Empty>No licences or certifications yet.</Empty> : (
        <ul className="divide-y divide-hairline">
          {items.map((c) => (
            <li key={c.id} className="flex items-start justify-between gap-3 py-2 text-sm">
              <div>
                <p className="font-medium">{c.name}{c.issuer ? ` — ${c.issuer}` : ""}</p>
                <p className="text-ink-muted">
                  {c.expires_on ? (c.expires_on < today ? `Expired ${c.expires_on}: not used` : `Valid until ${c.expires_on}`) : "No expiry date"}
                </p>
                <Proposed m={c} path="/profile/credentials" onDone={load} onError={setError} />
              </div>
              <div className="flex shrink-0 gap-2">
                <Button variant="secondary" className="!min-h-8 !px-2 !py-1" onClick={() => startEdit({ name: c.name, issuer: c.issuer ?? "", issued_on: c.issued_on ?? "", expires_on: c.expires_on ?? "" }, c.id)}>Edit</Button>
                <Button variant="danger" className="!min-h-8 !px-2 !py-1" onClick={() => remove(c.id)}>Remove</Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {!open ? (
        <Button variant="secondary" className="mt-4" onClick={startAdd}>Add licence or certification</Button>
      ) : (
        <form onSubmit={submit} className="mt-4 grid gap-3 border-t border-hairline pt-4 sm:grid-cols-2">
          <Field label="Licence or certification"><input className={inputCls} required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label="Issued by"><input className={inputCls} value={form.issuer} onChange={(e) => setForm({ ...form, issuer: e.target.value })} /></Field>
          <Field label="Issued on"><input className={inputCls} type="date" value={form.issued_on} onChange={(e) => setForm({ ...form, issued_on: e.target.value })} /></Field>
          <Field label="Expires on"><input className={inputCls} type="date" value={form.expires_on} onChange={(e) => setForm({ ...form, expires_on: e.target.value })} /></Field>
          <div className="flex gap-2 sm:col-span-2">
            <Button type="submit">{editing ? "Save changes" : "Save"}</Button>
            <Button type="button" variant="secondary" onClick={close}>Cancel</Button>
          </div>
        </form>
      )}
    </Card>
  );
}

function SelfIdentificationCard() {
  const [enabled, setEnabled] = useState(false);
  const [text, setText] = useState("");
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState("");
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api("/profile/self-identification")
      .then((s) => {
        setEnabled(s.enabled);
        setText(s.labels.join("\n"));
        setLoaded(true);
      })
      .catch(setError);
  }, []);

  async function save(e) {
    e.preventDefault();
    setError(null);
    setNotice("");
    // One label per line: the standard labels contain commas ("Yes, I have a disability, or have
    // had one in the past"), and splitting them on commas would turn them into a bare "Yes".
    const labels = text
      .split("\n")
      .map((x) => x.trim())
      .filter(Boolean);
    try {
      const s = await api("/profile/self-identification", { method: "PUT", json: { enabled, labels } });
      setText(s.labels.join("\n"));
      setNotice("Saved.");
    } catch (err) {
      setError(err);
    }
  }

  return (
    <Card title="Self-identification (EEOC / demographic) — optional">
      <p className="text-sm text-ink-muted">
        Voluntary, and off unless you turn it on. Your answers are used only to fill an EEOC/demographic question from the exact option
        labels you list — never guessed, never saved for reuse, never used in drafts, never shared.
      </p>
      <details className="mt-2 text-sm text-ink-muted">
        <summary className="cursor-pointer text-brand underline">How it works</summary>
        <p className="mt-2">
          When on, an equal-opportunity question about gender or pronouns, race or ethnicity, Hispanic or Latino origin, protected-veteran
          status, disability, sexual orientation or transgender identity is answered from the exact option labels you list below — your own
          stated identity. A label is used only when it matches an option on the form exactly, and only an option that names its own
          category: a bare “Yes” or “No” answers no question, because nothing says which question it was meant for. Criminal history,
          health, accommodation, age and other personal questions are never answered from it: you answer those yourself. Anything it
          doesn’t match stays a question for you, and the form’s own decline option is always still available. A question that takes
          several answers (such as race/ethnicity) is left for you unless you choose to decline, so a partial answer is never sent. A
          per-application choice you make always overrides this.
        </p>
      </details>
      <ErrorBox error={error} />
      {!loaded ? (
        <Loading />
      ) : (
        <form onSubmit={save} className="mt-3 space-y-3">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            Fill my self-identification on applications automatically
          </label>
          <Field label="Your self-identification labels (one per line, exactly as forms word them)">
            <textarea
              className={inputCls}
              rows={5}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={"Male\nAsian\nI am not a protected veteran"}
            />
          </Field>
          <p className="text-xs text-ink-muted">
            A bare “Yes” or “No” names no category, so it never answers a question: use the full wording, such as “No, I do not have a
            disability and have not had one in the past”.
          </p>
          {notice && <Notice>{notice}</Notice>}
          <Button type="submit">Save self-identification</Button>
        </form>
      )}
    </Card>
  );
}

function AiDraftingCard() {
  const [v, setV] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(() => {
    api("/drafting/consent").then(setV).catch(setError);
  }, []);
  useEffect(load, [load]);

  async function change(on) {
    setError(null);
    try {
      setV(
        await api("/drafting/consent", on ? { method: "PUT", json: { version: v.consent.version } } : { method: "DELETE" }),
      );
    } catch (err) {
      setError(err);
    }
  }

  return (
    <Card title="AI drafting">
      <ErrorBox error={error} />
      {v === null ? (
        <Loading />
      ) : !v.offered ? (
        <p className="text-sm text-ink-muted">
          {v.status === "not_for_this_account" ? "AI drafting is not available for this account." : "AI drafting is not configured on this server."} You
          write long answers, resumes and cover letters yourself.
        </p>
      ) : (
        <div className="space-y-3 text-sm">
          <p>
            {v.given_at ? <Badge tone="green">On</Badge> : <Badge tone="amber">Off</Badge>} Drafts are written by {v.provider} ({v.model}).
          </p>
          {v.earlier_text && <p className="text-caution-ink">The wording below has changed since you agreed. AI drafting stays off until you agree again.</p>}
          <div>
            <p className="font-medium">Each request holds only:</p>
            <ul className="list-disc pl-5">{v.consent.sends.map((x) => <li key={x}>{x}</li>)}</ul>
          </div>
          <div>
            <p className="font-medium">It never holds:</p>
            <ul className="list-disc pl-5">{v.consent.never_sends.map((x) => <li key={x}>{x}</li>)}</ul>
          </div>
          <p className="rounded-lg border border-hairline bg-surface-2 p-3 text-ink-muted" aria-label="What you agree to">{v.consent.text}</p>
          {v.daily_budget_usd !== null && (
            <p className="text-xs text-ink-faint">
              Spent today on this server: ${v.spent_today_usd?.toFixed(2)} of ${v.daily_budget_usd.toFixed(2)}.
            </p>
          )}
          {v.given_at ? (
            <Button variant="secondary" onClick={() => change(false)}>Turn AI drafting off</Button>
          ) : (
            <Button onClick={() => change(true)}>I agree: turn AI drafting on</Button>
          )}
        </div>
      )}
    </Card>
  );
}
