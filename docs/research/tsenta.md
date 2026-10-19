# Tsenta — public docs, terms and features

- Date: 2026-10-19
- Sources (all fetched via Firecrawl, public, not logged in):
  - D0 https://docs.tsenta.com/llms.txt
  - D1 https://docs.tsenta.com/developers/introduction (served content/URL resolved to https://docs.tsenta.com/product/introduction)
  - D2 https://docs.tsenta.com/product/how-auto-apply-works.md
  - D3 https://docs.tsenta.com/product/supported-job-boards.md
  - D4 https://docs.tsenta.com/product/mcp-connector.md
  - D5 https://docs.tsenta.com/product/apps-and-surfaces.md
  - D6 https://docs.tsenta.com/product/privacy-and-data.md
  - D7 https://docs.tsenta.com/product/tracking-applications.md
  - D8 https://docs.tsenta.com/product/faq.md
  - D9 https://docs.tsenta.com/product/profile-and-resume.md
  - T  https://tsenta.com/terms (Effective Date: September 23, 2025)
  - H  https://tsenta.com/ (Firecrawl cache from 2026-10-19T14:40Z)
- Labels: **observed** (what the fetch returned), **documented** (Tsenta says so), **inferred**, **unknown**.

## Developer API

**Correction (2026-10-19, recheck):** the first pass labelled the developer API "not found". That
overstated what was observed. The project owner reports the developer documentation at
https://docs.tsenta.com/developers/introduction is publicly accessible. From this environment it
is **inaccessible**, not proven absent:

| Fact | Label | Source |
|---|---|---|
| Fetching `/developers/introduction` (plain and with JS wait + alternate proxy, no login) returns HTTP 200 but the final URL is `/product/introduction`; no developer content is served to this fetcher | observed | Firecrawl recheck 2026-10-19 (two attempts) |
| `/api-reference/introduction` redirects to a Mintlify sign-in page (`app.mintlify.com/login?…redirect=/api-reference/introduction`); the docs header also has a "Log In" link | observed | Firecrawl recheck 2026-10-19 |
| Interpretation: some docs, plausibly the developer/API section, are gated behind docs-site sign-in or served conditionally; an unauthenticated server-side fetcher sees only product pages | inferred | — |
| `llms.txt` / `llms-full.txt` list only product pages | observed | D0, recheck |
| Content of the developer docs (auth model, endpoints, webhooks, approval semantics, confirmation evidence) | **inaccessible from this environment** | — |
| The remote MCP connector `https://api.autojobs.me/api/v1/mcp` (OAuth) is documented on public product pages | documented | D4 |
| MCP tools cover resume profiles, application review/status, tracker, inbox, networking, allowance; "The tools exposed to your client are the current capability list" | documented | D4 |
| MCP approval: "Approval behavior depends on your client; connecting it does not guarantee it will prompt before every change." | documented | D4 |
| Tsenta receives tool arguments, not general conversation/file access | documented | D4, D6 |

### Integration status (four separate questions)

| Question | Answer |
|---|---|
| Documentation found? | Developer docs: reported public by the owner; **inaccessible from this environment** (redirect / sign-in). Product + MCP docs: yes. |
| API/account access available? | **No.** No Tsenta account, API key or OAuth grant exists for this project. None will be created without the owner's approval. |
| Integration implemented? | **No.** No Tsenta code exists in the repository. |
| Integration tested? | **No.** |

Next step if the owner wants it: the owner shares the developer docs (export or copy) or grants
a documented test credential; we then design an optional, **disabled-by-default**
execution provider behind the provider interface, verify its approval semantics and
confirmation evidence against our policy, and only then test it. No spending, no account
creation and no real submissions without explicit approval.

## Approval / consent semantics (product)

- Three independent controls (documented, D2/D9): **Resume auto-approval** (off ⇒ pause for tailored-resume review), **Review before submit** (pauses *compatible* forms after fill; "Other systems may proceed without that pause"), **Auto Apply** (own filters, daily cap, match threshold; "These applications skip manual review").
- Resume optimisation modes: Off / Honest / **Aggressive** ("Rewrites more freely and may stretch claims") (documented, D9).
- Terms §4: "You are solely responsible for reviewing and approving all AI-generated content before submission to employers." (observed in T) — note the tension with Auto Apply skipping review (inferred).
- Messaging (iMessage/WhatsApp): "Review the role and requested action before authorizing an application." (documented, D5)

## Confirmation evidence

- "A completed record can include captured answers, documents, and a submission confirmation; the detail depends on the employer system." (D2) / "filled fields, generated answers, the resume and cover letter, and the final submission result" (D7).
- "An application in progress is not a confirmed submission." "A submission confirms an application was sent, not that the employer will respond." (D7, D2)
- Homepage shows a per-application "receipt" mock (fields, answers, résumé, "47s to complete") (observed in H; marketing mock-up, not evidence of real format).
- Billing: "Successful submissions use allowance. Failed or skipped attempts do not." (D8)
- Webhooks: none documented (unknown).

## Data handling

- Dedicated Tsenta inbox stores application mail, classifies, links to applications, auto-updates tracker when confident (D6, D7).
- Own Gmail/Outlook connection optional; docs say it "retrieves passcodes needed for supported applications. It is not a general mailbox-import feature." (D6). Terms §6: "We will only access your emails for the purpose of detecting and autofilling one-time passwords (OTPs)." (T)
- **Inconsistency (observed)**: homepage FAQ says connected inbox lets Tsenta read "confirmations, recruiter replies, interview invitations, and rejections" and save drafted replies to your drafts folder (H) — broader than Terms §6.
- Analytics/ad-measurement can receive usage/device/attribution signals incl. hashed account attributes (D6).
- Applications "run in the cloud"; Chrome extension only captures roles, "does not fill the employer's form in your tab" (D2, D3, D5). Account deletion via mobile settings or email (D6, D8). Bug bounty at tsenta.com/bug-bounty (D6).

## Terms clauses relevant to competitor inspection (T, observed quotes)

- §3(c) Prohibited: "Use automated systems (bots, scripts) to access the Services in ways not intended"
- §3(c): "Scrape, copy, or redistribute content from the Services without permission"
- §3(c): "Attempt to gain unauthorized access to our systems or other users' accounts"; "Interfere with or disrupt the Services or servers"
- §5(a): all content/features/software "owned by Tsenta or its licensors and are protected by copyright, trademark, and other intellectual property laws."
- No explicit clause on **reverse engineering**, **decompiling**, **competitive use** or **benchmarking** was found in the Terms (observed absence; the Privacy Policy, app-store EULAs and Chrome extension terms were not reviewed — unknown).
- §13: US law, binding AAA arbitration. §11: termination for conduct "harmful to Tsenta".

### What this appears to permit / prohibit (not legal advice; uncertain)

- **Likely fine (inferred)**: reading public marketing pages and docs manually; building a feature list from them; using the product as an ordinary user with your own account and data within normal use; documenting observed UX.
- **Likely prohibited or high risk (inferred)**: scripted/bot access to dashboard or MCP beyond intended use; scraping or redistributing Tsenta content (job feed, generated materials); probing APIs (`api.autojobs.me`) outside the documented MCP use; anything resembling unauthorized access. Copying their code/assets is excluded by §5(a).
- **Grey/uncertain**: static analysis of the public Chrome extension or mobile app bundles (no explicit RE ban in these Terms, but Chrome Web Store / app-store terms, copyright and DMCA §1201 may apply); automated benchmarking via the MCP connector (it is an intended automation surface, but "ways not intended" is vague). Get legal review before any of these; prefer clean-room observation of public behaviour.

## Publicly described features (candidate rows for an evidence matrix)

| # | Feature | Source |
|---|---|---|
| 1 | Watches "50,000+ career pages" for new roles; "be the first to apply" | H |
| 2 | ATS coverage claims: "30+ ATSes · ~95% of postings" and elsewhere "nineteen ATSes covered" (inconsistent); logos: Workday, Greenhouse, Lever, Ashby, Rippling, iCIMS, BambooHR, Workable, JazzHR, Jobvite, BreezyHR, Oracle Cloud | H |
| 3 | Match scoring (% match) with explanation; feed, search, paste job URL | H, D2 |
| 4 | Resume profiles (multiple, import PDF <10 MB / DOCX template, download) | D9 |
| 5 | Resume tailoring modes Off/Honest/Aggressive; ATS score display; diff shown before send | D9, H |
| 6 | Cover letters on demand where accepted/required | D9 |
| 7 | Open-ended answers "in your voice" drafted from résumé | H |
| 8 | Handles account creation/login and verification steps ("supported account and verification steps"), OTP autofill via email | D2, T, H |
| 9 | Review-before-submit (compatible forms only) | D2 |
| 10 | Auto Apply with filters, daily cap, match threshold | D2 |
| 11 | Cloud execution (not in user's tab) | D2, D5 |
| 12 | Application record/receipt with fields, answers, documents, confirmation | D2, D7, H |
| 13 | Tracker stages applied/interviewing/offer/rejected/ghosted; manual add; CSV import | D7 |
| 14 | Dedicated inbox with classification + auto status updates; reply from inbox | D6, D7 |
| 15 | Optional Gmail/Outlook connection (OTP; per homepage also mail reading + draft replies) | D6, H |
| 16 | Networking: find contact, verified work email, save email/LinkedIn draft (never sends) | D4 |
| 17 | Surfaces: web dashboard, iOS/Android apps, Chrome extension (capture), iMessage/WhatsApp, MCP (Claude/Codex) | D5, H |
| 18 | Work authorization / sponsorship-aware matching and answers | D8, H |
| 19 | Pricing: 25 free applications; $19/600, $39/1,500, $99/4,500 applications per 30-day cycle (monthly); pay only for submitted | H, D8 |
| 20 | "Does not intentionally add a Tsenta label"; no undetectability promise | D8, H |
