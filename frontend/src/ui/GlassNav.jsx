"use client";

import Link from "next/link";

import { cx } from "./cx";
import { Wordmark } from "./BrandMark";
import { IconBell } from "./icons";

/*
  Liquid-glass top navigation. Pure/presentational: the caller passes `pathname`
  (from usePathname) plus the nav items (each with an icon component), so it is
  SSR-safe and testable. A <header> (banner) with a brand row (brand, theme toggle,
  notifications bell, account) and a destination row. On desktop the destination row
  carries every destination; below `sm` it is hidden (display:none, so it leaves the
  accessibility tree and never double-matches) and the floating BottomNav takes over
  with the same destinations — the primary ones as tabs, the rest in a More sheet.
  Frosted glass with an opaque fallback (see globals.css .glass-nav). The brand row,
  including the notifications bell, stays on every viewport.
*/

function isActive(pathname, href) {
  return pathname === href || pathname.startsWith(href + "/");
}

export function GlassNav({ pathname = "/", items = [], unread = 0, email, onSignOut, themeToggle }) {
  const bellLabel = unread ? `Notifications, ${unread} unread` : "Notifications";

  return (
    <header className="glass-nav pt-safe sticky top-0 z-30 rounded-none border-x-0 border-t-0">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-2.5">
        <Link href="/jobs" aria-label="NoEfforts home" className="focus-ring rounded-[var(--r-md)]">
          <Wordmark />
        </Link>
        <div className="flex items-center gap-0.5">
          {themeToggle}
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
          {email && <span className="hidden max-w-44 truncate px-2 text-sm text-ink-muted sm:inline">{email}</span>}
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

      <nav aria-label="Main" className="mx-auto hidden max-w-6xl gap-1 overflow-x-auto px-3 pb-2 sm:flex [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {items.map((item) => {
          const active = isActive(pathname, item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cx(
                "focus-ring inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-[var(--r-md)] px-3 py-1.5 text-sm font-medium transition",
                active ? "bg-brand-weak text-brand" : "text-ink-muted hover:bg-surface-3 hover:text-ink",
              )}
            >
              {Icon && <Icon size={17} />}
              {item.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
