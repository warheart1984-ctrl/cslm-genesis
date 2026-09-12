"""Re-run verifier+JCR on a stored prompt+draft. Never call the live adapter."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from adapter import MockAdapter
from canonical import canonical_json, sha256_hex
from pipeline import run
from store import load_receipt
from receipt import replay_input_digest, VERIFIER_ID


def _verify_receipt_id(stored: dict[str, Any]) -> bool:
    """Check that the stored receipt_id matches the content digest."""
    clone = dict(stored)
    clone["receipt_id"] = ""
    clone.pop("prev_receipt_id", None)
    expected = "cslm:" + sha256_hex(canonical_json(clone))
    return expected == stored.get("receipt_id")


def stored_replay_fields(receipt: dict[str, Any]) -> tuple[str, str, str]:
    replay = receipt.get("organism_binding", {}).get("replay") or {}
    prompt = str(replay.get("prompt") or "").strip()
    draft = str(replay.get("draft") or "").strip()
    decision = str(
        replay.get("decision_class") or receipt.get("governance_compliance", {}).get("decision") or ""
    )
    if not prompt or not draft or not decision:
        raise ValueError("receipt is missing stored prompt, draft, or decision_class")
    return prompt, draft, decision


def replay_receipt(receipt_id: str) -> dict[str, Any]:
    stored = load_receipt(receipt_id)

    # ---- integrity: receipt_id must match content digest ----
    integrity_ok = _verify_receipt_id(stored)
    if not integrity_ok:
        return {
            "pass": False,
            "receipt_id": stored.get("receipt_id"),
            "integrity": "mismatch",
            "stored_decision": stored.get("governance_compliance", {}).get("decision"),
            "replayed_decision": None,
            "library_hash": stored.get("execution_provenance", {}).get("library_hash"),
            "constitution_version_hash": stored.get("constitution_version_hash"),
            "input_drift": None,
            "reason": "receipt_id does not match content digest",
        }

    prompt, draft, expected = stored_replay_fields(stored)

    # ---- run the pipeline on the stored draft (read-only, no log append) ----
    result = run(prompt, adapter=MockAdapter(draft))

    # ---- input-drift: same inputs under same law should yield same digest ----
    # Rebuild the replay_input digest from the stored hashes + replayed claims/support
    # fetched from the new receipt's factual_support
    replayed_claims = result.receipt["factual_support"]["claims"]
    claim_texts = [c["text"] for c in replayed_claims]
    support_rows = [
        {"id": c["id"], "status": c["status"], "sources": list(c["sources"])}
        for c in replayed_claims
    ]
    # stored provenance fields (model_id, store_id, library hash, const hash)
    model_id = (
        result.receipt["execution_provenance"].get("model_id")
        or stored.get("execution_provenance", {}).get("model_id")
        or "mock-v0"
    )
    store_id = (
        result.receipt["execution_provenance"].get("store_id")
        or stored.get("execution_provenance", {}).get("store_id")
        or stored.get("organism_binding", {}).get("replay", {}).get("library_hash", "")[:64]
        or "unknown"
    )
    lib_hash = (
        result.receipt["execution_provenance"].get("library_hash")
        or stored.get("execution_provenance", {}).get("library_hash")
    )
    const_hash = (
        result.receipt.get("constitution_version_hash")
        or stored.get("constitution_version_hash")
    )

    recomputed = replay_input_digest(
        prompt=prompt,
        draft=draft,
        claim_texts=claim_texts,
        support_rows=support_rows,
        constitution_version_hash=const_hash or "",
        library_hash=lib_hash or "",
        store_id=store_id,
        verifier_id=VERIFIER_ID,
        model_id=model_id,
    )
    drift = recomputed != stored.get("organism_binding", {}).get("replay", {}).get("input_digest", "")

    replayed = result.decision
    return {
        "pass": replayed == expected,
        "receipt_id": stored.get("receipt_id"),
        "integrity": "ok" if integrity_ok else "mismatch",
        "stored_decision": expected,
        "replayed_decision": replayed,
        "library_hash": stored.get("execution_provenance", {}).get("library_hash"),
        "constitution_version_hash": stored.get("constitution_version_hash"),
        "input_drift": drift,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay a stored CSLM-Genesis receipt without calling the live model."
    )
    parser.add_argument("receipt_id", help="Receipt id (cslm:… or the hex digest)")
    args = parser.parse_args(argv)
    try:
        outcome = replay_receipt(args.receipt_id)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    json.dump(outcome, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if outcome["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())