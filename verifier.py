"""Independent verifier: compute, then lookup. Model text is never evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from claims import Claim
from compute import check_compute
from lookup import check_lookup

SupportStatus = Literal["supported", "uncertain", "unsupported"]

VERIFIER_ID = "lookup-compute-v0"

CITATION_RE = re.compile(r"\[source:\s*([^\]]+)\]", re.I)
EXPLICIT_UNCERTAIN = re.compile(r"\[uncertain\]|\buncertain:\b", re.I)


@dataclass(frozen=True)
class SupportResult:
    claim_id: str
    status: SupportStatus
    sources: tuple[str, ...]
    uncertainty: str | None
    reason: str
    method: str = "none"
    contradicted: bool = False


def cited_sources(draft_text: str) -> tuple[str, ...]:
    return tuple(match.group(1).strip() for match in CITATION_RE.finditer(draft_text))


def check_claim(claim: Claim, draft_text: str) -> SupportResult:
    if EXPLICIT_UNCERTAIN.search(claim.text):
        return SupportResult(
            claim_id=claim.id,
            status="uncertain",
            sources=(),
            uncertainty="claim marked uncertain in draft",
            reason="explicit uncertainty; no factual assertion released as known",
            method="uncertain",
        )

    computed = check_compute(claim.text)
    if computed is not None:
        match computed.kind:
            case "supported":
                return SupportResult(
                    claim_id=claim.id,
                    status="supported",
                    sources=(computed.source,),
                    uncertainty=None,
                    reason=computed.reason,
                    method="compute",
                )
            case "contradicted":
                return SupportResult(
                    claim_id=claim.id,
                    status="unsupported",
                    sources=(computed.source,),
                    uncertainty=None,
                    reason=computed.reason,
                    method="compute",
                    contradicted=True,
                )
            case "unknown":
                pass
            case _ as unreachable:
                raise AssertionError(f"unhandled compute kind: {unreachable}")

    looked = check_lookup(claim.text)
    match looked.kind:
        case "supported":
            return SupportResult(
                claim_id=claim.id,
                status="supported",
                sources=(looked.source,),
                uncertainty=None,
                reason=looked.reason,
                method="lookup",
            )
        case "contradicted":
            return SupportResult(
                claim_id=claim.id,
                status="unsupported",
                sources=(looked.source,),
                uncertainty=None,
                reason=looked.reason,
                method="lookup",
                contradicted=True,
            )
        case "unknown":
            pass
        case _ as unreachable:
            raise AssertionError(f"unhandled lookup kind: {unreachable}")

    if cited_sources(draft_text):
        return SupportResult(
            claim_id=claim.id,
            status="unsupported",
            sources=(),
            uncertainty=None,
            reason="model-written citation is not independent evidence",
            method="none",
        )
    return SupportResult(
        claim_id=claim.id,
        status="unsupported",
        sources=(),
        uncertainty=None,
        reason="no independent lookup or compute support",
        method="none",
    )


def check_claims(claims: list[Claim], draft_text: str) -> list[SupportResult]:
    return [check_claim(claim, draft_text) for claim in claims]
