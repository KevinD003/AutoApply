"""The repository facts behind provider admission (providers/admission.py), checked in CI only:
admission reads Python constants at run time, and these tests prove the constants match the code,
the fixtures, the tests and the docs they stand for. Identity cases are fictional URLs that are
never requested; nothing here contacts anything external."""

import ast
import inspect
import itertools
import pathlib
import re
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.modules.audit.service import sanitize
from app.modules.discovery import provider as discovery
from app.modules.execution import policy, rehearsal
from app.modules.jobs.canonical import (
    ATS_DISPLAY,
    ATS_NAMES,
    canonicalize_url,
    dedupe_key,
    detect_ats,
)
from app.modules.preparation import gh_readonly
from app.modules.providers import admission, evidence, registry, routing, wording
from app.modules.providers.model import Kind, matrix
from tests.execution_harness import BASE
from tests.provider_contracts import IDENTITY_CASES, PROBES, RECEIPT_KEYS

ROOT = pathlib.Path(__file__).resolve().parents[2]
ARCH = ROOT / "docs" / "provider-architecture.md"
RUNS_DOC = ROOT / "docs" / "greenhouse-readonly-compatibility-proposal.md"
DECISIONS = ROOT / "docs" / "decisions.md"
ADAPTERS = ROOT / "backend" / "app" / "modules" / "execution" / "adapters"
ELSEWHERE = "https://careers.example.com"  # a non-fixture origin; never contacted


def _identity(url: str):
    a = detect_ats(canonicalize_url(url))
    return a.provider, a.company, a.requisition_id


def _key(url: str) -> str:
    return dedupe_key(canonical_url=canonicalize_url(url), employer=None, title=None,
                      location=None)  # fmt: skip


# -- identity --------------------------------------------------------------------------------------


def test_every_ats_name_has_the_full_identity_contract():
    assert set(IDENTITY_CASES) == ATS_NAMES == admission.IDENTITY_CONTRACT == set(ATS_DISPLAY)
    for ats, case in IDENTITY_CASES.items():
        assert {"positive", "variants", "tracking", "not_ats", "foreign_form"} <= set(case), ats
        assert case["variants"] and len(case["not_ats"]) >= 3, ats


@pytest.mark.parametrize("ats", sorted(IDENTITY_CASES))
def test_identity_contract(ats):
    case = IDENTITY_CASES[ats]
    url, (company, req) = case["positive"]
    assert _identity(url) == (ats, company, req)
    for variant in case["variants"]:  # case, region and suffix variants: the same posting
        assert _identity(variant) == (ats, company, req), variant
        assert _key(variant) == _key(url), variant
    # Tracking parameters are dropped, so they never split a job (its canonical URL, which
    # discovery matches on, and its key).
    assert canonicalize_url(url + case["tracking"]) == canonicalize_url(url)
    assert _key(url + case["tracking"]) == _key(url)
    for other in case["not_ats"]:  # the vendor's site, non-postings and lookalike hosts
        assert _identity(other)[0] == "unknown", other
    parts = url.split("/")
    fixture = f"{BASE}/{'/'.join(parts[3:])}"
    assert _identity(fixture)[0] == "unknown"  # a local fixture is never identified as an ATS


@pytest.mark.parametrize("ats", sorted(IDENTITY_CASES))
def test_identity_parts_are_bounded(ats):
    """A posting whose company part is longer than the key column still gets one stable key."""
    url, (company, _) = IDENTITY_CASES[ats]["positive"]
    long_url = url.replace(f"/{company}/", f"/{'a' * 300}/", 1).replace("acme.", f"{'a' * 300}.", 1)
    assert _identity(long_url)[0] == ats
    key = _key(long_url)
    assert len(key) <= 200 and key == _key(long_url) and key != _key(url)
    assert key.startswith("ats:h:")  # the kind, then a digest of the whole key


@pytest.mark.parametrize("ats", sorted(IDENTITY_CASES))
def test_a_job_on_each_ats_is_never_routed_with_a_foreign_form(ats):
    url, _ = IDENTITY_CASES[ats]["positive"]
    expected = IDENTITY_CASES[ats]["foreign_form"]
    origin = "/".join(url.split("/")[:3])
    for source in policy.FORM_SOURCE_ADAPTERS:
        if routing.FORM_SOURCE_ATS[source] == ats:
            continue  # its own source
        d = routing.decide({"origin": origin, "url": url, "submit_url": url,
                            "form_source": source})  # fmt: skip
        assert (d.route, d.reason) == ("manual_handoff", expected), (ats, source)
    if expected is None:  # no other ATS's form source exists
        assert {routing.FORM_SOURCE_ATS[s] for s in policy.FORM_SOURCE_ADAPTERS} == {ats}


def test_every_known_gap_is_still_real():
    """A fix without removing its entry fails, and so does a removal without a fix."""
    assert set(PROBES) == set(admission.KNOWN_GAPS)
    assert {code for code, probe in PROBES.items() if probe()} == set(admission.KNOWN_GAPS)


def test_every_known_gap_names_real_providers_or_ats():
    for code, members in admission.KNOWN_GAPS.items():
        assert members <= set(registry.PROVIDERS) | ATS_NAMES | {admission.ANY_ATS}, code


# -- fixtures, code tables and versions ------------------------------------------------------------


def test_every_tested_against_path_exists():
    for p in registry.PROVIDERS.values():
        for path in p.tested_against:
            assert (ROOT / path).exists(), (p.name, path)
            assert not path.startswith("/") and ".." not in path, (p.name, path)


def test_the_code_tables_are_the_runner_tables():
    """Each table admission reads names exactly the code that exists: a new adapter missing from
    one of them, or an entry with no code behind it, fails here."""
    from app.modules.execution import runner

    implemented = {k for k, p in registry.PROVIDERS.items()
                   if p.stage == "implemented" and p.kind in (Kind.browser, Kind.api)}  # fmt: skip
    assert set(policy.ADAPTER_VERSIONS) == implemented
    assert set(policy.ADAPTER_VERSIONS) == set(runner.ADAPTERS) | set(runner.API_ADAPTERS)
    assert set(policy.CAPABILITIES) == set(runner.ADAPTERS) == registry_keys(Kind.browser)
    assert rehearsal.API_ROUTE_ADAPTERS == set(runner.API_ADAPTERS) == registry_keys(Kind.api)
    assert set(routing.API_IDENTITY) == set(routing.API_CREDENTIALS) == set(runner.API_ADAPTERS)
    for key, cls in {**runner.ADAPTERS, **runner.API_ADAPTERS}.items():
        assert cls.name == key
    assert set(discovery.PROVIDERS) == registry_keys(Kind.discovery)
    assert {gh_readonly.PROVIDER} == registry_keys(Kind.observation)
    assert set(rehearsal.PATH_RULES) == rehearsal.BOARD_ADAPTERS | {"fixture_ats"}


def registry_keys(kind: Kind) -> set[str]:
    return {k for k, p in registry.PROVIDERS.items() if p.kind == kind and p.stage == "implemented"}


@pytest.mark.parametrize(
    "adapter,url",
    [
        ("fixture_ats", f"{BASE}/apply/clinic"),
        ("greenhouse_hosted", f"{BASE}/gh/examplehealth/jobs/4012001"),
        ("greenhouse_dom", f"{BASE}/gh2/northwind/jobs/5020001"),
        ("fake_api", f"{BASE}/gh2/northwind/jobs/5020001"),
    ],
)
def test_every_path_rule_reads_its_own_fixture_destination(adapter, url):
    assert set(rehearsal.PATH_RULES) == {"fixture_ats", "greenhouse_hosted", "greenhouse_dom",
                                         "fake_api"}  # fmt: skip
    path = rehearsal.execution_path({"origin": BASE, "url": url}, adapter)
    assert path is not None and path.adapter == adapter


def test_legacy_versions_cover_only_the_original_adapters():
    assert set(policy.LEGACY_VERSIONS) == admission.ORIGINAL_LEGACY
    assert policy.LEGACY_VERSIONS == {
        "fixture_ats": "fixture-ats-1+html-v1",
        "greenhouse_hosted": "greenhouse-hosted-1+greenhouse-v1",
    }


def _returned_dict_keys(fn: ast.FunctionDef) -> set[str]:
    keys = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict):
            keys |= {k.value for k in n.value.keys if isinstance(k, ast.Constant)}
    return keys


def test_every_adapter_keeps_only_its_declared_receipt_keys():
    from app.modules.execution import runner

    for key, cls in {**runner.ADAPTERS, **runner.API_ADAPTERS}.items():
        tree = ast.parse(inspect.getsource(cls))
        fns = [n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "receipt_evidence"]  # fmt: skip
        if not fns:  # inherited
            base = next(b for b in cls.__mro__[1:] if "receipt_evidence" in b.__dict__)
            fns = [n for n in ast.walk(ast.parse(inspect.getsource(base)))
                   if isinstance(n, ast.FunctionDef) and n.name == "receipt_evidence"]  # fmt: skip
        assert _returned_dict_keys(fns[0]) == RECEIPT_KEYS[key], key
    assert set(RECEIPT_KEYS) == set(runner.ADAPTERS) | set(runner.API_ADAPTERS)


# -- routing, audit --------------------------------------------------------------------------------


def test_every_form_source_is_generic_or_names_its_ats_and_adapter():
    sources = set(policy.FORM_SOURCE_ADAPTERS)
    assert set(wording.FORM_SOURCE_LABELS) == (policy.GENERIC_FORM_SOURCES - {None}) | sources
    assert set(routing.FORM_SOURCE_ATS) == sources
    for source, adapter in policy.FORM_SOURCE_ADAPTERS.items():
        assert routing.FORM_SOURCE_ATS[source] == registry.get(adapter).ats, source
    assert registry.get(policy.GENERIC_ADAPTER).ats is None


def test_an_unknown_form_source_is_refused_not_given_to_the_fixture_adapter():
    dest = {"origin": BASE, "url": f"{BASE}/apply/clinic", "submit_url": f"{BASE}/apply/clinic",
            "form_source": "example_form"}  # fmt: skip
    with pytest.raises(policy.UnsupportedDestination) as e:
        policy.adapter_for(dest)
    assert e.value.code == "no_adapter"
    d = routing.decide(dest)
    assert (d.route, d.provider, d.reason) == ("manual_handoff", "manual_handoff", "no_adapter")
    approval = SimpleNamespace(adapter="fixture_ats", adapter_version=policy.ADAPTER_VERSIONS[
        "fixture_ats"], user_id=None)  # fmt: skip
    with pytest.raises(policy.UnsupportedDestination):
        policy.check_binding(approval, dest)
    for source in policy.GENERIC_FORM_SOURCES:  # the generic sources still run as before
        assert policy.adapter_for({**dest, "form_source": source}) == policy.GENERIC_ADAPTER


def test_every_route_kind_is_audited_by_name():
    tree = ast.parse(inspect.getsource(routing))
    routes = {n.args[0].value for n in ast.walk(tree)
              if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "RouteDecision"
              and n.args and isinstance(n.args[0], ast.Constant)}  # fmt: skip
    assert routes and routes <= set(routing.AUDIT_ROUTE)


def test_every_route_decision_carries_recordable_metadata(monkeypatch):
    sources = (None, *sorted(s for s in policy.GENERIC_FORM_SOURCES if s),
               *policy.FORM_SOURCE_ADAPTERS, "example_form")  # fmt: skip
    urls = (f"{BASE}/gh2/northwind/jobs/5020001", IDENTITY_CASES["lever"]["positive"][0],
            IDENTITY_CASES["ashby"]["positive"][0], None)  # fmt: skip
    for env in ("test", "production"):
        monkeypatch.setattr(get_settings(), "env", env)
        for origin, source, url in itertools.product((BASE, ELSEWHERE, None), sources, urls):
            submit = f"{origin}/submit" if origin else None
            d = routing.decide({"origin": origin, "url": url, "submit_url": submit,
                                "form_source": source})  # fmt: skip
            meta = routing.route_meta(d)
            assert sanitize(meta) == meta, meta
            assert d.provider in registry.PROVIDERS


# -- recorded evidence -----------------------------------------------------------------------------


def _runs_table() -> dict[int, str]:
    text = RUNS_DOC.read_text().split("## Runs", 1)[1].split("\n\n", 2)[1]
    rows = {}
    for line in text.splitlines():
        m = re.match(r"\| CI read-only #(\d+)\b", line)
        if m:
            rows[int(m.group(1))] = line
    return rows


def test_the_recorded_runs_are_the_documented_runs():
    """evidence.READ_ONLY_RUNS is the Runs table: one record per CI read-only run; single-use
    exactly where the row says "authorized once"; completed exactly where it says completed."""
    rows = _runs_table()
    assert sorted(rows) == [r.run for r in evidence.READ_ONLY_RUNS] == list(range(1, 10))
    completed = re.compile(r"\*\*completed\b|observation outcome `completed`")
    for r in evidence.READ_ONLY_RUNS:
        line = rows[r.run]
        assert ("authorized once" in line) == (r.approval == "single_use"), r.run
        assert bool(completed.search(line)) == (r.outcome == "completed"), r.run
    assert {r.run for r in evidence.READ_ONLY_RUNS if r.approval == "not_single_use"} == {1, 2, 3}


def test_every_doc_review_names_a_recorded_decision():
    decisions = set(re.findall(r"^## (D\d+)\b", DECISIONS.read_text(), re.M))
    for r in evidence.DOC_REVIEWS:
        assert r.ats in ATS_NAMES and r.decision in decisions, r


# -- the documentation is the registry -------------------------------------------------------------


def _doc_table(text: str, heading: str) -> list[list[str]]:
    block = text.split(heading, 1)[1].split("\n|", 1)[1].split("\n\n", 1)[0]
    rows = [r for r in ("|" + block).splitlines() if r.startswith("|")]
    return [[c.strip() for c in r.strip("|").split("|")] for r in rows]


def test_the_documented_capability_matrix_is_the_registry():
    header, _, *rows = _doc_table(ARCH.read_text(), "### Capability matrix (registry as committed)")
    columns = {"FA": ["fixture_ats"], "GH": ["greenhouse_hosted"], "GD": ["greenhouse_dom"],
               "API": ["fake_api"], "RO": ["greenhouse_readonly"],
               "FH": ["freehire_mock", "freehire"], "MH": ["manual_handoff"]}  # fmt: skip
    assert header[1:] == list(columns)
    unplanned = {k for k, p in registry.PROVIDERS.items() if p.stage != "planned"}
    assert {k for keys in columns.values() for k in keys} == unplanned
    seen = set()
    for name, *cells in rows:
        seen.add(name)
        for col, cell in zip(columns, cells, strict=True):
            for key in columns[col]:
                spec = registry.get(key)
                if name == "real_destinations_enabled":
                    assert cell == ("yes" if spec.real_destinations_enabled else "no"), key
                else:
                    level = cell.strip("*").replace("–", "none")
                    assert level == matrix(spec)[name], (name, key)
    assert seen == set(matrix(registry.get("fixture_ats"))) | {"real_destinations_enabled"}


def test_the_documented_support_states_today_are_the_registry():
    line = next(x for x in ARCH.read_text().split("\n- ") if x.startswith("**Today:**"))
    line = " ".join(line.split())
    documented = {}
    for part in line.removeprefix("**Today:**").split(";"):
        names, state = part.rsplit(" are " if " are " in part else " is ", 1)
        for n in re.findall(r"`([a-z_]+)`", names):
            documented[n] = re.search(r"`([a-z_]+)`", state).group(1)
    assert documented == {k: wording.support_state(p) for k, p in registry.PROVIDERS.items()}


# -- fixture scenarios -----------------------------------------------------------------------------


def _functions(path: pathlib.Path) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef)}


def _calls(fn: ast.FunctionDef) -> set[str]:
    return {n.func.id for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}  # fmt: skip


def _reads_ledger(fn: ast.FunctionDef, module: dict[str, ast.FunctionDef], depth: int = 2) -> bool:
    if any(isinstance(n, ast.Attribute) and n.attr == "ledger" for n in ast.walk(fn)):
        return True
    return depth > 0 and any(_reads_ledger(module[c], module, depth - 1)
                             for c in _calls(fn) if c in module)  # fmt: skip


def _names(fn: ast.FunctionDef, module: dict[str, ast.FunctionDef], depth: int = 1) -> str:
    text = ast.unparse(fn)
    if depth > 0:
        text += "".join(_names(module[c], module, depth - 1) for c in _calls(fn) if c in module)
    return text


def test_every_required_scenario_is_a_ledger_test_or_a_recorded_gap():
    """Each execution provider's required scenarios (from its fixture levels) map to a test that
    exists, reads the receiver's ledger (itself or through a helper in its module) and builds
    an application for that provider, or are recorded in SCENARIO_GAPS: exactly one of the two."""
    from tests.provider_contracts import BUILDERS, SCENARIO_TESTS

    executors = {k for k, p in registry.PROVIDERS.items()
                 if p.stage == "implemented" and p.kind in (Kind.browser, Kind.api)}  # fmt: skip
    assert set(BUILDERS) == executors
    required = {(k, s) for k in executors
                for s in admission.required_scenarios(registry.get(k))}  # fmt: skip
    gaps = set(admission.SCENARIO_GAPS)
    assert not gaps & set(SCENARIO_TESTS)
    assert set(SCENARIO_TESTS) | gaps == required
    # A gap may be waived only for a pre-I2 provider whose frozen claim reached fixture_only.
    fixture_or_more = {k for k, s in admission.PRE_ADMISSION.items()
                       if admission._rank(s) >= admission._rank("fixture_only")}  # fmt: skip
    assert {k for k, _ in gaps} <= fixture_or_more
    for (key, scenario), node in SCENARIO_TESTS.items():
        path, name = node.split("::")
        module = _functions(ROOT / "backend" / path)
        assert name in module, node
        fn = module[name]
        assert _reads_ledger(fn, module), (key, scenario, node)
        assert any(b in _names(fn, module) for b in BUILDERS[key]), (key, scenario, node)


def test_an_over_long_identity_is_never_a_server_error(api):
    """An ATS company or posting id longer than its column, and a URL that canonicalizes past
    its own (scheme, encoded query), were a 500 (an unhandled DataError). Fictional URLs."""
    long_company = "https://boards.greenhouse.io/" + "a" * 180 + "/jobs/4000001"
    long_posting = "https://boards.greenhouse.io/acme/jobs/" + "9" * 230
    for url in (long_company, long_posting):
        new = {"url": url, "title": "Engineer", "employer": "Acme Example (fictional)"}
        first = api.post("/jobs", json=new)
        assert first.status_code == 201, first.text
        assert api.post("/jobs", json=new).status_code == 200  # the same job, recognised
    job = api.post("/jobs", json={"url": long_posting, "title": "x"}).json()["job"]
    assert job["ats_provider"] == "greenhouse"
    grows = "http://careers.example.com/openings?q=" + "é" * 700  # under 2048 as typed
    r = api.post("/jobs", json={"url": grows, "title": "Engineer"})
    assert r.status_code == 400 and r.json()["detail"] == "URL is too long"
