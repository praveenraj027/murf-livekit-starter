"""Pure-logic tests for the Day 6 outbound calling module.

Like test_schemes.py, these run fully offline — no LiveKit credentials, no real
phone call. They cover the parts of outbound calling that are easy to get subtly
wrong: what marks a job as outbound, what the person hears first, how SIP
failures map to outcomes, and the retry policy.
"""

import outbound
from outbound import OutboundContext, Outcome


def test_inbound_jobs_are_not_treated_as_outbound():
    # No metadata, or metadata without a phone number, means inbound (Days 1-5).
    assert OutboundContext.from_metadata(None) is None
    assert OutboundContext.from_metadata("") is None
    assert OutboundContext.from_metadata('{"foo": 1}') is None
    assert OutboundContext.from_metadata("not json at all") is None
    assert OutboundContext.from_metadata('{"phone_number": "  "}') is None


def test_metadata_parses_into_a_context():
    ctx = OutboundContext.from_metadata(
        '{"phone_number": "+919876543210", "caller_name": "Ramesh",'
        ' "scheme": "Atal Pension Yojana", "deadline": "31 March"}'
    )
    assert ctx is not None
    assert ctx.phone_number == "+919876543210"
    assert ctx.caller_name == "Ramesh"
    assert ctx.scheme == "Atal Pension Yojana"
    assert ctx.deadline == "31 March"


def test_opening_states_who_why_and_how_to_stop():
    ctx = OutboundContext(
        phone_number="+919876543210",
        caller_name="Ramesh",
        scheme="Atal Pension Yojana",
        deadline="31 March",
    )
    opening = ctx.opening().lower()
    assert "dhan saathi" in opening  # who is calling
    assert "atal pension yojana" in opening  # why we called
    assert "say stop" in opening  # how to make it stop
    assert "otp" in opening and "pin" in opening  # the safety promise, up front


def test_opening_works_without_optional_details():
    # A bare number must still produce a safe, complete opening.
    opening = OutboundContext(phone_number="+911").opening().lower()
    assert "dhan saathi" in opening
    assert "say stop" in opening


def test_sip_status_maps_to_outcomes():
    assert outbound._classify_sip_error(486) is Outcome.BUSY
    assert outbound._classify_sip_error(600) is Outcome.BUSY
    assert outbound._classify_sip_error(408) is Outcome.NO_ANSWER
    assert outbound._classify_sip_error(480) is Outcome.NO_ANSWER
    assert outbound._classify_sip_error(487) is Outcome.NO_ANSWER
    assert outbound._classify_sip_error(603) is Outcome.DECLINED
    # Unknown / unparseable codes fall back to FAILED, never crash.
    assert outbound._classify_sip_error(0) is Outcome.FAILED
    assert outbound._classify_sip_error(None) is Outcome.FAILED
    assert outbound._classify_sip_error("garbage") is Outcome.FAILED


def test_retry_policy_respects_refusals():
    # Worth another try — the person may simply have missed it.
    assert outbound.should_retry(Outcome.NO_ANSWER) is True
    assert outbound.should_retry(Outcome.BUSY) is True
    assert outbound.should_retry(Outcome.FAILED) is True
    # Never pester someone who refused, and nothing to retry once answered.
    assert outbound.should_retry(Outcome.DECLINED) is False
    assert outbound.should_retry(Outcome.OPTED_OUT) is False
    assert outbound.should_retry(Outcome.COMPLETED) is False
    assert outbound.should_retry(None) is False


def test_call_log_roundtrip(tmp_path, monkeypatch):
    # Point the log at a temp file so we don't touch the real one.
    monkeypatch.setattr(outbound, "CALL_LOG_PATH", tmp_path / "call_log.jsonl")
    ctx = OutboundContext(phone_number="+911", caller_name="Test", scheme="APY")

    assert outbound.read_outcome("room-1") is None  # nothing logged yet

    outbound.record_outcome("room-1", Outcome.ANSWERED, ctx, now="2026-08-11T00:00:00Z")
    outbound.record_outcome("room-1", Outcome.COMPLETED, ctx, now="2026-08-11T00:01:00Z")
    outbound.record_outcome("room-2", Outcome.BUSY, ctx, now="2026-08-11T00:02:00Z")

    # Latest wins for a given room; rooms don't bleed into each other.
    assert outbound.read_outcome("room-1") is Outcome.COMPLETED
    assert outbound.read_outcome("room-2") is Outcome.BUSY
    assert outbound.read_outcome("room-3") is None
