"""Extract asserted factual claims. Skip grammar, fiction, and unmarked hypo."""

from __future__ import annotations

import re
from dataclasses import dataclass

CITATION_RE = re.compile(r"\[source:\s*[^\]]+\]", re.I)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
HYPOTHETICAL = re.compile(
    r"\b(imagine|suppose|hypothetically|what if|let us assume|let's assume)\b",
    re.I,
)
UNCERTAINTY_ONLY = re.compile(
    r"\b(i (do not|don't) know|unknown|not enough (information|evidence)|"
    r"cannot (verify|confirm|release)|no identified support)\b",
    re.I,
)
ASSERTIVE = re.compile(
    r"\b(is|are|was|were|has|have|had|contains|consists|comprises|"
    r"includes|means|equals|measures|lives|lived|belongs|assumes|"
    r"performs|produces|proves|demonstrates|exhibits|undergoes)\b",
    re.I,
)


@dataclass(frozen=True)
class Claim:
    id: str
    text: str
    asserted_as_fact: bool


def strip_citations(text: str) -> str:
    return CITATION_RE.sub("", text).strip()


def normalize_claim(text: str) -> str:
    cleaned = strip_citations(text).lower()
    cleaned = re.sub(r"['’]s\b", "", cleaned)
    cleaned = re.sub(r"[^a-z0-9\s]", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def contains_phrase(normalized: str, phrase: str) -> bool:
    if not phrase:
        return False
    haystack = f" {normalized} "
    needle = f" {phrase} "
    return needle in haystack


def split_sentences(text: str) -> list[str]:
    chunks = SENTENCE_SPLIT.split(text.strip())
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def extract_claims(draft_text: str) -> list[Claim]:
    claims: list[Claim] = []
    index = 0
    for sentence in split_sentences(draft_text):
        bare = strip_citations(sentence)
        if not bare:
            continue
        if bare.endswith("?"):
            continue
        if HYPOTHETICAL.search(bare):
            continue
        if UNCERTAINTY_ONLY.search(bare) and not ASSERTIVE.search(bare) and "=" not in bare:
            continue
        if not ASSERTIVE.search(bare) and "=" not in bare:
            if not re.search(r"[A-Za-z]", bare):
                continue
        index += 1
        claims.append(
            Claim(
                id=f"c{index}",
                text=bare,
                asserted_as_fact=True,
            )
        )
    return claims
