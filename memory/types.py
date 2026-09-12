"""Shared Memoryboard particle types (CSLM-adapted Jarvis tiers)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Tier = Literal["stm", "ltm", "amul", "emr"]
MemoryKind = Literal["decision", "fact", "task", "preference", "architecture", "research"]
AuthorityStatus = Literal["draft", "released", "archived"]
Resolution = Literal["summary", "detail", "evidence"]


@dataclass
class EvidenceRef:
    """Pointer only — not independent factual support for JCR."""

    kind: str
    ref: str
    note: str = ""


@dataclass
class MemoryParticle:
    """One continuity particle. Never a substitute for evidence/library.json."""

    memory_id: str
    content: str
    session_id: str
    tier: Tier
    kind: MemoryKind = "fact"
    status: AuthorityStatus = "draft"
    subject: str | None = None
    tags: list[str] = field(default_factory=list)
    confidence: float = 0.5
    evidence: list[EvidenceRef] = field(default_factory=list)
    receipt_id: str | None = None
    source_agent: str = "cslm"
    created_at: str = ""
    updated_at: str = ""
    content_sha256: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "content": self.content,
            "session_id": self.session_id,
            "tier": self.tier,
            "kind": self.kind,
            "status": self.status,
            "subject": self.subject,
            "tags": list(self.tags),
            "confidence": self.confidence,
            "evidence": [
                {"kind": e.kind, "ref": e.ref, "note": e.note} for e in self.evidence
            ],
            "receipt_id": self.receipt_id,
            "source_agent": self.source_agent,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "content_sha256": self.content_sha256,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> MemoryParticle:
        evidence = [
            EvidenceRef(
                kind=str(item.get("kind") or "ref"),
                ref=str(item.get("ref") or ""),
                note=str(item.get("note") or ""),
            )
            for item in (raw.get("evidence") or [])
            if item.get("ref")
        ]
        return cls(
            memory_id=str(raw["memory_id"]),
            content=str(raw["content"]),
            session_id=str(raw.get("session_id") or ""),
            tier=raw.get("tier") or "ltm",  # type: ignore[arg-type]
            kind=raw.get("kind") or "fact",  # type: ignore[arg-type]
            status=raw.get("status") or "draft",  # type: ignore[arg-type]
            subject=raw.get("subject"),
            tags=list(raw.get("tags") or []),
            confidence=float(raw.get("confidence") or 0.5),
            evidence=evidence,
            receipt_id=raw.get("receipt_id"),
            source_agent=str(raw.get("source_agent") or "cslm"),
            created_at=str(raw.get("created_at") or ""),
            updated_at=str(raw.get("updated_at") or ""),
            content_sha256=str(raw.get("content_sha256") or ""),
            metadata=dict(raw.get("metadata") or {}),
        )


@dataclass(frozen=True)
class ActivationBreakdown:
    Q: float
    R: float
    P: float
    decay: float
    A: float
    age_hours: float
    D: float


@dataclass
class STMViewEntry:
    """Activated working-set view — summaries + LTM/STM provenance pointers."""

    memory_id: str
    summary: str
    payload: str
    resolution: Resolution
    activation: float
    components: ActivationBreakdown
    status: AuthorityStatus
    subject: str | None
    receipt_id: str | None
    evidence_refs: list[str] = field(default_factory=list)


class PromotionDenied(ValueError):
    """STM→LTM promotion refused (missing release / receipt)."""


class MemoryLawError(ValueError):
    """Board refused an operation that would bypass CSLM law."""
