"""Isolate the append-only receipt log so tests do not grow the live file."""

from __future__ import annotations

from pathlib import Path

import pytest

from store import RECEIPTS_LOG_ENV


@pytest.fixture(autouse=True)
def isolate_receipt_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    log_path = tmp_path / "receipts" / "log.jsonl"
    monkeypatch.setenv(RECEIPTS_LOG_ENV, str(log_path))
    return log_path
