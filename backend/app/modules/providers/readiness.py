"""Whether a live Greenhouse filling pilot could even be proposed: the seven conditions of
docs/greenhouse-readiness-gap.md ("Before a live filling pilot can be proposed"), each derived
from recorded evidence, never asserted by hand.

A condition is met only by evidence of its own kind: a capability level the registry records
for the adapter (reaching `observed` needs an approved read-only run), `real_destinations`
(no real upload or submission can have been made through NoEfforts while it is false), and
the live-pilot gate's separate permissions. The owner's manual observation (Path A) is shown
beside the conditions it bears on but meets none: it is advisory. A condition with no
evidence of its kind is not met. Nothing here approves or enables anything."""

from app.modules.providers import path_a, registry
from app.modules.providers.model import Capability

PROVIDER = "greenhouse_dom"
OBSERVED = {"observed", "live_fill", "live_submit"}
# docs/live-pilot-gate.md: the owner names the posting and gives permissions C (disclosure)
# and D (submission) separately. None has been given; none is recorded anywhere.
GATE_PERMISSIONS_RECORDED = False

_UNSET = object()


def conditions(observation=_UNSET) -> list[dict]:
    obs = path_a.load() if observation is _UNSET else observation
    advice = path_a.assess(obs)
    spec = registry.get(PROVIDER)

    def level(cap: Capability) -> str:
        return spec.support(cap).level()

    real = spec.real_destinations_enabled
    no_real = "real destinations are disabled, so NoEfforts cannot have made one"
    rows = [
        ("dropdowns", "each required dropdown opens through one bounded, fixture-tested "
         "strategy, with the complete list", level(Capability.custom_dropdowns) in OBSERVED,
         f"custom_dropdowns: {level(Capability.custom_dropdowns)}; Path A: "
         f"{advice['dropdowns']['state']}"),
        ("unmatched_required_controls", "the two required controls no question matches are "
         "understood and mapped by evidence", False,
         f"no mapping rule exists; Path A: u1 {advice['u1']['state']}, "
         f"u2 {advice['u2']['state']}"),
        ("location", "a supported, evidence-backed way to set the location without writing "
         "hidden coordinates", level(Capability.location_picker) in OBSERVED,
         f"location_picker: {level(Capability.location_picker)}"),
        ("real_upload", "attachments uploaded to a real form, proven on their own", real,
         f"file_upload: {level(Capability.file_upload)}; {no_real}"),
        ("real_submission", "a real final submit and its confirmation, proven separately",
         real, f"final_submit: {level(Capability.final_submit)}; {no_real}"),
        ("pilot_gate", "the owner named the posting and gave separate permissions for "
         "disclosure and submission", GATE_PERMISSIONS_RECORDED,
         "docs/live-pilot-gate.md: no permission given"),
        ("capability_entry", "the capabilities used are raised from fixture to observed, with "
         "a reviewed change to real destinations", real,
         f"real_destinations_enabled: {str(real).lower()}"),
    ]  # fmt: skip
    return [{"id": i, "condition": c, "met": bool(m), "evidence": e} for i, c, m, e in rows]


def summary(observation=_UNSET) -> dict:
    obs = path_a.load() if observation is _UNSET else observation
    rows = conditions(obs)
    return {
        "provider": PROVIDER,
        "met": sum(r["met"] for r in rows),
        "total": len(rows),
        "proposable": all(r["met"] for r in rows),
        "path_a": "pending" if obs is None else "recorded",
        "conditions": rows,
    }
