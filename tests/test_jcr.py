"""JCR decision table — fail-closed, no audit-after-release."""

from __future__ import annotations

from jcr import decide
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
