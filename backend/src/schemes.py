"""Government scheme eligibility + document checklist lookup (Day 5).

This is the agent's one real "tool": given the plain answers a caller gives
(age, gender, whether they have a bank account, and whether they are asking for
a young daughter), it works out which major central government schemes they
qualify for, and returns the benefit, the eligibility rule, and the exact
document checklist for each.

Data source
-----------
The scheme rules live in ``backend/data/schemes.json`` — a LOCAL, hand-curated
dataset built from the official scheme guidelines, NOT a live government API.
Every result carries the ``as_of`` date from that file so the agent can say how
current the information is. See the backend README for the "live vs local" note.

Failure path
------------
The data file is read fresh on every call (not cached at import time). If the
file is missing, unreadable, or malformed, ``check_eligibility`` returns a
result with ``status == "error"`` and a plain-English ``message`` instead of
raising. This is what lets the agent speak a graceful fallback ("I can't reach
my scheme list right now, please try again shortly") instead of going silent or
inventing an answer — exactly the behaviour Day 5 asks for. Deleting or renaming
``data/schemes.json`` is the easiest way to demo that fallback.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger("agent.schemes")

# backend/src/schemes.py -> parents[1] is backend/, then data/schemes.json.
DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "schemes.json"


def _load_dataset() -> dict:
    """Read and parse the scheme dataset. Raises on any problem (caught above)."""
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _matches(
    scheme: dict, age: int | None, gender: str, has_bank_account: bool
) -> bool:
    """True if this one person fits a single scheme's eligibility rule."""
    rule = scheme["eligibility"]

    if age is not None and (age < rule["age_min"] or age > rule["age_max"]):
        return False

    want_gender = rule.get("gender", "any")
    if want_gender != "any" and gender and gender.lower() != want_gender:
        return False

    return not (rule.get("requires_bank_account") and not has_bank_account)


def check_eligibility(
    age: int | None = None,
    gender: str = "",
    has_bank_account: bool = True,
    girl_child_age: int | None = None,
) -> dict:
    """Return the schemes a caller likely qualifies for, with document checklists.

    All the real logic lives here so the ``@function_tool`` in agent.py stays a
    thin wrapper. Never raises — on any data problem it returns
    ``{"status": "error", "message": ...}`` so the agent can speak a fallback.

    Args:
        age: The caller's own age in years, if known.
        gender: "female", "male", or "" if not known / not relevant.
        has_bank_account: Whether the caller already has a bank account.
        girl_child_age: If the caller is asking on behalf of a young daughter,
            her age in years. Drives the Sukanya Samriddhi (girl-child) match.

    Returns:
        On success: ``{"status": "ok", "as_of": <date>, "is_live": False,
        "eligible": [...], "girl_child_schemes": [...]}`` where each scheme is a
        small dict the agent can speak naturally.
        On failure: ``{"status": "error", "message": <plain English>}``.
    """
    try:
        data = _load_dataset()
    except FileNotFoundError:
        logger.error("Scheme dataset missing at %s", DATA_PATH)
        return {
            "status": "error",
            "message": (
                "The scheme list could not be reached right now. Tell the caller "
                "you cannot check eligibility this moment, apologise, and suggest "
                "they try again shortly or visit their nearest bank branch. Do NOT "
                "guess any scheme details."
            ),
        }
    except (json.JSONDecodeError, KeyError, OSError) as exc:
        logger.error("Scheme dataset unreadable: %s", exc)
        return {
            "status": "error",
            "message": (
                "The scheme list is temporarily unavailable. Tell the caller you "
                "cannot check eligibility right now and suggest they try again "
                "shortly. Do NOT guess any scheme details."
            ),
        }

    as_of = data.get("as_of", "an unspecified date")
    schemes = data.get("schemes", [])

    def _pack(scheme: dict) -> dict:
        # Only the fields worth speaking — no internal ids or raw rule dicts.
        packed = {
            "name": scheme["name"],
            "name_spoken_hi": scheme.get("name_spoken_hi", ""),
            "benefit": scheme["benefit"],
            "eligibility": scheme["eligibility_spoken"],
            "documents": scheme["documents"],
            "official_source": scheme.get("official_source", ""),
        }
        if scheme.get("premium"):
            packed["premium"] = scheme["premium"]
        return packed

    eligible: list[dict] = []
    girl_child: list[dict] = []

    for scheme in schemes:
        rule = scheme["eligibility"]
        if rule.get("girl_child_only"):
            # Only surface a girl-child scheme when the caller actually mentioned
            # a young daughter, so it never fires for the caller's own profile.
            if girl_child_age is not None and _matches(
                scheme, girl_child_age, "female", has_bank_account=False
            ):
                girl_child.append(_pack(scheme))
            continue
        if _matches(scheme, age, gender, has_bank_account):
            eligible.append(_pack(scheme))

    logger.info(
        "Eligibility check age=%s gender=%s bank=%s girl=%s -> %d schemes, %d girl-child",
        age,
        gender,
        has_bank_account,
        girl_child_age,
        len(eligible),
        len(girl_child),
    )

    return {
        "status": "ok",
        "as_of": as_of,
        "is_live": False,  # local curated dataset, not a live API
        "eligible": eligible,
        "girl_child_schemes": girl_child,
    }
