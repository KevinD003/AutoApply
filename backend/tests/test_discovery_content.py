"""D125 (Slice D): complete, structured, *safe* job detail.

The sanitizer turns untrusted HTML into plain blocks and drops anything that could run, fetch or
submit; salary is read with its provenance and never invented, annualized or converted; and the
detail consolidation prefers the freshest real description while keeping missing data missing.
Pure-Python (no DB): the API-level integration lives in test_jobs_content_detail.py."""

from app.modules.discovery import content as c
from app.modules.discovery.boards import normalize as board_normalize
from app.modules.discovery.provider import FreehireApiProvider

# ── Sanitizer: nothing active, nothing fetched ───────────────────────────────────────────────


def _all_spans(blocks):
    spans = []
    for b in blocks:
        if b.get("type") == "list":
            for item in b["items"]:
                spans += item
        else:
            spans += b.get("spans", [])
    return spans


def test_scripts_styles_and_media_are_dropped_whole():
    html = (
        "<p>Before</p>"
        "<script>window.x=1</script>"
        "<style>.a{color:red}</style>"
        "<iframe src='https://evil.test'></iframe>"
        "<img src='x' onerror='alert(1)'>"
        "<svg><use href='#x'/></svg>"
        "<p>After</p>"
    )
    blocks = c.to_blocks(html)
    text = c.blocks_text(blocks)
    assert "Before" in text and "After" in text
    assert "window.x" not in text and "color:red" not in text
    # No block or span references anything fetchable.
    assert all(b["type"] in ("paragraph", "heading", "list") for b in blocks)
    for span in _all_spans(blocks):
        assert set(span) <= {"text", "bold", "italic", "href"}


def test_forms_and_controls_are_dropped():
    html = "<p>Keep</p><form><input name='x'><button>Go</button><textarea>t</textarea></form>"
    assert c.blocks_text(c.to_blocks(html)) == "Keep"


def test_dangerous_links_lose_their_href_but_keep_text():
    for bad in ("javascript:alert(1)", "data:text/html,<b>", "vbscript:x", "file:///etc/passwd"):
        blocks = c.to_blocks(f'<p>click <a href="{bad}">here</a></p>')
        # The text survives; no span carries the dangerous link (adjacent plain spans merge).
        assert "here" in c.blocks_text(blocks), bad
        assert all(s.get("href") is None for s in _all_spans(blocks)), bad


def test_safe_links_are_kept():
    blocks = c.to_blocks('<p>see <a href="https://jobs.example.test/x">role</a> and '
                         '<a href="mailto:a@example.test">mail</a></p>')  # fmt: skip
    hrefs = {s.get("href") for s in _all_spans(blocks) if s.get("href")}
    assert hrefs == {"https://jobs.example.test/x", "mailto:a@example.test"}


def test_safe_link_helper():
    assert c.safe_link("https://a.test/x") == "https://a.test/x"
    assert c.safe_link("//cdn.test/x") == "https://cdn.test/x"  # scheme-relative → https
    assert c.safe_link("javascript:x") is None
    assert c.safe_link("/relative/path") is None  # no origin of its own: dropped
    assert c.safe_link("#anchor") is None
    assert c.safe_link("x" * 3000) is None


def test_headings_lists_and_emphasis_preserved():
    html = ("<h2>Responsibilities</h2><ul><li>Do <b>one</b></li><li>Do two</li></ul>"
            "<h3>Requirements</h3><ol><li>Have <em>this</em></li></ol>")  # fmt: skip
    blocks = c.to_blocks(html)
    kinds = [(b["type"], b.get("level") or b.get("ordered")) for b in blocks]
    assert kinds == [("heading", 2), ("list", False), ("heading", 3), ("list", True)]
    first_list = blocks[1]
    assert first_list["items"][0][0]["text"] == "Do "
    assert first_list["items"][0][1] == {"text": "one", "bold": True}
    assert blocks[0]["spans"][0]["text"] == "Responsibilities"


def test_entity_encoded_html_is_unescaped_then_parsed():
    # Greenhouse returns its body entity-encoded (the raw JSON holds "&lt;p&gt;...").
    gh = (
        "&lt;p&gt;Help &lt;b&gt;customers&lt;/b&gt;&lt;/p&gt;"
        "&lt;ul&gt;&lt;li&gt;Email&lt;/li&gt;&lt;/ul&gt;"
    )
    blocks = c.to_blocks(gh, unescape=True)
    assert blocks[0]["type"] == "paragraph"
    assert any(s.get("bold") and s["text"] == "customers" for s in blocks[0]["spans"])
    assert blocks[1]["type"] == "list" and blocks[1]["items"][0][0]["text"] == "Email"


def test_whitespace_is_collapsed():
    blocks = c.to_blocks("<p>a   lot\n\tof     space</p>")
    assert blocks[0]["spans"][0]["text"] == "a lot of space"


def test_plain_text_becomes_paragraphs():
    blocks = c.to_blocks("First paragraph.\n\nSecond paragraph.")
    assert [b["spans"][0]["text"] for b in blocks] == ["First paragraph.", "Second paragraph."]


def test_empty_and_malformed_inputs_never_raise():
    assert c.to_blocks("") == []
    assert c.to_blocks("   ") == []
    assert c.to_blocks(None) == []
    # Unbalanced tags: whatever parsed, no exception.
    assert c.blocks_text(c.to_blocks("<p>open <b>bold <ul><li>x")) != ""


def test_block_and_text_caps_bound_the_output():
    huge = "<p>x</p>" * (c.MAX_BLOCKS + 200)
    assert len(c.to_blocks(huge)) <= c.MAX_BLOCKS
    long_text = c.to_blocks("<p>" + "y " * 60_000 + "</p>")
    assert sum(len(s["text"]) for s in _all_spans(long_text)) <= c.MAX_TEXT


# ── Salary: structured, enrichment, extracted — provenance preserved, nothing invented ───────


def test_lever_structured_salary():
    s = c.salary_from_lever(
        {
            "salaryRange": {
                "min": 120000,
                "max": 150000,
                "currency": "USD",
                "interval": "per-year-salary",
            }
        }  # fmt: skip
    )
    assert s["source"] == "structured"
    assert s["currency"] == "USD" and s["period"] == "year"
    assert s["min"] == "120000" and s["max"] == "150000"
    assert s["kind"] == "unspecified"


def test_lever_salary_unknown_interval_keeps_raw_and_no_period():
    s = c.salary_from_lever({"salaryRange": {"min": 10, "max": 20, "interval": "per-fortnight"}})
    assert s["period"] is None and s["period_raw"] == "per-fortnight"


def test_lever_salary_description_fallback():
    s = c.salary_from_lever({"salaryDescriptionPlain": "Pay is $90,000 per year."})
    assert s["source"] == "extracted" and s["period"] == "year"


def test_lever_no_salary_is_none():
    assert c.salary_from_lever({"text": "Role"}) is None


def test_freehire_enrichment_salary_is_attributed_to_the_provider():
    s = c.salary_from_enrichment(
        {
            "salary_min": 80000,
            "salary_max": 95000,
            "salary_currency": "EUR",
            "salary_period": "year",
        }  # fmt: skip
    )
    assert s["source"] == "enrichment"
    assert "model" in s["basis"].lower()
    assert s["currency"] == "EUR" and s["period"] == "year"


def test_extracted_range_preserves_original_and_does_not_annualize():
    s = c.salary_from_text("The range is $120,000 - $150,000 per year, plus benefits.")
    assert s["source"] == "extracted"
    assert s["min"] == "120,000" and s["max"] == "150,000"  # kept exactly, not reformatted
    assert s["currency_symbol"] == "$" and s["currency"] is None  # '$' alone stays ambiguous
    assert s["period"] == "year"
    assert "120,000" in s["text"]


def test_extracted_various_currencies_and_periods():
    assert c.salary_from_text("£45,000 per annum")["currency"] == "GBP"
    assert c.salary_from_text("£45,000 per annum")["period"] == "year"
    assert c.salary_from_text("€50 per hour")["currency"] == "EUR"
    assert c.salary_from_text("€50 per hour")["period"] == "hour"
    assert c.salary_from_text("USD 90k annually")["currency"] == "USD"
    assert c.salary_from_text("up to $50/hr")["period"] == "hour"
    assert c.salary_from_text("up to $50/hr")["amount"] == "50"


def test_extracted_distinguishes_base_and_bonus_and_equity():
    assert c.salary_from_text("Base salary of $100,000")["kind"] == "base"
    assert c.salary_from_text("Annual bonus of $10,000")["kind"] == "bonus"
    assert c.salary_from_text("Plus equity worth $40,000")["kind"] == "equity"
    assert c.salary_from_text("$200,000 OTE")["kind"] == "ote"


def test_no_salary_in_text_returns_none():
    assert c.salary_from_text("Competitive salary and great benefits.") is None
    assert c.salary_from_text("Join our team of 50 people in 3 offices.") is None
    assert c.salary_from_text("") is None


# ── Provider content builders ────────────────────────────────────────────────────────────────


def test_greenhouse_content_sanitizes_and_reads_structure():
    raw = {
        "content": "&lt;p&gt;Lead the team.&lt;/p&gt;&lt;script&gt;alert(1)&lt;/script&gt;"
        "&lt;p&gt;Pay is $130,000 per year.&lt;/p&gt;",
        "departments": [{"name": "Engineering"}],
        "offices": [{"name": "Remote"}, {"name": "Berlin"}],
    }
    out = c.greenhouse_content(raw)
    assert "alert(1)" not in c.blocks_text(out["description_blocks"])
    assert out["department"] == "Engineering"
    assert out["locations"] == ["Remote", "Berlin"]
    assert out["salary"]["source"] == "extracted" and out["salary"]["period"] == "year"


def test_lever_content_uses_the_sources_own_sections_and_structured_salary():
    raw = {
        "description": "<p>About the role.</p>",
        "lists": [
            {"text": "Responsibilities", "content": "<ul><li>Build things</li></ul>"},
            {"text": "Requirements", "content": "<ul><li>Experience</li></ul>"},
        ],
        "additional": "<p>Equal opportunity employer.</p>",
        "categories": {"department": "Product", "allLocations": ["London", "Remote - EU"]},
        "salaryRange": {
            "min": 60000,
            "max": 80000,
            "currency": "GBP",
            "interval": "per-year-salary",
        },  # fmt: skip
    }
    out = c.lever_content(raw)
    headings = [s["heading"] for s in out["sections"]]
    assert headings[:2] == ["Responsibilities", "Requirements"]
    assert out["sections"][-1]["heading"] is None  # the `additional` block, unlabelled
    assert out["department"] == "Product"
    assert out["locations"] == ["London", "Remote - EU"]
    assert out["salary"]["source"] == "structured" and out["salary"]["currency"] == "GBP"


def test_freehire_content_reads_description_and_enrichment():
    raw = {
        "description": "<p>Analyse data.</p>",
        "cities": ["Toronto", "Vancouver"],
        "enrichment": {
            "seniority": "Mid",
            "category": "Data",
            "salary_min": 90000,
            "salary_max": 110000,
            "salary_currency": "CAD",
            "salary_period": "year",
        },  # fmt: skip
    }
    out = c.freehire_content(raw, raw["enrichment"])
    assert out["seniority"] == "Mid" and out["department"] == "Data"
    assert out["salary"]["source"] == "enrichment" and out["salary"]["currency"] == "CAD"
    assert out["locations"] == ["Toronto", "Vancouver"]


def test_missing_fields_stay_absent_never_guessed():
    out = c.freehire_content({"description": "<p>Hi.</p>"}, {})
    assert "salary" not in out and "seniority" not in out and "department" not in out
    assert out["description_blocks"]  # the one thing present


# ── Normalizers carry content through ────────────────────────────────────────────────────────


def test_freehire_normalizer_populates_content():
    raw = {
        "public_slug": "abc-123",
        "title": "Data Analyst",
        "company": "Contoso (fictional)",
        "url": "https://jobs.example.test/contoso/analyst",
        "description": "<p>Build <b>weekly</b> reports. Pay $70,000 per year.</p>",
        "enrichment": {"visa_sponsorship": True, "seniority": "Junior"},
    }
    n = FreehireApiProvider(base_url="http://127.0.0.1:8799").normalize_job(raw)
    assert n.content["description_blocks"]
    assert n.content["seniority"] == "Junior"
    assert n.content["salary"]["source"] == "extracted"
    d = n.as_dict()
    assert d["content"]["salary"]["period"] == "year"  # survives serialization


def test_board_normalizers_populate_content():
    gh = board_normalize(
        "greenhouse",
        "src1",
        "Acme (fictional)",
        {
            "id": 7,
            "title": "Engineer",
            "location": {"name": "Remote"},
            "absolute_url": "https://boards.example.test/acme/7",
            "content": "&lt;p&gt;Great role.&lt;/p&gt;",
            "departments": [],
            "offices": [],
        },  # fmt: skip
    )
    assert gh.content["description_blocks"]
    lv = board_normalize(
        "lever",
        "src2",
        "Globex (fictional)",
        {
            "id": "p-1",
            "text": "Nurse",
            "hostedUrl": "https://jobs.example.test/globex/p-1",
            "description": "<p>Care for patients.</p>",
            "lists": [{"text": "Duties", "content": "<ul><li>Help</li></ul>"}],
            "categories": {"location": "Shelbyville"},
        },  # fmt: skip
    )
    assert lv.content["sections"][0]["heading"] == "Duties"


# ── Consolidation for the detail view ────────────────────────────────────────────────────────


def _disc(normalized, stale=False, last_seen="2026-11-01T00:00:00+00:00"):
    return {"normalized": normalized, "stale": stale, "last_seen_at": last_seen}


def test_consolidate_prefers_discovery_description_over_own_text():
    normalized = {
        "job_url": "https://jobs.example.test/x",
        "employment_type": "Full-time",
        "content": {
            "description_blocks": [{"type": "paragraph", "spans": [{"text": "Full posting."}]}],
            "salary": {
                "source": "structured",
                "currency": "USD",
                "period": "year",
                "min": "100000",
                "max": "120000",
                "kind": "unspecified",
            },  # fmt: skip
        },
    }
    out = c.consolidate_detail(
        own_description="short summary", own={"url": None}, discovered=[_disc(normalized)]
    )
    assert out["origin"] == "discovery"
    assert c.blocks_text(out["description"]["blocks"]) == "Full posting."
    assert out["salary"]["source"] == "structured"
    assert out["facts"]["employment_type"] == "Full-time"
    assert out["facts"]["source_url"] == "https://jobs.example.test/x"


def test_consolidate_prefers_fresh_over_stale():
    fresh = _disc(
        {"content": {"description_blocks": [{"type": "paragraph", "spans": [{"text": "Fresh"}]}]}},
        stale=False,
        last_seen="2026-10-01T00:00:00+00:00",
    )
    stale = _disc(
        {"content": {"description_blocks": [{"type": "paragraph", "spans": [{"text": "Stale"}]}]}},
        stale=True,
        last_seen="2026-11-01T00:00:00+00:00",
    )
    out = c.consolidate_detail(own_description=None, own={}, discovered=[stale, fresh])
    assert c.blocks_text(out["description"]["blocks"]) == "Fresh"


def test_consolidate_falls_back_to_own_text_and_extracts_its_salary():
    out = c.consolidate_detail(
        own_description="We offer $55,000 per year for this role.",
        own={"employer": "Acme", "location": "Remote"},
        discovered=[],
    )
    assert out["origin"] == "your_entry"
    assert out["description"]["blocks"]
    assert out["salary"]["source"] == "extracted" and out["salary"]["period"] == "year"


def test_consolidate_with_nothing_has_no_salary():
    out = c.consolidate_detail(own_description=None, own={}, discovered=[])
    assert out["origin"] == "none"
    assert out["salary"] is None  # the UI then shows SALARY_ABSENT
    assert out["description"]["blocks"] == []
    assert c.SALARY_ABSENT == "Salary not provided."


def test_consolidate_salary_from_sibling_when_best_description_has_none():
    rich_no_salary = _disc(
        {"content": {"description_blocks": [{"type": "paragraph", "spans": [{"text": "Role."}]}]}},
        last_seen="2026-11-02T00:00:00+00:00",
    )
    thin_with_salary = _disc(
        {
            "content": {
                "salary": {
                    "source": "enrichment",
                    "currency": "USD",
                    "period": "year",
                    "min": "90000",
                    "max": None,
                    "kind": "unspecified",
                }
            }
        },  # fmt: skip
        last_seen="2026-10-01T00:00:00+00:00",
    )
    out = c.consolidate_detail(
        own_description=None, own={}, discovered=[rich_no_salary, thin_with_salary]
    )
    assert c.blocks_text(out["description"]["blocks"]) == "Role."
    assert out["salary"]["source"] == "enrichment"  # picked up from the sibling record
