"""AMUL — LTM substrate (append-only artifacts + lineage).

Jarvis name: AMUL Architect — persistence / structure / lineage beneath the
board. Also expanded in RAG/LLM docs as Adaptive / Modular / Universal /
Logical; this CSLM adapter implements the *Architect* substrate only.

AMUL does not adjudicate truth and does not feed the base LM. It anchors
released LTM particles as content-addressed artifacts.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from canonical import sha256_hex
from memory.types import MemoryParticle, Resolution

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_AMUL_PATH = ROOT / "memory" / "data" / "amul-field.jsonl"
AMUL_PATH_ENV = "CSLM_AMUL_PATH"
SCHEMA = "cslm.amul-artifact.v0"


def amul_path(override: Path | None = None) -> Path:
    if override is not None:
        return override
    env = os.environ.get(AMUL_PATH_ENV, "").strip()
    if env:
        return Path(env)
    return DEFAULT_AMUL_PATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AmulArtifact:
    artifact_id: str
    ledger_id: str
    resolution: Resolution
    payload: str
    payload_sha256: str
    authority_status: str
    receipt_id: str | None = None
    lineage_parent_ids: list[str] = field(default_factory=list)
    created_at: str = ""
    schema_version: str = SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "ledger_id": self.ledger_id,
            "resolution": self.resolution,
            "payload": self.payload,
            "payload_sha256": self.payload_sha256,
            "authority_status": self.authority_status,
            "receipt_id": self.receipt_id,
            "lineage_parent_ids": list(self.lineage_parent_ids),
            "created_at": self.created_at,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AmulArtifact:
        return cls(
            artifact_id=str(raw["artifact_id"]),
            ledger_id=str(raw["ledger_id"]),
            resolution=raw.get("resolution") or "detail",  # type: ignore[arg-type]
            payload=str(raw.get("payload") or ""),
            payload_sha256=str(raw.get("payload_sha256") or ""),
            authority_status=str(raw.get("authority_status") or "draft"),
            receipt_id=raw.get("receipt_id"),
            lineage_parent_ids=list(raw.get("lineage_parent_ids") or []),
            created_at=str(raw.get("created_at") or ""),
            schema_version=str(raw.get("schema_version") or SCHEMA),
        )


@dataclass
class AnchorReport:
    ledger_id: str
    created: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)


class AmulField:
    """Append-only JSONL artifact field. Existing lines are never rewritten."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = amul_path(path)
        self._artifacts: dict[str, AmulArtifact] = {}
        self._order: list[str] = []
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.path.is_file():
            return
        try:
            for raw in self.path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line:
                    continue
                art = AmulArtifact.from_dict(json.loads(line))
                self._artifacts[art.artifact_id] = art
                self._order.append(art.artifact_id)
        except Exception:
            pass

    def append(self, artifact: AmulArtifact) -> AmulArtifact:
        self._ensure_loaded()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(artifact.to_dict(), ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
        self._artifacts[artifact.artifact_id] = artifact
        self._order.append(artifact.artifact_id)
        return artifact

    def get(self, artifact_id: str) -> AmulArtifact | None:
        self._ensure_loaded()
        return self._artifacts.get(artifact_id)

    def list_all(self) -> list[AmulArtifact]:
        self._ensure_loaded()
        return [
            self._artifacts[aid] for aid in self._order if aid in self._artifacts
        ]

    def list_for_ledger(self, ledger_id: str) -> list[AmulArtifact]:
        return [a for a in self.list_all() if a.ledger_id == ledger_id]

    def latest_detail(self, ledger_id: str) -> AmulArtifact | None:
        arts = [
            a
            for a in self.list_for_ledger(ledger_id)
            if a.resolution == "detail"
        ]
        return arts[-1] if arts else None

    def verify(self) -> dict[str, Any]:
        """Rehash payloads; report integrity failures (does not mutate)."""
        self._ensure_loaded()
        failures: list[str] = []
        for art in self._artifacts.values():
            if sha256_hex(art.payload) != art.payload_sha256:
                failures.append(art.artifact_id)
        return {
            "schema_version": SCHEMA,
            "artifact_count": len(self._artifacts),
            "integrity_ok": not failures,
            "integrity_failures": failures,
        }

    def __len__(self) -> int:
        self._ensure_loaded()
        return len(self._artifacts)


def _make_summary(content: str, max_chars: int = 140) -> str:
    text = " ".join((content or "").split())
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars - 1].rsplit(" ", 1)[0]
    return (cut or text[: max_chars - 1]).rstrip(",;:") + "…"


def _artifact_id(ledger_id: str, resolution: str, digest: str, seq: int) -> str:
    return f"amul-{digest[:12]}-{resolution[0]}{seq}"


class AmulAdapter:
    """Thin AMUL interface used by JarvisBoard."""

    def __init__(self, field: AmulField | None = None) -> None:
        # Do not use `field or AmulField()` — empty fields are falsy via __len__.
        self.field = AmulField() if field is None else field

    def anchor(self, particle: MemoryParticle) -> AnchorReport:
        """Idempotent-ish: create summary/detail/evidence if detail payload changed."""
        resolutions: list[tuple[Resolution, str]] = [
            ("summary", _make_summary(particle.content)),
            ("detail", particle.content),
            (
                "evidence",
                particle.content
                + "\n"
                + json.dumps(
                    [
                        {"kind": e.kind, "ref": e.ref, "note": e.note}
                        for e in particle.evidence
                    ],
                    ensure_ascii=False,
                ),
            ),
        ]
        report = AnchorReport(ledger_id=particle.memory_id)
        prior = self.field.latest_detail(particle.memory_id)
        detail_sha = sha256_hex(particle.content)
        if prior is not None and prior.payload_sha256 == detail_sha:
            for resolution, _ in resolutions:
                report.unchanged.append(resolution)
            return report

        parent_ids = [prior.artifact_id] if prior is not None else []
        seq = len(self.field.list_for_ledger(particle.memory_id)) + 1
        detail_id: str | None = None
        for resolution, payload in resolutions:
            digest = sha256_hex(payload)
            aid = _artifact_id(particle.memory_id, resolution, digest, seq)
            art = AmulArtifact(
                artifact_id=aid,
                ledger_id=particle.memory_id,
                resolution=resolution,
                payload=payload,
                payload_sha256=digest,
                authority_status=particle.status,
                receipt_id=particle.receipt_id,
                lineage_parent_ids=list(parent_ids),
                created_at=_now_iso(),
            )
            self.field.append(art)
            report.created.append(aid)
            if resolution == "detail":
                detail_id = aid
        if detail_id is not None:
            # Point summary/evidence lineage at the new detail for this batch.
            _ = detail_id
        return report

    def get(self, artifact_id: str) -> AmulArtifact | None:
        return self.field.get(artifact_id)

    def verify(self) -> dict[str, Any]:
        return self.field.verify()
