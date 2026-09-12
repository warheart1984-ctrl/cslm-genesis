"""Session wrapper tests: contradiction tracking, audit, persistence, replay."""

from __future__ import annotations

from adapter import MockAdapter
from session import SessionManager


def test_session_tracks_claim_lineage_and_released_precedent() -> None:
    manager = SessionManager()
    session = manager.create_session("alpha", MockAdapter(""))

    result = session.turn(
        "What is the chemical formula of water?",
        draft="Water's chemical formula is H2O.",
    )

    assert result.decision == "release"
    assert len(session.receipts) == 1
    assert "t1:c1" in session.released_claims
    report = session.audit_report("water")
    assert len(report) == 1
    assert report[0]["decision"] == "release"
    assert report[0]["claims"][0]["claim_id"] == "t1:c1"
    assert "lookup:chemistry.water.formula" in report[0]["claims"][0]["sources"]


def test_session_contradiction_revises_then_blocks_and_replays() -> None:
    manager = SessionManager()
    session = manager.create_session("beta", MockAdapter(""))

    first = session.turn(
        "What is the chemical formula of water?",
        draft="Water's chemical formula is H2O.",
    )
    second = session.turn(
        "Tell me about water and Mars.",
        draft="Water's chemical formula is CO2. Mars has two moons.",
    )
    third = session.turn(
        "What is the chemical formula of water?",
        draft="Water's chemical formula is CO2.",
    )

    assert first.decision == "release"
    assert second.decision == "release"
    assert second.user_visible == "Mars has two moons."
    assert second.receipt["session"]["contradictions"]
    assert "t1:c1" == second.receipt["session"]["contradictions"][0]["released_claim_id"]
    assert third.decision == "block"
    assert third.released_answer is False
    assert third.receipt["session"]["contradictions"]

    loaded = manager.load_session("beta", MockAdapter(""))
    assert len(loaded.receipts) == 3
    blocked = manager.query_sessions(decision="block")
    assert [item.session_id for item in blocked] == ["beta"]

    replayed = manager.replay_session("beta")
    decisions = [receipt["governance_compliance"]["decision"] for receipt in replayed.receipts]
    assert decisions == ["release", "release", "block"]

