"""Independent fact lookup against the checked-in knowledge store."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from claims import contains_phrase, normalize_claim

KNOWLEDGE_PATH = Path(__file__).resolve().parent / "evidence" / "library.json"

LookupKind = Literal["supported", "contradicted", "unknown"]


@dataclass(frozen=True)
class Fact:
    id: str
    source: str
    subject_aliases: tuple[str, ...]
    predicate_aliases: tuple[str, ...]
    value_aliases: tuple[str, ...]
    canonical: str


@dataclass(frozen=True)
class LookupOutcome:
    kind: LookupKind
    source: str
    fact_id: str
    reason: str


def _as_phrases(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(normalize_claim(str(item)) for item in value if str(item).strip())


def load_facts(path: Path | None = None) -> tuple[Fact, ...]:
    raw = json.loads((path or KNOWLEDGE_PATH).read_text(encoding="utf-8"))
    facts: list[Fact] = []
    for item in raw.get("facts") or []:
        if not isinstance(item, dict):
            continue
        fact_id = str(item.get("id") or "").strip()
        source = str(item.get("source") or "").strip()
        if not fact_id or not source:
            continue
        facts.append(
            Fact(
                id=fact_id,
                source=source,
                subject_aliases=_as_phrases(item.get("subject_aliases")),
                predicate_aliases=_as_phrases(item.get("predicate_aliases")),
                value_aliases=_as_phrases(item.get("value_aliases")),
                canonical=str(item.get("canonical") or ""),
            )
        )
    return tuple(facts)


def _hits(normalized: str, aliases: tuple[str, ...]) -> bool:
    return any(contains_phrase(normalized, alias) for alias in aliases if alias)


def check_lookup(claim_text: str, facts: tuple[Fact, ...] | None = None) -> LookupOutcome:
    normalized = normalize_claim(claim_text)
    store = facts if facts is not None else load_facts()
    candidates = [fact for fact in store if _hits(normalized, fact.subject_aliases)]
    if not candidates:
        return LookupOutcome("unknown", "", "", "no subject match in knowledge store")

    value_hits = [fact for fact in candidates if _hits(normalized, fact.value_aliases)]
    if value_hits:
        fact = value_hits[0]
        return LookupOutcome(
            "supported",
            fact.source,
            fact.id,
            f"independent lookup matched fact {fact.id}",
        )

    predicate_hits = [fact for fact in candidates if _hits(normalized, fact.predicate_aliases)]
    if predicate_hits:
        fact = predicate_hits[0]
        return LookupOutcome(
            "contradicted",
            fact.source,
            fact.id,
            f"independent lookup contradicted fact {fact.id} (canonical {fact.canonical})",
        )
    return LookupOutcome("unknown", "", "", "subject matched but predicate and value did not")
