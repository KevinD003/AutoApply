"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";

import { api, ApiError, Me, setCsrf } from "@/lib/api";
import { ErrorBox, Loading } from "./ui";

const NAV = [
  { href: "/jobs", label: "Jobs" },
  { href: "/tracker", label: "Tracker" },
  { href: "/documents", label: "Documents" },
  { href: "/answers", label: "Saved answers" },
  { href: "/profile", label: "Profile" },
  { href: "/preferences", label: "Preferences" },
];

export default function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    api<Me>("/auth/me")
      .then((m) => {
        setCsrf(m.csrf_token);
        setMe(m);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) router.replace(`/login?next=${encodeURIComponent(path)}`);
        else setError(new Error("Could not reach the NoEfforts API. Is the backend running?"));
      });
  }, [router, path]);

  async function logout() {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    setCsrf(null);
    router.replace("/login");
  }

  if (error)
    return (
      <main className="mx-auto max-w-md p-6">
        <ErrorBox error={error} />
      </main>
    );
  if (!me) return <Loading label="Checking your session…" />;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-4 py-3">
          <Link href="/jobs" className="font-semibold text-indigo-700">
            NoEfforts
          </Link>
          <div className="flex items-center gap-3 text-sm">
            <span className="hidden text-slate-500 sm:inline">{me.email}</span>
            <button onClick={logout} className="text-slate-600 underline-offset-2 hover:underline">
              Sign out
            </button>
          </div>
        </div>
        <nav aria-label="Main" className="mx-auto flex max-w-5xl gap-1 overflow-x-auto px-2 pb-2">
          {NAV.map((n) => {
            const active = path.startsWith(n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                aria-current={active ? "page" : undefined}
                className={`whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium ${
                  active ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {n.label}
              </Link>
            );
          })}
        </nav>
      </header>
      <main className="mx-auto max-w-5xl space-y-4 px-4 py-5">{children}</main>
    </div>
  );
}
