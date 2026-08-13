import asyncio
import logging

from dotenv import load_dotenv
from livekit import api, rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    cli,
    function_tool,
    room_io,
)
from livekit.plugins import deepgram, google, murf, noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

import analytics
import escalation
import memory
import outbound
import schemes
from outbound import OutboundContext, Outcome

logger = logging.getLogger("agent")

load_dotenv(".env.local")

# Change this prompt to change what your voice agent does.
# See README.md for example prompts (customer support, language tutor, receptionist).
#
# Day 2 — Financial Services track. "Dhan Saathi" is a money guide for everyday
# people in India. The prompt is structured as IDENTITY / OBJECTIVES /
# KNOWLEDGE / LANGUAGE / GUARDRAILS / STYLE.
SYSTEM_PROMPT = """
IDENTITY
You are Dhan Saathi, a warm and trustworthy money guide for everyday people in India. You explain banking, saving, and government schemes in plain words for people who may be new to formal finance. You work for a community financial literacy helpline. You are not a bank, you cannot access anyone's account, and you are not a registered investment or tax advisor.

OBJECTIVES
A call goes well when you achieve at least one of these:
1. The caller understands one money idea clearly, like how a savings account works, what a scheme offers, or how to send money safely on UPI, and knows the correct next step.
2. The caller feels safer with money and can spot and avoid a common fraud.
3. You point the caller to the right official place, such as their bank branch, an official helpline, or a certified advisor, when the matter needs a human.

KNOWLEDGE
You know the basics of bank accounts, saving and budgeting, UPI and digital payment safety, common frauds, and the general idea of major Indian government schemes such as Jan Dhan, PMJJBY, PMSBY, Atal Pension Yojana, and Sukanya Samriddhi. You explain things with simple everyday examples. You do NOT know the caller's personal account details, and you do NOT know current interest rates or market prices. For government scheme benefits, eligibility, and documents, do not rely on memory — use the check_scheme_eligibility tool, which gives figures as of a set date. For anything else where numbers matter, say they must be checked from the official source, with the date, and point them to the bank or scheme website.

LANGUAGE
Speak in simple English by default. If the caller mixes in Hindi words, you may mix a little back in the same everyday register so it feels natural, but keep English as your main language. If the caller clearly switches fully to Hindi or another language, follow them. Be warm and respectful, and keep every word simple enough for someone new to banking.

LANGUAGE & SCRIPT
Always write every language in its own native script.
- Hindi must be written in Devanagari, like नमस्ते, never romanized like "namaste".
- Follow the same rule for every other non-English language.

SCHEME LOOKUP
You have a tool called check_scheme_eligibility that looks up which government schemes a caller qualifies for and the documents each one needs. Use it whenever the caller asks what schemes they can get, whether they are eligible, which scheme suits them, or what papers a scheme needs. Also use it once you naturally know their age and whether they have a bank account, to suggest suitable schemes.
- Do not interrogate. Gather age and bank-account status gently in normal talk, one question at a time, and only ask for what you are missing.
- The tool's answer is for you, not a script. Speak it in your own warm words, one scheme at a time, in short sentences. Never read out the raw data or a long list.
- Always say the information is as of the date the tool returns, and that exact amounts must be confirmed at the bank before enrolling.
- If the tool returns an error, tell the caller warmly that you cannot check just now and to try again shortly or visit their bank. Never invent a scheme or its details.

MEMORY — remembering callers across calls
You have three tools: recall_caller, remember_caller, and forget_caller. Follow these steps exactly. They are how you stop a returning caller from having to repeat themselves, so treat them as part of the job, not an extra.
1. RECALL FIRST. Warmly ask the caller's name early. The MOMENT they tell you their name, call recall_caller with that name — once, right away, before you continue talking. If a record comes back, greet them by name and carry on from last time: mention a scheme they had already checked and ask how it went, and do not re-ask what you already know. If nothing comes back, they are new; continue normally.
2. OFFER TO REMEMBER AT THE END. When the call is wrapping up — the caller says bye, says thanks, says "that's all", or the help is clearly finished — AND you have learned at least one useful, non-sensitive fact (a scheme they asked about, their age band, or whether they have a bank account), you MUST, before your goodbye, say one short line naming what you would remember and ask permission, for example: "Before you go, may I remember that you asked about Jan Dhan, so I can help you faster next time?" This permission step is a hard rule for a finance helpline.
3. SAVE ONLY ON A CLEAR YES. Only if they clearly agree, call remember_caller. Pass the ACTUAL facts as the values — schemes_checked like "Jan Dhan Yojana", eligibility like "age 45, has a bank account". Never pass a whole sentence, an instruction, or words like "asked to save" as a value; pass only the real fact. If they say no, do not save, and warmly reassure them.
4. FORGET ON REQUEST. If a caller asks you to forget them, call forget_caller and confirm it is done.
Never save an OTP, PIN, CVV, password, or any account, card, or ID number.

GUARDRAILS
These are hard rules. Never break them.
- Never ask for, or accept, an OTP, PIN, UPI PIN, CVV, password, or full card or account number. If the caller starts to share one, stop them at once and warn that these must never be told to anyone, not even to you.
- Never promise that a loan, scheme, subsidy, or application will be approved. Explain eligibility in general terms only, and say the bank or authority decides.
- Never guarantee investment returns, and never tell someone a particular stock or fund is sure to make a profit. Explain that all investment carries risk.
- Never state a current interest rate or market price as a fact from memory. For scheme benefits, premiums, and eligibility, use only what the check_scheme_eligibility tool returns, always say it is as of the date the tool gives, and add that the exact amount must be confirmed at the bank. Never quote scheme figures from your own memory.
- Never carry out a transaction or move money. You cannot access accounts. Guide the caller to do it themselves or at their bank.
- Stay on your job, which is personal finance and government schemes. Politely decline anything off topic and steer back.
- If the caller describes an active scam, or someone pressuring them for an OTP or money, warn them firmly and calmly, and give the escalation path below.

ESCALATION SCRIPT
For account problems, disputes, or fraud, say something warm like: "Iske liye aap apne bank ko unke official number par turant call karein. Agar paisa fraud mein gaya hai, toh cyber crime helpline one nine three zero par call karein, ya cybercrime dot gov dot in par report karein."

HUMAN HELP (when to hand off to a real person)
You are a guide, not a bank officer. Some problems are bigger than a helpline and
you must stop and raise a request for a human. There are exactly TWO such moments:
1. The caller reports possible FRAUD or a SCAM — money already gone, an unknown
   debit, or someone pressuring them for an OTP, PIN, or payment.
2. The caller has a DISPUTE or needs a DECISION you cannot make — a wrong
   deduction, a blocked or frozen account, a failed transaction, a refund, or a
   complaint that only a bank officer can settle.
Do NOT escalate for a normal question you can answer, like how a scheme works or
which documents are needed. Keep handling those yourself. Escalation is only for
the two moments above.

When one of those moments happens, follow these steps in order:
- First give the caller the immediate safety advice from the ESCALATION SCRIPT
  (call the bank, cyber helpline 1930). A human request is in addition to that,
  not instead of it.
- Then tell the caller, in plain words, that you would like to raise a request so
  a real person from the helpline team can follow up. Say exactly what you would
  share: their first name, what happened, how urgent it is, their language, and
  how they would like to be reached. Make clear you will NOT share any OTP, PIN,
  or account number.
- ASK PERMISSION. Only if they clearly say yes, call the create_escalation tool.
  If they say no, do not create anything; reassure them and give the self-help
  path only. This permission step is a hard rule.
- Never put an OTP, PIN, CVV, password, or account, card, or ID number into the
  request. Summarise in plain words only.
- After the tool returns, give the caller their reference id, spelled out simply
  (for example "E S C dash seven F three A"), and an HONEST next step: a team
  member will review open requests and follow up, but you cannot promise it will
  be instant. Do not invent a callback time.
- If the tool signals this matches a request already open for them, tell them it
  has been updated, not duplicated, and give the same reference id.

STYLE
You are speaking out loud, not writing. Use short sentences, under twenty words. No lists, no bullet points, no symbols, and no emojis. Share one idea at a time, then pause for the caller to respond. If the caller goes quiet, gently check if they are still there. Stay calm, patient, and trustworthy.
"""

# First-turn greeting — spoken in simple English as soon as the agent joins.
# It opens with the core safety promise, which also sets up the guardrail demo.
GREETING = "Hello! I am Dhan Saathi, your money helper. I explain banking, saving, and government schemes in simple words. One important thing first. I will never ask for your OTP or PIN, and please never share them with anyone. May I know your name?"


class Assistant(Agent):
    def __init__(
        self,
        *,
        greeting: str = GREETING,
        instructions: str = SYSTEM_PROMPT,
        ctx: JobContext | None = None,
        outbound_ctx: OutboundContext | None = None,
        call_id: str | None = None,
    ) -> None:
        super().__init__(instructions=instructions)
        # Inbound uses the default greeting/prompt. Outbound passes a tailored
        # opening (who's calling, why, how to stop) and a context so end_call can
        # hang up the phone and record how the call went.
        self._greeting = greeting
        self._ctx = ctx
        self._outbound = outbound_ctx
        # The room name, for Day 8 call analytics. Set for both inbound and
        # outbound (independent of _ctx, which stays outbound-only) so a success
        # can be attributed to this call from any tool.
        self._call_id = call_id

    async def on_enter(self) -> None:
        # Speak the first-turn greeting as soon as Saathi joins the call.
        await self.session.say(self._greeting, allow_interruptions=True)

    @function_tool
    async def end_call(self, context: RunContext, opted_out: bool = False):
        """Hang up the phone. Use this ONLY on an outbound call, once the reminder
        is delivered and there is nothing more the person needs, OR the moment the
        person asks you to stop or not call again.

        Let your final sentence finish first — say your short goodbye, THEN call
        this. Do not use it to dodge a genuine question.

        Args:
            opted_out: Set True if the person asked to stop / not be called again,
                so we record that and never call them back. Leave False for a
                normal, friendly end after the reminder was delivered.
        """
        if self._ctx is None:
            # Inbound call — there is no PSTN leg to hang up. Just acknowledge.
            return "This is not an outbound call, so there is nothing to hang up."

        if self._outbound is not None:
            result = Outcome.OPTED_OUT if opted_out else Outcome.COMPLETED
            outbound.record_outcome(self._ctx.room.name, result, self._outbound)

        # Let the goodbye finish playing before we cut the line.
        speech = context.session.current_speech
        if speech is not None:
            await speech.wait_for_playout()

        logger.info(
            "Ending call in room %s (opted_out=%s)", self._ctx.room.name, opted_out
        )
        await self._ctx.api.room.delete_room(
            api.DeleteRoomRequest(room=self._ctx.room.name)
        )
        return "Call ended."

    @function_tool
    async def recall_caller(self, context: RunContext, name: str):
        """Look up whether you have spoken with this caller before, by their name.

        Call this as soon as the caller tells you their name, before continuing
        the conversation. If a record is found, use it to greet them by name and
        continue from where you left off last time. Do not read the raw data out
        loud; weave it in naturally.

        Args:
            name: The caller's name, exactly as they told you.
        """
        user_id = memory.make_user_id(name)
        record = await asyncio.to_thread(memory.get_caller, user_id)
        if record is None:
            logger.info("No record for %s (%s) — new caller", name, user_id)
            return (
                f"No saved record for {name}. This is a new caller. Greet them "
                "normally. Later, remember to ask permission before saving anything."
            )
        logger.info("Recalled returning caller %s", user_id)
        return {
            "returning_caller": True,
            "name": record["name"],
            "language_preference": record["language_preference"],
            "facts": record["facts"],
            "last_interaction": record["last_interaction"],
        }

    @function_tool
    async def remember_caller(
        self,
        context: RunContext,
        name: str,
        schemes_checked: str = "",
        eligibility: str = "",
        other_notes: str = "",
        language_preference: str = "",
    ):
        """Save what you learned about the caller so you can help them better next time.

        IMPORTANT: Only call this AFTER the caller has clearly agreed to be
        remembered. Never save an OTP, PIN, CVV, password, or any account, card,
        or ID number. Leave any argument empty if you did not learn it. Pass only
        plain words, no numbers that could identify an account.

        Args:
            name: The caller's name.
            schemes_checked: Government schemes the caller has already looked into,
                e.g. "Jan Dhan, Atal Pension Yojana".
            eligibility: Plain eligibility answers, e.g. "age 45, has a bank account".
            other_notes: Any other useful, non-sensitive detail to remember.
            language_preference: The language the caller prefers, e.g. "Hindi" or "English".
        """
        facts = {
            "schemes_checked": schemes_checked,
            "eligibility": eligibility,
            "notes": other_notes,
        }
        # Only keep fields the agent actually learned, so blanks don't overwrite
        # what we already saved for a returning caller.
        facts = {k: v for k, v in facts.items() if v.strip()}
        user_id = memory.make_user_id(name)
        record = await asyncio.to_thread(
            memory.upsert_caller, user_id, name, facts, language_preference or None
        )
        logger.info("Remembered caller %s: %s", user_id, record["facts"])
        return f"Saved. I will remember this for {name} next time."

    @function_tool
    async def forget_caller(self, context: RunContext, name: str):
        """Delete everything you have saved about a caller, if they ask to be forgotten.

        Args:
            name: The caller's name.
        """
        user_id = memory.make_user_id(name)
        removed = await asyncio.to_thread(memory.forget_caller, user_id)
        if removed:
            return f"Done. I have forgotten everything saved about {name}."
        return f"There was nothing saved about {name} to forget."

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

        Call this whenever the caller asks what government schemes they can get,
        which scheme suits them, whether they are eligible for a scheme, or what
        documents a scheme needs. Also call it once you have naturally gathered
        the caller's basic details (age, whether they have a bank account) and it
        would help to suggest suitable schemes.

        Do NOT interrogate the caller. Ask only for details you are missing, one
        at a time, in plain words, and only if they are needed. You can call this
        with just the details you already have.

        The result is background data for YOU, not a script. Speak it naturally,
        one scheme at a time, in short sentences. Never read out JSON, field
        names, or the whole list at once. Always mention that the scheme
        information is as of the returned date, and that exact amounts must be
        confirmed at the bank. If status is "error", follow the message: tell the
        caller warmly that you cannot check right now, and do not invent schemes.

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
        logger.info("Scheme lookup returned status=%s", result.get("status"))
        # Day 8: a completed eligibility/document lookup is a success condition
        # for this call (the caller got the concrete help they came for). An
        # errored lookup is not counted — the call may still succeed another way.
        if result.get("status") != "error":
            await asyncio.to_thread(
                analytics.mark_success, self._call_id, analytics.Success.ELIGIBILITY_CHECK.value
            )
        return result

    @function_tool
    async def create_escalation(
        self,
        context: RunContext,
        caller_name: str,
        reason: str,
        summary: str,
        checked: str = "",
        urgency: str = "high",
        language: str = "",
        follow_up: str = "",
    ):
        """Raise a request for a real human to follow up on this caller's problem.

        Call this ONLY for the two escalation moments in the HUMAN HELP section:
        (1) the caller reports possible fraud or a scam, or (2) the caller has a
        dispute or needs a decision you cannot make. Do NOT call it for a normal
        question you can answer yourself.

        HARD RULE: you MUST have asked the caller for permission and heard a clear
        "yes" before calling this. If they said no, do not call it.

        Never pass an OTP, PIN, CVV, password, or any account, card, or ID number
        in any field. Summarise in plain words only. A backstop strips stray
        numbers, but you must not include them in the first place.

        Args:
            caller_name: The caller's first name, as they gave it.
            reason: "suspected_fraud" for fraud or a scam, or "dispute_or_decision"
                for a dispute or a decision only a human can make.
            summary: One or two plain sentences on what happened — the useful
                facts a human needs, no sensitive numbers.
            checked: What you already told or tried, e.g. "advised to call bank
                and cyber helpline 1930; confirmed no OTP was shared".
            urgency: "low", "medium", "high", or "emergency". Use "emergency" only
                for active, in-progress money loss or pressure right now.
            language: The caller's preferred language, e.g. "Hindi" or "English".
            follow_up: How the caller wants to be reached, in plain words, e.g.
                "call back" or "send an SMS". Never a full account or card number.
        """
        record = await asyncio.to_thread(
            escalation.create_escalation,
            caller_name=caller_name,
            reason=reason,
            summary=summary,
            checked=checked,
            urgency=urgency,
            language=language,
            follow_up=follow_up,
        )
        logger.info(
            "Escalation %s created (reason=%s, duplicate=%s)",
            record["ref_id"],
            reason,
            record.get("was_duplicate"),
        )
        # Day 8: raising a human-help request is a success condition — the caller
        # was safely routed to a real person for something we cannot settle.
        await asyncio.to_thread(
            analytics.mark_success, self._call_id, analytics.Success.HUMAN_ESCALATION.value
        )
        return {
            "reference_id": record["ref_id"],
            "urgency": record["urgency"],
            "was_duplicate": record.get("was_duplicate", False),
            "forwarded_to_team": record.get("webhook_sent", False),
            "next_step": (
                "A helpline team member will review open requests and follow up. "
                "Give the caller this reference id and be honest that you cannot "
                "promise an instant reply."
            ),
        }


server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


# Day 8: how an outbound dial that never connected reads in the call analytics.
# An answered/completed call is scored by what happened during it, not here.
_DIAL_OUTCOME_TO_FAILURE = {
    Outcome.NO_ANSWER: analytics.Failure.NO_ANSWER.value,
    Outcome.BUSY: analytics.Failure.BUSY.value,
    Outcome.DECLINED: analytics.Failure.DECLINED.value,
    Outcome.FAILED: analytics.Failure.DIAL_FAILED.value,
}


@server.rtc_session(agent_name="praveen's-agent")
async def my_agent(ctx: JobContext):
    # Logging setup
    # Add any other context you want in all log entries here
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Set up a voice AI pipeline using Murf Falcon, Gemini, Deepgram, and the LiveKit turn detector
    session = AgentSession(
        # Speech-to-text (STT) is your agent's ears, turning the user's speech into text that the LLM can understand
        # See all available models at https://docs.livekit.io/agents/models/stt/
        # "multi" lets Deepgram detect Hindi (and other) speech, not just English,
        # so returning callers can be greeted in their own language.
        stt=deepgram.STT(model="nova-3", language="multi"),
        # A Large Language Model (LLM) is your agent's brain, processing user input and generating a response
        # See all available models at https://docs.livekit.io/agents/models/llm/
        llm=google.LLM(
            model="gemini-3.5-flash-lite",
        ),
        # Text-to-speech (TTS) is your agent's voice, turning the LLM's text into speech that the user can hear
        # See all available models as well as voice selections at https://docs.livekit.io/agents/models/tts/
        # Indian English voice (Murf Falcon 2) — required for the challenge.
        # Keep it minimal: the plugin's default streaming tokenizer produces
        # smooth speech. A tiny min_sentence_len or text_pacing chops the audio
        # into fragments and adds lag, so we leave both off.
        tts=murf.TTS(
            voice="en-IN-anisha",
            style="Conversation",
        ),
        # VAD and turn detection are used to determine when the user is speaking and when the agent should respond
        # See more at https://docs.livekit.io/agents/build/turns
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        # allow the LLM to generate a response while waiting for the end of turn
        # See more at https://docs.livekit.io/agents/build/audio/#preemptive-generation
        preemptive_generation=True,
    )

    # To use a realtime model instead of a voice pipeline, use the following session setup instead.
    # (Note: This is for the OpenAI Realtime API. For other providers, see https://docs.livekit.io/agents/models/realtime/))
    # 1. Install livekit-agents[openai]
    # 2. Set OPENAI_API_KEY in .env.local
    # 3. Add `from livekit.plugins import openai` to the top of this file
    # 4. Use the following session setup instead of the version above
    # session = AgentSession(
    #     llm=openai.realtime.RealtimeModel(voice="marin")
    # )

    # # Add a virtual avatar to the session, if desired
    # # For other providers, see https://docs.livekit.io/agents/models/avatar/
    # avatar = hedra.AvatarSession(
    #   avatar_id="...",  # See https://docs.livekit.io/agents/models/avatar/plugins/hedra
    # )
    # # Start the avatar and wait for it to join
    # await avatar.start(session, room=ctx.room)

    # Shared room options: telephony-tuned noise cancellation for the SIP leg,
    # studio-grade for a browser participant.
    room_options = room_io.RoomOptions(
        audio_input=room_io.AudioInputOptions(
            noise_cancellation=lambda params: (
                noise_cancellation.BVCTelephony()
                if params.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                else noise_cancellation.BVC()
            ),
        ),
    )

    # Is this an OUTBOUND call? The dispatcher (make_call.py) packs the target
    # phone number into the job metadata; its presence is what flips us outbound.
    outbound_ctx = OutboundContext.from_metadata(ctx.job.metadata)

    # Day 8: record the outcome of every call. Register a shutdown callback once
    # so that however the job ends, we stamp the call's end time — and, if no
    # success condition was reached during it, record it as a failed call.
    async def _finalize_call(reason: str) -> None:
        await asyncio.to_thread(analytics.end_call, ctx.room.name)

    ctx.add_shutdown_callback(_finalize_call)

    if outbound_ctx is not None:
        # --- Day 6: the agent places the call -------------------------------
        # Connect to the room first, then dial the person through the SIP trunk.
        # dial_out blocks until they answer (or the dial fails), so we never
        # start talking to a dead room.
        await ctx.connect()
        analytics.start_call(ctx.room.name, "phone")
        result = await outbound.dial_out(
            ctx.api, ctx.room.name, outbound_ctx.phone_number
        )
        if result is not Outcome.ANSWERED:
            # No answer / busy / declined / trunk error: record it so the
            # dispatcher can apply its retry rule, mark the call failed with the
            # matching reason, then end the job cleanly.
            outbound.record_outcome(ctx.room.name, result, outbound_ctx)
            analytics.mark_failure(
                ctx.room.name,
                _DIAL_OUTCOME_TO_FAILURE.get(result, analytics.Failure.DIAL_FAILED.value),
            )
            ctx.shutdown(reason=f"outbound dial {result.value}")
            return

        outbound.record_outcome(ctx.room.name, Outcome.ANSWERED, outbound_ctx)
        await session.start(
            agent=Assistant(
                greeting=outbound_ctx.opening(),
                instructions=SYSTEM_PROMPT + outbound_ctx.prompt_addendum(),
                ctx=ctx,
                outbound_ctx=outbound_ctx,
                call_id=ctx.room.name,
            ),
            room=ctx.room,
            room_options=room_options,
        )
        return

    # --- Inbound (Days 1-5): wait for a browser/SIP caller to join ----------
    # Record the start of this browser call, then start the session, which
    # initializes the voice pipeline and warms up the models.
    analytics.start_call(ctx.room.name, "browser")
    await session.start(
        agent=Assistant(call_id=ctx.room.name), room=ctx.room, room_options=room_options
    )

    # Join the room and connect to the user
    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(server)
