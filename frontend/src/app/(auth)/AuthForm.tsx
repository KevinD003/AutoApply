"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";

import { Button, ErrorBox, Field, inputCls } from "@/components/ui";
import { api, Me, setCsrf } from "@/lib/api";

export default function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await api<Me>(`/auth/${mode}`, { json: { email, password } });
      setCsrf(me.csrf_token);
      const next = params.get("next");
      router.replace(mode === "register" ? "/profile" : next?.startsWith("/") ? next : "/jobs");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-4">
      <h1 className="mb-1 text-2xl font-semibold text-indigo-700">NoEfforts</h1>
      <p className="mb-6 text-sm text-slate-600">
        {mode === "login" ? "Sign in to your account." : "Create an account. You review everything before it is sent."}
      </p>
      {mode === "login" && params.get("deleted") === "1" && (
        <p role="status" className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          Your account and everything in it were deleted.
        </p>
      )}
      <form onSubmit={submit} className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <Field label="Email">
          <input className={inputCls} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password" hint={mode === "register" ? "At least 10 characters." : undefined}>
          <input
            className={inputCls}
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            minLength={10}
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        <ErrorBox error={error} />
        <Button type="submit" disabled={busy} className="w-full">
          {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
        </Button>
      </form>
      <p className="mt-4 text-center text-sm text-slate-600">
        {mode === "login" ? (
          <>
            New here? <Link className="text-indigo-700 underline" href="/register">Create an account</Link>
          </>
        ) : (
          <>
            Have an account? <Link className="text-indigo-700 underline" href="/login">Sign in</Link>
          </>
        )}
      </p>
    </main>
  );
}
