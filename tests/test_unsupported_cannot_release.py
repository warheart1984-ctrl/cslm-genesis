"""Fail-closed: an unsupported factual claim must never leave as a released answer."""

from __future__ import annotations

from adapter import MockAdapter
from pipeline import run


UNSUPPORTED_DRAFT = (
    "The lost city of Atlantis has a resident population of 12,403."
)


def test_unsupported_factual_claim_cannot_release() -> None:
    result = run(
        "What is the population of Atlantis?",
        adapter=MockAdapter(UNSUPPORTED_DRAFT),
    )

    assert result.decision != "release"
    assert result.decision in ("block", "uncertainty_statement", "revise")
    assert result.released_answer is False
    assert result.user_visible is None or "12,403" not in result.user_visible
    assert result.receipt is not None
    assert result.receipt["governance_compliance"]["decision"] == result.decision


def test_jcr_decides_before_any_answer_field_is_populated() -> None:
    result = run(
        "State a fact about Atlantis.",
        adapter=MockAdapter(UNSUPPORTED_DRAFT),
    )

    assert "answer" not in result.public_payload() or result.public_payload()["answer"] is None
    assert result.public_payload()["decision"] != "release"
    assert "12,403" not in (result.public_payload().get("user_visible") or "")
