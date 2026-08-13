"""Call analytics for Dhan Saathi (Day 8).

Days 1-7 the agent learned to talk, remember, look things up, place calls, and
ask a human for help. Day 8 asks a different question: *how is it doing?* This
module records the outcome of **every** call — browser (inbound) and phone
(outbound SIP) — so a tiny dashboard can show total, successful, and failed
calls from real data.

WHAT "SUCCESS" MEANS (decided from the Day 2 objectives, Financial Services track)
A call is **successful** when the caller receives the concrete help this helpline
exists to give. Measured, that is: at least one substantive help action completed
during the call —

  * a government-scheme **eligibility / document check** completed, or
  * a **human-help request** was raised for a fraud or dispute.

A call is **failed** when it ends without reaching that condition. A failure is
not necessarily a breakage: the caller may have hung up after the greeting, only
chatted, gone off-topic, an outbound dial may never have connected, or a tool may
have errored. It simply means the success condition was not met. (See ``Success``
and ``Failure`` for the closed sets of reasons.)

HOW IT IS RECORDED (see ``agent.py``)
  * ``start_call`` when the session starts — one row per call, ``in_progress``.
  * ``mark_success`` the moment a help action completes (from the tool bodies).
  * ``end_call`` from the job's shutdown callback — stamps the end time and,
    if no success was marked, records the call as ``failed``.

Success is sticky: once a call is marked successful, a later ``mark_failure`` or
``end_call`` will not downgrade it.

PRIVACY (Day 8 requirement)
This store is built to be safe to show on a dashboard. It records only the call
id (the random LiveKit room name), the channel, timestamps, duration, and a
coarse outcome reason from a closed set. It never stores a caller name, phone
number, transcript, OTP, PIN, or account number — there is nothing here to leak.

Like ``memory.py`` and ``escalation.py``, this is a tiny dependency-free SQLite
store (one row per call) with a stable absolute DB path so data survives a full
restart.
"""

import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

logger = logging.getLogger("agent.analytics")

# backend/src/analytics.py -> parents[1] is backend/. *.db is gitignored.
DB_PATH = Path(__file__).resolve().parents[1] / "call_analytics.db"

# The two real channels a call can arrive on. Inbound web callers are "browser";
# outbound SIP/PSTN calls the agent places are "phone".
CHANNELS = ("browser", "phone")


class Outcome(str, Enum):
    """Where a call is in its lifecycle. ``IN_PROGRESS`` is a live/ongoing call;
    it becomes ``SUCCESS`` or ``FAILED`` by the time the call ends."""

    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"


class Success(str, Enum):
    """The closed set of ways a call can reach its success condition."""

    ELIGIBILITY_CHECK = "eligibility_check"  # scheme eligibility / documents given
    HUMAN_ESCALATION = "human_escalation"  # a human-help request was raised


class Failure(str, Enum):
    """The closed set of failure reasons (Advanced: failure typing)."""

    INCOMPLETE = "incomplete"  # answered but no success action before it ended
    NO_ANSWER = "no_answer"  # outbound: rang out / unavailable
    BUSY = "busy"  # outbound: engaged
    DECLINED = "declined"  # outbound: actively rejected
    DIAL_FAILED = "dial_failed"  # outbound: trunk / config / unknown dial error
    ERROR = "error"  # a tool / API error prevented help


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the calls table if it does not exist. Safe to call repeatedly."""
    with closing(_connect()) as conn, conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS calls (
                call_id          TEXT PRIMARY KEY,
                channel          TEXT NOT NULL,
                started_at       TEXT NOT NULL,
                ended_at         TEXT,
                duration_seconds REAL,
                outcome          TEXT NOT NULL DEFAULT 'in_progress',
                success_reason   TEXT DEFAULT '',
                failure_reason   TEXT DEFAULT ''
            )
            """
        )
    logger.info("Call analytics ready at %s", DB_PATH)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _duration_seconds(started_at: str, ended_at: str) -> float | None:
    """Wall-clock seconds between two ISO timestamps, or None if unparseable."""
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(ended_at)
    except (TypeError, ValueError):
        return None
    return max(0.0, (end - start).total_seconds())


def _get_outcome(conn: sqlite3.Connection, call_id: str) -> str | None:
    row = conn.execute(
        "SELECT outcome FROM calls WHERE call_id = ?", (call_id,)
    ).fetchone()
    return row["outcome"] if row else None


def start_call(call_id: str, channel: str, *, now: str | None = None) -> None:
    """Record the start of a call as ``in_progress``. Idempotent per call id.

    Args:
        call_id: The LiveKit room name — a stable, non-sensitive id for the call.
        channel: ``"browser"`` (inbound web) or ``"phone"`` (outbound SIP).
        now: Injectable timestamp for tests; defaults to current UTC.
    """
    if not call_id:
        return
    channel = channel if channel in CHANNELS else "browser"
    ts = now or _now()
    with closing(_connect()) as conn, conn:
        # INSERT OR IGNORE: a re-entrant start for the same room never clobbers an
        # outcome already recorded for it.
        conn.execute(
            """
            INSERT OR IGNORE INTO calls (call_id, channel, started_at, outcome)
            VALUES (?, ?, ?, 'in_progress')
            """,
            (call_id, channel, ts),
        )
    logger.info("Call started: %s (%s)", call_id, channel)


def mark_success(call_id: str, reason: str, *, now: str | None = None) -> None:
    """Mark a call successful because a help action completed. Success is sticky.

    Safe to call more than once in a call (the first success reason is kept). If
    the call was never ``start_call``-ed (e.g. a race), this is a no-op.

    Args:
        call_id: The room name.
        reason: A ``Success`` value — what made the call a success.
        now: Injectable timestamp for tests.
    """
    if not call_id:
        return
    reason = _coerce(reason, Success, Success.ELIGIBILITY_CHECK).value
    with closing(_connect()) as conn, conn:
        current = _get_outcome(conn, call_id)
        if current is None:
            logger.debug("mark_success for unknown call %s — ignoring", call_id)
            return
        if current == Outcome.SUCCESS.value:
            return  # already a success; keep the first reason
        conn.execute(
            "UPDATE calls SET outcome = 'success', success_reason = ?, "
            "failure_reason = '' WHERE call_id = ?",
            (reason, call_id),
        )
    logger.info("Call success: %s (%s)", call_id, reason)


def mark_failure(call_id: str, reason: str, *, now: str | None = None) -> None:
    """Record a failure reason, unless the call has already succeeded.

    Success always wins — a call that helped the caller is not downgraded just
    because something later went wrong.
    """
    if not call_id:
        return
    reason = _coerce(reason, Failure, Failure.INCOMPLETE).value
    with closing(_connect()) as conn, conn:
        current = _get_outcome(conn, call_id)
        if current is None or current == Outcome.SUCCESS.value:
            return
        conn.execute(
            "UPDATE calls SET outcome = 'failed', failure_reason = ? WHERE call_id = ?",
            (reason, call_id),
        )
    logger.info("Call failed: %s (%s)", call_id, reason)


def end_call(
    call_id: str,
    *,
    default_failure_reason: str = Failure.INCOMPLETE.value,
    now: str | None = None,
) -> None:
    """Finalize a call: stamp the end time and duration.

    If the call never reached a success condition it is recorded as ``failed``
    with ``default_failure_reason``. A call already marked ``success`` keeps that
    outcome. Safe to call for a call id that was never started (no-op).

    Args:
        call_id: The room name.
        default_failure_reason: Reason to use if the call ends without a success.
        now: Injectable timestamp for tests.
    """
    if not call_id:
        return
    reason = _coerce(default_failure_reason, Failure, Failure.INCOMPLETE).value
    ts = now or _now()
    with closing(_connect()) as conn, conn:
        row = conn.execute(
            "SELECT started_at, outcome FROM calls WHERE call_id = ?", (call_id,)
        ).fetchone()
        if row is None:
            logger.debug("end_call for unknown call %s — ignoring", call_id)
            return
        duration = _duration_seconds(row["started_at"], ts)
        if row["outcome"] == Outcome.IN_PROGRESS.value:
            conn.execute(
                "UPDATE calls SET ended_at = ?, duration_seconds = ?, "
                "outcome = 'failed', failure_reason = ? WHERE call_id = ?",
                (ts, duration, reason, call_id),
            )
            logger.info("Call ended (failed/%s): %s", reason, call_id)
        else:
            conn.execute(
                "UPDATE calls SET ended_at = ?, duration_seconds = ? WHERE call_id = ?",
                (ts, duration, call_id),
            )
            logger.info("Call ended (%s): %s", row["outcome"], call_id)


def record_dial_failure(
    call_id: str, reason: str, *, channel: str = "phone", now: str | None = None
) -> None:
    """Convenience for an outbound dial that never connected (no answer / busy /
    declined / trunk error): start, fail, and end the call in one step so it still
    shows up in the totals."""
    ts = now or _now()
    start_call(call_id, channel, now=ts)
    mark_failure(call_id, reason, now=ts)
    end_call(call_id, default_failure_reason=reason, now=ts)


def _coerce(value: str, enum_cls: type, default: Enum) -> Enum:
    """Coerce a loose string into an enum member, defaulting on anything unknown
    so a bad reason never crashes a live call or drops a row."""
    try:
        return enum_cls((value or "").strip().lower())
    except (ValueError, AttributeError):
        return default


def _count(conn: sqlite3.Connection, where: str, params: tuple = ()) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS n FROM calls WHERE {where}", params).fetchone()
    return int(row["n"]) if row else 0


def get_stats() -> dict:
    """The numbers the dashboard shows. ``total`` counts only ended calls, so it
    always equals ``successful + failed``; live calls are reported separately as
    ``active`` and never inflate the totals.

    Returns a dict with: total, successful, failed, active, success_rate (0-100),
    by_channel, by_failure, by_success.
    """
    with closing(_connect()) as conn:
        successful = _count(conn, "outcome = 'success'")
        failed = _count(conn, "outcome = 'failed'")
        active = _count(conn, "outcome = 'in_progress'")

        by_channel: dict[str, dict[str, int]] = {}
        for row in conn.execute(
            "SELECT channel, outcome, COUNT(*) AS n FROM calls "
            "WHERE outcome != 'in_progress' GROUP BY channel, outcome"
        ):
            bucket = by_channel.setdefault(
                row["channel"], {"total": 0, "successful": 0, "failed": 0}
            )
            bucket["total"] += row["n"]
            if row["outcome"] == "success":
                bucket["successful"] += row["n"]
            elif row["outcome"] == "failed":
                bucket["failed"] += row["n"]

        by_failure = {
            r["failure_reason"] or "unknown": r["n"]
            for r in conn.execute(
                "SELECT failure_reason, COUNT(*) AS n FROM calls "
                "WHERE outcome = 'failed' GROUP BY failure_reason ORDER BY n DESC"
            )
        }
        by_success = {
            r["success_reason"] or "unknown": r["n"]
            for r in conn.execute(
                "SELECT success_reason, COUNT(*) AS n FROM calls "
                "WHERE outcome = 'success' GROUP BY success_reason ORDER BY n DESC"
            )
        }

    total = successful + failed
    success_rate = round(successful / total * 100, 1) if total else 0.0
    return {
        "total": total,
        "successful": successful,
        "failed": failed,
        "active": active,
        "success_rate": success_rate,
        "by_channel": by_channel,
        "by_failure": by_failure,
        "by_success": by_success,
    }


def recent_calls(limit: int = 20) -> list[dict]:
    """Recent calls, newest first, for the history table. Non-sensitive fields
    only — call id, channel, timestamps, duration, outcome, and coarse reason."""
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM calls ORDER BY started_at DESC LIMIT ?", (int(limit),)
        ).fetchall()
    return [dict(r) for r in rows]


# Ensure the table exists as soon as the module is imported (mirrors memory.py).
init_db()
