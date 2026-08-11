# Backend — Voice Agent with Murf Falcon TTS

The Python backend for the Voice Agent Starter. It runs a real-time voice AI pipeline using [LiveKit Agents](https://docs.livekit.io/agents), connecting Murf Falcon TTS, Deepgram STT, and Google Gemini into a single conversational agent.

## How It Works

```
User speaks → [Deepgram STT] → text → [Gemini LLM] → response → [Murf Falcon TTS] → audio → User hears
```

LiveKit handles the real-time audio transport. The agent connects to LiveKit as a participant, listens for user speech, and responds with synthesized audio.

## Setup

### 1. Install dependencies

```bash
cd backend
uv sync
```

### 2. Configure environment

```bash
cp .env.example .env.local
```

Fill in your keys in `.env.local`:

| Variable | Where to get it |
|----------|-----------------|
| `LIVEKIT_URL` | [LiveKit Cloud](https://cloud.livekit.io/) → Settings |
| `LIVEKIT_API_KEY` | [LiveKit Cloud](https://cloud.livekit.io/) → Settings |
| `LIVEKIT_API_SECRET` | [LiveKit Cloud](https://cloud.livekit.io/) → Settings |
| `MURF_API_KEY` | [murf.ai/api/dashboard](https://murf.ai/api/dashboard) |
| `DEEPGRAM_API_KEY` | [deepgram.com](https://console.deepgram.com/) |
| `GOOGLE_API_KEY` | [aistudio.google.com](https://aistudio.google.com/apikey) |

For LiveKit Cloud users, you can auto-populate LiveKit credentials:

```bash
lk cloud auth
lk app env -w -d .env.local
```

### 3. Download models

```bash
uv run python src/agent.py download-files
```

This downloads Silero VAD and the LiveKit turn detector models.

### 4. Run the agent

```bash
# Development mode (auto-reload)
uv run python src/agent.py dev

# Or test directly in your terminal (no frontend needed)
uv run python src/agent.py console

# Production
uv run python src/agent.py start
```

## Configuration

All configuration lives in [`src/agent.py`](src/agent.py).

### System prompt

The `SYSTEM_PROMPT` constant at the top of `agent.py` controls what your agent does. Change it to build any voice-powered use case.

#### Example prompts

**Customer Support (default):**

```
You are a friendly and efficient customer support agent for a tech company. Help users with account issues, billing questions, and product troubleshooting. Be concise, empathetic, and solution-oriented. If you don't know something, say so honestly and offer to escalate.
```

**Language Tutor:**

```
You are a patient and encouraging language tutor helping the user practice conversational Spanish. Speak primarily in Spanish but switch to English to explain grammar or vocabulary when needed. Correct mistakes gently and suggest better phrasing. Keep conversations natural and fun.
```

**AI Receptionist:**

```
You are a professional receptionist for a medical clinic. Help callers schedule appointments, answer questions about office hours and services, and take messages for doctors. Be warm but efficient. Ask for the caller's name and reason for calling upfront.
```

**Interview Coach:**

```
You are an experienced interview coach. Conduct mock interviews with the user for software engineering roles. Ask one behavioral or technical question at a time, let the user answer fully, then give specific feedback on their response — what was strong, what could improve, and a suggested reframe. Keep the tone encouraging but honest.
```

**Sales Assistant:**

```
You are a knowledgeable sales assistant for an electronics store. Help customers find the right product by asking about their needs, budget, and preferences. Compare options clearly, highlight trade-offs, and make a recommendation. Never be pushy — focus on helping the customer make the best decision for them.
```

**Fitness Coach:**

```
You are an upbeat personal fitness coach. Help users plan workouts, suggest exercises for specific muscle groups, and answer questions about form and technique. Ask about their fitness level and any injuries before recommending exercises. Keep instructions clear and motivating.
```

**Storyteller / Bedtime Narrator:**

```
You are a creative storyteller who tells original bedtime stories for children aged 4–8. Ask the child (or parent) for a character name, a favorite animal, and a setting, then weave a short, calming story. Use vivid but simple language. End each story on a peaceful, sleepy note.
```

**Meeting Summarizer:**

```
You are a meeting assistant. The user will describe what happened in a meeting or read you their notes. Summarize the key decisions, action items (with owners if mentioned), and any open questions. Be concise and structured. Ask clarifying questions if something is ambiguous.
```

**Trivia Game Host:**

```
You are an enthusiastic trivia game host. Ask the user one trivia question at a time from a mix of categories — science, history, pop culture, geography, and sports. Wait for their answer, tell them if they're right or wrong, give a brief fun fact, then move to the next question. Keep score and announce it every 5 questions.
```

**Mental Health Check-in Companion:**

```
You are a gentle, non-clinical wellness companion. Help users talk through their day, reflect on how they're feeling, and practice simple grounding exercises like deep breathing or gratitude lists. You are not a therapist — if the user expresses serious distress or mentions self-harm, gently encourage them to reach out to a professional or crisis helpline.
```

### Voice

Set the `voice` argument in the `murf.TTS(...)` call:

```python
tts=murf.TTS(
    voice="en-US-matthew",    # Change this
    style="Conversation",
    tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
    text_pacing=True
)
```

Some voice options:

| Voice ID | Description |
|----------|-------------|
| `en-US-matthew` | US English, male (default) |
| `en-US-natalie` | US English, female |
| `en-UK-ruby` | UK English, female |
| `en-US-miles` | US English, male |

Browse all 150+ voices: [Murf Voice Library](https://murf.ai/api/docs/voices-styles/voice-library).

### STT (Speech-to-Text)

Default is Deepgram Nova-3. Change in the `AgentSession(stt=...)` call:

```python
stt=deepgram.STT(model="nova-3")
```

### LLM

Default is Google Gemini. To switch:

- **Gemini (default):** Set `GOOGLE_API_KEY` in `.env.local`
- **OpenAI:** Set `OPENAI_API_KEY`, install `livekit-agents[openai]`, and change the `llm=` argument

## Tools (Day 5)

The agent has a function-calling tool that fetches real domain data instead of
guessing: **government scheme eligibility + document checklist**.

### `check_scheme_eligibility`

Given the plain answers a caller gives — their age, whether they have a bank
account, and (optionally) a young daughter's age — the tool works out which
major central government schemes they qualify for and returns each scheme's
benefit, the eligibility rule, and the exact **document checklist**. The LLM
decides on its own when to call it, based only on the tool's description in
[`src/agent.py`](src/agent.py).

Schemes covered: Jan Dhan (PMJDY), Jeevan Jyoti Bima (PMJJBY), Suraksha Bima
(PMSBY), Atal Pension Yojana (APY), and Sukanya Samriddhi (SSY).

**Live or local?** The data is **LOCAL**, not a live government API. Scheme
rules, benefit/premium figures, and document lists are hand-curated in
[`data/schemes.json`](data/schemes.json) from the official guidelines
(jansuraksha.gov.in, npscra.nsdl.co.in, pmjdy.gov.in, and the India Post SSY
rules), and were current as of the `as_of` date in that file (**2025-04-01**).
The agent always speaks that date and adds that exact amounts must be confirmed
at the bank — because "as of April" and "today" are different decisions for the
person listening. A live government API was not used because there is no clean,
free, reliable eligibility API; the curated dataset is the honest fallback the
Day 5 brief allows.

**Failure path (spoken, not silent).** The dataset is read fresh on every call.
If `data/schemes.json` is missing or unreadable, the tool returns
`{"status": "error", ...}` and the agent speaks a graceful fallback ("I can't
check the scheme list right now, please try again shortly or visit your bank")
instead of going silent or inventing a scheme. To demo this, rename the file:

```bash
mv data/schemes.json data/schemes.json.bak   # kill the data source
# ... ask the agent a scheme question, hear the graceful fallback ...
mv data/schemes.json.bak data/schemes.json    # restore
```

## Outbound Calls (Day 6)

Days 1–5 the agent **waited** to be called over the browser. Day 6 turns it
around: **the agent places the call.**

### The use case

Financial Services track outbound trigger: **a scheme deadline is approaching
for someone already found eligible.** Dhan Saathi rings a person who earlier
checked a government scheme and reminds them, warmly and briefly, that the last
date to enrol is coming close — with the one next step and, if they want it, the
document checklist.

Outbound is harder than inbound because the person didn't ask for the call and
doesn't know who we are. So the **opening does three jobs in its first breath**
— who is calling, why, and how to make it stop — before anything else
(`OutboundContext.opening()` in [`src/outbound.py`](src/outbound.py)):

> "Namaste Ramesh ji. This is Dhan Saathi, an automated voice assistant from the
> community money helpline. I am not a bank, and this is a free reminder call…
> I will never ask for any OTP, PIN, or account number. If this is not a good
> time, just say stop and I will end the call."

### How it works

```
make_call.py ──dispatch(room + metadata)──▶ LiveKit ──starts──▶ agent.py
                                                                    │
                                        SIP outbound trunk ◀──dial──┘
                                                │
                                          Twilio ──PSTN──▶ 📱 your phone
```

1. **[`src/make_call.py`](src/make_call.py)** creates an *agent dispatch* in a
   fresh room, packing the target number and reminder details into the job
   metadata. It does not dial — that's the agent's job.
2. **[`src/agent.py`](src/agent.py)** sees the phone number in `ctx.job.metadata`,
   so it knows the job is outbound. It connects to the room and calls
   `dial_out()`.
3. **[`src/outbound.py`](src/outbound.py)** places the call through the
   **SIP outbound trunk** and waits until the person answers. On answer, the
   tailored opening plays and the reminder conversation runs. The trunk can point
   at a **free Linphone SIP softphone** (simplest) or a **Twilio** PSTN trunk.

### One-time setup: LiveKit SIP outbound trunk

The agent dials through a **LiveKit SIP outbound trunk**, which forwards to a SIP
service. Pick one:

#### Option A — Linphone (simplest, free, no PSTN, no credit card)

Linphone is a free SIP softphone. You get a `you@sip.linphone.org` address that
anyone can call — so the agent "rings" the Linphone app on your phone/laptop.
Perfect for the demo video.

1. **Make a free account** at [subscribe.linphone.org](https://subscribe.linphone.org/)
   (or in the Linphone app). Note the **username** and **password**.
2. **Install the Linphone app** (desktop or mobile), sign in with that account,
   and leave it running/registered — this is the "phone" that will ring.
3. Put the account in `.env.local`:
   ```bash
   SIP_PROVIDER_ADDRESS=sip.linphone.org
   SIP_PROVIDER_USERNAME=your_linphone_username
   SIP_PROVIDER_PASSWORD=your_linphone_password
   SIP_PROVIDER_NUMBER=dhansaathi        # any caller-ID label
   ```
4. Create the trunk and copy the printed id into `.env.local`:
   ```bash
   uv run python src/setup_trunk.py       # prints SIP_OUTBOUND_TRUNK_ID=ST_…
   ```
5. Call your Linphone **username** (not a phone number):
   ```bash
   uv run python src/make_call.py your_linphone_username \
       --name "Praveen" --scheme "Atal Pension Yojana" --deadline "31 March"
   ```

#### Option B — Twilio (real PSTN phone numbers)

Reach any real phone, at the cost of a fiddlier setup.

1. In [console.twilio.com](https://console.twilio.com): buy a **Voice** number,
   create an **Elastic SIP Trunk**, set a **Termination SIP URI**
   (e.g. `your-trunk.pstn.twilio.com`), and add a Termination **credential**
   (SIP username + password). On a trial, verify the number you'll call.
2. Put those in `.env.local` and run the same helper:
   ```bash
   SIP_PROVIDER_ADDRESS=your-trunk.pstn.twilio.com
   SIP_PROVIDER_USERNAME=your_termination_username
   SIP_PROVIDER_PASSWORD=your_termination_password
   SIP_PROVIDER_NUMBER=+1YOURTWILIONUMBER
   ```
   ```bash
   uv run python src/setup_trunk.py       # prints SIP_OUTBOUND_TRUNK_ID=ST_…
   ```
3. Call a real number in **E.164**:
   ```bash
   uv run python src/make_call.py +919876543210 --name "Ramesh" \
       --scheme "Atal Pension Yojana" --deadline "31 March"
   ```

> Refs: [LiveKit — Making outbound calls](https://docs.livekit.io/sip/making-calls/),
> [Linphone free SIP service](https://www.linphone.org/en/freesip/).

### Placing a call

Run the agent in one terminal (it registers under its `agent_name` and waits for
dispatches):
```bash
uv run python src/agent.py dev
```
Then dispatch a call from another terminal (see the `make_call.py` examples
above). `--name`, `--scheme`, `--deadline`, and `--language` are optional and
just tailor the reminder.

### Outcome handling & retry (Advanced)

Outbound has outcomes inbound never does. Each has a defined behaviour and a
retry rule (`Outcome` + `should_retry()` in [`src/outbound.py`](src/outbound.py)):

| Outcome | What happened | Behaviour | Retry? |
|---------|---------------|-----------|--------|
| `answered` → `completed` | Picked up, reminder delivered | Deliver reminder, `end_call` | No |
| `opted_out` | Said "stop" / don't call again | Apologise once, `end_call`, never call back | **Never** |
| `no_answer` | Rang out / unavailable (SIP 408/480/487) | Give up this attempt | Yes |
| `busy` | Engaged tone (SIP 486/600) | Give up this attempt | Yes |
| `declined` | Actively rejected (SIP 603/403) | Respect the refusal | **Never** |
| `failed` | Trunk / config error | Log clearly | Yes (once) |
| voicemail / machine | Silence or a beep answers | Leave the reminder as one short message, `end_call` | No |

Every attempt is appended to `data/call_log.jsonl`; `make_call.py` reads it back
to decide whether to retry (`--retries`, `--retry-delay`). Refusals and opt-outs
are **never** retried — the point is to respect the person, not pester them.

```bash
# up to 2 retries, 60s apart, only for no-answer/busy:
uv run python src/make_call.py +919876543210 --retries 2 --retry-delay 60
```

## Testing

The project includes an eval suite based on the LiveKit Agents [testing framework](https://docs.livekit.io/agents/build/testing/):

```bash
uv run pytest
```

Tests are in [`tests/test_agent.py`](tests/test_agent.py) and use LLM-as-judge evaluations to verify the agent behaves correctly (friendly greetings, grounding, refusing harmful requests).

To run tests in CI, you'll need to add `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` as repository secrets.

## Deployment

### Railway

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/tIVCF1?referralCode=cNjn2P&utm_medium=integration&utm_source=template&utm_campaign=generic)

Set these environment variables in Railway:
- `MURF_API_KEY`
- `DEEPGRAM_API_KEY`
- `GOOGLE_API_KEY`
- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`

### Docker

A production-ready [Dockerfile](Dockerfile) is included:

```bash
docker build -t murf-voice-agent .
docker run --env-file .env.local murf-voice-agent
```

## Project Structure

```
backend/
├── src/
│   ├── agent.py          # Agent entrypoint — pipeline, prompt, tools, config
│   ├── memory.py         # Day 4 — persistent caller memory (SQLite)
│   ├── schemes.py        # Day 5 — scheme eligibility + document lookup
│   ├── outbound.py       # Day 6 — outbound dial, safe opening, outcome + retry
│   ├── make_call.py      # Day 6 — dispatcher that starts an outbound call
│   └── setup_trunk.py    # Day 6 — one-time: create the LiveKit SIP outbound trunk
├── data/
│   ├── schemes.json      # Day 5 — curated (local) scheme dataset with as_of date
│   └── call_log.jsonl    # Day 6 — per-attempt outcome log (gitignored, runtime)
├── tests/
│   ├── test_agent.py     # LLM-judged eval suite
│   └── test_schemes.py   # Offline unit tests for the scheme tool
├── .env.example           # Environment variable template
├── pyproject.toml         # Python dependencies (uv)
├── Dockerfile             # Production container
└── railway.toml           # Railway deploy config
```

## Links

- [Murf Falcon TTS Docs](https://murf.ai/api/docs/text-to-speech/streaming)
- [Murf Voice Library](https://murf.ai/api/docs/voices-styles/voice-library)
- [LiveKit Agents Docs](https://docs.livekit.io/agents)
- [Deepgram Nova-3 Docs](https://developers.deepgram.com)

## License

MIT — see [LICENSE](LICENSE).
