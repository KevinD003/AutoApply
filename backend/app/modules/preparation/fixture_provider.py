"""TEST DOUBLE inside the app, labelled as such: a local drafting provider for the end-to-end
journey (frontend/e2e/journey.spec.ts). It is used only when `env == "test"` and the account
matches `drafting_test_fixture_users`; anywhere else it does not exist. It sends nothing out of
NoEfforts and calls no model: the text is the cited facts' own text, as many as fit, so every
draft check (drafting.validate_draft) still runs on its result exactly as on a real provider's.
"""

from fnmatch import fnmatch

from app.modules.preparation import drafting

NAME = "local-test-fixture"


def applies_to(user) -> bool:
    from app.core.config import get_settings

    s = get_settings()
    if s.env != "test" or not s.drafting_test_fixture_users or user is None:
        return False
    email = (user.email or "").strip().lower()
    return any(fnmatch(email, p.strip().lower()) for p in s.drafting_test_fixture_users)


class FixtureDraftProvider:
    name = NAME
    external = False  # nothing leaves NoEfforts; refused outside env "test" (applies_to)

    def draft(self, req: drafting.DraftRequest) -> drafting.DraftResult:
        lines, used = [], []
        for f in req.facts:
            text = f.text.strip()
            if text and len("\n".join([*lines, text])) <= req.max_chars:
                lines.append(text)
                used.append(f.id)
        return drafting.DraftResult(text="\n".join(lines), evidence=used, provider=NAME,
                                    model=None, cost_usd=0.0)  # fmt: skip
