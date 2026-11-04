"use client";

import { useState } from "react";

import { BrandMark, Wordmark } from "@/ui/BrandMark";
import { GlassNav } from "@/ui/GlassNav";
import { ThemeToggle } from "@/ui/ThemeToggle";
import { SwipeDeck } from "@/ui/SwipeDeck";
import { Banner, Button, Card, Pill, SectionTitle, StatusPill } from "@/ui/primitives";
import { IconBriefcase, IconCompass, IconMapPin, IconReview, IconTracker, IconUser } from "@/ui/icons";

/*
  Design preview / living styleguide (D124). Not linked from the app nav and not
  behind the auth shell, so it renders without the backend. All job data here is
  obviously synthetic placeholder content for layout only — never real postings or
  candidate data. This route exercises the real premium kit end-to-end (Tailwind
  tokens, the .jsx components, the swipe deck) so the owner can approve the look.
*/

const NAV = [
  { href: "/discover", label: "Discover", icon: IconCompass, tab: true },
  { href: "/jobs", label: "Jobs", icon: IconBriefcase, tab: true },
  { href: "/review", label: "Review", icon: IconReview, tab: true },
  { href: "/tracker", label: "Tracker", icon: IconTracker, tab: true },
  { href: "/profile", label: "Profile", icon: IconUser, tab: true },
];

// Synthetic placeholder postings (layout only). Route labels here are generic placeholders:
// the real route wording has one source (backend providers/wording.py) served through the API,
// and tests/test_support_wording.py forbids the frontend from writing any of its own.
const SAMPLE = [
  { id: "a", title: "Product Designer", employer: "Northwind Studio", location: "Remote · UK", tags: ["Figma", "Design systems", "Prototyping"], route: { label: "Direct apply", tone: "brand" } },
  { id: "b", title: "Frontend Engineer", employer: "Harbour Labs", location: "Hybrid · Berlin", tags: ["React", "TypeScript", "Accessibility"], route: { label: "Assisted apply", tone: "brand" } },
  { id: "c", title: "UX Researcher", employer: "Meadow Health", location: "On-site · Boston", tags: ["Interviews", "Synthesis"], route: { label: "Apply on employer site", tone: "neutral" } },
  { id: "d", title: "Design Engineer", employer: "Atlas Maps", location: "Remote · EU", tags: ["Motion", "CSS", "Design tokens"], route: { label: "Direct apply", tone: "brand" } },
];

const JOURNEY = [
  { label: "Preparing", tone: "neutral" },
  { label: "Needs your answers", tone: "caution" },
  { label: "Ready for your review", tone: "caution" },
  { label: "Rehearsal needed first", tone: "caution" },
  { label: "Awaiting confirmation", tone: "caution" },
  { label: "Submitted (employer receipt)", tone: "positive" },
];

function JobCardBody({ job }) {
  return (
    <div className="flex h-full flex-col">
      <div className="brand-grad relative h-28 shrink-0 p-4 text-white">
        <div className="flex items-center justify-between">
          <Pill className="bg-white/20 text-white">{job.route.label}</Pill>
          <BrandMark size={22} />
        </div>
      </div>
      <div className="flex flex-1 flex-col gap-3 p-5">
        <div>
          <h3 className="text-xl font-semibold tracking-tight text-ink">{job.title}</h3>
          <p className="mt-1 text-sm text-ink-muted">{job.employer}</p>
          <p className="mt-2 inline-flex items-center gap-1.5 text-sm text-ink-muted">
            <IconMapPin size={16} /> {job.location}
          </p>
        </div>
        <div className="mt-auto flex flex-wrap gap-1.5">
          {job.tags.map((t) => (
            <Pill key={t} tone="neutral">
              {t}
            </Pill>
          ))}
        </div>
        <p className="text-xs text-ink-faint">
          Swipe right to add it to your applications to prepare — this is not an application. Swipe left to pass.
        </p>
      </div>
    </div>
  );
}

export default function PreviewPage() {
  const [deck, setDeck] = useState(SAMPLE);
  const [history, setHistory] = useState([]); // { card, dir }

  function decide(card, dir) {
    setHistory((h) => [...h, { card, dir }]);
    setDeck((d) => d.filter((c) => c.id !== card.id));
  }
  function undo() {
    setHistory((h) => {
      if (!h.length) return h;
      const last = h[h.length - 1];
      setDeck((d) => [last.card, ...d]);
      return h.slice(0, -1);
    });
  }

  const applied = history.filter((h) => h.dir === "apply").length;
  const passed = history.filter((h) => h.dir === "pass").length;

  return (
    <div className="min-h-screen bg-app">
      <GlassNav
        pathname="/discover"
        items={NAV}
        unread={3}
        email="you@example.com"
        onSignOut={() => {}}
        themeToggle={<ThemeToggle />}
      />

      <main className="mx-auto max-w-6xl px-4 pb-28 pt-6 md:pb-10">
        {/* Hero */}
        <section className="mb-8 animate-rise">
          <div className="flex items-center gap-3">
            <Wordmark size={40} showText={false} />
            <div>
              <h1 className="text-2xl font-semibold tracking-tight text-ink">
                No<span className="text-grad">Efforts</span>
              </h1>
              <p className="text-sm text-ink-muted">Find roles, prepare honestly, stay in control.</p>
            </div>
          </div>
        </section>

        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_340px]">
          {/* Swipe discovery */}
          <section>
            <SectionTitle hint={`${applied} to apply · ${passed} passed`}>Discover</SectionTitle>
            <SwipeDeck
              cards={deck}
              renderCard={(job) => <JobCardBody job={job} />}
              onDecide={decide}
              onUndo={undo}
              canUndo={history.length > 0}
              applyLabel="Apply"
              passLabel="Pass"
              emptyState={
                <Card>
                  <p className="py-10 text-center text-sm text-ink-muted">
                    That&apos;s everyone for now. Passed roles stay in your Passed collection.
                  </p>
                </Card>
              }
            />
          </section>

          {/* Styleguide rail */}
          <aside className="space-y-4">
            <Card title="Honest status" subtitle="Every application says exactly where it stands">
              <div className="flex flex-wrap gap-2">
                {JOURNEY.map((s) => (
                  <StatusPill key={s.label} tone={s.tone}>
                    {s.label}
                  </StatusPill>
                ))}
              </div>
            </Card>

            <Card title="Actions">
              <div className="flex flex-wrap gap-2">
                <Button variant="primary">Review &amp; approve</Button>
                <Button variant="secondary">Open</Button>
                <Button variant="positive">Confirm</Button>
                <Button variant="ghost">Later</Button>
                <Button variant="danger">Cancel</Button>
              </div>
            </Card>

            <Banner tone="caution" title="Rehearsal needed first">
              The first real submission to an employer runs a fill-and-check rehearsal that never submits.
            </Banner>

            <Banner tone="positive" title="Nothing is sent by swiping">
              Swiping right only adds a role to prepare. You approve every submission yourself.
            </Banner>
          </aside>
        </div>
      </main>
    </div>
  );
}
