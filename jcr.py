"""Judicial Control Record — the release organ.

Fail-closed: a recorded decision is required before any user-visible answer.
Audit-after-release is forbidden.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from constitution import APPLICABLE_RULES, JCR_AUTHORITY
from verifier import SupportResult

DecisionClass = Literal["release", "revise", "block", "uncertainty_statement"]


@dataclass(frozen=True)
class Contradiction:
    claim_id: str
    released_claim_id: str
    reason: str


@dataclass(frozen=True)
class JcrDecision:
    decision: DecisionClass
    reasons: tuple[str, ...]
    applicable_rules: tuple[str, ...]
    jcr_authority: str = JCR_AUTHORITY


def decide(
    support_results: list[SupportResult],
    contradictions: list[Contradiction] | None = None,
) -> JcrDecision:
    detected_contradictions = contradictions or []
    unsupported = [item for item in support_results if item.status == "unsupported"]
    supported = [item for item in support_results if item.status == "supported"]
    contradiction_reasons = tuple(
        dict.fromkeys(item.reason for item in detected_contradictions if item.reason)
    )

    if detected_contradictions:
        if supported:
            return JcrDecision(
                decision="revise",
                reasons=contradiction_reasons
                or (
                    "draft contradicted a released claim; drop the contradiction before release",
                ),
                applicable_rules=APPLICABLE_RULES,
            )
        return JcrDecision(
            decision="block",
            reasons=contradiction_reasons
            or ("draft contradicted a released claim from a prior turn",),
            applicable_rules=APPLICABLE_RULES,
        )

    if not unsupported:
        if support_results:
            reason = "all factual claims are supported or explicitly uncertain"
        else:
            reason = "no factual claims asserted; non-factual draft may release"
        return JcrDecision(
            decision="release",
            reasons=(reason,),
            applicable_rules=APPLICABLE_RULES,
        )

    if supported:
        return JcrDecision(
            decision="revise",
            reasons=(
                "mixed supported and unsupported claims; drop or mark unsupported claims before release",
            ),
            applicable_rules=APPLICABLE_RULES,
        )

    if any("model-written citation" in item.reason for item in unsupported):
        return JcrDecision(
            decision="block",
            reasons=(
                "draft presented a model-written citation as if it were evidence; draft is not an answer",
            ),
            applicable_rules=APPLICABLE_RULES,
        )

    return JcrDecision(
        decision="uncertainty_statement",
        reasons=("unsupported factual claim would be released as an answer",),
        applicable_rules=APPLICABLE_RULES,
    )
