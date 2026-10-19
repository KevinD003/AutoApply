# Decisions

Short records of choices made, with the reason and how to reverse them.

## D1 — Stack: Next.js + FastAPI + PostgreSQL + Redis/Celery (2026-10-19)
Followed the brief's default because the repository was empty. Python 3.12 managed with `uv`;
Node 22 with npm. Reversible: modules are plain FastAPI routers.

## D2 — Facts and preferences in separate tables
Residence, authorization and sponsorship are facts; target locations and relocation are
preferences. Keeping them in different tables means no code path can answer "where do you live"
from a desired city. Tested in `test_profile.py`.

## D3 — Tri-state answers everywhere
`yes / no / unknown / not_applicable` instead of booleans, so a missing answer is never coerced
to "no".

## D4 — Per-user job rows, not a shared job catalogue
Jobs are stored per user with a per-user dedupe key. Simpler isolation and no cross-tenant
leakage. A shared catalogue can be added later for feeds such as Freehire.

## D5 — Cookie sessions with CSRF header, not JWT
Server-side sessions can be revoked instantly; the token is stored only as a hash. The frontend
proxies `/api` so cookies stay first-party.

## D6 — Tests use a real PostgreSQL database
Duplicate detection relies on `ON CONFLICT` and unique constraints; SQLite would not prove that.
Tests migrate a dedicated database with Alembic, so migrations are tested too.

## D7 — Freehire: optional discovery source only (not yet integrated)
Pinned `strelov1/freehire@ec6e65f7`, MIT. Its public API (`https://freehire.me/api/v1`) is live
and keyless with a documented 600 req/min/IP limit, and its terms forbid scraping beyond the
documented API. Plan: a throttled discovery adapter that re-verifies postings at the source ATS.
Do **not** reuse its TLS-fingerprint spoofing or LinkedIn guest-API harvesting. Its ideas for
public form-schema endpoints and "unconfirmed ⇒ never resubmit" match our design; no code copied.
Not reachable from the current cloud sandbox (proxy 403), so integration must be tested locally.
Details: `docs/research/freehire.md`.

## D8 — Tsenta: public documentation only; no automated inspection
Tsenta has no public developer API (only an OAuth MCP connector), and its terms (eff.
2025-09-23, §3(c)) prohibit automated access "in ways not intended" and scraping. We therefore
use only public pages and normal manual use for the evidence matrix. Static analysis of its
extension or apps needs legal review first. A Tsenta execution provider stays out of scope until
a documented, permitted API exists. Details: `docs/research/tsenta.md`.

## D9 — REA: optional development aid
`rea-agents@6.7.0` (MIT, `morluto/rea@b4938ae`) runs headless with no credentials. Usable for
static analysis of public JS or our own HAR captures. Not a dependency of the product and not
used against logged-in competitor surfaces. Details: `docs/research/rea.md`.

## D10 — Gmail: manual code entry first, Gmail OAuth later and opt-in
Every Gmail read scope (including `gmail.metadata`) is *restricted*: public use needs Google
verification plus an annual CASA security assessment; testing mode caps at 100 users with
7-day refresh tokens. Phase D starts with manual code entry; Gmail stays optional.
Details: `docs/research/gmail-oauth.md`.

## D11 — Execution adapters before any "universal agent"
Order per the brief: documented API with valid credentials → tested deterministic browser
adapter → optional managed provider → manual handoff. Greenhouse and Lever public *submit*
endpoints need the employer's API key, so the first real adapter will be a browser adapter.
