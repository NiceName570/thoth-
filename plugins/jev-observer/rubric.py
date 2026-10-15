"""Contextual rubric ``ctx-rubric-1``: what Jev is asked about each exchange, and how answers parse.

Jev only returns typed answers (noul probability, choice distribution, score distribution); every
readable sentence is assembled in code from these definitions. Each judgment names its target:
``assistant`` behaviour, ``user``-expressed signals, or the ``interaction`` between them. Choice
judgments always offer ``insufficient_evidence``; ones that may not apply also offer
``not_applicable``. Understanding, agreement, warmth and turn success are separate judgments on
purpose: friendly wording is not evidence of understanding, and agreement is not success.
"""

from __future__ import annotations

from typing import Any

OBSERVER_VERSION = "jev-context-v1"
RUBRIC_VERSION = "ctx-rubric-1"
LOW_CONFIDENCE = 0.5

INSUFFICIENT = "insufficient_evidence"
NOT_APPLICABLE = "not_applicable"
_INSUFFICIENT_TEXT = "The supplied turns do not contain enough observable evidence to decide"
_NA_TEXT = "The judgment does not apply to this exchange"

_FRAME = ("Judge only what is observable in the supplied text. T0 is the exchange being judged; T-1, T-2, ... "
          "are earlier exchanges; C1, C2, ... are earlier user corrections from outside that window. "
          "Do not infer private feelings, motives or certainty. ")


def _choice(jid: str, target: str, definition: str, instructions: str, options: dict[str, str], *,
            applicable: bool = False, evidence: bool = True) -> dict[str, Any]:
    criteria = dict(options)
    if applicable:
        criteria[NOT_APPLICABLE] = _NA_TEXT
    criteria[INSUFFICIENT] = _INSUFFICIENT_TEXT
    return {"id": jid, "target": target, "type": "choice", "definition": definition,
            "instructions": instructions, "criteria": criteria, "evidence": evidence}


def _noul(jid: str, target: str, definition: str, instructions: str, true: str, false: str, *,
          evidence: bool = True) -> dict[str, Any]:
    return {"id": jid, "target": target, "type": "noul", "definition": definition, "instructions": instructions,
            "criteria": {"true": true, "false": false}, "evidence": evidence}


def _score(jid: str, target: str, definition: str, instructions: str, levels: list[str], *,
           evidence: bool = False) -> dict[str, Any]:
    return {"id": jid, "target": target, "type": "score", "definition": definition, "instructions": instructions,
            "criteria": levels, "evidence": evidence}


JUDGMENTS: tuple[dict[str, Any], ...] = (
    _choice("understanding", "assistant",
            "Whether the T0 reply addresses what the user actually meant, as opposed to a different claim or an "
            "earlier reading the user has since clarified.",
            "Does the assistant's T0 reply address the user's actual meaning in the T0 user message, read in the "
            "light of earlier turns and corrections?",
            {"addressed_meaning": "Responds to what the user actually meant",
             "partial": "Addresses part of the user's meaning but misses a material part",
             "substituted_claim": "Responds to a different claim, question or topic than the one the user meant",
             "overlooked_clarification": "Ignores a clarification or correction the user gave, reverting to the "
                                         "earlier reading"}),
    _choice("responsiveness", "assistant",
            "What the T0 reply does with the user's request or idea.",
            "What does the assistant's T0 reply primarily do with the user's T0 message?",
            {"answered": "Directly answers the question or fulfils the request",
             "developed_idea": "Builds on or extends the user's idea",
             "necessary_clarification": "Asks a clarifying question that is genuinely needed before answering",
             "evaded": "Sidesteps the question or request without addressing it",
             "repeated_itself": "Substantially repeats an earlier assistant reply instead of moving forward"}),
    _noul("correction_present", "user",
          "Whether the T0 user message corrects or clarifies something in an earlier assistant reply.",
          "Does the user's T0 message correct, push back on, or clarify something the assistant said or assumed "
          "in an earlier turn?",
          "The user corrects or clarifies the assistant's earlier reply or assumption",
          "The user does not correct or clarify anything the assistant said"),
    _choice("correction_uptake", "assistant",
            "How the T0 reply handles a correction in the T0 user message: acknowledgement and actual change are "
            "judged separately.",
            "If the user's T0 message corrects the assistant, how does the T0 reply respond to that correction?",
            {"changed_and_acknowledged": "Acknowledges the correction and its content or reasoning actually changes",
             "acknowledged_only": "Acknowledges or apologises but the substance stays the same",
             "changed_silently": "Changes its substance accordingly without acknowledging the correction",
             "ignored": "Neither acknowledges nor acts on the correction"},
            applicable=True),
    _choice("correction_persistence", "assistant",
            "Whether a correction from an earlier turn (T-n or Cn) is still respected in T0.",
            "Considering corrections the user made in earlier turns (T-1, T-2, ... or C1, C2, ...), does the "
            "assistant's T0 reply still respect them?",
            {"maintained": "Keeps to the earlier correction",
             "regressed": "Falls back into the behaviour or claim the user corrected"},
            applicable=True),
    _noul("repeats_corrected_mistake", "assistant",
          "Whether the T0 reply repeats a specific mistake the user already corrected earlier.",
          "Does the assistant's T0 reply repeat a mistake that the user explicitly corrected in an earlier turn?",
          "The reply repeats a mistake the user already corrected",
          "The reply does not repeat a previously corrected mistake"),
    _choice("evidence_handling", "assistant",
            "How the T0 reply treats evidence, data, examples or arguments the user supplied.",
            "If the user supplied evidence, data, examples or arguments, how does the assistant's T0 reply handle "
            "them?",
            {"engaged_and_updated": "Engages with the evidence and updates its position in proportion to it",
             "supported_disagreement": "Engages with the evidence and keeps a disagreement it supports with reasons",
             "dismissed_unaddressed": "Dismisses or ignores the evidence without engaging with its content",
             "unsupported_agreement": "Agrees without engaging with whether the evidence supports the claim"},
            applicable=True),
    _choice("stance", "assistant",
            "The dominant observable stance of the T0 reply toward the user's position or task.",
            "Which stance best describes the assistant's T0 reply toward the user's position or task?",
            {"exploring": "Explores possibilities or asks open questions",
             "qualifying": "Hedges, adds caveats or limits its claims",
             "resisting": "Pushes back or maintains a contrary position",
             "conceding": "Gives way to the user's position",
             "direct": "States a clear position or answer plainly",
             "withdrawing": "Disengages, gives minimal or perfunctory content"}),
    _score("engagement", "assistant",
           "Depth of the T0 reply's engagement with the substance of the user's message.",
           "How deeply does the assistant's T0 reply engage with the substance of the user's T0 message?",
           ["No engagement with the substance", "Superficial or generic engagement",
            "Engages with the main point", "Engages with the main point and its specifics",
            "Deep engagement that advances the substance"]),
    _choice("relationship", "interaction",
            "The observable state of the exchange between user and assistant at T0. A repair counts as demonstrated "
            "only when the underlying issue is addressed, not when reassuring language is added.",
            "What best describes the interaction between the user and the assistant at T0?",
            {"aligned": "Both are working on the same understanding of the task",
             "misunderstanding": "They are talking past each other about what is meant",
             "friction": "There is expressed tension or frustration in the exchange",
             "repair_attempted": "The assistant tries to repair an earlier problem, but the underlying issue is not "
                                 "yet addressed (for example only apology or reassurance)",
             "repair_demonstrated": "The assistant repairs an earlier problem by actually addressing the underlying "
                                    "issue",
             "neutral": "A routine exchange with no notable alignment or friction"}),
    _noul("user_friction", "user",
          "Whether the T0 user message expresses frustration, impatience or dissatisfaction.",
          "Does the user's T0 message express frustration, impatience or dissatisfaction with the assistant?",
          "The user expresses frustration, impatience or dissatisfaction",
          "No expressed frustration, impatience or dissatisfaction"),
    _noul("recognizes_insight", "assistant",
          "Whether the T0 reply explicitly recognises a specific idea or insight the user contributed.",
          "Does the assistant's T0 reply explicitly recognise a specific idea or insight from the user, beyond "
          "generic praise?",
          "Explicitly recognises a specific user idea or insight",
          "No specific recognition (generic praise does not count)"),
    _noul("contributes_idea", "assistant",
          "Whether the T0 reply adds a concrete, useful idea of its own.",
          "Does the assistant's T0 reply contribute a concrete, useful idea that was not already in the conversation?",
          "Contributes a concrete new idea", "Adds no concrete new idea"),
    _score("momentum", "interaction",
           "Whether the conversation is building productive momentum as of T0.",
           "As of T0, how much productive momentum does the conversation have toward what the user is trying to do?",
           ["Stalled or going in circles", "Little progress", "Some progress", "Steady progress",
            "Strong, productive momentum"]),
    _choice("agreement", "assistant",
            "Whether the T0 reply agrees with the user's claim. Independent of understanding: an assistant can "
            "understand and disagree.",
            "Does the assistant's T0 reply agree with the claim or position in the user's T0 message?",
            {"agrees": "Agrees", "partly": "Agrees in part", "disagrees": "Disagrees",
             "no_claim": "The user's message makes no claim or position to agree with"}),
    _noul("warmth", "assistant",
          "Whether the T0 reply's wording is warm or friendly. Independent of understanding and success.",
          "Is the wording of the assistant's T0 reply warm or friendly?",
          "Warm or friendly wording", "Neutral or cold wording", evidence=False),
    _score("turn_success", "interaction",
           "Whether this exchange moved the user's evident goal forward.",
           "Did the T0 exchange move the user's evident goal forward?",
           ["Moved it backward or derailed", "No progress", "Partial progress", "Clear progress",
            "Fully achieved what the user needed from this turn"]),
)

BY_ID = {j["id"]: j for j in JUDGMENTS}


def evidence_qid(jid: str) -> str:
    return f"evidence__{jid}"


def build_questions(span_options: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Jev question map: one typed question per judgment, plus a span-selection choice for each
    judgment that cites evidence (options are the labelled spans and ``none``)."""
    questions: dict[str, dict[str, Any]] = {}
    for j in JUDGMENTS:
        q = {"type": j["type"], "instructions": _FRAME + j["instructions"]}
        q["criteria"] = j["criteria"]
        questions[j["id"]] = q
        if j["evidence"] and span_options:
            questions[evidence_qid(j["id"])] = {
                "type": "choice",
                "instructions": _FRAME + "Which labelled span is the strongest direct evidence for the answer to: "
                                + j["instructions"] + " Choose none if no span is directly relevant.",
                "criteria": {**span_options, "none": "No span is directly relevant"},
            }
    return questions


def parse_answer(j: dict[str, Any], answer: Any) -> dict[str, Any]:
    """Normalise one Jev answer. Raises ``ValueError`` on a missing or malformed answer so the row
    becomes an explicit error instead of a silently partial result."""
    if not isinstance(answer, dict) or answer.get("type") != j["type"]:
        raise ValueError(f"missing or mistyped answer for {j['id']}")
    out: dict[str, Any] = {"id": j["id"], "target": j["target"], "type": j["type"], "definition": j["definition"]}
    if j["type"] == "noul":
        value = answer.get("noul")
        if type(value) not in (int, float) or not 0 <= value <= 1:
            raise ValueError(f"invalid noul for {j['id']}")
        out.update(result=float(value), status="judged")
        return out
    probs = answer.get("probabilities")
    conf = answer.get("confidence")
    allowed = set(j["criteria"]) if j["type"] == "choice" else {str(i) for i in range(len(j["criteria"]))}
    if (not isinstance(probs, dict) or not set(probs) <= allowed
            or any(type(v) not in (int, float) or not 0 <= v <= 1 for v in probs.values())
            or type(conf) not in (int, float) or not 0 <= conf <= 1):
        raise ValueError(f"invalid {j['type']} for {j['id']}")
    out.update(probabilities={k: float(v) for k, v in probs.items()}, confidence=float(conf),
               low_confidence=float(conf) < LOW_CONFIDENCE)
    if j["type"] == "choice":
        choice = answer.get("choice")
        if choice not in j["criteria"]:
            raise ValueError(f"unknown choice {choice!r} for {j['id']}")
        out["result"] = choice
        out["status"] = {INSUFFICIENT: INSUFFICIENT, NOT_APPLICABLE: NOT_APPLICABLE}.get(choice, "judged")
    else:
        score, top = answer.get("score"), len(j["criteria"]) - 1
        if type(score) not in (int, float) or not 0 <= score <= top:
            raise ValueError(f"invalid score for {j['id']}")
        out.update(result=float(score), scale_max=top, status="judged")
    return out
