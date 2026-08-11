"""One-time setup: create the LiveKit SIP *outbound* trunk (Day 6).

Run this once to wire LiveKit to whatever SIP service you're calling through.
It prints a trunk id (``ST_…``) — paste that into ``SIP_OUTBOUND_TRUNK_ID`` in
``.env.local`` and you can place outbound calls. This replaces the ``lk sip
outbound create`` CLI command, so you don't need the LiveKit CLI installed.

It is provider-neutral. Fill these in ``.env.local``:

    SIP_PROVIDER_ADDRESS=sip.linphone.org        # the SIP server to dial through
    SIP_PROVIDER_USERNAME=...                     # SIP account username
    SIP_PROVIDER_PASSWORD=...                     # SIP account password
    SIP_PROVIDER_NUMBER=dhansaathi                # caller-ID shown (optional)

Two ways to fill them (see the backend README, "Outbound Calls"):
  • Linphone (simplest, free, no PSTN): make a free account at linphone.org,
    ADDRESS=sip.linphone.org, USERNAME/PASSWORD = that account. NUMBER can be any
    label. You then call your own Linphone SIP username and the app rings.
  • Twilio (real phone numbers): ADDRESS = your Twilio Termination URI host,
    USERNAME/PASSWORD = the Termination credential, NUMBER = your Twilio number.

Then:  uv run python src/setup_trunk.py

Requires LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET (already in .env.local).
"""

import asyncio
import os

from dotenv import load_dotenv
from livekit import api
from livekit.protocol import sip

load_dotenv(".env.local")

REQUIRED = {
    "SIP_PROVIDER_ADDRESS": "the SIP server to dial through (e.g. sip.linphone.org)",
    "SIP_PROVIDER_USERNAME": "the SIP account username",
    "SIP_PROVIDER_PASSWORD": "the SIP account password",
}


def _get(name: str) -> str:
    return os.getenv(name, "").strip()


async def main() -> None:
    missing = [k for k in REQUIRED if not _get(k)]
    if missing:
        print("Missing required values in .env.local:\n")
        for k in missing:
            print(f"  {k}  —  {REQUIRED[k]}")
        raise SystemExit(1)

    # Accept a "sip:" prefix but store the bare host, which is what LiveKit wants.
    address = _get("SIP_PROVIDER_ADDRESS").removeprefix("sip:").strip("/")
    username = _get("SIP_PROVIDER_USERNAME")
    password = _get("SIP_PROVIDER_PASSWORD")
    # Caller-ID label. Cosmetic for a softphone; for Twilio it must be your number.
    number = _get("SIP_PROVIDER_NUMBER") or username

    lk_api = api.LiveKitAPI()
    try:
        # Idempotent: if a trunk for this address already exists, reuse it instead
        # of creating a duplicate every run.
        existing = await lk_api.sip.list_outbound_trunk(
            sip.ListSIPOutboundTrunkRequest()
        )
        for t in existing.items:
            if t.address == address and list(t.numbers) == [number]:
                print("An outbound trunk for this address already exists; reusing it.\n")
                _report(t)
                return

        trunk = await lk_api.sip.create_outbound_trunk(
            sip.CreateSIPOutboundTrunkRequest(
                trunk=sip.SIPOutboundTrunkInfo(
                    name="Dhan Saathi outbound",
                    address=address,
                    transport=sip.SIP_TRANSPORT_AUTO,
                    numbers=[number],
                    auth_username=username,
                    auth_password=password,
                )
            )
        )
    finally:
        await lk_api.aclose()

    print("Outbound trunk created.\n")
    _report(trunk)


def _report(trunk: sip.SIPOutboundTrunkInfo) -> None:
    print(f"   Trunk id: {trunk.sip_trunk_id}")
    print(f"   Address : {trunk.address}")
    print(f"   Numbers : {list(trunk.numbers)}\n")
    print("Put this line in backend/.env.local:\n")
    print(f"   SIP_OUTBOUND_TRUNK_ID={trunk.sip_trunk_id}\n")


if __name__ == "__main__":
    asyncio.run(main())
