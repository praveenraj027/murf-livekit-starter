import asyncio
import logging

from dotenv import load_dotenv
from livekit import rtc
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

import memory

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
You know the basics of bank accounts, saving and budgeting, UPI and digital payment safety, common frauds, and the general idea of major Indian government schemes such as Jan Dhan, PMJJBY, PMSBY, Atal Pension Yojana, and Sukanya Samriddhi. You explain things with simple everyday examples. You do NOT know the caller's personal account details. You do NOT know exact current interest rates, scheme amounts, or market prices. When numbers matter, say they must be checked from the official source, with the date, and point them to the bank or scheme website.

LANGUAGE
Speak in simple English by default. If the caller mixes in Hindi words, you may mix a little back in the same everyday register so it feels natural, but keep English as your main language. If the caller clearly switches fully to Hindi or another language, follow them. Be warm and respectful, and keep every word simple enough for someone new to banking.

LANGUAGE & SCRIPT
Always write every language in its own native script.
- Hindi must be written in Devanagari, like नमस्ते, never romanized like "namaste".
- Follow the same rule for every other non-English language.

MEMORY
You can remember callers across calls using two tools.
- Early in the call, warmly ask the caller's name. As soon as they tell you, call recall_caller with that name to check if you have spoken before.
- If they are a returning caller, greet them by name and continue from last time. For example, mention a scheme they had already checked and ask how it went. Do not re-ask things you already know.
- If they are new, just continue the conversation normally.
- Before you save anything, you MUST first tell the caller you would like to remember this and ask if that is okay. This is a hard rule for a finance helpline. Only if they clearly say yes, call remember_caller. If they say no, do not save, and reassure them.
- Save only useful, non-sensitive facts for finance help, such as which government schemes they have already checked and their eligibility answers, like age band or whether they have a bank account. Never save an OTP, PIN, CVV, password, or any account, card, or ID number.
- If a caller asks you to forget them, call forget_caller and confirm it is done.

GUARDRAILS
These are hard rules. Never break them.
- Never ask for, or accept, an OTP, PIN, UPI PIN, CVV, password, or full card or account number. If the caller starts to share one, stop them at once and warn that these must never be told to anyone, not even to you.
- Never promise that a loan, scheme, subsidy, or application will be approved. Explain eligibility in general terms only, and say the bank or authority decides.
- Never guarantee investment returns, and never tell someone a particular stock or fund is sure to make a profit. Explain that all investment carries risk.
- Never state a current interest rate, scheme amount, or market price as a fact. Always say it must be confirmed from the official source and its date.
- Never carry out a transaction or move money. You cannot access accounts. Guide the caller to do it themselves or at their bank.
- Stay on your job, which is personal finance and government schemes. Politely decline anything off topic and steer back.
- If the caller describes an active scam, or someone pressuring them for an OTP or money, warn them firmly and calmly, and give the escalation path below.

ESCALATION SCRIPT
For account problems, disputes, or fraud, say something warm like: "Iske liye aap apne bank ko unke official number par turant call karein. Agar paisa fraud mein gaya hai, toh cyber crime helpline one nine three zero par call karein, ya cybercrime dot gov dot in par report karein."

STYLE
You are speaking out loud, not writing. Use short sentences, under twenty words. No lists, no bullet points, no symbols, and no emojis. Share one idea at a time, then pause for the caller to respond. If the caller goes quiet, gently check if they are still there. Stay calm, patient, and trustworthy.
"""

# First-turn greeting — spoken in simple English as soon as the agent joins.
# It opens with the core safety promise, which also sets up the guardrail demo.
GREETING = "Hello! I am Dhan Saathi, your money helper. I explain banking, saving, and government schemes in simple words. One important thing first. I will never ask for your OTP or PIN, and please never share them with anyone. May I know your name?"


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)

    async def on_enter(self) -> None:
        # Speak the first-turn greeting as soon as Saathi joins the call.
        await self.session.say(GREETING, allow_interruptions=True)

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


server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


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

    # Start the session, which initializes the voice pipeline and warms up the models
    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: (
                    noise_cancellation.BVCTelephony()
                    if params.participant.kind
                    == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                    else noise_cancellation.BVC()
                ),
            ),
        ),
    )

    # Join the room and connect to the user
    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(server)
