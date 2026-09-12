"""Emit a three-bucket receipt plus an organism_receipt.v1-shaped binding."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from adapter import Draft
from canonical import canonical_json, digest_of, sha256_hex
from claims import Claim
from constitution import CONSTITUTION_ID, constitution_version_hash
from jcr import JcrDecision
from verifier import SupportResult, VERIFIER_ID

RECEIPT_VERSION = "cslm.receipt.v0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_receipt(
    *,
    prompt: str,
    draft: Draft,
    claims: list[Claim],
    support: list[SupportResult],
    decision: JcrDecision,
    request_id: str,
    started_utc: str,
    finished_utc: str | None = None,
    released_answer: bool,
    payload_kind: str,
) -> dict[str, Any]:
    finished = finished_utc or _utc_now()
    const_hash = constitution_version_hash()
    claim_by_id = {claim.id: claim for claim in claims}
    factual_claims = []
    for item in support:
        claim = claim_by_id[item.claim_id]
        factual_claims.append(
            {
                "id": item.claim_id,
                "text": claim.text,
                "status": item.status,
                "sources": list(item.sources),
                "uncertainty": item.uncertainty,
                "reason": item.reason,
            }
        )

    replay_input = {
        "prompt": prompt,
        "draft": draft.text,
        "claims": [claim.text for claim in claims],
        "support": [
            {"id": item.claim_id, "status": item.status, "sources": list(item.sources)}
            for item in support
        ],
        "constitution_version_hash": const_hash,
        "verifier_id": VERIFIER_ID,
        "model_id": draft.model_id,
    }
    input_digest = digest_of(replay_input)

    receipt: dict[str, Any] = {
        "receipt_version": RECEIPT_VERSION,
        "receipt_id": "",
        "constitution_id": CONSTITUTION_ID,
        "constitution_version_hash": const_hash,
        "factual_support": {"claims": factual_claims},
        "governance_compliance": {
            "constitution_id": CONSTITUTION_ID,
            "constitution_version_hash": const_hash,
            "applicable_rules": list(decision.applicable_rules),
            "decision": decision.decision,
            "reasons": list(decision.reasons),
            "jcr_authority": decision.jcr_authority,
        },
        "execution_provenance": {
            "model_id": draft.model_id,
            "model_version": draft.model_version,
            "config": {
                "adapter": draft.model_id,
                "verifier": VERIFIER_ID,
            },
            "timestamps": {
                "started_utc": started_utc,
                "finished_utc": finished,
            },
            "request_id": request_id,
            "generation_id": draft.generation_id,
        },
        "organism_binding": {
            "organ": {
                "name": "cslm-genesis",
                "kind": "language_organ",
                "dialect": "cslm-jcr-v0",
            },
            "intent": {
                "kind": "language_release",
                "prompt_digest": digest_of(prompt),
            },
            "decision": {
                "class": decision.decision,
                "reasons": list(decision.reasons),
                "authority": decision.jcr_authority,
            },
            "effect": {
                "released_answer": released_answer,
                "payload_kind": payload_kind,
                "performed": released_answer or payload_kind == "uncertainty",
            },
            "evidence": {
                "factual_digest": digest_of(factual_claims),
                "governance_digest": digest_of(
                    {
                        "decision": decision.decision,
                        "reasons": list(decision.reasons),
                    }
                ),
            },
            "replay": {
                "input_digest": input_digest,
                "decision_class": decision.decision,
                "deterministic": True,
            },
            "continuity": {
                "constitution_id": CONSTITUTION_ID,
                "constitution_version_hash": const_hash,
                "spine_id": "cslm-genesis.language_organ",
            },
        },
    }
    clone = dict(receipt)
    clone["receipt_id"] = ""
    receipt["receipt_id"] = "cslm:" + sha256_hex(canonical_json(clone))
    return receipt
