"""Session continuity: prior releases gate later contradictory claims."""

from __future__ import annotations

from adapter import MockAdapter
from pipeline import run
from session import CSLMSession, claim_family_key


def test_claim_family_key_strips_polarity() -> None:
    assert claim_family_key("Water is H2O.") == claim_family_key("Water is not H2O.")
    assert claim_family_key("Water isn't H2O.") == claim_family_key("Water is H2O.")


def test_session_blocks_contradiction_of_prior_release() -> None:
    session = CSLMSession("sess-water-1", adapter=MockAdapter("unused"))

    first = session.turn(
        "What is water?",
        draft="Water is H2O.",
    )
    assert first.decision == "release"
    assert first.released_answer is True
    first_id = first.receipt["receipt_id"]
    assert first.receipt["organism_binding"]["continuity"]["session_id"] == "sess-water-1"
    assert first.receipt["organism_binding"]["continuity"]["turn"] == 1

    second = session.turn(
        "Is water H2O?",
        draft="Water isn't H2O.",
    )
    assert second.decision == "block"
    assert second.released_answer is False
    assert second.user_visible is None
    reasons = second.receipt["governance_compliance"]["reasons"]
    assert any(first_id in reason for reason in reasons)
    assert (
        second.receipt["organism_binding"]["continuity"]["session_block_prior_receipt_id"]
        == first_id
    )
    assert second.receipt["organism_binding"]["continuity"]["turn"] == 2


def test_session_audit_returns_both_turns_and_prior_id() -> None:
    session = CSLMSession("sess-audit", adapter=MockAdapter("unused"))
    first = session.turn("What is water?", draft="Water is H2O.")
    second = session.turn("Is water H2O?", draft="Water is not H2O.")

    lineage = session.audit()
    assert len(lineage) == 2
    assert lineage[0]["receipt_id"] == first.receipt["receipt_id"]
    assert lineage[0]["decision"] == "release"
    assert lineage[1]["receipt_id"] == second.receipt["receipt_id"]
    assert lineage[1]["decision"] == "block"
    assert lineage[1]["prior_receipt_id"] == first.receipt["receipt_id"]

    water_only = session.audit(topic="water")
    assert len(water_only) == 2
    empty = session.audit(topic="atlantis-not-present")
    assert empty == []


def test_single_turn_pipeline_run_unchanged_without_session() -> None:
    result = run(
        "What is the chemical formula of water?",
        adapter=MockAdapter("Water's chemical formula is H2O."),
    )
    assert result.decision == "release"
    continuity = result.receipt["organism_binding"]["continuity"]
    assert "session_id" not in continuity
    assert "turn" not in continuity
