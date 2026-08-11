"""Place an outbound reminder call with Dhan Saathi (Day 6 dispatcher).

This is the button that starts an outbound call. It does NOT dial the phone
itself — that is the agent's job. Instead it creates an *agent dispatch*: it
tells LiveKit "start my agent in a fresh room, and here is who to call and why".
The agent (`agent.py`) sees that metadata, dials through the SIP outbound trunk,
and has the conversation. This split is the standard LiveKit outbound pattern
and keeps the telephony logic in one place.

After dispatching, this script watches the shared call log
(`data/call_log.jsonl`, written by the agent) for how the attempt ended, and
applies a simple retry rule: a missed or busy call is worth trying again; an
active "no, stop calling me" is not.

Usage
-----
    uv run python src/make_call.py +919876543210 \
        --name "Ramesh" --scheme "Atal Pension Yojana" --deadline "31 March" \
        --language Hindi

    # give up after 2 retries, 60s apart, on no-answer/busy:
    uv run python src/make_call.py +919876543210 --retries 2 --retry-delay 60

The number must be in E.164 form (a leading "+" and country code). Requires
LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET in the environment
(loaded from .env.local) and SIP_OUTBOUND_TRUNK_ID configured for the agent.
"""

import argparse
import asyncio
import json
import logging
import os
import uuid

from dotenv import load_dotenv
from livekit import api

import outbound
from outbound import Outcome

load_dotenv(".env.local")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("make_call")

# Must match the agent_name in the @server.rtc_session(...) decorator in agent.py.
DEFAULT_AGENT_NAME = "praveen's-agent"


def _build_metadata(args: argparse.Namespace) -> str:
    """Pack the call target and reminder details into the job metadata JSON."""
    return json.dumps(
        {
            "phone_number": args.phone_number,
            "caller_name": args.name,
            "scheme": args.scheme,
            "deadline": args.deadline,
            "language": args.language,
        }
    )


async def _dispatch(lk_api: api.LiveKitAPI, agent_name: str, metadata: str) -> str:
    """Create one agent dispatch in a fresh room. Returns the room name."""
    room_name = f"outbound-{uuid.uuid4().hex[:12]}"
    await lk_api.agent_dispatch.create_dispatch(
        api.CreateAgentDispatchRequest(
            agent_name=agent_name,
            room=room_name,
            metadata=metadata,
        )
    )
    logger.info("Dispatched %s to room %s", agent_name, room_name)
    return room_name


async def _wait_for_outcome(room_name: str, timeout: float) -> Outcome | None:
    """Poll the call log until this room's outcome appears, or we time out.

    A dial failure (no answer / busy / declined) is logged within seconds. An
    answered call is logged as ANSWERED immediately and later overwritten with
    COMPLETED / OPTED_OUT, so we keep watching until the call actually settles or
    the timeout hits.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    last: Outcome | None = None
    while asyncio.get_event_loop().time() < deadline:
        current = outbound.read_outcome(room_name)
        if current is not None:
            last = current
            # Terminal states — stop watching as soon as we see one.
            if current in {
                Outcome.NO_ANSWER,
                Outcome.BUSY,
                Outcome.DECLINED,
                Outcome.FAILED,
                Outcome.COMPLETED,
                Outcome.OPTED_OUT,
            }:
                return current
        await asyncio.sleep(2)
    return last


async def place_call(args: argparse.Namespace) -> Outcome | None:
    """Dispatch the call and, if it fails, retry per the policy in outbound.py."""
    metadata = _build_metadata(args)
    lk_api = api.LiveKitAPI()
    try:
        attempt = 0
        while True:
            attempt += 1
            logger.info("Attempt %d — calling %s", attempt, args.phone_number)
            room_name = await _dispatch(lk_api, args.agent, metadata)
            outcome = await _wait_for_outcome(room_name, args.wait)

            if outcome is None:
                logger.warning("No outcome recorded within %ss.", args.wait)
            else:
                logger.info("Attempt %d ended: %s", attempt, outcome.value)

            if not outbound.should_retry(outcome) or attempt > args.retries:
                return outcome

            logger.info(
                "Retrying in %ss (%d of %d retries used)...",
                args.retry_delay,
                attempt,
                args.retries,
            )
            await asyncio.sleep(args.retry_delay)
    finally:
        await lk_api.aclose()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Place an outbound Dhan Saathi reminder call.")
    p.add_argument(
        "phone_number",
        help=(
            "Who to call: a phone number in E.164 (e.g. +919876543210) for a PSTN "
            "provider, OR a SIP username (e.g. praveendhan) when the trunk points "
            "at a softphone service like sip.linphone.org"
        ),
    )
    p.add_argument("--name", default="", help="Person's name, for a warm opening")
    p.add_argument("--scheme", default="", help="Scheme the reminder is about")
    p.add_argument("--deadline", default="", help="Deadline, spoken, e.g. '31 March'")
    p.add_argument("--language", default="", help="Preferred language, e.g. Hindi")
    p.add_argument(
        "--agent",
        default=os.getenv("AGENT_NAME", DEFAULT_AGENT_NAME),
        help="Agent name to dispatch (must match agent.py)",
    )
    p.add_argument("--retries", type=int, default=1, help="Max retries on no-answer/busy")
    p.add_argument("--retry-delay", type=float, default=45.0, help="Seconds between retries")
    p.add_argument(
        "--wait",
        type=float,
        default=180.0,
        help="Seconds to wait for an outcome before giving up on this attempt",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    # A PSTN number must be E.164 (leading "+"); a SIP username (Linphone) starts
    # with a letter and is fine as-is. A leading digit means a malformed number.
    if args.phone_number[:1].isdigit():
        raise SystemExit(
            "A phone number must be E.164 with a leading '+' (e.g. +919876543210). "
            "For a Linphone SIP username, pass it as-is (e.g. praveendhan)."
        )
    if not outbound.get_trunk_id():
        logger.warning(
            "%s is not set. The agent will not be able to place the call until a "
            "SIP outbound trunk is configured — see the backend README.",
            outbound.TRUNK_ENV,
        )
    outcome = asyncio.run(place_call(args))
    if outcome is None:
        print("\nCall finished with no recorded outcome (check the agent logs).")
    else:
        print(f"\nFinal outcome: {outcome.value}")


if __name__ == "__main__":
    main()
