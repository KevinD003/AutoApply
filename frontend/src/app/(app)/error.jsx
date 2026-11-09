"use client";

import { useEffect, useRef } from "react";

import { Button, Card } from "@/components/ui";

/** D133: a page inside the app that fails while it is being shown keeps the navigation around it
 * and says so, instead of replacing everything with a blank error screen. The error itself is
 * never read, shown or logged here: it can quote an answer or a server reply (the same rule as
 * the API's error boundary, docs/audit-events.md "Logs"). It does not catch the app shell, the
 * root layout, the sign-in pages, or failures in a button's action (those show their own
 * message). */
export default function AppError({ reset }) {
  const heading = useRef(null);
  useEffect(() => {
    heading.current?.focus();
  }, []);

  return (
    <>
      <h1 ref={heading} tabIndex={-1} className="font-display text-[1.7rem] font-semibold leading-[1.1] text-ink outline-none">
        This page could not be shown
      </h1>
      <Card>
        <p role="alert" className="text-sm">
          Something on this page failed while it was being shown. Anything you already saved is kept.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button onClick={() => reset()}>Try again</Button>
          <Button variant="secondary" onClick={() => window.location.reload()}>
            Reload the page
          </Button>
        </div>
      </Card>
    </>
  );
}
