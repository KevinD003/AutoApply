"use client";

import { cloneElement, isValidElement, ReactElement, ReactNode, useId } from "react";

/*
  Shared primitives for the pages not yet migrated to the premium src/ui kit.
  Restyled onto the NoEfforts design tokens (globals.css): same component APIs,
  structure, roles and text — only the classes change — so every page using these
  adopts the crafted look and dark mode at once, with no behavioural change.
*/

export function Card({ title, children, actions }: { title?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="rounded-[var(--r-lg)] border border-hairline bg-surface p-4 shadow-[var(--shadow-sm)] sm:p-5">
      {(title || actions) && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {title && <h2 className="text-base font-semibold tracking-tight text-ink">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <p role="status" className="py-6 text-center text-sm text-ink-muted">
      {label}
    </p>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-[var(--r-lg)] border border-dashed border-hairline-strong p-6 text-center text-sm text-ink-muted">{children}</p>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <p role="alert" className="rounded-[var(--r-md)] border border-[color:var(--danger)]/30 bg-danger-weak p-3 text-sm text-danger-ink">
      {msg}
    </p>
  );
}

export function Notice({ children }: { children: ReactNode }) {
  return (
    <p role="status" className="rounded-[var(--r-md)] border border-[color:var(--positive)]/25 bg-positive-weak p-3 text-sm text-positive-ink">
      {children}
    </p>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  // Associate the label with its control by id so its accessible name is exactly `label`.
  const id = useId();
  const hintId = `${id}-hint`;
  const control = isValidElement(children)
    ? cloneElement(children as ReactElement<{ id?: string; "aria-describedby"?: string }>, {
        id,
        "aria-describedby": hint ? hintId : undefined,
      })
    : children;
  return (
    <div className="block text-sm">
      <label htmlFor={id} className="mb-1 block font-medium text-ink">
        {label}
      </label>
      {control}
      {hint && (
        <span id={hintId} className="mt-1 block text-xs text-ink-muted">
          {hint}
        </span>
      )}
    </div>
  );
}

export const inputCls =
  "w-full rounded-[var(--r-md)] border border-hairline-strong bg-surface px-3 py-2 text-base text-ink placeholder:text-ink-faint focus-ring focus:border-brand sm:text-sm";

export function Button({
  children,
  variant = "primary",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }) {
  const styles = {
    primary: "brand-grad text-brand-contrast shadow-[var(--shadow-sm)] hover:brightness-[1.06] disabled:opacity-50",
    secondary: "border border-hairline-strong bg-surface text-ink hover:bg-surface-3 disabled:opacity-50",
    danger: "border border-danger/40 bg-danger-weak text-danger-ink hover:brightness-[1.03] disabled:opacity-50",
  }[variant];
  return (
    <button
      {...props}
      className={`focus-ring min-h-10 rounded-[var(--r-md)] px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed ${styles} ${props.className ?? ""}`}
    >
      {children}
    </button>
  );
}

export function Badge({ children, tone = "slate" }: { children: ReactNode; tone?: "slate" | "green" | "amber" | "red" | "indigo" }) {
  const t = {
    slate: "bg-surface-3 text-ink-muted",
    green: "bg-positive-weak text-positive-ink",
    amber: "bg-caution-weak text-caution-ink",
    red: "bg-danger-weak text-danger-ink",
    indigo: "bg-brand-weak text-brand",
  }[tone];
  return <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${t}`}>{children}</span>;
}

export function TriSelect({ value, onChange, id }: { value: string; onChange: (v: string) => void; id?: string }) {
  return (
    <select id={id} className={inputCls} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="unknown">Not answered yet</option>
      <option value="yes">Yes</option>
      <option value="no">No</option>
      <option value="not_applicable">Not applicable</option>
    </select>
  );
}

export function splitList(s: string): string[] {
  return s
    .split(/[\n,]/)
    .map((x) => x.trim())
    .filter(Boolean);
}

/** A source's credit: a link to its own page for the listing when there is one, else the text. */
export function Credit({ a }: { a: { text: string; url: string | null } }) {
  return a.url ? (
    <a className="text-xs text-ink-muted underline" href={a.url} target="_blank" rel="noopener noreferrer nofollow">
      {a.text}
    </a>
  ) : (
    <span className="text-xs text-ink-muted">{a.text}</span>
  );
}
