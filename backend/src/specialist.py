"""Day 9 — the Government Scheme Specialist agent, "Yojana Mitra".

The main agent (``Assistant`` / "Dhan Saathi" in ``agent.py``) is a broad money
guide. It deliberately does NOT handle government-scheme detail itself. When a
caller asks which schemes they qualify for, what a scheme gives, or which
documents an enrolment needs, the main agent HANDS OFF to this specialist.

Why a separate agent?
    One agent should not try to be an expert at everything. This specialist has
    a smaller, sharper job than the main guide: government central schemes only.
    It owns the ``check_scheme_eligibility`` tool and the enrolment know-how, and
    it stays out of general banking, UPI, and fraud — for those it hands the
    call back to the main guide.

The handoff mechanics (LiveKit Agents 1.4):
    A ``@function_tool`` that returns an ``Agent`` instance makes the session
    switch to that agent. We pass ``chat_ctx`` so the whole conversation carries
    over — the specialist already knows what the caller asked and never makes
    them repeat themselves. On arrival, ``on_enter`` introduces the specialist
    and answers the pending question in one continuous turn.
"""

import asyncio
import logging

from livekit.agents import Agent, ChatContext, JobContext, RunContext, function_tool

import analytics
import schemes
from outbound import OutboundContext

logger = logging.getLogger("agent.specialist")

# The specialist's own role, instructions, and LIMITS. Deliberately narrower
# than the main guide's prompt — schemes are the whole job here.
SPECIALIST_PROMPT = """
IDENTITY
You are Yojana Mitra, the government scheme specialist on a community financial
literacy helpline. A colleague, Dhan Saathi, has just connected a caller to you
because they have a question about Indian central government schemes. You are a
specialist: you go deeper on schemes than the main guide does. You are not a
bank, you cannot access anyone's account, and you cannot approve any application.

YOUR ONE JOB
Government central schemes, and only these:
- Which schemes a caller likely qualifies for.
- What a scheme gives (the benefit) and its premium, if any.
- The exact documents an enrolment needs.
- The plain next steps to enrol: where to go (their bank branch or post office)
  and what to carry.
Stay on schemes. If the caller moves to a different topic — general banking, a
savings or budgeting question, UPI or payment safety, a fraud or a scam, a
dispute, or anything not about a scheme — do NOT try to handle it. Hand the call
back to the main guide with transfer_to_main_guide, telling the caller you are
connecting them back to Dhan Saathi.

TAKING OVER THE CALL
You can see the whole conversation so far. Do NOT ask the caller to repeat
themselves. In your first turn, warmly introduce yourself in one short sentence
as the scheme specialist, then go straight to answering what they already asked,
using the tool below.

SCHEME LOOKUP
Use the check_scheme_eligibility tool for every scheme answer. Do not quote
scheme figures, benefits, premiums, or documents from your own memory — use only
what the tool returns.
- Do not interrogate. You may already know the caller's age or whether they have
  a bank account from the earlier conversation. Only ask, gently and one at a
  time, for a detail you are actually missing and actually need.
- The tool's answer is background data for you, not a script. Speak it in your
  own warm words, one scheme at a time, in short sentences. Never read out raw
  data, field names, or a long list.
- Always say the information is as of the date the tool returns, and that the
  exact amounts and rules must be confirmed at the bank before enrolling.
- If the tool returns an error, tell the caller warmly that you cannot check just
  now and to try again shortly or visit their bank. Never invent a scheme or its
  details.

GUARDRAILS
These are hard rules. Never break them.
- Never promise that a scheme, subsidy, or application will be approved. Explain
  eligibility in general terms only, and say the bank or authority decides.
- Never ask for, or accept, an OTP, PIN, UPI PIN, CVV, password, or full card or
  account number. If the caller starts to share one, stop them at once.
- Never state a current interest rate or exact figure from memory. Use only the
  tool's numbers, always with the as-of date and "confirm at the bank".

LANGUAGE & SCRIPT
Speak in simple English by default; follow the caller if they switch to Hindi or
another language. Always write every language in its own native script — Hindi in
Devanagari like नमस्ते, never romanized. Keep every word simple enough for
someone new to banking.

STYLE
You are speaking out loud, not writing. Short sentences, under twenty words. No
lists, no bullet points, no symbols, no emojis. One idea at a time, then pause.
Stay calm, patient, and trustworthy.
"""


class SchemeSpecialist(Agent):
    """The government-scheme specialist the main guide hands off to."""

    def __init__(
        self,
        *,
        chat_ctx: ChatContext | None = None,
        call_id: str | None = None,
        ctx: JobContext | None = None,
        outbound_ctx: OutboundContext | None = None,
        greeting: str = "",
    ) -> None:
        # chat_ctx carries the whole prior conversation, so the specialist
        # continues seamlessly instead of starting cold.
        super().__init__(instructions=SPECIALIST_PROMPT, chat_ctx=chat_ctx)
        self._call_id = call_id
        # Kept only so we can rebuild the main guide faithfully on a hand-back.
        self._ctx = ctx
        self._outbound = outbound_ctx
        self._greeting = greeting

    async def on_enter(self) -> None:
        # Introduce the specialist AND answer the pending question in one turn,
        # using the conversation that came across in chat_ctx. generate_reply
        # (not a fixed say) lets it speak to whatever the caller actually asked.
        await self.session.generate_reply(
            instructions=(
                "You have just taken over the call as Yojana Mitra, the "
                "government scheme specialist. In one short, warm sentence "
                "introduce yourself as the scheme specialist. Then, without "
                "asking the caller to repeat anything, address the scheme "
                "question they already asked earlier in this conversation — call "
                "check_scheme_eligibility with the details you already know and "
                "begin helping. Do not re-greet at length; get to their answer."
            )
        )

    @function_tool
    async def check_scheme_eligibility(
        self,
        context: RunContext,
        age: int | None = None,
        gender: str = "",
        has_bank_account: bool = True,
        girl_child_age: int | None = None,
    ):
        """Find which government schemes the caller qualifies for and list the documents needed.

        Call this for every scheme question: which schemes they can get, which
        suits them, whether they are eligible, what a scheme gives, or what
        documents an enrolment needs. You can call it with just the details you
        already know from the conversation.

        Do NOT interrogate the caller. Ask only for a detail you are genuinely
        missing, one at a time, in plain words.

        The result is background data for YOU, not a script. Speak it naturally,
        one scheme at a time, in short sentences. Never read out JSON, field
        names, or the whole list at once. Always mention the information is as of
        the returned date, and that exact amounts must be confirmed at the bank.
        If status is "error", follow the message: tell the caller warmly that you
        cannot check right now, and do not invent schemes.

        Args:
            age: The caller's own age in years, if you know it.
            gender: "female", "male", or leave empty if not known.
            has_bank_account: Whether the caller already has a bank account.
            girl_child_age: Only if the caller is asking about a young daughter —
                her age in years. This is what surfaces the girl-child scheme.
        """
        result = await asyncio.to_thread(
            schemes.check_eligibility,
            age,
            gender,
            has_bank_account,
            girl_child_age,
        )
        logger.info("Specialist scheme lookup returned status=%s", result.get("status"))
        # Day 8: a completed eligibility/document lookup is a success condition
        # for this call. It stays a success even though the specialist, not the
        # main guide, ran it.
        if result.get("status") != "error":
            await asyncio.to_thread(
                analytics.mark_success,
                self._call_id,
                analytics.Success.ELIGIBILITY_CHECK.value,
            )
        return result

    @function_tool
    async def transfer_to_main_guide(self, context: RunContext):
        """Hand the call BACK to Dhan Saathi, the main money guide.

        Use this the moment the caller's need is no longer about government
        schemes — for example they now ask a general banking, saving, UPI safety,
        or fraud question, want to be remembered for next time, or say the scheme
        help is finished and they have something else to ask. Do NOT use it while
        you are still answering a scheme question.

        Before calling this, tell the caller in one short sentence that you are
        connecting them back to the main guide.
        """
        # Import here to avoid a circular import (agent.py imports this module).
        from agent import Assistant

        logger.info("Specialist handing call back to the main guide")
        return Assistant(
            greeting=self._greeting,
            ctx=self._ctx,
            outbound_ctx=self._outbound,
            call_id=self._call_id,
            chat_ctx=self.chat_ctx,
            skip_greeting=True,
        )
