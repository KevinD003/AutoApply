# Public-exposure review, 2026-11-05

This review was done after the owner made the repository public. It records scope, revisions,
findings, limitations and remediation only. No matched value, raw match or private session link
is reproduced here, and none was printed during the review.

**No exposure found in reviewed material.**

## Scope

- **Visibility and runners.** The repository is public. Every `runs-on` in every version of both
  workflows, on every ref, is `ubuntu-24.04`, a GitHub-hosted standard runner. There are no
  self-hosted or larger runners.
- **Git content.** Every unique blob reachable from the refs listed under Revisions (2,647 blobs,
  91.7 MB), and every commit (351): author and committer metadata, and commit messages. The checks
  covered:
  - **Credentials:** private keys; GitHub, Anthropic, OpenAI, Google (API key, OAuth client secret
    and ID, refresh and access tokens), AWS, Slack, Stripe, Telegram, SendGrid and npm tokens;
    JWTs; credentials inside URLs; high-entropy literals assigned to secret-like names.
  - **Personal data:** the owner's email address (compared by hash), personal-provider and other
    email addresses, phone numbers (North American and international), SSN-like numbers, LinkedIn
    handles, street addresses, date-of-birth labels, and the owner's surname.
  - **Employer and posting identifiers:** Greenhouse board, API and embed URLs, and Lever, Ashby
    and Workday hosts, each compared with the slugs that tests and fixtures use.
  - **Raw captures:** HTML documents, Greenhouse job JSON, and Greenhouse page markers.
  - **File types:** env, key, document, image, video, archive, data, model and capture files.
  - **The review environment's own long credential values,** checked by exact match.
- **Consent and decision records.** `backend/app/core/authorizations.py` and `docs/` were read with
  proper nouns, digits, emails and URLs masked, looking for statements of the owner's actual facts
  (work authorization, residence, salary, demographics).
- **GitHub surfaces:**
  - all 30 pull-request titles and descriptions;
  - issues, issue comments and releases (none exist);
  - Actions artifacts for every run whose artifacts could still be retained;
  - the logs of the 11 manual "Greenhouse read-only check" runs, the only runs ever given the
    posting secret. They were read line by line, and every summary string was checked against
    that run's own privacy allowlist.

  CI job logs were not read line by line. No version of `ci.yml` has ever used a secret, and CI
  output comes from the repository content scanned above.

## Revisions

The review ran on 2026-11-05 between about 20:55 and 21:30 UTC, against these refs (78 in total):

- `main` at `9a7f390`;
- every branch head (47), every pull-request head (#1–#30) and the one tag
  (`readonly-inspect-181b7c3`), as fetched at the start of the review;
- the 21 commits that existed only in the reviewing clone's reflogs (171 blobs), with the same
  result.

## Findings

No secrets or credentials were found, and no personal contact details or statements of the owner's
facts. There were no résumés, documents, answer-bank or answer-model data, no raw employer-page
captures, and no employer or posting identifiers.

- **Commit metadata.** All 351 author emails are GitHub noreply addresses. Committers are noreply
  addresses or GitHub's own web-flow address.
- **Read-only run logs.** 10 of the 11 logs were read completely. The only masks (`***`) are the
  expected secret and token masks, and every printed summary string passes the run's allowlist.
  The summaries show the form's structure (for example the number of custom questions): a weak
  fingerprint, not an identifier.

Low-severity items that are not exposure:

| # | Location | Item | Remediation |
|---|---|---|---|
| 1 | `main` | No branch protection or ruleset | Owner to apply the minimal ruleset proposed separately: pull request required; the four CI checks `backend`, `frontend`, `docker-smoke` and `execution-compose` required; force pushes and deletion blocked; no reviewer requirement; no bypass. |
| 2 | Actions artifact `playwright-results` from CI run #160 (retained until 2026-11-09) | End-to-end results from the synthetic test app; CI has no real data or secrets | None needed. |
| 3 | 20 of the 30 pull-request descriptions | Links to private assistant sessions (access-controlled, not credentials) | Optional: remove them. New pull requests omit them. |
| 4 | `.env.example` | Example local database password (a non-secret default) | Already refused for deployments by `scripts/check_env.py` (`WEAK_DEFAULTS`). |
| 5 | `backend/app/core/authorizations.py`, `docs/decisions.md` | Verbatim owner instructions (no contact details or personal facts) | Optional: summarize rather than quote. |
| 6 | `.github/workflows/ci.yml` | Third-party action pinned by tag (`astral-sh/setup-uv@v6`) | Optional hardening: pin by commit SHA. The CI job holds no secrets. |

Workflow safety:

- `ci.yml` runs on `push` to `main` and on `pull_request`, with `permissions: contents: read` and no
  secrets.
- `greenhouse-readonly.yml` runs on `workflow_dispatch` only, with `contents: read`, and masks both
  parts of its secret.
- Neither workflow uses `pull_request_target` or `workflow_run`.
- Artifacts are kept for at most 7 days.

## Limitations

- **Unavailable log.** Read-only run #3 (run `39432345404`, job `118660349161`): the log endpoint
  returned 404 when the review ran, so the log was not reviewed. Its unavailability is a review
  limitation, not proof that it was deleted.
- **Secret-scanning alerts not reviewed.** No tool in the review session could list GitHub's
  secret-scanning alerts. GitHub's content-scan API answered "Repository does not have GitHub
  Advanced Security enabled". The alert state is therefore unknown. An empty alert list would not
  prove absence either.
- **Unreachable commits.** Commits on GitHub that no ref reaches (for example history from a
  force-push or a deleted branch) cannot be listed. The reviewing clone recorded no forced updates.
- **Pattern limits.** Pattern checks can miss identifiers written as free text that match no
  pattern, such as an employer named in prose. The docs use aliases, and the read-only summaries
  pass an allowlist.
- **Fork policy not checked.** The fork pull-request approval setting was not verifiable from the
  review session.
- **Existing copies.** Copies made while the repository is public (forks, clones, caches) are
  outside the owner's control. Making it private again would not retract them.

## Remediation

- Owner: check Security → Secret scanning, and enable secret scanning and push protection (free for
  public repositories).
- Owner: set the Actions fork pull-request policy to "Require approval for all outside
  collaborators".
- Owner: apply the proposed `main` ruleset after review (finding 1).
- Optional: items 3, 5 and 6.
