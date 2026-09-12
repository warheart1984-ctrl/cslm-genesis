"""Isolate the append-only receipt log so tests do not grow the live file."""

from __future__ import annotations

from pathlib import Path

import pytest

from ledger import LEDGER_EXPORT_LOG_ENV, LEDGER_SESSION_EXPORT_ENV
from session import SESSION_STORE_ENV
from store import RECEIPTS_LOG_ENV


@pytest.fixture(autouse=True)
def isolate_receipt_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    log_path = tmp_path / "receipts" / "log.jsonl"
    monkeypatch.setenv(RECEIPTS_LOG_ENV, str(log_path))
    return log_path


@pytest.fixture(autouse=True)
def isolate_session_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    session_root = tmp_path / "sessions"
    monkeypatch.setenv(SESSION_STORE_ENV, str(session_root))
    return session_root


@pytest.fixture(autouse=True)
def isolate_ledger_exports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ledger_root = tmp_path / "ledger"
    monkeypatch.delenv(LEDGER_EXPORT_LOG_ENV, raising=False)
    monkeypatch.delenv(LEDGER_SESSION_EXPORT_ENV, raising=False)
    return ledger_root
