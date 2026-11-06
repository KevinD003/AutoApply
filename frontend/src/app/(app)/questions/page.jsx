"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import AnswerInput from "@/components/AnswerInput";
import { Badge, Button, Card, Empty, ErrorBox, Loading, Notice } from "@/components/ui";
import { api, NOTIFICATIONS_CHANGED } from "@/lib/api";

// D132: every question your applications leave to you, on one page, and the forms that changed
// under an attempt. Answering here is the same as on the application's own page (and you choose
// whether an answer is saved for reuse); approving and submitting stay on that page.
const CATEGORY = {
  answer: { label: "Your answer", tone: "amber" },
  consent: { label: "Your choice", tone: "indigo" },
  document: { label: "Choose a document", tone: "indigo" },
  profile: { label: "From your profile", tone: "slate" },
  technical: { label: "Apply on the employer's site", tone: "red" },
};

function PauseCard({ item, busy, onRecapture, onDismiss }) {
  const p = item.pause;
  const counts = [
    p.counts.new && `${p.counts.new} new`,
    p.counts.changed && `${p.counts.changed} changed`,
    p.counts.missing && `${p.counts.missing} gone`,
  ].filter(Boolean);
  return (
    <div role="status" className="rounded-[var(--r-md)] border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100">
      <p className="font-medium">The employer&apos;s form no longer matches what you approved.</p>
      <p className="mt-1">
        NoEfforts stopped before sending anything. {counts.length > 0 && `(${counts.join(", ")} question(s).)`} Nothing can be approved or sent
        until you read the form again or try this version again.
      </p>
      {p.status === "unexplained" ? (
        <p className="mt-2">
          Reading the form again showed no difference NoEfforts can see (the page&apos;s own scripts may add it). Try this version again
          (the page is checked again before anything is entered), or apply on the employer&apos;s site.
        </p>
      ) : item.recapture_available ? (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Button disabled={busy} onClick={onRecapture}>
            Read the form again
          </Button>
          <span className="text-xs">Reads the employer&apos;s form as it is now; nothing is sent.</span>
        </div>
      ) : (
        <p className="mt-2">
          This form was attached by you, so NoEfforts cannot read it again. Try this version again, or apply on the employer&apos;s site.
        </p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Button variant="secondary" disabled={busy} onClick={onDismiss}>
          Try this version again
        </Button>
        <span className="text-xs">Lets you approve it again; the page is checked again before anything is entered.</span>
      </div>
    </div>
  );
}

function QuestionRow({ item, q, busy, onSave }) {
  const c = CATEGORY[q.category] ?? CATEGORY.technical;
  return (
    <li className="space-y-2 rounded-[var(--r-md)] border border-hairline p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-ink">{q.label}</span>
        {q.required && <Badge tone="amber">Required</Badge>}
        <Badge tone={c.tone}>{c.label}</Badge>
      </div>
      {q.help_text && <p className="text-xs text-ink-muted">{q.help_text}</p>}
      {q.explanation && <p className="text-sm text-ink-muted">{q.explanation}</p>}
      {q.category === "answer" ? (
        <AnswerInput
          key={`${item.application_id}-${q.key}-${item.package.version}`}
          q={q}
          busy={busy}
          offerReuse={!q.sensitive}
          onSave={onSave}
        />
      ) : (
        <p className="text-sm">
          <Link className="text-brand underline" href={`/applications/${item.application_id}`}>
            {q.category === "profile"
              ? "Open the application (the fact is answered in your profile)"
              : q.category === "document"
                ? "Choose the document on the application's page"
                : "Decide on the application's page"}
          </Link>
        </p>
      )}
    </li>
  );
}

export default function QuestionsPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api("/questions")
      .then(setData)
      .catch(setError);
  }, []);
  useEffect(load, [load]);

  async function run(fn, done) {
    setBusy(true);
    setError(null);
    setNotice("");
    try {
      const out = await fn();
      setNotice(done(out));
      window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED));
      load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const recapture = (appId) =>
    run(
      () => api(`/applications/${appId}/form/recapture`, { method: "POST" }),
      // What happened to the pause decides the notice, not whether a new version was stored:
      // a newer form may already have been stored, and a reverted one is a new version too.
      (out) =>
        out.pause?.status === "resolved"
          ? "The form was read again: answer what is new below, then approve on the application's page."
          : out.pause?.status === "unexplained"
            ? "The form was read again and showed no difference NoEfforts can see."
            : "The form was read again; it has not changed.",
    );
  const dismiss = (appId) =>
    run(
      () => api(`/applications/${appId}/pause/dismiss`, { method: "POST" }),
      () => "You can approve this version again on the application's page; nothing was sent.",
    );
  const save = (appId, key) => (value, save_to_bank = false) =>
    run(
      () => api(`/applications/${appId}/answers`, { method: "PUT", json: { key, value, save_to_bank } }),
      () => (save_to_bank ? "Answer saved, and kept for this exact question next time." : "Answer saved for this application."),
    );

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Questions needing your answer</h1>
        <p className="text-sm text-ink-muted">
          What your applications leave to you, in one place. NoEfforts never guesses these: answer here, and approve each application on its own
          page. Nothing is sent from this page.
        </p>
      </header>
      <ErrorBox error={error} />
      {notice && <Notice>{notice}</Notice>}
      {!data ? (
        <Loading />
      ) : data.items.length === 0 ? (
        <Empty>No questions are waiting for you.</Empty>
      ) : (
        data.items.map((item) => (
          <Card
            key={item.application_id}
            title={`${item.title ?? "Untitled job"}${item.employer ? ` — ${item.employer}` : ""}`}
            actions={
              <Link className="text-sm text-brand underline" href={`/applications/${item.application_id}`}>
                Review and approve
              </Link>
            }
          >
            <div className="space-y-3">
              {item.pause && (
                <PauseCard
                  item={item}
                  busy={busy}
                  onRecapture={() => recapture(item.application_id)}
                  onDismiss={() => dismiss(item.application_id)}
                />
              )}
              {item.questions.length > 0 && (
                <ul className="space-y-2" aria-label="Open questions">
                  {item.questions.map((q) => (
                    <QuestionRow key={q.key} item={item} q={q} busy={busy} onSave={save(item.application_id, q.key)} />
                  ))}
                </ul>
              )}
            </div>
          </Card>
        ))
      )}
    </div>
  );
}
