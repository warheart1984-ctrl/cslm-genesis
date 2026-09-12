"""JarvisBoard — CSLM Memoryboard over AMUL / EMR / STM / LTM.

Canonical Jarvis stack (adapted, not vendored):

    AMUL (LTM substrate) → Board (access) → EMR (activation) → STM → consumers

CSLM law overlays:
  - Memory is continuity / provenance, not evidence.
  - Excited ≠ Authorized.
  - STM→LTM promotion requires status=released AND a receipt_id.
  - Board contents never bypass JCR / verifier / evidence library.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, NoReturn
from uuid import uuid4

from canonical import sha256_hex
from memory.amul import AmulAdapter, AmulField
from memory.emr import EmrEngine, ExciteResult, make_summary
from memory.ltm import LongTermMemory
from memory.stm import ShortTermMemory
from memory.types import (
    EvidenceRef,
    MemoryKind,
    MemoryLawError,
    MemoryParticle,
    PromotionDenied,
    Tier,
)

TierName = Literal["stm", "ltm", "amul", "emr"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str = "mem") -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


class JarvisBoard:
    """Unified store/retrieve + promote interface for the four Jarvis tiers."""

    def __init__(
        self,
        session_id: str,
        *,
        ltm_path: Path | None = None,
        amul_path: Path | None = None,
    ) -> None:
        self.session_id = session_id
        self.stm = ShortTermMemory(session_id)
        self.ltm = LongTermMemory(ltm_path)
        self.amul = AmulAdapter(AmulField(amul_path))
        self.emr = EmrEngine()

    # --- store / retrieve -------------------------------------------------

    def store(
        self,
        content: str,
        *,
        tier: Tier = "stm",
        kind: MemoryKind = "fact",
        status: str = "draft",
        subject: str | None = None,
        tags: list[str] | None = None,
        receipt_id: str | None = None,
        evidence: list[EvidenceRef] | None = None,
        memory_id: str | None = None,
        confidence: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryParticle:
        if tier == "emr":
            raise MemoryLawError(
                "EMR is an activation layer, not a durable store; "
                "write STM/LTM then call excite()"
            )
        if tier == "amul":
            raise MemoryLawError(
                "AMUL is anchored from LTM via amul.anchor(); "
                "do not write AMUL particles directly"
            )
        if tier == "ltm" and not (status == "released" and receipt_id):
            raise PromotionDenied(
                "direct LTM write requires status='released' and a receipt_id "
                "(continuity ≠ evidence; only previously released claims may persist)"
            )

        now = _now_iso()
        mid = memory_id or _new_id("stm" if tier == "stm" else "ltm")
        particle = MemoryParticle(
            memory_id=mid,
            content=content.strip(),
            session_id=self.session_id,
            tier=tier,
            kind=kind,
            status=status,  # type: ignore[arg-type]
            subject=subject,
            tags=list(tags or []),
            confidence=confidence,
            evidence=list(evidence or []),
            receipt_id=receipt_id,
            created_at=now,
            updated_at=now,
            content_sha256=sha256_hex(content.strip()),
            metadata=dict(metadata or {}),
        )
        if tier == "stm":
            return self.stm.write(particle)
        stored = self.ltm.append(particle)
        self.amul.anchor(stored)
        return stored

    def retrieve(
        self,
        memory_id: str,
        *,
        tier: Tier | None = None,
    ) -> MemoryParticle | None:
        if tier in (None, "stm"):
            hit = self.stm.get(memory_id)
            if hit is not None:
                return hit
            if tier == "stm":
                return None
        if tier in (None, "ltm"):
            hit = self.ltm.get(memory_id)
            if hit is not None:
                return hit
            if tier == "ltm":
                return None
        if tier == "amul":
            art = self.amul.get(memory_id)
            if art is None:
                return None
            return MemoryParticle(
                memory_id=art.artifact_id,
                content=art.payload,
                session_id=self.session_id,
                tier="amul",
                status=art.authority_status,  # type: ignore[arg-type]
                receipt_id=art.receipt_id,
                content_sha256=art.payload_sha256,
                created_at=art.created_at,
                updated_at=art.created_at,
                metadata={"ledger_id": art.ledger_id, "resolution": art.resolution},
            )
        if tier == "emr":
            for entry in self.emr.get_stm_view(self.session_id):
                if entry.memory_id == memory_id:
                    return MemoryParticle(
                        memory_id=entry.memory_id,
                        content=entry.payload,
                        session_id=self.session_id,
                        tier="emr",
                        status=entry.status,
                        subject=entry.subject,
                        receipt_id=entry.receipt_id,
                        metadata={"activation": entry.activation},
                    )
            return None
        return None

    def list_tier(self, tier: TierName) -> list[MemoryParticle]:
        if tier == "stm":
            return self.stm.list()
        if tier == "ltm":
            return self.ltm.list()
        if tier == "amul":
            out: list[MemoryParticle] = []
            for art in self.amul.field.list_all():
                out.append(
                    MemoryParticle(
                        memory_id=art.artifact_id,
                        content=art.payload,
                        session_id=self.session_id,
                        tier="amul",
                        status=art.authority_status,  # type: ignore[arg-type]
                        receipt_id=art.receipt_id,
                        content_sha256=art.payload_sha256,
                        created_at=art.created_at,
                        updated_at=art.created_at,
                        metadata={
                            "ledger_id": art.ledger_id,
                            "resolution": art.resolution,
                        },
                    )
                )
            return out
        if tier == "emr":
            return [
                MemoryParticle(
                    memory_id=e.memory_id,
                    content=e.payload,
                    session_id=self.session_id,
                    tier="emr",
                    status=e.status,
                    subject=e.subject,
                    receipt_id=e.receipt_id,
                    metadata={"activation": e.activation},
                )
                for e in self.emr.get_stm_view(self.session_id)
            ]
        return _assert_never(tier)

    # --- EMR --------------------------------------------------------------

    def excite(
        self,
        query: str,
        *,
        include_stm: bool = True,
        token_budget: int | None = None,
        theta_promote: float | None = None,
        trajectory: list[str] | None = None,
    ) -> ExciteResult:
        """Activate LTM (+ optional STM) into an EMR working view. Does not mutate LTM."""
        candidates = list(self.ltm.list())
        if include_stm:
            candidates.extend(self.stm.list())
        # Deduplicate by id (STM wins for same id).
        by_id: dict[str, MemoryParticle] = {}
        for particle in candidates:
            by_id[particle.memory_id] = particle
        return self.emr.excite(
            session_id=self.session_id,
            query=query,
            candidates=list(by_id.values()),
            trajectory=trajectory,
            token_budget=token_budget,
            theta_promote=theta_promote,
        )

    # --- promote STM → LTM -----------------------------------------------

    def promote_stm_to_ltm(self, memory_id: str) -> MemoryParticle:
        """Persist STM particle to LTM only if previously released with receipt_id."""
        particle = self.stm.get(memory_id)
        if particle is None:
            raise KeyError(f"STM particle not found: {memory_id}")
        if particle.status != "released" or not particle.receipt_id:
            raise PromotionDenied(
                "STM→LTM promote requires status='released' and receipt_id; "
                "memory alone cannot authorize durable facts"
            )
        now = _now_iso()
        if particle.memory_id.startswith("ltm-"):
            durable_id = particle.memory_id
        elif particle.memory_id.startswith("stm-"):
            durable_id = particle.memory_id.replace("stm-", "ltm-", 1)
        else:
            durable_id = f"ltm-{particle.memory_id}"
        durable = MemoryParticle(
            memory_id=durable_id,
            content=particle.content,
            session_id=self.session_id,
            tier="ltm",
            kind=particle.kind,
            status="released",
            subject=particle.subject,
            tags=list(particle.tags),
            confidence=particle.confidence,
            evidence=list(particle.evidence),
            receipt_id=particle.receipt_id,
            source_agent=particle.source_agent,
            created_at=particle.created_at or now,
            updated_at=now,
            content_sha256=particle.content_sha256 or sha256_hex(particle.content),
            metadata={
                **dict(particle.metadata),
                "promoted_from_stm": particle.memory_id,
                "promoted_at": now,
            },
        )
        stored = self.ltm.append(durable)
        self.amul.anchor(stored)
        return stored

    # --- session continuity helpers --------------------------------------

    def note_turn(
        self,
        *,
        turn: int,
        prompt: str,
        decision: str,
        receipt_id: str | None,
        draft: str = "",
    ) -> MemoryParticle:
        """Record a session turn summary into STM (draft continuity, not evidence)."""
        summary = make_summary(
            f"turn={turn} decision={decision} prompt={prompt} draft={draft}"
        )
        return self.store(
            summary,
            tier="stm",
            kind="decision",
            status="draft",
            subject=f"session:{self.session_id}:turn:{turn}",
            tags=["session-turn", decision],
            receipt_id=receipt_id,
            metadata={"turn": turn, "prompt": prompt, "decision": decision},
        )

    def ingest_released_claim(
        self,
        *,
        claim_text: str,
        receipt_id: str,
        turn: int,
        subject: str | None = None,
    ) -> MemoryParticle:
        """Place a JCR-released claim into STM, eligible for later LTM promote."""
        if not receipt_id:
            raise PromotionDenied("released claim ingest requires receipt_id")
        return self.store(
            claim_text,
            tier="stm",
            kind="fact",
            status="released",
            subject=subject or make_summary(claim_text, max_chars=80),
            tags=["released-claim"],
            receipt_id=receipt_id,
            confidence=1.0,
            evidence=[EvidenceRef(kind="receipt", ref=receipt_id, note="jcr-release")],
            metadata={"turn": turn, "eligible_for_ltm": True},
        )

    def continuity_context(self, query: str | None = None) -> list[dict[str, Any]]:
        """STM (+ optional EMR excite) as continuity hints — never trusted facts."""
        if query:
            self.excite(query, theta_promote=0.05)
        rows: list[dict[str, Any]] = []
        for particle in self.stm.list():
            rows.append(
                {
                    "tier": "stm",
                    "memory_id": particle.memory_id,
                    "content": particle.content,
                    "status": particle.status,
                    "receipt_id": particle.receipt_id,
                    "trusted_fact": False,
                }
            )
        for entry in self.emr.get_stm_view(self.session_id):
            rows.append(
                {
                    "tier": "emr",
                    "memory_id": entry.memory_id,
                    "content": entry.summary,
                    "status": entry.status,
                    "receipt_id": entry.receipt_id,
                    "activation": entry.activation,
                    "trusted_fact": False,
                }
            )
        return rows


def _assert_never(value: object) -> NoReturn:
    raise MemoryLawError(f"unknown tier: {value}")
