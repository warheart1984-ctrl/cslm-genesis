"""Session continuity: point-gated turns plus cross-turn contradiction gating."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any

from adapter import BaseLMAdapter, MockAdapter
from canonical import canonical_json, digest_of, sha256_hex
from claims import Polarity, normalize_claim, polarity_of, remove_phrases
from memory.board import JarvisBoard
from pipeline import PipelineResult, run
from store import append_receipt

# Polarity tokens stripped to form a shared fact-family key for P vs ¬P.
_POLARITY_PHRASES = ("not", "cannot", "no", "never")


@dataclass(frozen=True)
class ReleasedClaimRecord:
    """Prior session release, keyed by polarity-stripped claim family."""

    content_key: str
    content_digest: str
    polarity: Polarity
    claim_text: str
    receipt_id: str
    turn: int


def claim_family_key(text: str) -> str:
    """Normalized claim with polarity markers removed (same family for P and ¬P)."""
    normalized = normalize_claim(text)
    stripped = remove_phrases(normalized, _POLARITY_PHRASES)
    return re.sub(r"\s+", " ", stripped).strip()


def _rehash_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    clone = dict(receipt)
    clone["receipt_id"] = ""
    receipt["receipt_id"] = "cslm:" + sha256_hex(canonical_json(clone))
    return receipt


def _stamp_continuity(receipt: dict[str, Any], *, session_id: str, turn: int) -> dict[str, Any]:
    stamped = copy.deepcopy(receipt)
    continuity = stamped["organism_binding"]["continuity"]
    continuity["session_id"] = session_id
    continuity["turn"] = turn
    return _rehash_receipt(stamped)


def _force_block(result: PipelineResult, prior: ReleasedClaimRecord) -> PipelineResult:
    reason = (
        "session continuity: new claim contradicts prior released claim "
        f"(receipt_id={prior.receipt_id})"
    )
    receipt = copy.deepcopy(result.receipt)
    receipt["governance_compliance"]["decision"] = "block"
    receipt["governance_compliance"]["reasons"] = [reason]
    binding = receipt["organism_binding"]
    binding["decision"]["class"] = "block"
    binding["decision"]["reasons"] = [reason]
    binding["effect"]["released_answer"] = False
    binding["effect"]["payload_kind"] = "blocked"
    binding["effect"]["performed"] = False
    binding["continuity"]["session_block_prior_receipt_id"] = prior.receipt_id
    _rehash_receipt(receipt)
    append_receipt(receipt)
    return PipelineResult(
        decision="block",
        released_answer=False,
        user_visible=None,
        receipt=receipt,
        payload_kind="blocked",
    )


class CSLMSession:
    """Thin multi-turn wrapper: pipeline point gating + session continuity gating."""

    def __init__(
        self,
        session_id: str,
        adapter: BaseLMAdapter,
        board: JarvisBoard | None = None,
    ) -> None:
        self.session_id = session_id
        self.adapter = adapter
        self.board = board
        self.receipts: list[dict[str, Any]] = []
        # Keyed by content digest of polarity-stripped normalized claim text.
        self.released_claims: dict[str, ReleasedClaimRecord] = {}
        self._turn = 0

    def turn(self, prompt: str, draft: str | None = None) -> PipelineResult:
        self._turn += 1
        adapter: BaseLMAdapter = (
            MockAdapter(draft) if draft is not None else self.adapter
        )
        result = run(
            prompt,
            adapter=adapter,
            session_id=self.session_id,
            turn=self._turn,
        )
        # Ensure session fields are present even if run() omitted them (defensive).
        receipt = result.receipt
        continuity = receipt.get("organism_binding", {}).get("continuity", {})
        if continuity.get("session_id") != self.session_id or continuity.get("turn") != self._turn:
            receipt = _stamp_continuity(
                receipt, session_id=self.session_id, turn=self._turn
            )
            result = PipelineResult(
                decision=result.decision,
                released_answer=result.released_answer,
                user_visible=result.user_visible,
                receipt=receipt,
                payload_kind=result.payload_kind,
            )

        prior = self._contradicting_prior(result)
        if prior is not None:
            result = _force_block(result, prior)
        elif result.released_answer and result.decision == "release":
            self._record_released(result)

        self.receipts.append(result.receipt)
        self._sync_board(prompt, result)
        return result

    def _sync_board(self, prompt: str, result: PipelineResult) -> None:
        """Optional Jarvis board: STM continuity only — never feeds JCR evidence."""
        if self.board is None:
            return
        receipt_id = str(result.receipt.get("receipt_id") or "") or None
        draft = str(
            ((result.receipt.get("organism_binding") or {}).get("replay") or {}).get(
                "draft"
            )
            or ""
        )
        self.board.note_turn(
            turn=self._turn,
            prompt=prompt,
            decision=str(result.decision),
            receipt_id=receipt_id,
            draft=draft,
        )
        if not (result.released_answer and result.decision == "release" and receipt_id):
            return
        claims = (result.receipt.get("factual_support") or {}).get("claims") or []
        for claim in claims:
            if claim.get("status") != "supported":
                continue
            text = str(claim.get("text") or "").strip()
            if not text:
                continue
            self.board.ingest_released_claim(
                claim_text=text,
                receipt_id=receipt_id,
                turn=self._turn,
            )

    def audit(self, topic: str | None = None) -> list[dict[str, Any]]:
        """Lineage of session decisions / receipt ids; optional topic substring filter."""
        needle = topic.lower().strip() if topic else None
        rows: list[dict[str, Any]] = []
        for index, receipt in enumerate(self.receipts, start=1):
            binding = receipt.get("organism_binding") or {}
            continuity = binding.get("continuity") or {}
            governance = receipt.get("governance_compliance") or {}
            replay = binding.get("replay") or {}
            prompt = str(replay.get("prompt") or "")
            draft = str(replay.get("draft") or "")
            claim_texts = [
                str(claim.get("text") or "")
                for claim in (receipt.get("factual_support") or {}).get("claims") or []
            ]
            haystack = " ".join([prompt, draft, *claim_texts]).lower()
            if needle and needle not in haystack:
                continue
            rows.append(
                {
                    "turn": continuity.get("turn", index),
                    "session_id": continuity.get("session_id", self.session_id),
                    "receipt_id": receipt.get("receipt_id"),
                    "decision": governance.get("decision")
                    or (binding.get("decision") or {}).get("class"),
                    "reasons": list(
                        governance.get("reasons")
                        or (binding.get("decision") or {}).get("reasons")
                        or ()
                    ),
                    "prior_receipt_id": continuity.get("session_block_prior_receipt_id"),
                    "prompt": prompt,
                    "draft": draft,
                }
            )
        return rows

    def _contradicting_prior(self, result: PipelineResult) -> ReleasedClaimRecord | None:
        claims = (result.receipt.get("factual_support") or {}).get("claims") or []
        for claim in claims:
            text = str(claim.get("text") or "").strip()
            if not text:
                continue
            family = claim_family_key(text)
            if not family:
                continue
            digest = digest_of(family)
            prior = self.released_claims.get(digest)
            if prior is None:
                continue
            new_polarity = polarity_of(text)
            if new_polarity != prior.polarity:
                return prior
        return None

    def _record_released(self, result: PipelineResult) -> None:
        receipt_id = str(result.receipt.get("receipt_id") or "")
        claims = (result.receipt.get("factual_support") or {}).get("claims") or []
        for claim in claims:
            if claim.get("status") != "supported":
                continue
            text = str(claim.get("text") or "").strip()
            if not text:
                continue
            family = claim_family_key(text)
            if not family:
                continue
            digest = digest_of(family)
            # First release for a family wins; later same-polarity repeats keep it.
            if digest in self.released_claims:
                continue
            self.released_claims[digest] = ReleasedClaimRecord(
                content_key=family,
                content_digest=digest,
                polarity=polarity_of(text),
                claim_text=text,
                receipt_id=receipt_id,
                turn=self._turn,
            )
