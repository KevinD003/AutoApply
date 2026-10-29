"""Claude as the drafting provider (L4, D74): Anthropic's Messages API through the official SDK.

The one provider that sends anything out of NoEfforts, so it is behind every check in
`drafting_access` (owner account, the user's consent to the exact text, the day's budget) and is
off unless the owner configures it (`configured()`). Nothing in this repository holds a key.

One request per draft, presented only through `drafting.prompt` (the rules as the system prompt,
the facts and the quoted employer text as one JSON user message). The answer is constrained to
JSON {"text", "evidence"} and then checked like every draft (`drafting.validate_draft`). No
sampling parameters (the API refuses them), no tools, no retries: a failed request is reported
with a fixed code and the user asks again. Before each request the API host must resolve to
public addresses only (R10.5). No server-side fallback to another model: the budget is priced
for the configured model, and a declined draft means the user writes it.
"""

import json
import socket
from decimal import Decimal

from app.core.urlsafety import UnsafeURL, resolve_public_destination
from app.modules.preparation import drafting, drafting_access

NAME = "anthropic"
# USD per million tokens (input, output), Anthropic's list prices of 2026-10-06. A model not
# listed here is never used: its cost could not be bounded.
MODEL_ID = "claude-opus-5-5"
PRICES_PER_MTOK = {MODEL_ID: (Decimal("4.00"), Decimal("20.00"))}
MAX_TOKENS = 16_000  # thinking and the answer together; bounds the output cost
EFFORT = "medium"
SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["text", "evidence"],
    "additionalProperties": False,
}
_FRAMING_TOKENS = 200  # message framing and the output format instruction
OUTPUT_RULE = (
    " Answer with `text`, the answer itself, and `evidence`, the ids of the facts it uses."
)


def configured() -> "AnthropicProvider | None":
    from app.core.config import get_settings

    s = get_settings()
    if s.drafting_provider != NAME or not s.anthropic_api_key.get_secret_value():
        return None
    if s.drafting_model not in PRICES_PER_MTOK:
        return None
    return AnthropicProvider(s.drafting_model, s.anthropic_base_url, s.drafting_timeout_seconds)


def worst_case_usd(model: str, system: str, user: str) -> Decimal:
    """An upper bound on one request's cost. The user message is ASCII-only JSON, and a token
    covers at least one character, so the characters bound the input tokens."""
    inp, out = PRICES_PER_MTOK[model]
    tokens_in = len(system) + len(user) + _FRAMING_TOKENS
    return (tokens_in * inp + MAX_TOKENS * out) / Decimal(1_000_000)


def cost_usd(model: str, usage) -> Decimal:
    """What the provider reported, every input token at the full input price."""
    inp, out = PRICES_PER_MTOK[model]
    tokens_in = (
        (usage.input_tokens or 0)
        + (usage.cache_creation_input_tokens or 0)
        + (usage.cache_read_input_tokens or 0)
    )
    return (tokens_in * inp + (usage.output_tokens or 0) * out) / Decimal(1_000_000)


class AnthropicProvider:
    name = NAME
    external = True  # sends the request out of NoEfforts: drafting.provider_for checks it

    def __init__(self, model: str, base_url: str, timeout: float, *, user_id=None,
                 client=None, resolver=socket.getaddrinfo):  # fmt: skip
        self.model, self.base_url, self.timeout = model, base_url.rstrip("/"), timeout
        self.user_id, self.resolver, self._client = user_id, resolver, client

    def bound(self, user_id) -> "AnthropicProvider":
        return AnthropicProvider(self.model, self.base_url, self.timeout, user_id=user_id,
                                 client=self._client, resolver=self.resolver)  # fmt: skip

    def client(self):
        if self._client is None:
            import anthropic

            from app.core.config import get_settings

            self._client = anthropic.Anthropic(
                api_key=get_settings().anthropic_api_key.get_secret_value(),
                base_url=self.base_url,
                timeout=self.timeout,
                max_retries=0,
            )
        return self._client

    def draft(self, req: drafting.DraftRequest) -> drafting.DraftResult:
        import anthropic

        if self.user_id is None:
            raise RuntimeError("an external provider is used only through provider_for")
        (rules,), (user,) = (
            [m["content"] for m in drafting.prompt(req) if m["role"] == role]
            for role in ("system", "user")
        )
        system = rules + OUTPUT_RULE
        usage_id = drafting_access.reserve(
            self.user_id, NAME, self.model, worst_case_usd(self.model, system, user)
        )
        try:
            resolve_public_destination(self.base_url, self.resolver)
            resp = self.client().messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={
                    "effort": EFFORT,
                    "format": {"type": "json_schema", "schema": SCHEMA},
                },
            )
        except UnsafeURL:
            return self._fail(usage_id, "provider_destination_refused", Decimal(0))
        except anthropic.APITimeoutError:
            return self._fail(usage_id, "provider_timeout", None)
        except anthropic.APIConnectionError:
            return self._fail(usage_id, "provider_unreachable", None)
        except anthropic.APIStatusError:
            return self._fail(usage_id, "provider_error", Decimal(0))
        except anthropic.AnthropicError:  # anything else the SDK raises: the outcome is unknown
            return self._fail(usage_id, "provider_error", None)
        cost, u = cost_usd(self.model, resp.usage), resp.usage
        code = {"refusal": "provider_refused", "max_tokens": "provider_incomplete"}.get(
            resp.stop_reason or ""
        )
        out = None
        if code is None:
            try:
                text = next(b.text for b in resp.content if b.type == "text")
                out = json.loads(text)
                if not (isinstance(out.get("text"), str) and isinstance(out.get("evidence"), list)
                        and all(isinstance(e, str) for e in out["evidence"])):  # fmt: skip
                    raise ValueError
            except (StopIteration, ValueError, AttributeError):
                code = "provider_unparseable"
        drafting_access.settle(usage_id, code or "drafted", cost, u.input_tokens, u.output_tokens)
        if code is not None:
            raise drafting.ProviderFailed(code)
        return drafting.DraftResult(text=out["text"], evidence=out["evidence"], provider=NAME,
                                    model=resp.model, cost_usd=float(cost))  # fmt: skip

    def _fail(self, usage_id, code: str, cost: Decimal | None):
        drafting_access.settle(usage_id, code, cost)
        raise drafting.ProviderFailed(code)
