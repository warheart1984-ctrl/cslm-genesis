"""Optional export layer for external persistence/ledger systems."""

from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any

from canonical import digest_of, sha256_hex

LEDGER_EXPORT_VERSION = "cslm.ledger_export.v0"
LEDGER_EXPORT_LOG_ENV = "CSLM_LEDGER_EXPORT_LOG"
LEDGER_SESSION_EXPORT_ENV = "CSLM_LEDGER_SESSION_EXPORT_DIR"
SOURCE_REPOSITORY = "warheart1984-ctrl/cslm-genesis"
SOURCE_SYSTEM = "cslm-genesis"
_PATH_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.Lock] = {}


def ledger_export_log_path() -> Path | None:
    override = os.environ.get(LEDGER_EXPORT_LOG_ENV, "").strip()
    return Path(override) if override else None


def ledger_session_export_root() -> Path | None:
    override = os.environ.get(LEDGER_SESSION_EXPORT_ENV, "").strip()
    return Path(override) if override else None


def _path_lock(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.Lock())


def _write_json(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _path_lock(path):
        temp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
        temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temp.replace(path)
    return path


def build_receipt_export(receipt: dict[str, Any]) -> dict[str, Any]:
    session_meta = receipt.get("session") or {}
    effect = receipt.get("organism_binding", {}).get("effect", {})
    event = {
        "export_version": LEDGER_EXPORT_VERSION,
        "event_kind": "cslm.receipt",
        "recorded_at": receipt.get("execution_provenance", {})
        .get("timestamps", {})
        .get("finished_utc"),
        "source": {
            "system": SOURCE_SYSTEM,
            "repository": SOURCE_REPOSITORY,
        },
        "record": {
            "receipt_id": receipt.get("receipt_id"),
            "session_id": session_meta.get("session_id"),
            "turn_id": session_meta.get("turn_id"),
            "decision": receipt.get("governance_compliance", {}).get("decision"),
            "released_answer": effect.get("released_answer"),
            "payload_kind": effect.get("payload_kind"),
        },
        "receipt": receipt,
    }
    event["event_id"] = "ledger:" + sha256_hex(
        json.dumps(
            {
                "event_kind": event["event_kind"],
                "receipt_id": event["record"]["receipt_id"],
                "session_id": event["record"]["session_id"],
                "turn_id": event["record"]["turn_id"],
            },
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return event


def append_receipt_export(receipt: dict[str, Any], path: Path | None = None) -> Path | None:
    target = path or ledger_export_log_path()
    if target is None:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    event = build_receipt_export(receipt)
    with _path_lock(target):
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
            handle.flush()
    return target


def build_session_export(session: dict[str, Any]) -> dict[str, Any]:
    receipts = list(session.get("receipts") or [])
    decisions = [
        receipt.get("governance_compliance", {}).get("decision")
        for receipt in receipts
    ]
    return {
        "export_version": LEDGER_EXPORT_VERSION,
        "event_kind": "cslm.session",
        "event_id": "ledger:" + sha256_hex(
            json.dumps(
                {
                    "session_id": session.get("session_id"),
                    "updated_at": session.get("updated_at"),
                    "turns": len(receipts),
                },
                sort_keys=True,
                ensure_ascii=False,
            )
        ),
        "source": {
            "system": SOURCE_SYSTEM,
            "repository": SOURCE_REPOSITORY,
        },
        "session": {
            "session_id": session.get("session_id"),
            "created_at": session.get("created_at"),
            "updated_at": session.get("updated_at"),
            "turns": len(receipts),
            "decisions": decisions,
            "released_claims": session.get("released_claims") or {},
            "receipts_digest": digest_of(receipts),
        },
        "receipts": receipts,
    }


def write_session_export(session: dict[str, Any], root: Path | None = None) -> Path | None:
    target_root = root or ledger_session_export_root()
    if target_root is None:
        return None
    session_id = str(session.get("session_id") or "").strip()
    if not session_id:
        raise ValueError("session export requires session_id")
    path = target_root / f"{sha256_hex(session_id)}.json"
    return _write_json(path, build_session_export(session))
