"""Pure-logic tests for the Day 7 human-help escalation store.

Like test_schemes.py and test_outbound.py, these run fully offline — no LiveKit,
no LLM, no network. Each test points the store at a temp SQLite file so the real
escalations.db is never touched, and covers the parts that are easy to get subtly
wrong: reference ids, the redaction backstop, the create/list/get roundtrip,
dedup of open requests, and status transitions.
"""

import sqlite3

import pytest

import escalation
from escalation import Status, Urgency


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Point the escalation store at a fresh temp DB and initialise it."""
    monkeypatch.setattr(escalation, "DB_PATH", tmp_path / "escalations.db")
    # No webhook during tests — the sink of record is the local DB.
    monkeypatch.delenv(escalation.WEBHOOK_ENV, raising=False)
    escalation.init_db()
    return escalation


def test_reference_id_is_short_and_speakable(store):
    ref = store.make_ref_id()
    assert ref.startswith("ESC-")
    assert len(ref) == len("ESC-") + 6
    assert ref[4:].isalnum() and ref[4:].isupper()


def test_redaction_strips_secrets_but_keeps_useful_facts():
    # OTPs, PINs, card/account numbers must never survive to storage.
    assert "1234" not in store_redact("my OTP is 1234")
    assert "[redacted]" in store_redact("card 4111111111111111 was charged")
    assert "998877" not in store_redact("account 998877665544")
    # Small numbers that are safe and useful stay untouched.
    assert (
        store_redact("caller is 45 and lost 2 lakh") == "caller is 45 and lost 2 lakh"
    )
    assert store_redact("deadline 31 March") == "deadline 31 March"


def store_redact(text: str) -> str:
    # Tiny helper so the redaction test reads cleanly; _redact needs no DB.
    return escalation._redact(text)


def test_create_and_get_roundtrip(store):
    rec = store.create_escalation(
        caller_name="Ramesh",
        reason="suspected_fraud",
        summary="Money left his account after a fake KYC call.",
        checked="Advised bank + cyber helpline 1930; no OTP shared.",
        urgency="emergency",
        language="Hindi",
        follow_up="call back",
    )
    assert rec["ref_id"].startswith("ESC-")
    assert rec["status"] == "open"
    assert rec["urgency"] == "emergency"
    assert rec["reason_label"] == store.REASONS["suspected_fraud"]
    assert rec["was_duplicate"] is False

    fetched = store.get_escalation(rec["ref_id"])
    assert fetched["summary"] == "Money left his account after a fake KYC call."
    assert fetched["language"] == "Hindi"


def test_secrets_are_redacted_on_the_way_into_storage(store):
    rec = store.create_escalation(
        caller_name="Sita",
        reason="suspected_fraud",
        summary="Scammer asked for OTP 4455 and her account 123456789012.",
        urgency="high",
    )
    stored = store.get_escalation(rec["ref_id"])
    assert "4455" not in stored["summary"]
    assert "123456789012" not in stored["summary"]
    assert "[redacted]" in stored["summary"]


def test_unknown_urgency_defaults_to_high(store):
    rec = store.create_escalation(
        caller_name="Anon",
        reason="dispute_or_decision",
        summary="Disputes a wrong deduction.",
        urgency="whenever",
    )
    assert rec["urgency"] == Urgency.HIGH.value


def test_duplicate_open_request_is_updated_not_duplicated(store):
    first = store.create_escalation(
        caller_name="Ramesh",
        reason="suspected_fraud",
        summary="Fake KYC call, money gone.",
        urgency="high",
    )
    second = store.create_escalation(
        caller_name="Ramesh",
        reason="suspected_fraud",
        summary="Adds that it was UPI, still the same incident.",
        urgency="emergency",
    )
    # Same reference id, marked as a duplicate, and only ONE row exists.
    assert second["ref_id"] == first["ref_id"]
    assert second["was_duplicate"] is True
    assert second["urgency"] == "emergency"  # refreshed in place
    assert len(store.list_escalations()) == 1


def test_a_different_reason_creates_a_separate_request(store):
    store.create_escalation(
        caller_name="Ramesh", reason="suspected_fraud", summary="Money gone."
    )
    store.create_escalation(
        caller_name="Ramesh", reason="dispute_or_decision", summary="Wrong deduction."
    )
    assert len(store.list_escalations()) == 2


def test_resolved_request_does_not_block_a_new_one(store):
    first = store.create_escalation(
        caller_name="Ramesh", reason="suspected_fraud", summary="Money gone."
    )
    store.update_status(first["ref_id"], "resolved")
    second = store.create_escalation(
        caller_name="Ramesh", reason="suspected_fraud", summary="A brand new incident."
    )
    assert second["ref_id"] != first["ref_id"]
    assert second["was_duplicate"] is False
    assert len(store.list_escalations()) == 2


def test_status_filter_and_transitions(store):
    rec = store.create_escalation(
        caller_name="Ravi", reason="dispute_or_decision", summary="Blocked account."
    )
    assert len(store.list_escalations("open")) == 1
    assert store.list_escalations("resolved") == []

    updated = store.update_status(rec["ref_id"], "in_progress")
    assert updated["status"] == Status.IN_PROGRESS.value
    assert len(store.list_escalations("open")) == 0
    assert len(store.list_escalations("in_progress")) == 1


def test_bad_status_update_is_rejected(store):
    rec = store.create_escalation(
        caller_name="Ravi", reason="dispute_or_decision", summary="Blocked account."
    )
    assert store.update_status(rec["ref_id"], "banana") is None
    assert store.update_status("ESC-NOPE0", "resolved") is None
    # The original request is untouched.
    assert store.get_escalation(rec["ref_id"])["status"] == "open"


def test_webhook_is_skipped_when_not_configured(store):
    # With no ESCALATION_WEBHOOK_URL, nothing is forwarded and it still stores.
    rec = store.create_escalation(
        caller_name="Ravi", reason="suspected_fraud", summary="Money gone."
    )
    assert rec["webhook_sent"] is False
    assert store.get_escalation(rec["ref_id"]) is not None


def test_schema_has_no_transcript_column(store):
    # Privacy: we store a short summary, never the raw conversation.
    with sqlite3.connect(store.DB_PATH) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(escalations)")}
    assert "transcript" not in cols
    assert "summary" in cols
