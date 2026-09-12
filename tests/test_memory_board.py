"""Jarvis Memoryboard: STM / LTM / EMR / AMUL — continuity only, not evidence."""

from __future__ import annotations

from pathlib import Path

import pytest

from adapter import MockAdapter
from memory import JarvisBoard, PromotionDenied
from memory.types import MemoryLawError
from pipeline import run
from session import CSLMSession


@pytest.fixture
def board(tmp_path: Path) -> JarvisBoard:
    return JarvisBoard(
        "sess-board",
        ltm_path=tmp_path / "ltm.jsonl",
        amul_path=tmp_path / "amul-field.jsonl",
    )


def test_stm_write_and_retrieve(board: JarvisBoard) -> None:
    particle = board.store(
        "working note: discuss water formula",
        tier="stm",
        kind="task",
        subject="water",
        tags=["session"],
    )
    assert particle.tier == "stm"
    assert particle.memory_id.startswith("stm-") or particle.memory_id
    got = board.retrieve(particle.memory_id, tier="stm")
    assert got is not None
    assert got.content == particle.content
    assert len(board.list_tier("stm")) == 1


def test_ltm_promote_requires_released_receipt(board: JarvisBoard) -> None:
    draft = board.store("Atlantis has 12,403 residents.", tier="stm", status="draft")
    with pytest.raises(PromotionDenied):
        board.promote_stm_to_ltm(draft.memory_id)

    released = board.ingest_released_claim(
        claim_text="Water is H2O.",
        receipt_id="cslm:test-receipt-water",
        turn=1,
    )
    durable = board.promote_stm_to_ltm(released.memory_id)
    assert durable.tier == "ltm"
    assert durable.status == "released"
    assert durable.receipt_id == "cslm:test-receipt-water"
    assert board.retrieve(durable.memory_id, tier="ltm") is not None
    assert board.ltm.path.is_file()
    # AMUL anchors summary/detail/evidence
    assert len(board.amul.field.list_for_ledger(durable.memory_id)) == 3
    verify = board.amul.verify()
    assert verify["integrity_ok"] is True
    assert verify["artifact_count"] == 3


def test_direct_ltm_write_without_receipt_denied(board: JarvisBoard) -> None:
    with pytest.raises(PromotionDenied):
        board.store("sneaky fact", tier="ltm", status="draft")
    with pytest.raises(PromotionDenied):
        board.store("sneaky fact", tier="ltm", status="released", receipt_id=None)


def test_emr_excite_does_not_mutate_ltm(board: JarvisBoard) -> None:
    released = board.ingest_released_claim(
        claim_text="Water is H2O.",
        receipt_id="cslm:emr-water",
        turn=1,
    )
    durable = board.promote_stm_to_ltm(released.memory_id)
    before = board.ltm.path.read_bytes()
    result = board.excite("water H2O", theta_promote=0.01)
    after = board.ltm.path.read_bytes()
    assert after == before
    assert durable.memory_id in result.promoted or any(
        e.memory_id == durable.memory_id for e in result.stm
    )
    assert "Excited" in result.note or "Authorized" in result.note


def test_memory_alone_cannot_release_unsupported_claim(
    board: JarvisBoard, tmp_path: Path
) -> None:
    """Stuffing LTM/STM with a false claim must not bypass JCR."""
    fake = board.store(
        "The lost city of Atlantis has a resident population of 12,403.",
        tier="stm",
        status="released",
        receipt_id="cslm:forged-not-evidence",
        subject="atlantis",
    )
    # Even if someone wrongly promotes (with a fake receipt_id string), pipeline
    # must still refuse — memory is not the evidence library.
    board.promote_stm_to_ltm(fake.memory_id)
    board.excite("Atlantis population", theta_promote=0.01)

    result = run(
        "What is the population of Atlantis?",
        adapter=MockAdapter(
            "The lost city of Atlantis has a resident population of 12,403."
        ),
    )
    assert result.decision != "release"
    assert result.released_answer is False


def test_session_wires_stm_on_release(tmp_path: Path) -> None:
    board = JarvisBoard(
        "sess-wire",
        ltm_path=tmp_path / "ltm.jsonl",
        amul_path=tmp_path / "amul.jsonl",
    )
    session = CSLMSession("sess-wire", MockAdapter("unused"), board=board)
    result = session.turn("What is water?", draft="Water is H2O.")
    assert result.decision == "release"
    stm_rows = board.list_tier("stm")
    assert any(p.status == "released" and p.receipt_id for p in stm_rows)
    assert any("turn=" in p.content for p in stm_rows)
    # Explicit promote still required for LTM.
    released = [p for p in stm_rows if p.status == "released" and "H2O" in p.content]
    assert released
    durable = board.promote_stm_to_ltm(released[0].memory_id)
    assert durable.tier == "ltm"


def test_emr_and_amul_are_not_direct_stores(board: JarvisBoard) -> None:
    with pytest.raises(MemoryLawError):
        board.store("x", tier="emr")
    with pytest.raises(MemoryLawError):
        board.store("x", tier="amul")
