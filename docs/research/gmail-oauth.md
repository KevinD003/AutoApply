# Gmail OAuth scopes and verification — research notes

- Date: 2026-10-19
- Sources (fetched via Firecrawl; all **documented** = Google's own pages):
  - S1 https://developers.google.com/workspace/gmail/api/auth/scopes ("Last updated 2026-09-10 UTC")
  - S2 https://support.google.com/cloud/answer/15549945 ("Manage App Audience")
  - S3 https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification ("Last updated 2026-08-19 UTC")
  - S5 https://developers.google.com/workspace/workspace-api-user-data-developer-policy (Gmail API policy; "Last updated 2026-09-03 UTC"), rechecked 2026-10-19
  - S3 rechecked 2026-10-19 (same "Last updated 2026-08-19 UTC")
  - S4 search excerpt of https://developers.google.com/identity/protocols/oauth2 ("Refresh token expiration") — excerpt only, page not fully scraped.

## Scope tiers (S1, documented)

| Tier | Gmail scopes |
|---|---|
| Non-sensitive | `gmail.addons.current.action.compose`, `gmail.addons.current.message.action`, `gmail.labels` |
| Sensitive | `gmail.addons.current.message.metadata`, `gmail.addons.current.message.readonly`, `gmail.send` |
| **Restricted** | `https://mail.google.com/`, `gmail.readonly`, `gmail.compose`, `gmail.insert`, `gmail.modify`, **`gmail.metadata`** ("labels and headers, but not the email body"), `gmail.settings.basic`, `gmail.settings.sharing` |

Key point: **`gmail.metadata` is restricted, same tier as `gmail.readonly`** — choosing metadata does not avoid restricted-scope verification. Any scope that can read message content/headers outside the add-on context is restricted. `gmail.labels` (non-sensitive) cannot read messages.

## Restricted-scope implications (S1, S3, documented)

- S1: "If you store restricted scope data on servers (or transmit), then you must go through a security assessment."
- S3: apps that access restricted data "from or through a third-party server must undergo an annual security assessment by a Google-approved third party" (CASA via App Defense Alliance); reassessment "at least every 12 months after your assessor's Letter of Assessment (LOA) approval date"; adding a new restricted scope may require reassessment; process "can potentially take several weeks"; brand verification first (~2–3 business days).
- S3: requirements include permitted application type, Limited Use compliant privacy policy on the app's domain, verified authorized domains, unlisted YouTube demo video of consent + each scope's use, and justification why narrower scopes are insufficient.
- S3 exceptions (no verification needed): personal use / few known users; development/testing/staging projects (Testing status); service-owned data only; Internal (Workspace org) apps.
- Cost: not stated on Google pages fetched (**unknown** from official source). Freehire's internal doc (`docs/google-oauth-verification.md`, not Google) claims ~$500–1500/yr and that the free self-scan tier is gone — **unverified**.

## Testing mode (S2, documented)

- Testing status: "limited to up to 100 test users listed in the OAuth consent screen"; a test user consumes quota once added.
- Test users see an unverified-app warning.
- "Authorizations by a test user will expire seven days from the time of consent. If your OAuth client requests an `offline` access type and receives a refresh token, that token will also expire." Exception: only `openid`/`userinfo.email`/`userinfo.profile` (or Sign in with Google).
- Unverified production apps requesting sensitive/restricted scopes: lifetime cap of **100 new users** after the unverified-app screen (cannot be reset).
- S4 excerpt (consistent): external app in "Testing" is "issued a refresh token expiring in 7 days".

## Implications for NoEfforts (inferred)

- Confirmation-email parsing via Gmail API on a server = restricted scope + annual CASA. For an early/private beta, stay in Testing (≤100 named users, weekly re-consent) or use the personal-use exception.
- Alternatives avoiding restricted scopes: user-configured forwarding to an app-owned inbound address (freehire and Tsenta both offer a dedicated inbox), or manual paste/upload of confirmation emails. Gmail's non-sensitive/sensitive scopes (outside add-on context) do not give message reads.

## Is our intended use permitted? (recheck 2026-10-19, S5)

Intended use: read a one-time verification code or link from an employer/ATS email, for one
specific application attempt, within a short time window.

Google's **approved use cases** for Gmail scopes (S5, quoted list):
1. email clients that let users compose, send, read and process email via a user interface;
2. automatic email backup;
3. apps that enhance the email experience for productivity (CRM, delayed send, mail merge,
   generative-AI summaries);
4. apps that use information from emails to provide reporting or monitoring services for the
   benefit of users that improve the email experience (e.g. travel itineraries, flight or
   package tracking).

Assessment (**inferred, not a determination**): retrieving verification codes to complete
third-party job applications is **not explicitly listed**. Category 4 is the closest analogue,
but whether Google accepts it is uncertain and is Google's decision during verification. We
must not promise approval. S3 notes that if unsure of the application type you can leave the
features question blank and Google's team will decide.

Other S5 obligations that apply if we ever request a Gmail read scope:
- Minimum permissions; request in context (incremental auth), not up front.
- In-product disclosure immediately before consent, explaining what is read and why; affirmative
  consent; not only in the privacy policy.
- Limited Use: data only for the user-visible feature; no transfer except listed exceptions; no
  human reading without explicit consent; no ads; no training general AI models.
- Restricted scopes: encrypt user data and OAuth tokens at rest, HTTPS, proper key management,
  **prompt-injection protection** (Model Armor or equivalent) — relevant because email text is
  untrusted input; CASA compliance and a periodic third-party assessment / Letter of Assessment.
- A published privacy policy on the app's domain with the Limited Use statement.

## Requirements by deployment type (S3, S2, S5)

| Deployment | Verification | Security assessment | Practical limits |
|---|---|---|---|
| **Personal use** — only you, or a few users all personally known to you | Not required (S3 exception) | Not required by the exception | Users click through the "unverified app" screen. Policies (Limited Use, User Data Policy) still apply. |
| **Testing** publishing status | Not required (S3 exception) | Not required | ≤100 listed test users; their authorizations and refresh tokens **expire after 7 days** (S2), so users must reconnect weekly. |
| **Public, server-side** (any Google user, tokens and mail data on our servers) | Brand verification + restricted-scope verification: permitted app type, privacy policy, domain verification, demo video, justification of scopes | **Annual third-party CASA assessment**, re-verification at least every 12 months | Takes weeks; cost not stated on Google's pages (unknown). Approval not guaranteed, especially as the use case is not explicitly listed. |

## Decision for NoEfforts

1. Phase D ships **manual code entry** first (works for everyone, no Google review).
2. Optional Gmail connection only in **personal/testing** mode at first, clearly labelled, with
   the narrowest workable scope (`gmail.readonly` is restricted; there is no non-restricted
   scope that can read message bodies), time-and-sender-bounded queries, tokens encrypted at
   rest, disconnect/deletion, and no storage of email bodies beyond the extracted code.
3. Public multi-user Gmail access only after a deliberate decision to pursue verification and
   CASA, with no promise of approval.
