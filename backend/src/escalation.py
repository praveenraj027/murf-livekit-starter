"""Human-help escalations for Dhan Saathi (Day 7).

Days 1-6 the agent handled the whole call on its own. Day 7 teaches it the
opposite skill: knowing when a problem is bigger than a voice helpline, and
handing it to a real person cleanly.

For the Financial Services track we escalate on exactly two situations (see the
HUMAN HELP section of the system prompt in ``agent.py``):

1. **Possible fraud / scam** the caller reports — money already gone, someone
   pressuring them for an OTP, an unknown debit. These need a human on a case,
   fast.
2. **A decision or dispute the agent cannot make** — a wrong deduction, a
   blocked account, a refund or complaint that only a bank officer can settle.

This module is the sink. It stores each request in a tiny SQLite table (one row
per request, like ``memory.py``), hands back a short human-friendly reference id
(``ESC-XXXXXX``), and optionally forwards a redacted summary to a real endpoint
(a Discord / Slack / generic webhook) when ``ESCALATION_WEBHOOK_URL`` is set.
The human reads open requests through ``dashboard.py``.

Privacy is the whole point of Day 7, so two rules are baked in here, not left to
the prompt:

- ``_redact`` is a hard backstop that strips anything looking like an OTP, PIN,
  card, account, or Aadhaar number from every free-text field before it is ever
  stored or sent. The prompt already tells the agent not to include these; this
  makes sure a slip never reaches the database or the webhook.
- We store only the useful, non-sensitive summary fields, never the transcript.
"""

import json
import logging
import os
import re
import sqlite3
import urllib.error
import urllib.request
import uuid
from contextlib import closing
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

logger = logging.getLogger("agent.escalation")

# Store the DB inside the backend dir (this file is backend/src/escalation.py, so
# parents[1] is backend/). A stable absolute path means open requests survive a
# full restart, wherever the process is launched from. *.db is gitignored.
DB_PATH = Path(__file__).resolve().parents[1] / "escalations.db"

# Optional real sink. If set, every new request is POSTed here as JSON. A Discord
# webhook URL works out of the box (we send a "content" field); a Slack incoming
# webhook or any generic endpoint that accepts JSON works too.
WEBHOOK_ENV = "ESCALATION_WEBHOOK_URL"

# Any run of 4+ digits looks like an OTP, PIN, card, account, or Aadhaar number
# and must never be stored or forwarded. 4 is deliberately tight: OTPs and PINs
# are 4-6 digits, so a higher threshold would let them through. Ages ("45"),
# short amounts ("2 lakh"), and dates ("31 March") stay untouched.
_LONG_DIGITS = re.compile(r"\d{4,}")

# Explicit secret words: redact the value that follows an OTP/PIN/CVV/password
# mention even if the caller spelled the digits out or it slipped through above.
_SECRET_PHRASE = re.compile(
    r"\b(otp|pin|cvv|password|passcode)\b[\s:is]*\S+",
    re.IGNORECASE,
)

_REDACTED = "[redacted]"


class Urgency(str, Enum):
    """How fast a human needs to pick this up. The agent picks one; the
    dashboard sorts and colours by it."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EMERGENCY = "emergency"

    @classmethod
    def parse(cls, value: str | None) -> "Urgency":
        """Coerce a loose string from the LLM into a valid level, defaulting to HIGH.

        For a finance helpline, when the agent is unsure we would rather a human
        look sooner than later, so an unknown value lands on HIGH, not LOW.
        """
        try:
            return cls((value or "").strip().lower())
        except ValueError:
            return cls.HIGH


class Status(str, Enum):
    """Where a request is in the human's queue."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"

    @classmethod
    def parse(cls, value: str | None) -> "Status | None":
        try:
            return cls((value or "").strip().lower())
        except ValueError:
            return None


# The two situations we escalate on, and how they read to a human. Keeping the
# set closed (rather than free text) means the dashboard can group by reason and
# a normal call can never invent a new escalation category.
REASONS = {
    "suspected_fraud": "Possible fraud or scam reported",
    "dispute_or_decision": "Dispute / decision only a human can make",
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the escalations table if it does not exist. Safe to call repeatedly."""
    with closing(_connect()) as conn, conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS escalations (
                ref_id         TEXT PRIMARY KEY,
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL,
                user_id        TEXT DEFAULT '',
                caller_name    TEXT DEFAULT '',
                reason         TEXT NOT NULL,
                reason_label   TEXT NOT NULL,
                summary        TEXT NOT NULL,
                checked        TEXT DEFAULT '',
                urgency        TEXT NOT NULL,
                language       TEXT DEFAULT '',
                follow_up      TEXT DEFAULT '',
                status         TEXT NOT NULL DEFAULT 'open',
                webhook_sent   INTEGER NOT NULL DEFAULT 0
            )
            """
        )
    logger.info("Escalation store ready at %s", DB_PATH)


def make_ref_id() -> str:
    """A short, speakable reference like 'ESC-7F3A2C' the caller can quote later."""
    return "ESC-" + uuid.uuid4().hex[:6].upper()


def make_user_id(name: str) -> str:
    """Same slug rule as memory.py, so an escalation links to a caller's record."""
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
    return slug or "unknown"


def _redact(text: str) -> str:
    """Strip anything that looks like a secret before it is stored or sent.

    A hard backstop on top of the prompt guardrails: removes OTP/PIN/CVV/password
    values and any 4+ digit run (card, account, Aadhaar, OTP). Never raises.
    """
    if not text:
        return ""
    cleaned = _SECRET_PHRASE.sub(_REDACTED, text)
    cleaned = _LONG_DIGITS.sub(_REDACTED, cleaned)
    return cleaned.strip()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["webhook_sent"] = bool(d.get("webhook_sent"))
    return d


def find_open_duplicate(user_id: str, reason: str) -> dict | None:
    """Return an existing OPEN/IN_PROGRESS request from the same caller for the
    same reason, so we update it instead of piling up duplicates. Newest first."""
    if not user_id:
        return None
    with closing(_connect()) as conn, conn:
        row = conn.execute(
            """
            SELECT * FROM escalations
            WHERE user_id = ? AND reason = ? AND status IN ('open', 'in_progress')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id, reason),
        ).fetchone()
    return _row_to_dict(row) if row else None


def create_escalation(
    *,
    caller_name: str,
    reason: str,
    summary: str,
    checked: str = "",
    urgency: str = "high",
    language: str = "",
    follow_up: str = "",
    now: str | None = None,
) -> dict:
    """Create (or update a matching open) human-help request. Returns the record.

    All free-text fields are redacted here as a hard backstop. If an open request
    already exists for the same caller and reason, we refresh it in place and
    return it (its ``ref_id`` is unchanged and ``was_duplicate`` is True) instead
    of creating a second one. Never raises on the webhook — a delivery failure
    still leaves a stored request the dashboard can show.

    Args:
        caller_name: The caller's name, as they gave it.
        reason: One of the keys in ``REASONS``. An unknown value is stored as-is
            with a generic label, so a request is never silently dropped.
        summary: What happened, in one or two plain sentences (redacted).
        checked: What the agent already tried or confirmed before escalating.
        urgency: "low" | "medium" | "high" | "emergency".
        language: The caller's language / preferred follow-up language.
        follow_up: How the caller wants to be reached, e.g. "call back".
        now: Injectable timestamp for tests; defaults to current UTC.
    """
    reason_label = REASONS.get(reason, "Human help requested")
    urgency_level = Urgency.parse(urgency).value
    user_id = make_user_id(caller_name)
    ts = now or datetime.now(timezone.utc).isoformat()

    clean_summary = _redact(summary)
    clean_checked = _redact(checked)
    clean_follow_up = _redact(follow_up)
    clean_name = _redact(caller_name)

    # Dedup: same caller, same reason, still open -> refresh rather than duplicate.
    existing = find_open_duplicate(user_id, reason)
    if existing is not None:
        with closing(_connect()) as conn, conn:
            conn.execute(
                """
                UPDATE escalations SET
                    updated_at = ?, summary = ?, checked = ?, urgency = ?,
                    language = ?, follow_up = ?
                WHERE ref_id = ?
                """,
                (
                    ts,
                    clean_summary,
                    clean_checked,
                    urgency_level,
                    language,
                    clean_follow_up,
                    existing["ref_id"],
                ),
            )
        logger.info("Updated existing open escalation %s (dedup)", existing["ref_id"])
        record = get_escalation(existing["ref_id"])
        record["was_duplicate"] = True
        return record

    ref_id = make_ref_id()
    with closing(_connect()) as conn, conn:
        conn.execute(
            """
            INSERT INTO escalations (
                ref_id, created_at, updated_at, user_id, caller_name, reason,
                reason_label, summary, checked, urgency, language, follow_up,
                status, webhook_sent
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', 0)
            """,
            (
                ref_id,
                ts,
                ts,
                user_id,
                clean_name,
                reason,
                reason_label,
                clean_summary,
                clean_checked,
                urgency_level,
                language,
                clean_follow_up,
            ),
        )
    logger.info(
        "Created escalation %s reason=%s urgency=%s", ref_id, reason, urgency_level
    )

    record = get_escalation(ref_id)
    # Best-effort forward to the real endpoint; failure must not sink the request.
    sent = _post_to_webhook(record)
    if sent:
        _mark_webhook_sent(ref_id)
        record["webhook_sent"] = True
    record["was_duplicate"] = False
    return record


def get_escalation(ref_id: str) -> dict | None:
    """Return one request by reference id, or None if there is no such request."""
    with closing(_connect()) as conn, conn:
        row = conn.execute(
            "SELECT * FROM escalations WHERE ref_id = ?", (ref_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_escalations(status: str | None = None) -> list[dict]:
    """All requests, newest first. Pass a status to filter (e.g. only 'open')."""
    query = "SELECT * FROM escalations"
    params: tuple = ()
    parsed = Status.parse(status) if status else None
    if parsed is not None:
        query += " WHERE status = ?"
        params = (parsed.value,)
    query += " ORDER BY created_at DESC"
    with closing(_connect()) as conn, conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_status(ref_id: str, status: str, *, now: str | None = None) -> dict | None:
    """Move a request to a new status (used by the human dashboard). Returns the
    updated record, or None if the ref id or status is invalid."""
    parsed = Status.parse(status)
    if parsed is None:
        return None
    ts = now or datetime.now(timezone.utc).isoformat()
    with closing(_connect()) as conn, conn:
        cur = conn.execute(
            "UPDATE escalations SET status = ?, updated_at = ? WHERE ref_id = ?",
            (parsed.value, ts, ref_id),
        )
    if cur.rowcount == 0:
        return None
    logger.info("Escalation %s -> %s", ref_id, parsed.value)
    return get_escalation(ref_id)


def _mark_webhook_sent(ref_id: str) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute(
            "UPDATE escalations SET webhook_sent = 1 WHERE ref_id = ?", (ref_id,)
        )


def get_webhook_url() -> str | None:
    url = os.getenv(WEBHOOK_ENV, "").strip()
    return url or None


def _webhook_payload(record: dict) -> dict:
    """Build the short, already-redacted message a human receives. This is the
    only thing that leaves the machine — never the transcript."""
    lines = [
        f"**New help request {record['ref_id']}** — {record['urgency'].upper()}",
        f"Reason: {record['reason_label']}",
        f"Who: {record['caller_name'] or 'unknown'}"
        + (f" (language: {record['language']})" if record["language"] else ""),
        f"What happened: {record['summary']}",
    ]
    if record.get("checked"):
        lines.append(f"Agent already checked: {record['checked']}")
    if record.get("follow_up"):
        lines.append(f"Preferred follow-up: {record['follow_up']}")
    text = "\n".join(lines)
    # "content" is what a Discord webhook renders; Slack/other endpoints get the
    # structured fields too, so one payload fits the common sinks.
    return {"content": text, "escalation": record}


def _post_to_webhook(record: dict) -> bool:
    """POST the redacted summary to the configured webhook. Returns True on a 2xx.

    Never raises: a helpline must not crash because a webhook is down. When no
    URL is configured we simply skip (the dashboard is then the sink of record).
    """
    url = get_webhook_url()
    if not url:
        return False
    data = json.dumps(_webhook_payload(record)).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = 200 <= resp.status < 300
        if ok:
            logger.info("Forwarded escalation %s to webhook", record["ref_id"])
        else:
            logger.warning(
                "Webhook returned %s for escalation %s", resp.status, record["ref_id"]
            )
        return ok
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.warning("Could not forward escalation %s: %s", record["ref_id"], exc)
        return False


# Ensure the table exists as soon as the module is imported (mirrors memory.py).
init_db()
