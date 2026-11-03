"use client";

import { useState } from "react";
import Link from "next/link";

import { cx } from "./cx";
import { Sheet } from "./motion";
import { IconChevronRight, IconMore } from "./icons";

/*
  The mobile primary navigation (D125): a floating Liquid-Glass bar with a small, fixed set
  of primary destinations and a "More" surface for the rest. Shown only below `sm` (the
  desktop top nav carries the same destinations). A single indicator slides under the active
  tab (transform only; the reduced-motion rule in globals.css makes it instant). Every tab is
  a real link with an icon, a stable label and aria-current; icon-only is never used here.

  The secondary destinations live in the More sheet as real links with the same accessible
  names, so navigation history and deep links work exactly as from the desktop nav.
*/

function isActive(pathname, href) {
  return pathname === href || pathname.startsWith(href + "/");
}

export function BottomNav({ pathname = "/", primary = [], secondary = [] }) {
  const [moreOpen, setMoreOpen] = useState(false);

  const activePrimary = primary.findIndex((it) => isActive(pathname, it.href));
  const secondaryActive = secondary.some((it) => isActive(pathname, it.href));
  // The indicator sits under the active primary tab, or under "More" when a secondary
  // destination is open; it hides when neither applies.
  const slots = primary.length + 1;
  const activeIndex = activePrimary >= 0 ? activePrimary : secondaryActive ? primary.length : -1;

  return (
    <>
      <nav
        aria-label="Primary"
        className="glass-nav pb-safe fixed inset-x-0 bottom-0 z-40 rounded-none border-x-0 border-b-0 sm:hidden"
      >
        <div
          className="relative mx-auto grid max-w-md px-2 pt-1"
          style={{ gridTemplateColumns: `repeat(${slots}, minmax(0, 1fr))` }}
        >
          {/* Sliding active indicator: a short bar that moves between slots. */}
          {activeIndex >= 0 && (
            <span
              aria-hidden="true"
              className="pointer-events-none absolute top-0 h-[3px] rounded-full bg-brand"
              style={{
                width: `calc((100% / ${slots}) - 1.75rem)`,
                left: `calc((100% / ${slots}) * ${activeIndex} + 0.875rem)`,
                transition: "left var(--dur-3) var(--ease-standard)",
              }}
            />
          )}
          {primary.map((item) => {
            const active = isActive(pathname, item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cx(
                  "focus-ring ne-interactive ne-press flex min-h-[3.25rem] flex-col items-center justify-center gap-0.5 rounded-[var(--r-md)] px-1 py-1.5 text-[0.68rem] font-medium",
                  active ? "text-brand" : "text-ink-muted",
                )}
              >
                {Icon && <Icon size={21} />}
                <span className="leading-none">{item.label}</span>
              </Link>
            );
          })}
          <button
            type="button"
            onClick={() => setMoreOpen(true)}
            aria-haspopup="dialog"
            aria-expanded={moreOpen}
            aria-current={secondaryActive ? "page" : undefined}
            className={cx(
              "focus-ring ne-interactive ne-press flex min-h-[3.25rem] flex-col items-center justify-center gap-0.5 rounded-[var(--r-md)] px-1 py-1.5 text-[0.68rem] font-medium",
              secondaryActive ? "text-brand" : "text-ink-muted",
            )}
          >
            <IconMore size={21} />
            <span className="leading-none">More</span>
          </button>
        </div>
      </nav>

      <Sheet open={moreOpen} onClose={() => setMoreOpen(false)} labelledBy="more-nav-title">
        <div className="px-4 pb-2 pt-4">
          <h2 id="more-nav-title" className="font-display text-[1.35rem] font-semibold text-ink">
            More
          </h2>
          <p className="mt-0.5 text-sm text-ink-faint">Documents, answers and settings.</p>
        </div>
        <ul className="px-2 pb-3">
          {secondary.map((item) => {
            const active = isActive(pathname, item.href);
            const Icon = item.icon;
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  onClick={() => setMoreOpen(false)}
                  aria-current={active ? "page" : undefined}
                  className={cx(
                    "focus-ring ne-interactive flex items-center gap-3 rounded-[var(--r-md)] px-3 py-3 text-[0.95rem] font-medium",
                    active ? "bg-brand-weak text-brand" : "text-ink hover:bg-surface-3",
                  )}
                >
                  {Icon && <Icon size={20} className={active ? "text-brand" : "text-ink-muted"} />}
                  <span className="flex-1">{item.label}</span>
                  <IconChevronRight size={18} className="text-ink-faint" />
                </Link>
              </li>
            );
          })}
        </ul>
      </Sheet>
    </>
  );
}
