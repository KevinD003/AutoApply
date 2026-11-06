"""D120 bridge hardening: the package->plan bridge must never trust a section dict that did not come
from our own freeze. These prove that malformed content, an unknown section kind or field name, an
unsafe or missing root, a colliding row identity and a bad value shape are each REFUSED (a clean
``Refused``, never a KeyError and never silently driven), and that a frozen section's own row
controls are told apart from an unexpected required control. Pure logic: no browser, no database.
"""

import copy

import pytest

from app.modules.execution.adapters.greenhouse_dom import GreenhouseDomAdapter
from app.modules.execution.adapters.greenhouse_sections import (
    Refused,
    plan_content_section,
    section_root,
    validate_content_section,
)


def _good_content() -> dict:
    return {
        "kind": "education",
        "root": "#education-section",
        "rows": [
            {
                "record_id": "r1",
                "fields": {
                    "school_name_id": {"status": "resolved", "value": {"id": "s1"},
                                       "display": "State University"},
                    "degree_id": {"status": "resolved", "value": {"id": "d1"},
                                  "display": "Bachelor's Degree"},
                    "discipline_id": {"status": "resolved", "value": {"id": "x1"},
                                      "display": "Computer Science"},
                    "start_date": {"status": "resolved", "value": {"month": 9, "year": 2014},
                                   "display": "09/2014"},
                    "end_date": {"status": "resolved", "value": {"month": 5, "year": 2018},
                                 "display": "05/2018"},
                },
            }
        ],
    }  # fmt: skip


def test_good_content_validates_and_plans():
    data = _good_content()
    validate_content_section(data)  # does not raise
    assert section_root(data) == "#education-section"
    plan = plan_content_section(data)
    assert plan.kind == "education" and len(plan.rows) == 1


@pytest.mark.parametrize("bad", ["not-a-dict", 42, None, [], ()])
def test_non_object_content_refuses(bad):
    with pytest.raises(Refused):
        validate_content_section(bad)
    with pytest.raises(Refused):
        section_root(bad)


@pytest.mark.parametrize("kind", [None, "", "skills", "references", "education "])
def test_unknown_section_kind_refuses(kind):
    data = _good_content()
    data["kind"] = kind
    with pytest.raises(Refused):
        plan_content_section(data)


@pytest.mark.parametrize(
    "root",
    [None, "", "education-section", ".education-section", "#edu section",
     "#education-section .row", "div#x", "//div[@id='x']", "#", "#1bad", 42],
)  # fmt: skip
def test_unsafe_or_missing_root_refuses(root):
    """The root is used live as a Playwright locator, so only a plain ``#id`` is trusted -- never an
    arbitrary CSS or XPath selector carried through package content."""
    data = _good_content()
    data["root"] = root
    with pytest.raises(Refused):
        validate_content_section(data)
    with pytest.raises(Refused):
        section_root(data)


def test_unknown_field_name_refuses():
    # A field we never freeze has no control type we would drive; refuse, do not silently drop.
    data = _good_content()
    data["rows"][0]["fields"]["evil--0"] = {"status": "resolved", "value": {"text": "x"},
                                            "display": "x"}  # fmt: skip
    with pytest.raises(Refused):
        plan_content_section(data)


def test_duplicate_row_identity_refuses():
    data = _good_content()
    data["rows"].append(copy.deepcopy(data["rows"][0]))  # a second row sharing record_id "r1"
    with pytest.raises(Refused):
        validate_content_section(data)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(rows="not-a-list"),
        lambda d: d["rows"].append("not-an-object"),
        lambda d: d["rows"][0].pop("record_id"),
        lambda d: d["rows"][0].update(record_id=""),
        lambda d: d["rows"][0].update(record_id=7),
        lambda d: d["rows"][0].update(fields="not-an-object"),
        lambda d: d["rows"][0]["fields"].update(school_name_id="not-an-object"),
        lambda d: d["rows"][0]["fields"]["school_name_id"].pop("status"),
    ],
)
def test_malformed_rows_refuse(mutate):
    data = _good_content()
    mutate(data)
    with pytest.raises(Refused):
        plan_content_section(data)


@pytest.mark.parametrize(
    "value",
    [{"month": 9}, {"year": 2014}, {"month": 13, "year": 2014}, {"month": 9, "year": "2014"},
     "not-a-dict", None],
)  # fmt: skip
def test_bad_date_value_shape_refuses(value):
    data = _good_content()
    data["rows"][0]["fields"]["start_date"]["value"] = value
    with pytest.raises(Refused):
        plan_content_section(data)


@pytest.mark.parametrize("display", ["", "   ", None, 7])
def test_empty_or_non_text_display_refuses(display):
    data = _good_content()
    data["rows"][0]["fields"]["school_name_id"]["display"] = display
    with pytest.raises(Refused):
        plan_content_section(data)


def _rf(value, display, status="resolved"):
    return {"status": status, "value": value, "display": display}


@pytest.mark.parametrize("value", [{"bool": "yes"}, {"bool": 1}, {}, "not-a-dict", None])
def test_checkbox_value_shape_refuses(value):
    data = {
        "kind": "employment",
        "root": "#employment-section",
        "rows": [{
            "record_id": "e1",
            "fields": {
                "company_name": _rf({"text": "Acme"}, "Acme"),
                "title": _rf({"text": "Eng"}, "Eng"),
                "start_date": _rf({"month": 1, "year": 2020}, "01/2020"),
                "current": _rf(value, "Current"),
            },
        }],
    }  # fmt: skip
    with pytest.raises(Refused):
        plan_content_section(data)


def test_frozen_section_controls_are_told_apart_from_unexpected_required_controls():
    """A frozen section's own row controls are excluded from the adapter's unlisted-control check;
    every OTHER required control the package did not account for -- the ordinary identity, question
    and phone controls a real Greenhouse apply form carries -- is NOT a section control, so it still
    trips the "new unlisted control" stop rather than being quietly filled or ignored."""
    adapter = GreenhouseDomAdapter.__new__(GreenhouseDomAdapter)
    adapter.content = {"sections": [{"kind": "education"}, {"kind": "employment"}]}
    # The legacy per-row section ids (double dash for education, single for employment):
    for cid in ("school--0", "degree--1", "discipline--0", "company-name-0", "current-role-0"):
        assert adapter._is_section_control(cid) is True
    # Controls a real hosted Greenhouse form shows that are NOT part of a structured section:
    for cid in ("first_name", "last_name", "phone", "question_9234145005", "school-name-0"):
        assert adapter._is_section_control(cid) is False


def test_section_controls_only_count_for_a_kind_the_package_carries():
    adapter = GreenhouseDomAdapter.__new__(GreenhouseDomAdapter)
    adapter.content = {"sections": [{"kind": "education"}]}  # no employment section frozen
    assert adapter._is_section_control("school--0") is True
    assert adapter._is_section_control("company-name-0") is False  # employment not carried
