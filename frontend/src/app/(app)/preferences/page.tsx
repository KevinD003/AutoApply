"use client";

import { FormEvent, useEffect, useState } from "react";

import { Button, Card, ErrorBox, Field, inputCls, Loading, Notice, splitList, TriSelect } from "@/components/ui";
import { api } from "@/lib/api";

interface Prefs {
  titles: string[];
  fields: string[];
  industries: string[];
  seniority: string[];
  employment_types: string[];
  work_modes: string[];
  excluded_employers: string[];
  target_locations: { city: string | null; region: string | null; country: string | null }[];
  willing_to_relocate: string;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  salary_period: string | null;
}

const LISTS = [
  ["titles", "Job titles", "e.g. Registered Nurse, Sous Chef, Data Analyst"],
  ["fields", "Fields", ""],
  ["industries", "Industries", ""],
  ["seniority", "Seniority", "e.g. entry, mid, senior"],
  ["employment_types", "Employment types", "e.g. full-time, part-time, contract"],
  ["excluded_employers", "Employers to exclude", "Jobs from these employers are marked excluded on import."],
] as const;

export default function PreferencesPage() {
  const [p, setP] = useState<Prefs | null>(null);
  const [text, setText] = useState<Record<string, string>>({});
  const [locs, setLocs] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api<Prefs>("/profile/preferences")
      .then((r) => {
        setP(r);
        setText(Object.fromEntries(LISTS.map(([k]) => [k, (r[k] as string[]).join(", ")])));
        setLocs(r.target_locations.map((l) => [l.city, l.region, l.country].filter(Boolean).join(", ")).join("\n"));
      })
      .catch(setError);
  }, []);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!p) return;
    setError(null);
    setSaved(false);
    // Each line: "City, Region, CC" — a trailing 2-letter token is treated as the country code.
    const target_locations = locs
      .split("\n")
      .map((l) => l.split(",").map((x) => x.trim()).filter(Boolean))
      .filter((parts) => parts.length)
      .map((parts) => {
        const country = parts.length > 1 && /^[A-Za-z]{2}$/.test(parts[parts.length - 1]) ? parts.pop()!.toUpperCase() : null;
        return { city: parts[0] ?? null, region: parts[1] ?? null, country };
      });
    try {
      const body = {
        ...p,
        ...Object.fromEntries(LISTS.map(([k]) => [k, splitList(text[k] ?? "")])),
        target_locations,
        salary_min: p.salary_min || null,
        salary_max: p.salary_max || null,
        salary_currency: p.salary_currency || null,
        salary_period: p.salary_period || null,
      };
      delete (body as Record<string, unknown>).updated_at;
      setP(await api<Prefs>("/profile/preferences", { method: "PUT", json: body }));
      setSaved(true);
    } catch (err) {
      setError(err);
    }
  }

  if (!p) return <><ErrorBox error={error} /><Loading /></>;

  const toggleMode = (m: string) =>
    setP({ ...p, work_modes: p.work_modes.includes(m) ? p.work_modes.filter((x) => x !== m) : [...p.work_modes, m] });

  return (
    <>
      <h1 className="text-xl font-semibold">Job preferences</h1>
      <p className="text-sm text-slate-600">What you are looking for. These guide matching only — they never change the factual answers in your profile.</p>
      <form onSubmit={save} className="space-y-4">
        <Card title="Roles">
          <div className="grid gap-3 sm:grid-cols-2">
            {LISTS.map(([k, label, hint]) => (
              <Field key={k} label={label} hint={hint || "Comma-separated."}>
                <input className={inputCls} value={text[k] ?? ""} onChange={(e) => setText({ ...text, [k]: e.target.value })} />
              </Field>
            ))}
          </div>
        </Card>
        <Card title="Where and how">
          <fieldset className="mb-3">
            <legend className="mb-1 text-sm font-medium text-slate-700">Work modes you accept</legend>
            <div className="flex flex-wrap gap-4 text-sm">
              {["remote", "hybrid", "onsite"].map((m) => (
                <label key={m} className="flex items-center gap-2">
                  <input type="checkbox" checked={p.work_modes.includes(m)} onChange={() => toggleMode(m)} /> {m}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Target locations" hint="One per line: City, Region, Country code (e.g. Austin, TX, US). These are targets, not where you live.">
              <textarea className={inputCls} rows={3} value={locs} onChange={(e) => setLocs(e.target.value)} />
            </Field>
            <Field label="Willing to relocate?">
              <TriSelect value={p.willing_to_relocate} onChange={(v) => setP({ ...p, willing_to_relocate: v })} />
            </Field>
          </div>
        </Card>
        <Card title="Compensation">
          <div className="grid gap-3 sm:grid-cols-4">
            <Field label="Minimum"><input className={inputCls} type="number" min={0} value={p.salary_min ?? ""} onChange={(e) => setP({ ...p, salary_min: e.target.value ? Number(e.target.value) : null })} /></Field>
            <Field label="Maximum"><input className={inputCls} type="number" min={0} value={p.salary_max ?? ""} onChange={(e) => setP({ ...p, salary_max: e.target.value ? Number(e.target.value) : null })} /></Field>
            <Field label="Currency" hint="e.g. USD, EUR, INR"><input className={inputCls} maxLength={3} value={p.salary_currency ?? ""} onChange={(e) => setP({ ...p, salary_currency: e.target.value.toUpperCase() })} /></Field>
            <Field label="Per">
              <select className={inputCls} value={p.salary_period ?? ""} onChange={(e) => setP({ ...p, salary_period: e.target.value || null })}>
                <option value="">—</option>
                {["hour", "day", "week", "month", "year"].map((x) => <option key={x} value={x}>{x}</option>)}
              </select>
            </Field>
          </div>
        </Card>
        <ErrorBox error={error} />
        {saved && <Notice>Preferences saved.</Notice>}
        <Button type="submit">Save preferences</Button>
      </form>
    </>
  );
}
