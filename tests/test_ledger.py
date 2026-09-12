"""Ledger export tests."""

from __future__ import annotations

import json

from adapter import MockAdapter
from cli import main
from ledger import LEDGER_EXPORT_LOG_ENV, LEDGER_SESSION_EXPORT_ENV
from pipeline import run
from session import SessionManager


def test_receipt_append_can_mirror_to_ledger_log(
    isolate_ledger_exports, monkeypatch
) -> None:
    ledger_log = isolate_ledger_exports / "ledger.jsonl"
    monkeypatch.setenv(LEDGER_EXPORT_LOG_ENV, str(ledger_log))

    result = run(
        "What is the chemical formula of water?",
        adapter=MockAdapter("Water's chemical formula is H2O."),
    )

    lines = ledger_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["event_kind"] == "cslm.receipt"
    assert event["record"]["receipt_id"] == result.receipt["receipt_id"]
    assert event["record"]["decision"] == "release"


def test_session_save_can_write_ledger_bundle(
    isolate_ledger_exports, monkeypatch
) -> None:
    export_root = isolate_ledger_exports / "sessions"
    monkeypatch.setenv(LEDGER_SESSION_EXPORT_ENV, str(export_root))

    manager = SessionManager()
    session = manager.create_session("alpha", MockAdapter(""))
    session.turn(
        "What is the chemical formula of water?",
        draft="Water's chemical formula is H2O.",
    )

    files = list(export_root.glob("*.json"))
    assert len(files) == 1
    bundle = json.loads(files[0].read_text(encoding="utf-8"))
    assert bundle["event_kind"] == "cslm.session"
    assert bundle["session"]["session_id"] == "alpha"
    assert bundle["session"]["decisions"] == ["release"]
    assert len(bundle["receipts"]) == 1


def test_cli_can_export_session_bundle(capsys) -> None:
    manager = SessionManager()
    session = manager.create_session("beta", MockAdapter(""))
    session.turn(
        "What is the chemical formula of water?",
        draft="Water's chemical formula is H2O.",
    )

    assert main(["export-session", "beta"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["event_kind"] == "cslm.session"
    assert out["session"]["session_id"] == "beta"


def test_cli_can_export_receipt_event(capsys) -> None:
    result = run(
        "What is the chemical formula of water?",
        adapter=MockAdapter("Water's chemical formula is H2O."),
    )

    assert main(["export-receipt", result.receipt["receipt_id"]]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["event_kind"] == "cslm.receipt"
    assert out["record"]["receipt_id"] == result.receipt["receipt_id"]
