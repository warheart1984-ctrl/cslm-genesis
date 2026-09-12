"""Thin session wrapper for multi-turn CSLM-Genesis conversations."""

from __future__ import annotations

import json
import os
import re
import threading
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from adapter import BaseLMAdapter, MockAdapter
from canonical import sha256_hex
from claims import Claim, extract_claims, normalize_claim, polarity_of
from jcr import Contradiction
from ledger import build_session_export, write_session_export
from pipeline import PipelineResult, run_draft
from replay import stored_replay_fields
from store import append_receipt
from verifier import SupportResult, check_claims

SESSION_STORE_ENV = "CSLM_SESSION_STORE"
DEFAULT_SESSION_ROOT = Path(__file__).resolve().parent / "receipts" / "sessions"
SESSION_INDEX = "index.json"
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _session_root(path: Path | None = None) -> Path:
    if path is not None:
        return path
    override = os.environ.get(SESSION_STORE_ENV, "").strip()
    if override:
        return Path(override)
    return DEFAULT_SESSION_ROOT


def _session_receipts(receipts: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    return tuple(deepcopy(receipt) for receipt in receipts)


def _result_with_receipt(result: PipelineResult, receipt: dict[str, Any]) -> PipelineResult:
    return PipelineResult(
        decision=result.decision,
        released_answer=result.released_answer,
        user_visible=result.user_visible,
        receipt=receipt,
        payload_kind=result.payload_kind,
    )


def _claim_identity(text: str) -> str:
    return " ".join(
        token
        for token in normalize_claim(text).split()
        if token not in {"not", "cannot", "never", "no"}
    )


def _support_from_claim(claim: dict[str, Any], claim_id: str) -> SupportResult:
    return SupportResult(
        claim_id=claim_id,
        status=str(claim["status"]),  # type: ignore[arg-type]
        sources=tuple(str(item) for item in claim.get("sources") or ()),
        uncertainty=claim.get("uncertainty"),
        reason=str(claim.get("reason") or ""),
    )


def _released_answers(receipts: tuple[dict[str, Any], ...]) -> list[str]:
    answers: list[str] = []
    for receipt in receipts:
        released = str((receipt.get("session") or {}).get("released_answer_text") or "").strip()
        if released:
            answers.append(released)
    return answers


@dataclass(frozen=True)
class QueryResult:
    session_id: str
    created_at: str
    updated_at: str
    turns: int
    decisions: tuple[str, ...]
    path: str


def _receipt_signature(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision": receipt.get("governance_compliance", {}).get("decision"),
        "reasons": receipt.get("governance_compliance", {}).get("reasons"),
        "draft": receipt.get("organism_binding", {}).get("replay", {}).get("draft"),
        "released_answer": receipt.get("organism_binding", {}).get("effect", {}).get("released_answer"),
        "payload_kind": receipt.get("organism_binding", {}).get("effect", {}).get("payload_kind"),
        "session": {
            "turn_id": receipt.get("session", {}).get("turn_id"),
            "prompt": receipt.get("session", {}).get("prompt"),
            "history_context": receipt.get("session", {}).get("history_context"),
            "submitted_draft": receipt.get("session", {}).get("submitted_draft"),
            "released_claim_ids": receipt.get("session", {}).get("released_claim_ids"),
            "released_answer_text": receipt.get("session", {}).get("released_answer_text"),
            "contradictions": receipt.get("session", {}).get("contradictions"),
        },
    }


class CSLMSession:
    def __init__(
        self,
        session_id: str,
        adapter: BaseLMAdapter,
        *,
        receipts: list[dict[str, Any]] | None = None,
        released_claims: dict[str, SupportResult] | None = None,
        manager: SessionManager | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> None:
        self.session_id = session_id
        self.adapter = adapter
        self._receipts = list(receipts or [])
        self.released_claims = dict(released_claims or {})
        self._released_precedents = self._build_released_precedents(self._receipts)
        self._manager = manager
        now = _utc_now()
        self.created_at = created_at or now
        self.updated_at = updated_at or now

    @property
    def receipts(self) -> tuple[dict[str, Any], ...]:
        return _session_receipts(tuple(self._receipts))

    def _next_turn_id(self) -> str:
        return f"t{len(self._receipts) + 1}"

    def _scoped_claim_id(self, turn_id: str, claim_id: str) -> str:
        return f"{turn_id}:{claim_id}"

    def _effective_prompt(self, prompt: str, history_context: bool) -> str:
        if not history_context:
            return prompt
        released_answers = _released_answers(tuple(self._receipts))
        if not released_answers:
            return prompt
        context = "\n".join(f"- {answer}" for answer in released_answers)
        return (
            "Prior released answers in this session:\n"
            f"{context}\n\n"
            f"Current user prompt:\n{prompt}"
        )

    def _detect_contradictions(
        self,
        claims: list[Claim],
        support: list[SupportResult],
    ) -> list[Contradiction]:
        contradictions: list[Contradiction] = []
        for claim, item in zip(claims, support):
            for prior in self._released_precedents.values():
                if not set(item.sources).intersection(prior["sources"]):
                    continue
                if item.contradicted:
                    reason = f"{item.reason}; contradicts released claim {prior['claim_id']}"
                elif (
                    claim.polarity != prior["polarity"]
                    and _claim_identity(claim.text) == prior["identity"]
                ):
                    reason = f"claim polarity contradicts released claim {prior['claim_id']}"
                else:
                    continue
                contradictions.append(
                    Contradiction(
                        claim_id=item.claim_id,
                        released_claim_id=str(prior["claim_id"]),
                        reason=reason,
                    )
                )
                break
        return contradictions

    def _build_released_precedents(
        self,
        receipts: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        precedents: dict[str, dict[str, Any]] = {}
        for receipt in receipts:
            if receipt.get("governance_compliance", {}).get("decision") != "release":
                continue
            session_meta = receipt.get("session") or {}
            claim_ids = session_meta.get("claim_ids") or {}
            for claim in receipt.get("factual_support", {}).get("claims", []):
                if str(claim.get("status")) != "supported":
                    continue
                scoped_id = claim_ids.get(str(claim["id"]), str(claim["id"]))
                precedents[scoped_id] = {
                    "claim_id": scoped_id,
                    "sources": tuple(str(source) for source in claim.get("sources") or ()),
                    "identity": _claim_identity(str(claim.get("text") or "")),
                    "polarity": polarity_of(str(claim.get("text") or "")),
                }
        return precedents

    def _annotate_receipt(
        self,
        result: PipelineResult,
        *,
        turn_id: str,
        prompt: str,
        history_context: bool,
        submitted_draft: str,
        contradictions: list[Contradiction],
    ) -> PipelineResult:
        receipt = deepcopy(result.receipt)
        local_to_scoped: dict[str, str] = {}
        for claim in receipt.get("factual_support", {}).get("claims", []):
            scoped = self._scoped_claim_id(turn_id, str(claim["id"]))
            local_to_scoped[str(claim["id"])] = scoped
        receipt["session"] = {
            "session_id": self.session_id,
            "turn_id": turn_id,
            "prompt": prompt,
            "history_context": history_context,
            "submitted_draft": submitted_draft,
            "claim_ids": local_to_scoped,
            "released_claim_ids": [
                local_to_scoped[str(claim["id"])]
                for claim in receipt.get("factual_support", {}).get("claims", [])
                if str(claim.get("status")) == "supported" and result.decision == "release"
            ],
            "released_answer_text": result.user_visible if result.released_answer else None,
            "contradictions": [
                {
                    "claim_id": local_to_scoped.get(item.claim_id, item.claim_id),
                    "released_claim_id": item.released_claim_id,
                    "reason": item.reason,
                }
                for item in contradictions
            ],
        }
        return _result_with_receipt(result, receipt)

    def _lock_released_claims(self, receipt: dict[str, Any]) -> None:
        if receipt.get("governance_compliance", {}).get("decision") != "release":
            return
        session_meta = receipt.get("session") or {}
        claim_ids = session_meta.get("claim_ids") or {}
        for claim in receipt.get("factual_support", {}).get("claims", []):
            if str(claim.get("status")) != "supported":
                continue
            scoped_id = claim_ids.get(str(claim["id"]))
            if not scoped_id:
                continue
            self.released_claims[scoped_id] = _support_from_claim(claim, scoped_id)
            self._released_precedents[scoped_id] = {
                "claim_id": scoped_id,
                "sources": tuple(str(source) for source in claim.get("sources") or ()),
                "identity": _claim_identity(str(claim.get("text") or "")),
                "polarity": polarity_of(str(claim.get("text") or "")),
            }

    def turn(
        self,
        prompt: str,
        draft: str | None = None,
        *,
        history_context: bool = False,
        persist: bool = True,
    ) -> PipelineResult:
        turn_id = self._next_turn_id()
        effective_prompt = self._effective_prompt(prompt, history_context)
        live_adapter = MockAdapter(draft) if draft is not None else self.adapter
        generated_draft = live_adapter.generate(effective_prompt)
        claims = extract_claims(generated_draft.text)
        support = check_claims(claims, generated_draft.text)
        contradictions = self._detect_contradictions(claims, support)
        result = run_draft(
            effective_prompt,
            draft=generated_draft,
            contradictions=contradictions or None,
            store_receipt=False,
        )
        annotated = self._annotate_receipt(
            result,
            turn_id=turn_id,
            prompt=prompt,
            history_context=history_context,
            submitted_draft=generated_draft.text,
            contradictions=contradictions,
        )
        if persist:
            append_receipt(annotated.receipt)
        self._receipts.append(annotated.receipt)
        self.updated_at = _utc_now()
        self._lock_released_claims(annotated.receipt)
        if persist and self._manager is not None:
            self._manager.save_session(self)
        return annotated

    def audit_report(self, topic: str | None = None) -> list[dict[str, Any]]:
        needle = (topic or "").strip().lower()
        report: list[dict[str, Any]] = []
        for receipt in self._receipts:
            session_meta = receipt.get("session") or {}
            claim_ids = session_meta.get("claim_ids") or {}
            claims = receipt.get("factual_support", {}).get("claims", [])
            filtered_claims = [
                {
                    "claim_id": claim_ids.get(str(claim["id"]), str(claim["id"])),
                    "text": claim.get("text"),
                    "status": claim.get("status"),
                    "reason": claim.get("reason"),
                    "sources": claim.get("sources"),
                }
                for claim in claims
                if not needle
                or needle in str(claim.get("text") or "").lower()
                or needle == claim_ids.get(str(claim["id"]), "").lower()
            ]
            contradictions = [
                item
                for item in session_meta.get("contradictions") or []
                if not needle
                or needle == str(item.get("claim_id") or "").lower()
                or needle == str(item.get("released_claim_id") or "").lower()
                or needle in str(item.get("reason") or "").lower()
            ]
            if needle and not filtered_claims and not contradictions:
                continue
            report.append(
                {
                    "session_id": self.session_id,
                    "turn_id": session_meta.get("turn_id"),
                    "prompt": session_meta.get("prompt"),
                    "decision": receipt.get("governance_compliance", {}).get("decision"),
                    "reasons": receipt.get("governance_compliance", {}).get("reasons"),
                    "claims": filtered_claims,
                    "contradictions": contradictions,
                }
            )
        return report

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "receipts": self._receipts,
            "released_claims": {
                claim_id: {
                    "claim_id": item.claim_id,
                    "status": item.status,
                    "sources": list(item.sources),
                    "uncertainty": item.uncertainty,
                    "reason": item.reason,
                }
                for claim_id, item in self.released_claims.items()
            },
        }


class SessionManager:
    _index_lock = threading.RLock()
    _session_locks_guard = threading.Lock()
    _session_locks: dict[str, threading.RLock] = {}

    def __init__(self, root: Path | None = None) -> None:
        self.root = _session_root(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _validate_session_id(self, session_id: str) -> str:
        cleaned = session_id.strip()
        if not SESSION_ID_RE.fullmatch(cleaned):
            raise ValueError("session_id must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}")
        return cleaned

    def normalize_session_id(self, session_id: str) -> str:
        return self._validate_session_id(session_id)

    def _session_lock(self, session_id: str) -> threading.RLock:
        with self._session_locks_guard:
            return self._session_locks.setdefault(session_id, threading.RLock())

    @property
    def index_path(self) -> Path:
        return self.root / SESSION_INDEX

    def _session_filename(self, session_id: str) -> str:
        return f"{sha256_hex(self._validate_session_id(session_id))}.json"

    def _session_path(self, session_id: str) -> Path:
        return self.root / self._session_filename(session_id)

    def _write_index_json(self, data: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temp = self.root / f"{SESSION_INDEX}.tmp"
        temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temp.replace(self.index_path)

    def _write_session_json(self, session_id: str, data: dict[str, Any]) -> Path:
        path = self._session_path(session_id)
        self.root.mkdir(parents=True, exist_ok=True)
        temp = self.root / f"{self._session_filename(session_id)}.tmp"
        temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temp.replace(path)
        return path

    def _load_index(self) -> dict[str, Any]:
        with self._index_lock:
            if not self.index_path.is_file():
                return {"sessions": {}}
            return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _save_index(self, index: dict[str, Any]) -> None:
        with self._index_lock:
            self._write_index_json(index)

    def create_session(self, session_id: str, adapter: BaseLMAdapter) -> CSLMSession:
        return CSLMSession(self._validate_session_id(session_id), adapter, manager=self)

    def save_session(self, session: CSLMSession) -> Path:
        session_id = self._validate_session_id(session.session_id)
        session_data = session.to_dict()
        with self._session_lock(session_id):
            path = self._write_session_json(session_id, session_data)
            decisions = tuple(
                receipt.get("governance_compliance", {}).get("decision", "")
                for receipt in session._receipts
            )
            with self._index_lock:
                index = {"sessions": {}}
                if self.index_path.is_file():
                    index = json.loads(self.index_path.read_text(encoding="utf-8"))
                index["sessions"][session_id] = {
                    "session_id": session_id,
                    "created_at": session.created_at,
                    "updated_at": session.updated_at,
                    "turns": len(session._receipts),
                    "decisions": list(decisions),
                    "path": str(path),
                }
                self._write_index_json(index)
            write_session_export(session_data)
        return path

    def export_session(self, session_id: str) -> dict[str, Any]:
        cleaned = self._validate_session_id(session_id)
        if not self._session_path(cleaned).is_file():
            raise FileNotFoundError(f"session not found: {cleaned}")
        session = self.load_session(cleaned, MockAdapter(""))
        return build_session_export(session.to_dict())

    def load_session(self, session_id: str, adapter: BaseLMAdapter) -> CSLMSession:
        cleaned = self._validate_session_id(session_id)
        with self._session_lock(cleaned):
            path = self._session_path(cleaned)
            if not path.is_file():
                return self.create_session(cleaned, adapter)
            data = json.loads(path.read_text(encoding="utf-8"))
            released_claims = {
                claim_id: SupportResult(
                    claim_id=str(item.get("claim_id") or claim_id),
                    status=str(item["status"]),  # type: ignore[arg-type]
                    sources=tuple(str(source) for source in item.get("sources") or ()),
                    uncertainty=item.get("uncertainty"),
                    reason=str(item.get("reason") or ""),
                )
                for claim_id, item in (data.get("released_claims") or {}).items()
            }
            return CSLMSession(
                session_id=cleaned,
                adapter=adapter,
                receipts=list(data.get("receipts") or []),
                released_claims=released_claims,
                manager=self,
                created_at=str(data.get("created_at") or _utc_now()),
                updated_at=str(data.get("updated_at") or _utc_now()),
            )

    def replay_session(self, session_id: str) -> CSLMSession:
        cleaned = self._validate_session_id(session_id)
        with self._session_lock(cleaned):
            path = self._session_path(cleaned)
            if not path.is_file():
                raise FileNotFoundError(f"session not found: {cleaned}")
            stored = json.loads(path.read_text(encoding="utf-8"))
        replayed = CSLMSession(cleaned, MockAdapter(""), created_at=str(stored.get("created_at") or _utc_now()))
        for receipt in stored.get("receipts") or []:
            prompt, draft, expected = stored_replay_fields(receipt)
            history_context = bool((receipt.get("session") or {}).get("history_context"))
            submitted_draft = str((receipt.get("session") or {}).get("submitted_draft") or draft)
            result = replayed.turn(
                str((receipt.get("session") or {}).get("prompt") or prompt),
                draft=submitted_draft,
                history_context=history_context,
                persist=False,
            )
            if result.decision != expected or _receipt_signature(result.receipt) != _receipt_signature(receipt):
                raise ValueError(
                    f"session replay diverged for {cleaned}: stored and replayed turn do not match"
                )
        return replayed

    def turn(
        self,
        session_id: str,
        *,
        adapter: BaseLMAdapter,
        prompt: str,
        draft: str | None = None,
        history_context: bool = False,
    ) -> PipelineResult:
        cleaned = self._validate_session_id(session_id)
        with self._session_lock(cleaned):
            session = self.load_session(cleaned, adapter)
            return session.turn(prompt, draft=draft, history_context=history_context, persist=True)

    def query_sessions(
        self,
        *,
        session_id: str | None = None,
        start_utc: str | None = None,
        end_utc: str | None = None,
        decision: str | None = None,
    ) -> list[QueryResult]:
        sessions = self._load_index().get("sessions") or {}
        results: list[QueryResult] = []
        for item in sessions.values():
            current_id = str(item.get("session_id") or "")
            created_at = str(item.get("created_at") or "")
            updated_at = str(item.get("updated_at") or "")
            decisions = tuple(str(entry) for entry in item.get("decisions") or [])
            if session_id and current_id != self._validate_session_id(session_id):
                continue
            if start_utc and updated_at < start_utc:
                continue
            if end_utc and updated_at > end_utc:
                continue
            if decision and decision not in decisions:
                continue
            results.append(
                QueryResult(
                    session_id=current_id,
                    created_at=created_at,
                    updated_at=updated_at,
                    turns=int(item.get("turns") or 0),
                    decisions=decisions,
                    path=str(item.get("path") or ""),
                )
            )
        return sorted(results, key=lambda item: item.updated_at)
