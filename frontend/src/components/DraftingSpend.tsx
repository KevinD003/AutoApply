"use client";

import { useEffect, useState } from "react";

import { Badge, Card, Empty, ErrorBox } from "./ui";
import { api } from "@/lib/api";

// D97: what AI drafting has used against the server's daily budget, from the same ledger that
// enforces it (drafting_usage). Every amount says what it is: NoEfforts' estimate from the tokens
// the provider reported, a worst case kept because the outcome or cost is unknown, a worst case
// held while a request runs, or nothing sent. None of it is the provider's invoice.
type Basis = "reserved" | "estimated" | "unknown" | "not_sent";
interface Totals {
  requests: number;
  input_tokens: number;
  output_tokens: number;
  estimated_usd: number;
  worst_case_usd: number;
}
interface Day extends Totals {
  day: string;
}
interface Request {
  at: string;
  provider: string;
  model: string;
  status: "reserved" | "settled";
  outcome: string | null;
  cost_usd: number;
  cost_basis: Basis;
  input_tokens: number | null;
  output_tokens: number | null;
  price_version: string | null;
}
interface View {
  offered: boolean;
  provider: string | null;
  model: string | null;
  budget_usd: number | null;
  resets: string;
  day: string;
  all_accounts_today_usd: number | null;
  remaining_usd: number | null;
  today: Totals;
  days: Day[];
  recent: Request[];
  pricing: { version: string; model: string; input_per_mtok: number; output_per_mtok: number } | null;
}

const BASIS: Record<Basis, { label: string; tone: "slate" | "amber" | "indigo" }> = {
  estimated: { label: "estimated", tone: "indigo" },
  unknown: { label: "unknown: worst case kept", tone: "amber" },
  reserved: { label: "in progress: worst case held", tone: "amber" },
  not_sent: { label: "nothing sent", tone: "slate" },
};

const usd = (n: number | null) => (n === null ? "—" : `$${n.toFixed(4)}`);

export default function DraftingSpend() {
  const [v, setV] = useState<View | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    api<View>("/drafting/usage").then(setV).catch(setError);
  }, []);
  if (!v) return <ErrorBox error={error} />;
  return (
    <Card title="AI drafting spend">
      <p className="text-sm text-slate-600">
        What AI drafting has used against this server&rsquo;s daily budget, counted by NoEfforts. Amounts are
        NoEfforts&rsquo; own accounting, not an invoice: check your provider&rsquo;s billing for what was charged.
      </p>
      {!v.offered ? (
        <p className="mt-2 text-sm text-slate-600" data-testid="spend-not-offered">
          AI drafting is not available for this account, so nothing is counted here.
        </p>
      ) : (
        <>
          <dl className="mt-3 grid grid-cols-1 gap-2 text-sm sm:grid-cols-2" data-testid="spend-today">
            <div>
              <dt className="text-slate-500">Daily budget (this server, all accounts)</dt>
              <dd className="font-medium">{v.budget_usd === 0 ? "none set: nothing is sent" : usd(v.budget_usd)}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Resets</dt>
              <dd className="font-medium">{v.resets}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Used today (all accounts)</dt>
              <dd className="font-medium">{usd(v.all_accounts_today_usd)}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Left today</dt>
              <dd className="font-medium">{usd(v.remaining_usd)}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Your requests today</dt>
              <dd className="font-medium">
                {v.today.requests} · {v.today.input_tokens.toLocaleString()} tokens in, {v.today.output_tokens.toLocaleString()} out
              </dd>
            </div>
            <div>
              <dt className="text-slate-500">Model</dt>
              <dd className="font-medium">{v.provider ? `${v.provider} · ${v.model}` : "not configured"}</dd>
            </div>
          </dl>
          <p className="mt-2 text-xs text-slate-500">
            Used and left include estimates and worst cases kept for requests whose cost is unknown.
            {v.pricing &&
              ` Estimates use the tokens the provider reported at the list prices NoEfforts recorded (${v.pricing.version}: $${v.pricing.input_per_mtok.toFixed(2)} in, $${v.pricing.output_per_mtok.toFixed(2)} out per million tokens), which may differ from what you are billed.`}
          </p>
          <h3 className="mt-4 text-sm font-semibold">Recent days (yours)</h3>
          {v.days.length === 0 ? (
            <Empty>No drafting requests yet.</Empty>
          ) : (
            <ul className="mt-1 divide-y divide-slate-100 text-sm" data-testid="spend-days">
              {v.days.map((d) => (
                <li key={d.day} className="flex flex-wrap justify-between gap-2 py-1">
                  <span>{d.day}</span>
                  <span className="text-slate-600">
                    {d.requests} request{d.requests === 1 ? "" : "s"} · estimated {usd(d.estimated_usd)}
                    {d.worst_case_usd > 0 && ` · worst case kept ${usd(d.worst_case_usd)}`}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <h3 className="mt-4 text-sm font-semibold">Recent requests (yours)</h3>
          {v.recent.length === 0 ? (
            <Empty>No drafting requests yet.</Empty>
          ) : (
            <ul className="mt-1 divide-y divide-slate-100 text-sm" data-testid="spend-requests">
              {v.recent.map((r, i) => (
                <li key={i} className="flex flex-wrap items-center justify-between gap-2 py-1">
                  <span>
                    {new Date(r.at).toLocaleString()} · {r.outcome ?? "in progress"}
                  </span>
                  <span className="flex items-center gap-2 text-slate-600">
                    {r.input_tokens !== null && `${r.input_tokens} in / ${r.output_tokens ?? 0} out · `}
                    {usd(r.cost_usd)} <Badge tone={BASIS[r.cost_basis].tone}>{BASIS[r.cost_basis].label}</Badge>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Card>
  );
}
