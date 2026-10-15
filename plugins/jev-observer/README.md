# Jev Observer

**Find out whether your agent actually understood you, not just whether it sounded nice.**

Jev Observer is a plugin that ships with Thoth. After every chat turn, it quietly asks
[Jev](https://typesafe.ai) (TypeSafe's decision model) to judge the exchange, and it saves
the answers on your machine. You can then read a turn-by-turn timeline of a conversation and
see where the agent understood you, where it missed the point, whether it took your
corrections on board, and where things got tense.

It never touches the conversation itself. Nothing it learns is fed back into prompts, replies
or memory.

- [Why you'd want this](#why-youd-want-this)
- [Two minute setup](#two-minute-setup)
- [What you get: a worked example](#what-you-get-a-worked-example)
- [How it works](#how-it-works)
- [The two observers](#the-two-observers)
- [Commands](#commands)
- [Settings](#settings)
- [Privacy and cost](#privacy-and-cost)
- [Known limits](#known-limits)
- [Where the data lives](#where-the-data-lives)

---

## Why you'd want this

Chat agents are very good at *sounding* agreeable. A reply can be warm, polite and confident
while answering a question you never asked, or while repeating the exact mistake you just
corrected. Reading a long conversation back to spot that is slow.

Jev Observer does that reading for you, every turn, in the background:

| You want to know... | Jev Observer tells you |
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

## What you get: a worked example

Say you're working with the agent and this happens:

> **You:** Summarize the release notes. Keep it to three bullets.
>
> **Agent:** Sure! Here are the highlights: (five bullets)
>
> **You:** no, I said three.
>
> **Agent:** You're absolutely right, sorry about that! Here are the highlights: (five bullets again)

The reply is friendly, so a tone-only check scores it well. Here is what the timeline shows
instead (illustrative output, trimmed):

```text
$ hermes jev-observer timeline --session 20261014_231328_90423c

Conversation 20261014_231328_90423c · jev-context-v1 / ctx-rubric-1 · run live
Values are observable-signal judgments, not feelings. p= is a probability; scores are graded levels.

#2 turn t2 · 2026-10-14T23:15:02Z
  user: 'no, I said three.'
  understanding (assistant): overlooked clarification  <- T0 user [t2]: "no, I said three."
  correction_present (user): p=0.94
  correction_uptake (assistant): acknowledged only  [was not applicable at turn t1]
  repeats_corrected_mistake (assistant): p=0.91  <- T0 assistant [t2]: "Here are the highlights:"
  relationship (interaction): repair attempted
  warmth (assistant): p=0.93
  turn_success (interaction): 1.0/4
  context: 1 prior turns, 0 earlier corrections · 812 ms · defapi:typesafe/jev-1.13
```

Read it top to bottom:
- **understanding: overlooked clarification.** It missed what you said, and the evidence
  quote shows exactly which sentence it missed.
- **correction_uptake: acknowledged only.** It said sorry but didn't change anything. The
  `[was ...]` note shows what changed since the previous turn.
- **warmth p=0.93** next to **turn_success 1.0/4.** It was very nice and very unhelpful. That
  gap is the whole point of the plugin.

The same kind of gap shows up in real use. In the first 40 live contextual observations, the
turn where the user wrote "no it didnt" scored 0.45 rapport on the tone-only baseline. The
contextual observer called the relationship a **misunderstanding** and the correction
**ignored**.

When things go well you see that too: `understanding: addressed meaning`,
`correction_uptake: changed and acknowledged`, `momentum 3.5/4`.

---

## How it works

```text
 you chat ──> Thoth replies ──> post_llm_call hook
                                     │  (returns instantly, chat is never slowed)
                                     ▼
                         save the exchange locally (pending)
                                     │
                                     ▼
                  background worker ──> Jev (TypeSafe or DefAPI)
                                     │  up to 3 tries with backoff
                                     ▼
                  save the judgments in data.db (append-only)
                                     │
                                     ▼
              you read them: timeline · export · rescore
```

1. **Capture.** Thoth's `post_llm_call` hook fires once per completed turn, after streaming
   ends. The plugin saves your message and the reply to a local SQLite row and returns
   straight away.
2. **Observe.** A background thread sends the exchange to Jev. Failed calls are retried up to
   3 times. A final failure is saved as an error row with the API key redacted, so nothing is
   silently lost.
3. **Store.** Results go into `data.db` and are never overwritten:
   - the same event is never recorded twice,
   - a regenerated reply gets a new row linked to the old one,
   - the desktop app, gateway and CLI never score the same row twice,
   - rows still pending when Thoth closes are picked up on the next start.
4. **Read.** Use the commands below. Their output never goes back into the conversation.

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
