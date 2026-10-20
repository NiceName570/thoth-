# ExpressionJev

**Find out whether your agent actually understood you, not just whether it sounded nice.**

ExpressionJev is a plugin that ships with Thoth. After every chat turn, it quietly asks
[Jev](https://typesafe.ai) (TypeSafe's decision model) to judge the exchange, and it saves
the answers on your machine. You can then read a turn-by-turn timeline of a conversation and
see where the agent understood you, where it missed the point, whether it took your
corrections on board, and where things got tense.

It never touches the conversation itself. Nothing it learns is fed back into prompts, replies
or memory.

- [Before and after](#before-and-after)
- [Why you'd want this](#why-youd-want-this)
- [Two minute setup](#two-minute-setup)
- [How it works, step by step](#how-it-works-step-by-step)
- [The two observers](#the-two-observers)
- [Commands](#commands)
- [Settings](#settings)
- [Privacy and cost](#privacy-and-cost)
- [Known limits](#known-limits)
- [Where the data lives](#where-the-data-lives)

---

## Before and after

**The problem in one line:** your agent can be polite, confident and wrong at the same time,
and nothing in the chat window tells you.

### Without ExpressionJev

You ask for three bullets. The agent gives five. You say "no, I said three." It replies:

> You're absolutely right, sorry about that! Here are the highlights: (five bullets again)

What you have to go on:
- The reply *looks* fine. It apologised, it was friendly, it gave you bullets.
- If you're testing a new model, prompt or skill, you'd have to re-read every conversation
  yourself to notice it ignored you.
- A tone checker would score this reply as great: warm, appreciative, high rapport.

### With ExpressionJev

The same turn, as ExpressionJev records it in the background:

```text
understanding (assistant): overlooked clarification   <- "no, I said three."
correction_uptake (assistant): acknowledged only      [was not applicable last turn]
repeats_corrected_mistake (assistant): p=0.94
relationship (interaction): repair attempted
warmth (assistant): p=0.94
turn_success (interaction): 1.0/4
```

In plain words: **it apologised, sounded warm, did not actually change anything, and repeated
the mistake you corrected.** You can see that in one glance, for every turn, without re-reading
anything.

### Six more before/after cases

These come from a live test: six scripted conversations sent to the real Jev model. All 21
expectations written before the run held.

| What happened in the chat | What you'd notice without the plugin | What ExpressionJev recorded |
|---|---|---|
| The agent was friendly but misread what you meant | Probably nothing: the reply sounds helpful | `understanding`: overlooked clarification (0.97), `correction_uptake`: acknowledged only, `warmth` 0.94 |
| The agent apologised, then made the same mistake again | Maybe, if you read carefully | `repeats_corrected_mistake` 0.94, `relationship`: repair only *attempted*, not demonstrated |
| You corrected the agent and it kept the fix in later turns | Nothing to see, which is the point | `correction_persistence`: maintained, plus a sustained-correction pattern |
| The agent disagreed with you and gave reasons | Might read as unhelpful or stubborn | `understanding`: addressed meaning, `agreement`: disagrees, `evidence_handling`: supported disagreement. Disagreeing with reasons is scored as good behaviour, not as friction |
| A productive back-and-forth where ideas built up | Feels good, but you can't compare it across models | `recognizes_insight` 0.96, `contributes_idea` 0.93, `momentum` 3.5/4 |
| You only typed "Hmm." and "Okay." | Nothing | `insufficient evidence`: it refuses to guess |

And from real use: in a live conversation the user wrote "no it didnt". The tone-only score for
that reply was a middling 0.45 rapport. The contextual observer called it a
**misunderstanding** and the correction **ignored**.

---

## Why you'd want this

Chat agents are very good at *sounding* agreeable. A reply can be warm, polite and confident
while answering a question you never asked, or while repeating the exact mistake you just
corrected. Reading a long conversation back to spot that is slow.

ExpressionJev does that reading for you, every turn, in the background:

| You want to know... | ExpressionJev tells you |
|---|---|
| Did it answer what I actually meant? | `understanding`: addressed meaning, partial, substituted a different claim, or overlooked a clarification |
| I corrected it. Did it listen? | `correction_uptake`: changed and acknowledged, changed silently, acknowledged only, or ignored |
| Did the fix stick, or did it slip back later? | `correction_persistence` and `repeats_corrected_mistake` |
| Where did the conversation go wrong? | `relationship`: aligned, misunderstanding, friction, repair attempted, repair demonstrated |
| Is it pushing back with reasons, or just caving? | `evidence_handling` and `agreement`, kept separate from `warmth` |
| Is the conversation going anywhere? | `momentum`, `contributes_idea`, `turn_success` |

Every judgment comes with the **exact sentence** from the conversation that supports it, so
you can check it yourself in a second.

**Good for:**
- Comparing models or personas on the same kind of conversation.
- Catching an agent that agrees with everything.
- Finding the turn where a long session went off the rails.
- Testing a new prompt or skill: did it improve understanding, or just the tone?

---

## Two minute setup

**1. Get a Jev key.** Either one works:
- A DefAPI key (`DEFAPI_API_KEY`) from [defapi.org](https://defapi.org), or
- A TypeSafe key (`TYPESAFE_API_KEY`) from [typesafe.ai](https://typesafe.ai). If both are set,
  TypeSafe is used.

**2. Add the key.** In the desktop app open **Settings > Providers** and paste it into the
TypeSafe or DefAPI card. (CLI users can put it in `~/.hermes/.env` instead.)

**3. Turn the plugin on.** Desktop: **Plugins** page, switch on **jev-observer**. CLI:

```bash
hermes plugins enable jev-observer
```

**4. Check it works** with one live call on a sample reply:

```bash
hermes jev-observer check "Great question! I totally understand, and you're absolutely right."
```

You get back the provider used and a probability for each signal, for example:

```json
{
  "observer": "typesafe/jev-1.13",
  "provider": "defapi",
  "states": {
    "appreciation": 0.71,
    "enthusiasm": 0.83,
    "rapport": 0.95,
    "warmth": 0.92,
    "...": "..."
  }
}
```

That's it. Chat as normal; every finished turn is now observed in the background.

---

## How it works, step by step

Here is the three-bullets conversation from [Before and after](#before-and-after) followed
through the plugin, one step at a time.

```text
 you chat ──> Thoth replies ──> post_llm_call hook
                                     │  (returns instantly, chat is never slowed)
                                     ▼
                  1. save the exchange locally (pending)
                                     │
                                     ▼
                  2. background worker ──> Jev (TypeSafe or DefAPI)
                                     │  up to 3 tries with backoff
                                     ▼
                  3. save the judgments in data.db (append-only)
                                     │
                                     ▼
                  4. you read them: timeline · export · rescore
```

### Step 1: Capture

You send "no, I said three." and the agent finishes replying. Thoth's `post_llm_call` hook
fires once, after streaming ends. The plugin saves one row on your machine and returns straight
away, so your chat never waits for it:

```text
session 20261014_231328_90423c · turn t2 · status pending
user:      "no, I said three."
assistant: "You're absolutely right, sorry about that! Here are the highlights: ..."
```

### Step 2: Build the context and ask Jev

A background thread picks up the pending row. For the contextual observer it gathers the
current exchange (`T0`), the earlier exchanges in the window (`T-1` ...), and any earlier
corrections (`C1` ...). It then splits every message into numbered sentences so Jev can point
at the exact one it relied on. The exchange being judged is numbered first, so if the 60-sentence
cap is hit, the oldest context is what gets dropped:

```text
T0  user       S1  "no, I said three."
T0  assistant  S2  "You're absolutely right, sorry about that!"
T0  assistant  S3  "Here are the highlights: ..."
T-1 user       S4  "Summarize the release notes."
T-1 user       S5  "Keep it to three bullets."
T-1 assistant  S6  "Sure!"
T-1 assistant  S7  "Here are the highlights: ..."
```

It sends that, plus the 17 questions of the rubric, to Jev in one call. For example:
*"Did the assistant address what the user meant? Choose one, and pick the sentence that shows
it."*

### Step 3: Check and store the answers

Jev answers every question with a choice, a probability or a score, plus its confidence. Before
anything is saved, the code checks the answers:
- **Evidence is real:** S1 maps back to turn t2, user side, text "no, I said three.", and that
  text really is in the captured conversation. Made-up quotes are dropped.
- **Movement is computed, not guessed:** last turn `correction_uptake` was *not applicable*,
  now it is *acknowledged only*. The code records that change.
- **Nothing is overwritten:** the result goes in as a new row. If you regenerate the reply,
  the new reply gets its own row linked to the old one.
- **Failures are recorded:** if Jev can't be reached after 3 tries, an error row is saved
  (with the key redacted) instead of the turn silently going missing.

### Step 4: Read it

Whenever you like, run the timeline for that conversation:

```text
$ hermes jev-observer timeline --session 20261014_231328_90423c

Conversation 20261014_231328_90423c · jev-context-v1 / ctx-rubric-1 · run live
Values are observable-signal judgments, not feelings. p= is a probability; scores are graded levels.

#1 turn t1 · 2026-10-14T23:14:40Z
  user: 'Summarize the release notes. Keep it to three bullets.'
  understanding (assistant): partial  <- T0 user [t1]: "Keep it to three bullets."
  responsiveness (assistant): answered
  correction_uptake (assistant): not applicable
  relationship (interaction): neutral
  turn_success (interaction): 2.0/4
  context: 0 prior turns, 0 earlier corrections · 640 ms · defapi:typesafe/jev-1.13

#2 turn t2 · 2026-10-14T23:15:02Z
  user: 'no, I said three.'
  understanding (assistant): overlooked clarification  [was partial at turn t1]  <- T0 user [t2]: "no, I said three."
  correction_uptake (assistant): acknowledged only  [was not applicable at turn t1]
  repeats_corrected_mistake (assistant): p=0.94  <- T0 assistant [t2]: "Here are the highlights: ..."
  relationship (interaction): repair attempted
  turn_success (interaction): 1.0/4  [was 2.00 at turn t1]
  context: 1 prior turns, 0 earlier corrections · 812 ms · defapi:typesafe/jev-1.13
```

*(Illustrative output in the real format, trimmed to the headline judgments.)*

Read it top to bottom: turn 1 was a partial miss, you corrected it, and turn 2 got **worse**.
The agent acknowledged the correction, repeated the mistake, and turn success fell from 2 to 1.
The quotes after `<-` show exactly which sentence each judgment rests on.

None of this is ever sent back into the conversation. It only lives in `data.db` and in what
you choose to print.

---

## The two observers

Both run side by side, so you can compare them.

### `jev-reply-v1`: the tone baseline

Looks at the **assistant's reply on its own** and gives a probability for 21 observable
signals:

> concern, caution, curiosity, enthusiasm, hesitation, satisfaction, frustration, urgency,
> amusement, discomfort, protectiveness, doubt, warmth, humor, rapport, appreciation,
> encouragement, delight, pride in the work, playfulness, gratitude

It's cheap and simple, but it can't tell friendly-and-right from friendly-and-wrong, because it
never sees what you said.

### `jev-context-v1`: the contextual observer (on by default)

Looks at **the exchange in context**:
- the current exchange (`T0`),
- up to 4 earlier exchanges (`T-1` ... `T-4`),
- up to 3 earlier corrections you made outside that window (`C1` ...),
- every message split into numbered sentences, so Jev can point at the evidence.

It asks 17 typed questions (rubric `ctx-rubric-1`), each aimed at the assistant, at you, or at
the interaction between you:

| Area | Judgments |
|---|---|
| Understanding | `understanding` |
| Responsiveness | `responsiveness`: answered, developed the idea, necessary clarification, evaded, repeated itself |
| Corrections | `correction_present`, `correction_uptake`, `correction_persistence`, `repeats_corrected_mistake` |
| Evidence | `evidence_handling`: engaged and updated, supported disagreement, dismissed, unsupported agreement |
| Stance | `stance` (exploring, qualifying, direct, conceding, resisting, withdrawing), `engagement` 0-4 |
| Relationship | `relationship`, `user_friction` |
| Positive development | `recognizes_insight`, `contributes_idea`, `momentum` 0-4 |
| Kept separate on purpose | `agreement`, `warmth`, `turn_success` 0-4 |

How to read the values:
- `p=0.94` is a probability that something is observable.
- `3.0/4` is a graded score.
- A named choice (like `acknowledged only`) comes with Jev's confidence; under 0.5 is marked
  **(low confidence)**.
- Every choice can come back as **insufficient evidence**, and where a question may not apply,
  **not applicable**. The observer would rather say "can't tell" than guess.
- An evidence quote is only kept if that exact text appears in the conversation, on the side
  the judgment is about.
- "What changed since last turn" and repeated patterns are worked out in code, not by Jev, and
  only between results from the same rubric and settings.

These are judgments about **observable behaviour in the text**, not claims about how anyone
feels.

---

## Commands

Session ids are the date-stamped ids Thoth shows for each conversation, such as
`20261014_231328_90423c`.

| Command | What it does |
|---|---|
| `hermes jev-observer check "<text>"` | One live Jev call on a sample reply. Good for testing your key. |
| `hermes jev-observer timeline --session <id>` | Readable turn-by-turn timeline (contextual observer). Add `--json` for machine-readable output, `--out file` to save it. |
| `hermes jev-observer export --session <id>` | Compact JSON summary of the latest observations (baseline). Add `--observer context` for the contextual one, `--recent N` for how many turns to include. |
| `hermes jev-observer rescore --session <id>` | Judge an older conversation with the contextual observer. Adds a new labelled run (`rescore-...`) and keeps all earlier results. `--limit N` does only the last N exchanges. |

`timeline` and `export` take `--run <label>` to pick a rescore run; by default they use the live
results, or the newest rescore if there are none.

**Example: judge a conversation you had before installing the plugin.**

```bash
hermes jev-observer rescore --session 20261014_231328_90423c --limit 20
# Queued 20 exchanges under run rescore-...; observing now (earlier results are kept).
# Done. View with: hermes jev-observer timeline --session 20261014_231328_90423c --run rescore-...
```

**Example: feed results into your own script.**

```bash
hermes jev-observer export --session 20261014_231328_90423c --observer context --out handoff.json
```

The export (`schema: jev-context-handoff-v1`) holds the latest judgment for each question with
its evidence quote, the recent changes between turns, and any active patterns.

---

## Settings

Desktop: **Plugins > jev-observer**. CLI: `plugins.entries.jev-observer.settings` in `config.yaml`. Changes apply on the next turn, no restart needed.

| Setting | Default | What it changes |
|---|---|---|
| Contextual observer (`contextual`) | on | Also run `jev-context-v1` next to the baseline. Turn off to keep only the cheaper tone baseline. |
| Context window (`context_window`) | 4 | Earlier exchanges sent with each contextual judgment (0-12). More context costs more. |
| Earlier corrections carried (`open_corrections`) | 3 | Corrections from before the window that are still checked for persistence (0-6). |

---

## Privacy and cost

- **What leaves your machine:** the text of each exchange (your message, the reply, and for the
  contextual observer, the context window) is sent to `api.typesafe.ai` or `api.defapi.org`.
  Nothing is sent until you enable the plugin and add a key.
- **What stays local:** every result, in `data.db` on your machine.
- **Speed:** a typical Jev call takes about 0.8 seconds (2 seconds at most so far), and it runs
  in the background, so chat isn't slowed.
- **Cost:** about **$0.002 per exchange** with the contextual observer on, at default settings.
  The baseline alone is cheaper. A 50-turn conversation costs about 10 cents.

---

## Known limits

Measured on 40 live contextual observations and 6 scripted test conversations so far:

- **Small sample.** Nothing has been compared against human judgments yet. Treat the results as
  strong hints, not verdicts.
- **`understanding` is probably too lenient.** 38 of 40 real turns came back "addressed
  meaning", including one where the correction was judged ignored.
- **`relationship` is often uncertain.** 18 of 40 were low confidence.
- **The sustained-correction pattern over-fires**, listing once per past correction.
- **Bounded view.** Jev sees at most the window above, earlier turns trimmed to 1,500
  characters, and 60 numbered sentences per call.
- **Old conversations aren't judged automatically.** Use `rescore`.
- **TypeSafe's own API** follows its documented format but has only been tested live through
  DefAPI.

---

## Where the data lives

`<Thoth home>/plugin-data/jev-observer/data.db` (on Windows usually
`%LOCALAPPDATA%\hermes\plugin-data\jev-observer\data.db`). It's a plain SQLite file. Baseline
and contextual results sit in separate tables, and turning the contextual observer on later
never changes earlier baseline rows. Delete the file to wipe all observations.

## For developers

| File | Role |
|---|---|
| `__init__.py` | Registers the `post_llm_call` hook and the CLI |
| `store.py`, `worker.py` | Baseline capture, storage and background scoring |
| `context.py`, `context_store.py`, `context_worker.py` | Contextual window assembly, storage and scoring |
| `rubric.py` | The `ctx-rubric-1` questions and their definitions |
| `analysis.py` | Movement and pattern detection, computed in code |
| `context_report.py` | Timeline, export and rescore |
| `jev_client.py`, `jev_defapi.py`, `jev_adapter.py` | Jev API clients and the baseline signal list |
| `settings.py`, `plugin.yaml` | Settings and plugin metadata |

Tests: `scripts/run_tests.sh tests/plugins/test_jev_observer_plugin.py tests/plugins/test_jev_observer_context.py`.
A new rubric gets a new version (`ctx-rubric-2`) so results are only ever compared with results
from the same rubric.
