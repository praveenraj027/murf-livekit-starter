"""Offline unit tests for the Day 8 call analytics store.

Like test_outbound.py / test_escalation.py, these run fully offline — no LiveKit,
no real call. Each test points ``analytics.DB_PATH`` at a fresh temp database and
recreates the table, so tests never touch the real ``call_analytics.db`` and
never bleed into each other. They cover the parts easy to get subtly wrong: the
success/failure lifecycle, that success is sticky, that an unfinished call counts
as failed on end, and that the dashboard totals add up.
"""

import importlib

import pytest

import analytics


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A fresh, isolated analytics DB for one test."""
    monkeypatch.setattr(analytics, "DB_PATH", tmp_path / "call_analytics.db")
    analytics.init_db()
    return analytics


def test_a_completed_help_action_is_a_success(store):
    store.start_call("room-1", "browser", now="2026-08-13T10:00:00+00:00")
    store.mark_success("room-1", store.Success.ELIGIBILITY_CHECK.value)
    store.end_call("room-1", now="2026-08-13T10:02:30+00:00")

    stats = store.get_stats()
    assert stats["total"] == 1
    assert stats["successful"] == 1
    assert stats["failed"] == 0
    assert stats["success_rate"] == 100.0

    (call,) = store.recent_calls()
    assert call["outcome"] == "success"
    assert call["success_reason"] == "eligibility_check"
    # 2m30s -> 150 seconds duration, computed from the timestamps.
    assert call["duration_seconds"] == 150.0


def test_a_call_that_never_reaches_success_is_failed_on_end(store):
    # Caller joined but hung up after the greeting — no help action ever fired.
    store.start_call("room-2", "browser", now="2026-08-13T10:00:00+00:00")
    store.end_call("room-2", now="2026-08-13T10:00:20+00:00")

    stats = store.get_stats()
    assert stats["total"] == 1
    assert stats["successful"] == 0
    assert stats["failed"] == 1
    assert stats["by_failure"] == {"incomplete": 1}


def test_success_is_sticky_and_wins_over_later_failure(store):
    store.start_call("room-3", "browser")
    store.mark_success("room-3", store.Success.HUMAN_ESCALATION.value)
    # A later failure signal (or a plain end) must NOT downgrade a helped call.
    store.mark_failure("room-3", store.Failure.ERROR.value)
    store.end_call("room-3")

    (call,) = store.recent_calls()
    assert call["outcome"] == "success"
    assert call["success_reason"] == "human_escalation"
    assert store.get_stats()["successful"] == 1


def test_first_success_reason_is_kept(store):
    store.start_call("room-4", "browser")
    store.mark_success("room-4", store.Success.ELIGIBILITY_CHECK.value)
    store.mark_success("room-4", store.Success.HUMAN_ESCALATION.value)
    (call,) = store.recent_calls()
    assert call["success_reason"] == "eligibility_check"


def test_outbound_dial_failure_records_a_failed_phone_call(store):
    store.record_dial_failure(
        "room-5", store.Failure.NO_ANSWER.value, now="2026-08-13T10:00:00+00:00"
    )
    stats = store.get_stats()
    assert stats["total"] == 1
    assert stats["failed"] == 1
    assert stats["by_channel"]["phone"] == {"total": 1, "successful": 0, "failed": 1}
    assert stats["by_failure"] == {"no_answer": 1}


def test_totals_add_up_and_active_calls_are_excluded(store):
    store.start_call("ok", "browser")
    store.mark_success("ok", store.Success.ELIGIBILITY_CHECK.value)
    store.end_call("ok")

    store.start_call("bad", "phone")
    store.end_call("bad")  # ends without success -> failed

    store.start_call("live", "browser")  # still in progress, not ended

    stats = store.get_stats()
    # total counts only ended calls, so it always equals successful + failed.
    assert stats["total"] == 2
    assert stats["successful"] + stats["failed"] == stats["total"]
    assert stats["active"] == 1
    assert stats["success_rate"] == 50.0


def test_unknown_reasons_do_not_crash_and_default_safely(store):
    store.start_call("room-6", "weird-channel")  # unknown channel -> browser
    store.mark_success("room-6", "not-a-real-reason")  # unknown -> default success
    store.end_call("room-6")
    (call,) = store.recent_calls()
    assert call["channel"] == "browser"
    assert call["outcome"] == "success"
    assert call["success_reason"] == store.Success.ELIGIBILITY_CHECK.value


def test_operations_on_unknown_calls_are_safe_noops(store):
    # None of these were started; nothing should be created or raised.
    store.mark_success("ghost", store.Success.ELIGIBILITY_CHECK.value)
    store.mark_failure("ghost", store.Failure.ERROR.value)
    store.end_call("ghost")
    store.start_call("", "browser")  # empty id ignored
    assert store.get_stats()["total"] == 0
    assert store.recent_calls() == []


def test_module_reimport_is_safe():
    # Importing the module runs init_db(); doing it again must not raise.
    importlib.reload(analytics)
