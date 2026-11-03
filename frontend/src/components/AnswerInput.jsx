"use client";

import { useState } from "react";

import { Button, inputCls } from "./ui";

/** Builds the canonical answer value for a question from a type-appropriate control.
 * offerReuse shows "Reuse for this exact question" (only where the caller sends save_to_bank). */
export default function AnswerInput({ q, onSave, busy, offerReuse = false }) {
  const current = q.value ?? {};
  const [text, setText] = useState(
    current.text ?? current.date ?? (current.number !== undefined ? String(current.number) : ""),
  );
  const [choice, setChoice] = useState(current.label ?? "");
  const [multi, setMulti] = useState((current.options ?? []).map((o) => o.label));
  // D115: remembered by default where reuse is allowed (untick to keep it to this application).
  const [bank, setBank] = useState(offerReuse && q.bankable);
  const id = `in-${q.key}`;

  function build() {
    switch (q.type) {
      case "radio":
      case "select":
        return choice ? { label: choice } : null;
      case "checkbox_group":
      case "multiselect":
        return multi.length ? { labels: multi } : null;
      case "number":
        return text ? { number: Number(text) } : null;
      case "date":
        return text ? { date: text } : null;
      default:
        return text.trim() ? { text } : null;
    }
  }

  let control;
  if (q.type === "radio" || q.type === "select") {
    control = (
      <select id={id} aria-label={q.label} className={inputCls} value={choice} onChange={(e) => setChoice(e.target.value)}>
        <option value="">Choose…</option>
        {q.options.map((o) => (
          <option key={o.value} value={o.label}>
            {o.label}
          </option>
        ))}
      </select>
    );
  } else if (q.type === "checkbox_group" || q.type === "multiselect") {
    control = (
      <fieldset aria-label={q.label} className="flex flex-wrap gap-3 text-sm">
        {q.options.map((o) => (
          <label key={o.value} className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={multi.includes(o.label)}
              onChange={(e) => setMulti(e.target.checked ? [...multi, o.label] : multi.filter((x) => x !== o.label))}
            />
            {o.label}
          </label>
        ))}
      </fieldset>
    );
  } else if (q.type === "textarea") {
    control = (
      <div>
        <textarea id={id} aria-label={q.label} className={inputCls} rows={4} value={text} maxLength={q.max_length ?? undefined} onChange={(e) => setText(e.target.value)} />
        {q.max_length && (
          <p className="text-right text-xs text-ink-faint">
            {text.length}/{q.max_length}
          </p>
        )}
      </div>
    );
  } else {
    const type = { number: "number", date: "date", email: "email", tel: "tel", url: "url" }[q.type] ?? "text";
    control = <input id={id} aria-label={q.label} className={inputCls} type={type} value={text} onChange={(e) => setText(e.target.value)} />;
  }

  const value = build();
  return (
    <div className="space-y-2">
      {control}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" disabled={!value || busy} onClick={() => value && onSave(value, bank)} className="!min-h-9 !py-1.5">
          Save answer
        </Button>
        {offerReuse && q.bankable && (
          <label className="flex items-center gap-2 text-sm text-ink-muted">
            <input type="checkbox" checked={bank} onChange={(e) => setBank(e.target.checked)} />
            Reuse for this exact question in future applications
          </label>
        )}
      </div>
    </div>
  );
}
