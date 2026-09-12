import json
import os
from pathlib import Path
from typing import Any

from canonical import canonical_json, sha256_hex

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

    # Build chain: link to previous receipt's receipt_id, if any
    prev_id = ""
    if target.is_file():
        # Read the last line's receipt_id to establish the chain
        with target.open("r", encoding="utf-8") as handle:
            last_line = None
            for raw in handle:
                line = raw.strip()
                if not line:
                    continue
                last_line = line
        if last_line:
            try:
                last_receipt_obj = json.loads(last_line)
                prev_id = last_receipt_obj.get("receipt_id", "")
            except (json.JSONDecodeError, KeyError):
                prev_id = ""

    # Zero out receipt_id for digest computation
    clone = dict(receipt)
    clone["receipt_id"] = ""
    receipt["receipt_id"] = "cslm:" + sha256_hex(canonical_json(clone))

    # Attach the chain link
    receipt["prev_receipt_id"] = prev_id

    line = json.dumps(receipt, ensure_ascii=False)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
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