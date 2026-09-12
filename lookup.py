"""Independent fact lookup against the checked-in knowledge store."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from canonical import digest_of
from claims import (
    ASSERTIVE,
    contains_phrase,
    looks_like_clause,
    normalize_claim,
    polarity_of,
    remove_phrases,
)

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


@dataclass(frozen=True)
class LibraryBinding:
    store_id: str
    content_hash: str


def _as_phrases(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(normalize_claim(str(item)) for item in value if str(item).strip())


def load_library_raw(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or KNOWLEDGE_PATH).read_text(encoding="utf-8"))


def library_binding(path: Path | None = None) -> LibraryBinding:
    raw = load_library_raw(path)
    store_id = str(raw.get("store_id") or "")
    return LibraryBinding(
        store_id=store_id,
        content_hash=digest_of({"store_id": store_id, "content": raw}),
    )


def load_facts(path: Path | None = None) -> tuple[Fact, ...]:
    raw = load_library_raw(path)
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


def _has_predicate(normalized: str, claim_text: str, fact: Fact) -> bool:
    if _hits(normalized, fact.predicate_aliases):
        return True
    # Copula/assertive verb may stand in for an identity predicate when the value is present.
    return bool(ASSERTIVE.search(claim_text) and _hits(normalized, fact.value_aliases))


def _canonical_clause_match(
    normalized: str, claim_text: str, store: tuple[Fact, ...]
) -> Fact | None:
    if not looks_like_clause(claim_text):
        return None
    for fact in store:
        canonical = normalize_claim(fact.canonical)
        if canonical and contains_phrase(canonical, normalized):
            return fact
    return None


def _content_remainder(normalized: str, fact: Fact) -> str:
    remainder = remove_phrases(normalized, fact.subject_aliases)
    remainder = ASSERTIVE.sub(" ", remainder)
    return re.sub(r"\s+", " ", remainder).strip()


def _remainder_in_canonical(normalized: str, fact: Fact) -> bool:
    remainder = _content_remainder(normalized, fact)
    if not remainder or len(remainder.split()) < 2:
        return False
    canonical = normalize_claim(fact.canonical)
    return bool(canonical) and contains_phrase(canonical, remainder)


def check_lookup(claim_text: str, facts: tuple[Fact, ...] | None = None) -> LookupOutcome:
    normalized = normalize_claim(claim_text)
    store = facts if facts is not None else load_facts()
    candidates = [fact for fact in store if _hits(normalized, fact.subject_aliases)]
    if not candidates:
        fact = _canonical_clause_match(normalized, claim_text, store)
        if fact is None:
            return LookupOutcome("unknown", "", "", "no subject match in knowledge store")
        match polarity_of(claim_text, fact.value_aliases):
            case "negated":
                return LookupOutcome(
                    "contradicted",
                    fact.source,
                    fact.id,
                    (
                        f"independent lookup contradicted fact {fact.id} "
                        f"(negation does not match canonical {fact.canonical})"
                    ),
                )
            case "affirmative":
                return LookupOutcome(
                    "supported",
                    fact.source,
                    fact.id,
                    f"independent lookup matched fact {fact.id}",
                )
            case _ as unreachable:
                raise AssertionError(f"unhandled polarity: {unreachable}")

    triple_hits = [
        fact
        for fact in candidates
        if _has_predicate(normalized, claim_text, fact) and _hits(normalized, fact.value_aliases)
    ]
    if triple_hits:
        fact = triple_hits[0]
        match polarity_of(claim_text, fact.value_aliases):
            case "negated":
                return LookupOutcome(
                    "contradicted",
                    fact.source,
                    fact.id,
                    (
                        f"independent lookup contradicted fact {fact.id} "
                        f"(negation does not match canonical {fact.canonical})"
                    ),
                )
            case "affirmative":
                return LookupOutcome(
                    "supported",
                    fact.source,
                    fact.id,
                    f"independent lookup matched fact {fact.id}",
                )
            case _ as unreachable:
                raise AssertionError(f"unhandled polarity: {unreachable}")

    predicate_hits = [fact for fact in candidates if _hits(normalized, fact.predicate_aliases)]
    if predicate_hits:
        fact = predicate_hits[0]
        return LookupOutcome(
            "contradicted",
            fact.source,
            fact.id,
            f"independent lookup contradicted fact {fact.id} (canonical {fact.canonical})",
        )
    remainder_hits = [fact for fact in candidates if _remainder_in_canonical(normalized, fact)]
    if remainder_hits:
        fact = remainder_hits[0]
        match polarity_of(claim_text, fact.value_aliases):
            case "negated":
                return LookupOutcome(
                    "contradicted",
                    fact.source,
                    fact.id,
                    (
                        f"independent lookup contradicted fact {fact.id} "
                        f"(negation does not match canonical {fact.canonical})"
                    ),
                )
            case "affirmative":
                return LookupOutcome(
                    "supported",
                    fact.source,
                    fact.id,
                    f"independent lookup matched fact {fact.id}",
                )
            case _ as unreachable:
                raise AssertionError(f"unhandled polarity: {unreachable}")
    return LookupOutcome("unknown", "", "", "subject matched but predicate and value did not")
