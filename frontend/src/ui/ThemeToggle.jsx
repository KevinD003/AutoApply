"use client";

import { useEffect, useState } from "react";

import { IconMoon, IconSun } from "./icons";

/*
  Light/dark toggle. Defaults to the system preference; once the user chooses, the
  choice is written to <html data-theme> (which globals.css honours) and persisted.
  All storage access is wrapped — it is only a per-device convenience, and the page
  renders correctly if it is empty or throws (private windows, blocked storage).
*/
const KEY = "ne-theme";

export function ThemeToggle() {
  const [mounted, setMounted] = useState(false);
  const [dark, setDark] = useState(false);

  useEffect(() => {
    // Default is light during the migration (so pages not yet themed never render
    // dark from a system preference). A pre-paint script in the root layout applies
    // the stored choice; here we read the live attribute so the icon matches.
    let isDark = false;
    try {
      isDark = document.documentElement.getAttribute("data-theme") === "dark";
    } catch {
      /* ignore */
    }
    setDark(isDark);
    setMounted(true);
  }, []);

  function toggle() {
    const next = !dark;
    setDark(next);
    try {
      document.documentElement.setAttribute("data-theme", next ? "dark" : "light");
      localStorage.setItem(KEY, next ? "dark" : "light");
    } catch {
      /* ignore */
    }
  }

  return (
    <button
      onClick={toggle}
      aria-label={mounted ? (dark ? "Switch to light theme" : "Switch to dark theme") : "Toggle theme"}
      className="focus-ring inline-flex h-11 w-11 items-center justify-center rounded-full text-ink-muted hover:bg-surface-3 hover:text-ink"
    >
      {mounted && dark ? <IconSun size={20} /> : <IconMoon size={20} />}
    </button>
  );
}
