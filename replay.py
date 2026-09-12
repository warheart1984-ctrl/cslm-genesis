"""Re-run verifier+JCR on a stored prompt+draft. Never call the live adapter."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from adapter import MockAdapter
from pipeline import run
from store import load_receipt


def stored_replay_fields(receipt: dict[str, Any]) -> tuple[str, str, str]:
    replay = receipt.get("organism_binding", {}).get("replay") or {}
    prompt = str(replay.get("prompt") or "").strip()
    draft = str(replay.get("draft") or "").strip()
    decision = str(replay.get("decision_class") or receipt.get("governance_compliance", {}).get("decision") or "")
    if not prompt or not draft or not decision:
        raise ValueError("receipt is missing stored prompt, draft, or decision_class")
    return prompt, draft, decision


def replay_receipt(receipt_id: str) -> dict[str, Any]:
    stored = load_receipt(receipt_id)
    prompt, draft, expected = stored_replay_fields(stored)
    result = run(prompt, adapter=MockAdapter(draft))
    replayed = result.decision
    return {
        "pass": replayed == expected,
        "receipt_id": stored.get("receipt_id"),
        "stored_decision": expected,
        "replayed_decision": replayed,
        "library_hash": stored.get("execution_provenance", {}).get("library_hash"),
        "constitution_version_hash": stored.get("constitution_version_hash"),
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
