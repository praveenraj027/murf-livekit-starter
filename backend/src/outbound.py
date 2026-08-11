"""Outbound calling for Dhan Saathi (Day 6).

Days 1-5 the agent *waited* to be called over the browser. Day 6 turns it
around: the agent places the call. For the Financial Services track the natural
outbound use case is a **scheme-deadline reminder** — Dhan Saathi rings someone
who was already found eligible for a government scheme and reminds them, warmly
and briefly, that the last date to enrol is coming close.

Outbound is harder than inbound because the person did not ask to be called and
does not know who we are. Two things follow, and both live in this file:

1. **A safe opening.** `OutboundContext.opening()` builds the first thing the
   person hears — it says who is calling, why, and how to make it stop, before
   anything else.
2. **Outcome handling.** A person who did not pick up, a busy tone, or a flat
   "no" are outcomes inbound never has. `dial_out()` places the real PSTN call
   through the SIP *outbound trunk* (wired to a provider such as Twilio) and
   maps SIP failures to plain outcomes so the caller side can log and retry
   sensibly. `record_outcome()` / `read_outcome()` persist that to a small JSONL
   call log the dispatcher (`make_call.py`) reads back.

This module talks only to the LiveKit *server* API (`livekit.api`), never to the
Agents runtime, so the dial + outcome logic stays easy to test and reason about.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path

from livekit import api

logger = logging.getLogger("agent.outbound")

# Env var holding the LiveKit SIP outbound trunk id (starts with "ST_").
# Created once with `lk sip outbound create` and pointed at your telephony
# provider (Twilio elastic SIP trunk). See the backend README, "Outbound Calls".
TRUNK_ENV = "SIP_OUTBOUND_TRUNK_ID"

# One JSONL line per dial attempt, so the dispatcher can read the outcome back
# and apply retry rules. backend/src/outbound.py -> parents[1] is backend/.
CALL_LOG_PATH = Path(__file__).resolve().parents[1] / "data" / "call_log.jsonl"


class Outcome(str, Enum):
    """Every way an outbound attempt can end. The first four are dial failures
    (no media ever flowed); the rest describe how an answered call went."""

    ANSWERED = "answered"  # callee picked up — conversation is starting
    NO_ANSWER = "no_answer"  # rang out / unavailable / we cancelled
    BUSY = "busy"  # engaged tone
    DECLINED = "declined"  # actively rejected at the network
    FAILED = "failed"  # trunk / config / unknown SIP error
    COMPLETED = "completed"  # answered and the reminder was delivered
    OPTED_OUT = "opted_out"  # person asked us to stop / not call again

    @property
    def is_dial_failure(self) -> bool:
        return self in {Outcome.NO_ANSWER, Outcome.BUSY, Outcome.DECLINED, Outcome.FAILED}


# SIP response code -> outcome. Anything not listed is treated as FAILED.
# See https://docs.livekit.io/sip/ for the codes LiveKit surfaces on a failed dial.
_SIP_STATUS_TO_OUTCOME = {
    486: Outcome.BUSY,  # Busy Here
    600: Outcome.BUSY,  # Busy Everywhere
    408: Outcome.NO_ANSWER,  # Request Timeout — rang out
    480: Outcome.NO_ANSWER,  # Temporarily Unavailable
    487: Outcome.NO_ANSWER,  # Request Terminated (we hit the ringing timeout)
    603: Outcome.DECLINED,  # Decline
    403: Outcome.DECLINED,  # Forbidden
}


@dataclass
class OutboundContext:
    """Who we are calling, and why — parsed from the job metadata.

    `phone_number` is required (its presence is what marks a job as outbound).
    The rest tailor the reminder; all are optional so a bare number still works.
    """

    phone_number: str
    caller_name: str = ""
    scheme: str = ""
    deadline: str = ""
    language: str = ""

    @classmethod
    def from_metadata(cls, raw: str | None) -> "OutboundContext | None":
        """Parse job metadata into a context, or None if this isn't an outbound job.

        Returns None for empty metadata or metadata without a `phone_number`, so
        inbound jobs (Days 1-5) fall straight through unchanged.
        """
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Ignoring non-JSON job metadata: %r", raw)
            return None
        if not isinstance(data, dict):
            return None
        phone = str(data.get("phone_number", "")).strip()
        if not phone:
            return None
        return cls(
            phone_number=phone,
            caller_name=str(data.get("caller_name", "")).strip(),
            scheme=str(data.get("scheme", "")).strip(),
            deadline=str(data.get("deadline", "")).strip(),
            language=str(data.get("language", "")).strip(),
        )

    def opening(self) -> str:
        """The first thing the person hears.

        Outbound's hardest moment: they didn't ask for this call and don't know
        us. So the opening does three jobs in its first breath — who is calling,
        why, and how to make it stop — before we ask for anything.
        """
        name = f"{self.caller_name} ji" if self.caller_name else "ji"
        scheme = self.scheme or "a government scheme you had checked"
        deadline = f" It closes around {self.deadline}." if self.deadline else ""
        return (
            f"Namaste {name}. This is Dhan Saathi, an automated voice assistant "
            f"from the community money helpline. I am not a bank, and this is a "
            f"free reminder call, nothing to pay. I am calling because the last "
            f"date for {scheme} is coming close.{deadline} I will never ask for "
            f"any OTP, PIN, or account number. If this is not a good time, just "
            f"say stop and I will end the call. Is it okay if I take one minute?"
        )

    def prompt_addendum(self) -> str:
        """Extra instructions appended to the base system prompt for outbound calls."""
        scheme = self.scheme or "the scheme they had checked"
        deadline = self.deadline or "soon"
        return f"""

OUTBOUND CALL — READ CAREFULLY
This is an OUTBOUND reminder call that YOU placed. The person did not call you.
Treat their time and consent as the first priority.
- Your opening line already told them who you are, why you called, and that they
  can say "stop". Do not repeat all of that. Continue naturally.
- Your ONE goal: remind {self.caller_name or 'the person'} that the last date for
  {scheme} is near ({deadline}), tell them the single next step (visit their bank
  branch or Bank Mitra with their documents), and offer the free document
  checklist if they want it. Keep the whole call under a minute or two.
- The moment they say stop, not interested, busy, call later, or ask you not to
  call again: apologise warmly in one short line, say you will not disturb them,
  then call the end_call tool. Never push, never argue, never call back in-call.
- If a machine or voicemail answers (silence, a beep, or a recorded message),
  leave the reminder as one short spoken message, then call end_call.
- You may use check_scheme_eligibility to read out the exact documents for {scheme}.
- Hard rules still apply: never promise enrolment or approval, never ask for an
  OTP, PIN, CVV, or account number, and speak scheme figures only as of the
  tool's date, to be confirmed at the bank.
- When the reminder is delivered and there is nothing more they need, thank them
  warmly and call the end_call tool. Do not linger.
"""


def get_trunk_id() -> str | None:
    """The configured SIP outbound trunk id, or None if not set up yet."""
    trunk = os.getenv(TRUNK_ENV, "").strip()
    return trunk or None


async def dial_out(
    lk_api: api.LiveKitAPI,
    room_name: str,
    phone_number: str,
    *,
    ringing_timeout: int = 25,
    max_call_duration: int = 600,
) -> Outcome:
    """Place the real PSTN call into `room_name` and wait for the callee to answer.

    Returns ``Outcome.ANSWERED`` when the person picks up. On any dial failure it
    classifies the SIP response into ``NO_ANSWER`` / ``BUSY`` / ``DECLINED`` /
    ``FAILED`` and returns that instead of raising, so the entrypoint can shut
    down cleanly and the dispatcher can decide whether to retry.

    Args:
        lk_api: An open LiveKit server API client.
        room_name: The room the agent is already connected to.
        phone_number: E.164 number to dial, e.g. "+919876543210".
        ringing_timeout: Seconds to let it ring before giving up (no-answer).
        max_call_duration: Hard cap on the whole call, in seconds.
    """
    trunk_id = get_trunk_id()
    if not trunk_id:
        logger.error(
            "%s is not set — cannot place outbound calls. See the backend README, "
            "'Outbound Calls', to create a SIP outbound trunk.",
            TRUNK_ENV,
        )
        return Outcome.FAILED

    logger.info("Dialing %s via trunk %s into room %s", phone_number, trunk_id, room_name)
    try:
        await lk_api.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                sip_trunk_id=trunk_id,
                sip_call_to=phone_number,
                room_name=room_name,
                # A stable identity so we can find the SIP leg in the room.
                participant_identity="phone_user",
                participant_name=phone_number,
                # Block until the callee answers, so failures raise here and we
                # can classify them instead of joining a dead room.
                wait_until_answered=True,
                play_dialtone=True,
                # These are protobuf Duration fields — pass timedelta, not int.
                ringing_timeout=timedelta(seconds=ringing_timeout),
                max_call_duration=timedelta(seconds=max_call_duration),
            )
        )
    except api.TwirpError as exc:
        status_code = exc.metadata.get("sip_status_code", "")
        status_text = exc.metadata.get("sip_status", "")
        outcome = _classify_sip_error(status_code)
        logger.warning(
            "Dial to %s failed: %s (SIP %s %s) -> %s",
            phone_number,
            exc.message,
            status_code,
            status_text,
            outcome.value,
        )
        return outcome

    logger.info("%s answered.", phone_number)
    return Outcome.ANSWERED


def _classify_sip_error(status_code: str | int | None) -> Outcome:
    """Map a SIP response code (from a TwirpError) to an Outcome."""
    try:
        code = int(status_code)
    except (TypeError, ValueError):
        return Outcome.FAILED
    return _SIP_STATUS_TO_OUTCOME.get(code, Outcome.FAILED)


def record_outcome(
    room_name: str,
    outcome: Outcome,
    ctx: OutboundContext,
    *,
    now: str | None = None,
) -> None:
    """Append one line to the call log so the dispatcher can read the result back.

    Never raises — a logging problem must not crash a live call. `now` is
    injectable for tests; in production it defaults to the current UTC time.
    """
    entry = {
        "room": room_name,
        "outcome": outcome.value,
        "phone_number": ctx.phone_number,
        "caller_name": ctx.caller_name,
        "scheme": ctx.scheme,
        "timestamp": now or datetime.now(timezone.utc).isoformat(),
    }
    try:
        CALL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CALL_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        logger.info("Recorded outcome %s for room %s", outcome.value, room_name)
    except OSError as exc:
        logger.warning("Could not write call log: %s", exc)


def read_outcome(room_name: str) -> Outcome | None:
    """Return the most recent recorded outcome for a room, or None if not logged yet."""
    try:
        lines = CALL_LOG_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("room") == room_name:
            try:
                return Outcome(entry.get("outcome"))
            except ValueError:
                return None
    return None


# Retry policy, applied by the dispatcher. Dial failures where the person may
# simply have missed the call are worth another try; an active refusal is not.
_RETRYABLE = {Outcome.NO_ANSWER, Outcome.BUSY, Outcome.FAILED}


def should_retry(outcome: Outcome | None) -> bool:
    """Whether a fresh attempt is warranted. We never retry a refusal or opt-out,
    and there is nothing to retry once a call has been answered or completed."""
    return outcome in _RETRYABLE


def outcome_to_dict(outcome: Outcome, ctx: "OutboundContext") -> dict:
    """Small helper for structured logging / tests."""
    return {"outcome": outcome.value, **asdict(ctx)}
