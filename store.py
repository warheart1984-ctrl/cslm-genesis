"""Append-only receipt log. The adapter never writes this store."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ledger import append_receipt_export

ROOT = Path(__file__).resolve().parent
DEFAULT_RECEIPTS_LOG = ROOT / "receipts" / "log.jsonl"
RECEIPTS_LOG_ENV = "CSLM_RECEIPTS_LOG"


def receipts_log_path() -> Path:
    override = os.environ.get(RECEIPTS_LOG_ENV, "").strip()
    if override:
        return Path(override)
    return DEFAULT_RECEIPTS_LOG


def append_receipt(receipt: dict[str, Any], path: Path | None = None) -> Path:
    target = path or receipts_log_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(receipt, ensure_ascii=False)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
    append_receipt_export(receipt)
    return target


def load_receipt(receipt_id: str, path: Path | None = None) -> dict[str, Any]:
    target = path or receipts_log_path()
    if not target.is_file():
        raise FileNotFoundError(f"receipt store not found: {target}")
    wanted = {receipt_id}
    if receipt_id.startswith("cslm:"):
        wanted.add(receipt_id.removeprefix("cslm:"))
    else:
        wanted.add(f"cslm:{receipt_id}")
    with target.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("receipt_id") in wanted:
                return row
    raise KeyError(f"receipt not found: {receipt_id}")
