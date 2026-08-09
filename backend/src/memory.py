"""Persistent caller memory for the voice agent (Day 4).

A tiny SQLite store so the agent can remember callers across calls and even
across full restarts. One row per caller, keyed by a slug of their name.

The agent never touches this module directly through the prompt — it reads and
writes only through the `recall_caller` / `remember_caller` function tools in
`agent.py`.

Financial Services track safety: we NEVER persist an OTP, PIN, CVV, password,
or any account / card / ID number. `_sanitize_facts` is a hard backstop that
drops any fact whose value carries a long digit sequence, on top of the prompt
guardrails.
"""

import json
import logging
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("agent.memory")

# Store the DB inside the backend dir (this file is backend/src/memory.py, so
# parents[1] is backend/). A stable absolute path means the data is still there
# after a full restart, wherever the process is launched from.
DB_PATH = Path(__file__).resolve().parents[1] / "agent_memory.db"

# Any value containing 6+ consecutive digits looks like an account / card /
# Aadhaar / OTP number and must never be stored.
_LONG_DIGITS = re.compile(r"\d{6,}")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the callers table if it does not exist. Safe to call repeatedly."""
    with closing(_connect()) as conn, conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS callers (
                user_id             TEXT PRIMARY KEY,
                name                TEXT NOT NULL,
                language_preference TEXT DEFAULT '',
                facts               TEXT DEFAULT '{}',
                last_interaction    TEXT
            )
            """
        )
    logger.info("Caller memory ready at %s", DB_PATH)


def make_user_id(name: str) -> str:
    """Turn a spoken name into a stable lookup key, e.g. 'Ramesh Kumar' -> 'ramesh_kumar'."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "unknown"


def _sanitize_facts(facts: dict) -> dict:
    """Drop anything that looks like a sensitive number before it is ever stored."""
    clean: dict[str, str] = {}
    for key, value in (facts or {}).items():
        text = str(value)
        if _LONG_DIGITS.search(text) or _LONG_DIGITS.search(str(key)):
            logger.warning("Refusing to store sensitive-looking fact: %r", key)
            continue
        clean[str(key)] = text
    return clean


def get_caller(user_id: str) -> dict | None:
    """Return the caller record as a dict, or None if we have never met them."""
    with closing(_connect()) as conn, conn:
        row = conn.execute(
            "SELECT * FROM callers WHERE user_id = ?", (user_id,)
        ).fetchone()
    if row is None:
        return None
    return {
        "user_id": row["user_id"],
        "name": row["name"],
        "language_preference": row["language_preference"] or "",
        "facts": json.loads(row["facts"] or "{}"),
        "last_interaction": row["last_interaction"],
    }


def upsert_caller(
    user_id: str,
    name: str,
    facts: dict | None = None,
    language_preference: str | None = None,
) -> dict:
    """Create or update a caller. New facts are merged into any existing ones."""
    existing = get_caller(user_id)
    merged_facts = dict(existing["facts"]) if existing else {}
    merged_facts.update(_sanitize_facts(facts or {}))

    if language_preference is None:
        language_preference = existing["language_preference"] if existing else ""

    now = datetime.now(timezone.utc).isoformat()
    with closing(_connect()) as conn, conn:
        conn.execute(
            """
            INSERT INTO callers (user_id, name, language_preference, facts, last_interaction)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                name = excluded.name,
                language_preference = excluded.language_preference,
                facts = excluded.facts,
                last_interaction = excluded.last_interaction
            """,
            (user_id, name, language_preference, json.dumps(merged_facts), now),
        )
    logger.info("Saved caller %s (%s)", user_id, name)
    return get_caller(user_id)


def forget_caller(user_id: str) -> bool:
    """Delete a caller's record. Returns True if a row was removed."""
    with closing(_connect()) as conn, conn:
        cur = conn.execute("DELETE FROM callers WHERE user_id = ?", (user_id,))
    removed = cur.rowcount > 0
    if removed:
        logger.info("Forgot caller %s", user_id)
    return removed


# Ensure the table exists as soon as the module is imported.
init_db()
