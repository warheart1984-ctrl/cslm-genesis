"""JCR decision table — fail-closed, no audit-after-release."""

from __future__ import annotations

from jcr import Contradiction, decide
from verifier import SupportResult


def _item(claim_id: str, status: str, reason: str = "") -> SupportResult:
    return SupportResult(
        claim_id=claim_id,
        status=status,  # type: ignore[arg-type]
        sources=(),
        uncertainty=None,
        reason=reason,
    )


def test_all_supported_releases() -> None:
    assert decide([_item("c1", "supported")]).decision == "release"


def test_unsupported_only_is_uncertainty_statement() -> None:
    assert decide([_item("c1", "unsupported", "no citation → unsupported")]).decision == (
        "uncertainty_statement"
    )


def test_invented_citation_blocks() -> None:
    assert (
        decide(
            [_item("c1", "unsupported", "model-written citation is not independent evidence")]
        ).decision
        == "block"
    )


def test_mixed_requires_revise() -> None:
    assert (
        decide([_item("c1", "supported"), _item("c2", "unsupported")]).decision == "revise"
    )


def test_session_contradiction_blocks_when_no_safe_claim_remains() -> None:
    decision = decide(
        [_item("c1", "unsupported", "independent lookup contradicted fact x")],
        [Contradiction("c1", "t1:c1", "contradicts released claim t1:c1")],
    )
    assert decision.decision == "block"


def test_session_contradiction_revises_when_safe_claim_remains() -> None:
    decision = decide(
        [
            _item("c1", "unsupported", "independent lookup contradicted fact x"),
            _item("c2", "supported"),
        ],
        [Contradiction("c1", "t1:c1", "contradicts released claim t1:c1")],
    )
    assert decision.decision == "revise"
