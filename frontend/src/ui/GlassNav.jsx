"use client";

import Link from "next/link";

import { cx } from "./cx";
import { Wordmark } from "./BrandMark";
import { IconBell } from "./icons";

/*
  Liquid-glass navigation. Pure/presentational: the caller passes `pathname` (from
  usePathname) and the nav items with their icon components, so it is SSR-safe and
  testable. It renders two chromes:
    - a sticky frosted top bar (desktop)
    - a compact frosted top bar + a fixed bottom tab bar (mobile, safe-area padded)
  Active links carry aria-current="page"; the bell's accessible name includes the
  unread count. Link labels/hrefs match the existing shell so navigation tests and
  muscle memory are preserved when this replaces the old header.
*/

function isActive(pathname, href) {
  return pathname === href || pathname.startsWith(href + "/") || pathname.startsWith(href + "?") ||
    (href !== "/" && pathname.startsWith(href));
}

export function GlassNav({ pathname = "/", items = [], unread = 0, email, onSignOut, themeToggle }) {
  const tabs = items.filter((i) => i.tab);
  const bellLabel = unread ? `Notifications, ${unread} unread` : "Notifications";

  const Bell = (
    <Link
      href="/notifications"
      aria-current={isActive(pathname, "/notifications") ? "page" : undefined}
      aria-label={bellLabel}
      className="focus-ring relative inline-flex h-11 w-11 items-center justify-center rounded-full text-ink-muted hover:bg-surface-3 hover:text-ink"
    >
      <IconBell size={20} />
      {!!unread && (
        <span
          aria-hidden="true"
          className="absolute right-1.5 top-1.5 min-w-4 rounded-full bg-brand px-1 text-center text-[10px] font-bold leading-4 text-brand-contrast"
        >
          {unread > 9 ? "9+" : unread}
        </span>
      )}
    </Link>
  );

  return (
    <>
      {/* Top bar */}
      <header className="glass-nav pt-safe sticky top-0 z-30 rounded-none border-x-0 border-t-0">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-2 px-4">
          <Link href="/jobs" className="focus-ring rounded-[var(--r-md)] py-1" aria-label="NoEfforts home">
            <Wordmark />
          </Link>

          <nav aria-label="Primary" className="ml-4 hidden items-center gap-1 md:flex">
            {items.map((item) => {
              const active = isActive(pathname, item.href);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cx(
                    "focus-ring inline-flex items-center gap-2 rounded-[var(--r-md)] px-3 py-2 text-sm font-medium transition",
                    active ? "bg-brand-weak text-brand" : "text-ink-muted hover:bg-surface-3 hover:text-ink",
                  )}
                >
                  {Icon && <Icon size={18} />}
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-1">
            {themeToggle}
            {Bell}
            {email && <span className="hidden max-w-40 truncate px-2 text-sm text-ink-muted lg:inline">{email}</span>}
            {onSignOut && (
              <button
                onClick={onSignOut}
                className="focus-ring rounded-[var(--r-md)] px-3 py-2 text-sm font-medium text-ink-muted hover:bg-surface-3 hover:text-ink"
              >
                Sign out
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Bottom tab bar (mobile only) */}
      {tabs.length > 0 && (
        <nav
          aria-label="Primary"
          className="glass-nav pb-safe fixed inset-x-0 bottom-0 z-30 rounded-none border-x-0 border-b-0 md:hidden"
        >
          <ul className="mx-auto flex max-w-lg items-stretch justify-around px-2 pt-1">
            {tabs.map((item) => {
              const active = isActive(pathname, item.href);
              const Icon = item.icon;
              return (
                <li key={item.href} className="flex-1">
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={cx(
                      "focus-ring mx-auto flex min-h-12 flex-col items-center justify-center gap-0.5 rounded-[var(--r-md)] px-2 py-1 text-[11px] font-medium transition",
                      active ? "text-brand" : "text-ink-muted",
                    )}
                  >
                    {Icon && <Icon size={22} />}
                    <span>{item.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      )}
    </>
  );
}
