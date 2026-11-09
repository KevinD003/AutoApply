"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api, ApiError, NOTIFICATIONS_CHANGED, setCsrf } from "@/lib/api";
import { GlassNav } from "@/ui/GlassNav";
import { BottomNav } from "@/ui/BottomNav";
import { RouteTransition } from "@/ui/motion";
import { ThemeToggle } from "@/ui/ThemeToggle";
import { Loading, ErrorText } from "@/ui/primitives";
import {
  IconBookmark,
  IconBriefcase,
  IconCompass,
  IconFileText,
  IconGear,
  IconQuestion,
  IconReview,
  IconSliders,
  IconTracker,
  IconUser,
} from "@/ui/icons";

/*
  The app shell: authenticates the session, keeps the unread-notifications count
  fresh, and frames every page with the premium Liquid-Glass navigation. The nav
  carries every destination with its exact label, matching the prior shell so all
  navigation and the notifications-bell contract are preserved.
*/

// label text is the link's accessible name — must match the existing e2e contract exactly.
// Primary = the core discovery→application workflow (the mobile bottom-nav tabs); secondary =
// documents, answers and settings (the mobile "More" sheet). Desktop shows all of them in the
// top nav, in this order, so its navigation is unchanged.
const PRIMARY = [
  { href: "/jobs", label: "Jobs", icon: IconBriefcase },
  { href: "/discover", label: "Discover", icon: IconCompass },
  { href: "/review", label: "Review", icon: IconReview },
  { href: "/tracker", label: "Tracker", icon: IconTracker },
];
const SECONDARY = [
  // D132: every question an application leaves to you, and forms that changed, on one page.
  { href: "/questions", label: "Questions", icon: IconQuestion },
  { href: "/documents", label: "Documents", icon: IconFileText },
  { href: "/answers", label: "Saved answers", icon: IconBookmark },
  { href: "/profile", label: "Profile", icon: IconUser },
  { href: "/preferences", label: "Preferences", icon: IconSliders },
  { href: "/account", label: "Account", icon: IconGear },
];
const NAV = [...PRIMARY, ...SECONDARY];

export default function AppShell({ children }) {
  const router = useRouter();
  const path = usePathname();
  const [me, setMe] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api("/auth/me")
      .then((m) => {
        setCsrf(m.csrf_token);
        setMe(m);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) router.replace(`/login?next=${encodeURIComponent(path)}`);
        else setError(new Error("Could not reach the NoEfforts API. Is the backend running?"));
      });
  }, [router, path]);

  // D83: the unread count, read again on every page and after marking.
  const [unread, setUnread] = useState(null);
  useEffect(() => {
    if (!me) return;
    const refresh = () =>
      api("/notifications/unread")
        .then((r) => setUnread(r.unread))
        .catch(() => setUnread(null));
    refresh();
    window.addEventListener(NOTIFICATIONS_CHANGED, refresh);
    return () => window.removeEventListener(NOTIFICATIONS_CHANGED, refresh);
  }, [me, path]);

  async function logout() {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    setCsrf(null);
    router.replace("/login");
  }

  if (error)
    return (
      <main className="mx-auto max-w-md p-6">
        <ErrorText error={error} />
      </main>
    );
  if (!me) return <Loading label="Checking your session…" />;

  return (
    <div className="min-h-screen bg-app">
      <GlassNav
        pathname={path}
        items={NAV}
        unread={unread ?? 0}
        email={me.email}
        onSignOut={logout}
        themeToggle={<ThemeToggle />}
      />
      <main className="mx-auto max-w-6xl px-4 py-6 pb-28 sm:pb-6">
        <RouteTransition className="space-y-5">{children}</RouteTransition>
      </main>
      <BottomNav pathname={path} primary={PRIMARY} secondary={SECONDARY} />
    </div>
  );
}
