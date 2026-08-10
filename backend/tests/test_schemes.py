"""Pure-logic tests for the Day 5 scheme eligibility tool.

Unlike test_agent.py (which needs LiveKit credentials and an LLM judge), these
run offline against the curated dataset, so they are the fast way to check the
eligibility rules and the graceful failure path.
"""

import schemes


def test_working_adult_with_bank_gets_the_core_schemes():
    result = schemes.check_eligibility(age=30, gender="male", has_bank_account=True)
    assert result["status"] == "ok"
    assert result["is_live"] is False  # local curated dataset, documented in README
    assert result["as_of"]  # every result carries a data date
    names = {s["name"] for s in result["eligible"]}
    assert "Pradhan Mantri Jeevan Jyoti Bima Yojana" in names  # 18-50
    assert "Atal Pension Yojana" in names  # 18-40
    assert "Pradhan Mantri Suraksha Bima Yojana" in names  # 18-70


def test_no_bank_account_only_gets_jan_dhan():
    result = schemes.check_eligibility(age=22, has_bank_account=False)
    names = {s["name"] for s in result["eligible"]}
    assert names == {"Pradhan Mantri Jan Dhan Yojana"}


def test_age_gates_are_respected():
    result = schemes.check_eligibility(age=60, has_bank_account=True)
    names = {s["name"] for s in result["eligible"]}
    assert "Atal Pension Yojana" not in names  # over 40
    assert "Pradhan Mantri Jeevan Jyoti Bima Yojana" not in names  # over 50
    assert "Pradhan Mantri Suraksha Bima Yojana" in names  # still within 18-70


def test_girl_child_scheme_only_surfaces_for_a_daughter():
    without = schemes.check_eligibility(age=35, gender="female", has_bank_account=True)
    assert without["girl_child_schemes"] == []

    with_daughter = schemes.check_eligibility(
        age=35, gender="female", has_bank_account=True, girl_child_age=5
    )
    names = {s["name"] for s in with_daughter["girl_child_schemes"]}
    assert names == {"Sukanya Samriddhi Yojana"}


def test_every_scheme_carries_a_document_checklist():
    result = schemes.check_eligibility(age=30, has_bank_account=True)
    for scheme in result["eligible"]:
        assert scheme["documents"], f"{scheme['name']} has no document checklist"


def test_missing_data_source_fails_gracefully(monkeypatch, tmp_path):
    # Simulate the data source being "killed": point at a file that isn't there.
    monkeypatch.setattr(schemes, "DATA_PATH", tmp_path / "gone.json")
    result = schemes.check_eligibility(age=30, has_bank_account=True)
    assert result["status"] == "error"
    assert "try again" in result["message"].lower()
    assert "eligible" not in result  # no fabricated schemes on failure
