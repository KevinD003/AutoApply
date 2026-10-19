# Gmail OAuth scopes and verification — research notes

- Date: 2026-10-19
- Sources (fetched via Firecrawl; all **documented** = Google's own pages):
  - S1 https://developers.google.com/workspace/gmail/api/auth/scopes ("Last updated 2026-09-10 UTC")
  - S2 https://support.google.com/cloud/answer/15549945 ("Manage App Audience")
  - S3 https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification ("Last updated 2026-08-19 UTC")
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
