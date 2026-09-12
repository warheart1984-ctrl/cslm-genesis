"""EMR — Excitation / Memory Recall (governed activation over the board).

Jarvis: EMR decides what becomes *active cognition* over LTM. It does not
invent persistent truth. Constitutional rule carried into CSLM:

    Excited ≠ Authorized

Activation may surface particles into STM for continuity context. It must
never bypass JCR / the verifier / evidence library.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from memory.types import (
    ActivationBreakdown,
    AuthorityStatus,
    MemoryParticle,
    STMViewEntry,
)

_WORD_RE = re.compile(r"[a-z0-9_]{2,}", re.I)

_TYPE_DECAY: dict[str, float] = {
    "architecture": 0.0008,
    "decision": 0.004,
    "preference": 0.006,
    "research": 0.012,
    "fact": 0.012,
    "task": 0.03,
}

_STATUS_P: dict[str, float] = {
    "released": 1.0,
    "draft": 0.55,
    "archived": 0.0,
}

FORMULA = "A = Q * R * P * exp(-D * age_hours)"
REINFORCEMENT_RULE = (
    "Reinforcement strengthens retrievability only; truth/authority stay "
    "independently certified (CSLM: JCR + evidence library). Excited ≠ Authorized."
)


def _tokenize(text: str) -> set[str]:
    return {m.group(0).lower() for m in _WORD_RE.finditer(text or "")}


def _parse_ts(iso: str) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def make_summary(content: str, max_chars: int = 140) -> str:
    text = re.sub(r"\s+", " ", (content or "").strip())
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars - 1].rsplit(" ", 1)[0]
    return (cut or text[: max_chars - 1]).rstrip(",;:") + "…"


def query_alignment(particle: MemoryParticle, query: str) -> float:
    q_tokens = _tokenize(query)
    if not q_tokens:
        return 0.15
    blob = _tokenize(
        " ".join(
            [
                particle.content,
                particle.subject or "",
                " ".join(particle.tags),
                particle.kind,
            ]
        )
    )
    if not blob:
        return 0.05
    overlap = len(q_tokens & blob) / len(q_tokens)
    q_lower = query.lower().strip()
    if q_lower and q_lower in particle.content.lower():
        overlap = min(1.0, overlap + 0.35)
    if particle.subject and q_lower in particle.subject.lower():
        overlap = min(1.0, overlap + 0.2)
    return max(0.05, min(1.0, overlap))


def resonance(
    particle: MemoryParticle, trajectory: list[str], prior_ids: list[str]
) -> float:
    sticky = 0.35 if particle.memory_id in prior_ids else 0.0
    if not trajectory:
        return max(0.2, sticky + 0.2)
    traj_tokens = _tokenize(" ".join(trajectory))
    blob = _tokenize(
        " ".join(
            [
                particle.content,
                particle.subject or "",
                " ".join(particle.tags),
                particle.kind,
            ]
        )
    )
    if not traj_tokens or not blob:
        return max(0.15, sticky)
    overlap = len(traj_tokens & blob) / len(traj_tokens)
    return max(0.1, min(1.0, overlap + sticky))


def provenance_authority(particle: MemoryParticle) -> float:
    """P_i — status × confidence × evidence count. Not a JCR truth claim."""
    status_w = _STATUS_P.get(particle.status, 0.4)
    if status_w <= 0:
        return 0.0
    conf = max(0.05, min(1.0, float(particle.confidence)))
    ev_bonus = 1.0 + min(0.25, 0.05 * len(particle.evidence or []))
    # Released particles with a receipt_id get a mild boost (still not evidence).
    receipt_bump = 1.05 if particle.receipt_id else 1.0
    return max(0.0, min(1.0, status_w * conf * ev_bonus * receipt_bump))


def activation_score(
    particle: MemoryParticle,
    *,
    query: str,
    trajectory: list[str] | None = None,
    prior_ids: list[str] | None = None,
    now: datetime | None = None,
) -> ActivationBreakdown:
    now = now or datetime.now(timezone.utc)
    q = query_alignment(particle, query)
    r = resonance(particle, trajectory or [], prior_ids or [])
    p = provenance_authority(particle)
    d = _TYPE_DECAY.get(particle.kind, 0.012)
    ts = _parse_ts(particle.updated_at) or _parse_ts(particle.created_at)
    age_h = 0.0
    if ts is not None:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_h = max(0.0, (now - ts).total_seconds() / 3600.0)
    decay = math.exp(-d * age_h)
    a = q * r * p * decay
    return ActivationBreakdown(
        Q=round(q, 6),
        R=round(r, 6),
        P=round(p, 6),
        decay=round(decay, 6),
        A=round(a, 6),
        age_hours=round(age_h, 4),
        D=d,
    )


@dataclass
class ExciteResult:
    session_id: str
    stm: list[STMViewEntry]
    promoted: list[str]
    evicted: list[str]
    scored: int
    budget_used: int
    budget_limit: int
    formula: str = FORMULA
    note: str = (
        "EMR activation is continuity context only. Excited ≠ Authorized. "
        "Factual release still requires independent lookup/compute/JCR."
    )


@dataclass
class EmrEngine:
    """Governed activation adapter. Never mutates LTM bytes."""

    theta_promote: float = 0.12
    theta_evict: float = 0.04
    token_budget: int = 512
    _active: dict[str, list[STMViewEntry]] = field(default_factory=dict)

    def get_stm_view(self, session_id: str) -> list[STMViewEntry]:
        return list(self._active.get(session_id, []))

    def clear_stm_view(self, session_id: str | None = None) -> None:
        if session_id is None:
            self._active.clear()
        else:
            self._active.pop(session_id, None)

    def excite(
        self,
        *,
        session_id: str,
        query: str,
        candidates: list[MemoryParticle],
        trajectory: list[str] | None = None,
        token_budget: int | None = None,
        theta_promote: float | None = None,
    ) -> ExciteResult:
        budget = token_budget if token_budget is not None else self.token_budget
        theta = theta_promote if theta_promote is not None else self.theta_promote
        prior = [e.memory_id for e in self._active.get(session_id, [])]
        scored: list[tuple[MemoryParticle, ActivationBreakdown]] = []
        for particle in candidates:
            if particle.status == "archived":
                continue
            br = activation_score(
                particle,
                query=query,
                trajectory=trajectory,
                prior_ids=prior,
            )
            scored.append((particle, br))
        scored.sort(key=lambda item: item[1].A, reverse=True)

        selected: list[STMViewEntry] = []
        promoted: list[str] = []
        budget_used = 0
        for particle, br in scored:
            if br.A < theta:
                continue
            summary = make_summary(particle.content)
            cost = estimate_tokens(summary)
            if budget_used + cost > budget and selected:
                break
            entry = STMViewEntry(
                memory_id=particle.memory_id,
                summary=summary,
                payload=summary,
                resolution="summary",
                activation=br.A,
                components=br,
                status=particle.status,  # type: ignore[arg-type]
                subject=particle.subject,
                receipt_id=particle.receipt_id,
                evidence_refs=[e.ref for e in particle.evidence],
            )
            selected.append(entry)
            if particle.memory_id not in prior:
                promoted.append(particle.memory_id)
            budget_used += cost

        previous_ids = set(prior)
        new_ids = {e.memory_id for e in selected}
        evicted = sorted(previous_ids - new_ids)
        self._active[session_id] = selected
        return ExciteResult(
            session_id=session_id,
            stm=selected,
            promoted=promoted,
            evicted=evicted,
            scored=len(scored),
            budget_used=budget_used,
            budget_limit=budget,
        )


def as_authority(status: str) -> AuthorityStatus:
    if status in ("released", "draft", "archived"):
        return status  # type: ignore[return-value]
    return "draft"
