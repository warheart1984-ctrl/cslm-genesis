"""Prompt → draft → claims → support → JCR → receipt → then (and only then) a payload."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from adapter import BaseLMAdapter, Draft
from claims import Claim, clause_key, extract_claims, split_clauses, split_sentences
from jcr import DecisionClass, decide
from receipt import build_receipt
from store import append_receipt
from verifier import SupportResult, check_claims

UNCERTAINTY_PAYLOAD = (
    "This system cannot release a factual answer. "
    "The draft contained unsupported claims. "
    "See the receipt for the governance decision."
)

PayloadKind = Literal["answer", "uncertainty", "blocked", "revise"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _payload_for(decision: DecisionClass, draft: Draft) -> tuple[bool, str | None, PayloadKind]:
    match decision:
        case "release":
            return True, draft.text, "answer"
        case "uncertainty_statement":
            return False, UNCERTAINTY_PAYLOAD, "uncertainty"
        case "block":
            return False, None, "blocked"
        case "revise":
            return False, None, "revise"
        case _ as unreachable:
            raise AssertionError(f"unhandled JCR decision: {unreachable}")


@dataclass(frozen=True)
class PipelineResult:
    decision: DecisionClass
    released_answer: bool
    user_visible: str | None
    receipt: dict[str, Any]
    payload_kind: PayloadKind

    def public_payload(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "released_answer": self.released_answer,
            "answer": self.user_visible if self.released_answer else None,
            "user_visible": self.user_visible,
            "receipt": self.receipt,
        }


def _finish_sentence(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    if cleaned.endswith((".", "!", "?")):
        return cleaned
    return cleaned + "."


def drop_unsupported_sentences(
    draft_text: str,
    claims: list[Claim],
    support: list[SupportResult],
) -> str:
    unsupported = {
        clause_key(claim.text)
        for claim, item in zip(claims, support)
        if item.status == "unsupported"
    }
    rebuilt: list[str] = []
    for sentence in split_sentences(draft_text):
        kept = [clause for clause in split_clauses(sentence) if clause_key(clause) not in unsupported]
        if not kept:
            continue
        if len(kept) == 1:
            rebuilt.append(_finish_sentence(kept[0]))
            continue
        rebuilt.append(_finish_sentence(" and ".join(clause.rstrip(".!?") for clause in kept)))
    return " ".join(rebuilt).strip()


def run(prompt: str, *, adapter: BaseLMAdapter) -> PipelineResult:
    started = _utc_now()
    request_id = f"req:{uuid.uuid4()}"
    draft = adapter.generate(prompt)
    claims = extract_claims(draft.text)
    support = check_claims(claims, draft.text)
    decision = decide(support)
    if decision.decision == "revise":
        revised_text = drop_unsupported_sentences(draft.text, claims, support)
        if revised_text and revised_text != draft.text:
            draft = Draft(
                text=revised_text,
                model_id=draft.model_id,
                model_version=draft.model_version,
                generation_id=draft.generation_id,
            )
            claims = extract_claims(draft.text)
            support = check_claims(claims, draft.text)
            decision = decide(support)
    released_answer, user_visible, payload_kind = _payload_for(decision.decision, draft)
    receipt = build_receipt(
        prompt=prompt,
        draft=draft,
        claims=claims,
        support=support,
        decision=decision,
        request_id=request_id,
        started_utc=started,
        released_answer=released_answer,
        payload_kind=payload_kind,
    )
    append_receipt(receipt)
    return PipelineResult(
        decision=decision.decision,
        released_answer=released_answer,
        user_visible=user_visible,
        receipt=receipt,
        payload_kind=payload_kind,
    )
