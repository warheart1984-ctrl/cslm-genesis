"""Extract asserted factual claims. Skip grammar, fiction, and unmarked hypo."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

CITATION_RE = re.compile(r"\[source:\s*[^\]]+\]", re.I)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
# Semicolons always bound independent clauses. Coordinators and commas
# split only when both sides look like clauses — not list nouns.
SEMICOLON_SPLIT = re.compile(r"\s*;\s*")
COORD_SPLIT = re.compile(
    r"("
    r"\s+as well as\s+"
    r"|\s+and\s+"
    r"|\s+but\s+"
    r"|\s+nor\s+"
    r"|\s+or\s+"
    r"|\s*:\s*"
    r"|\s*—\s*"
    r"|\s*--\s*"
    r")",
    re.I,
)
COMMA_SPLIT = re.compile(r"(\s*,\s*)")
PRONOUN_SUBJECT = re.compile(r"^(it|this|that|these|those|they)$", re.I)
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
POLARITY_RE = re.compile(r"\b(not|cannot|no|never)\b", re.I)

Polarity = Literal["affirmative", "negated"]


@dataclass(frozen=True)
class Claim:
    id: str
    text: str
    asserted_as_fact: bool
    polarity: Polarity = "affirmative"


def strip_citations(text: str) -> str:
    return CITATION_RE.sub("", text).strip()


def normalize_claim(text: str) -> str:
    cleaned = strip_citations(text).lower()
    # Possessive 's is not negation; strip it before expanding n't.
    cleaned = re.sub(r"['’]s\b", "", cleaned)
    # Fold contractions so polarity sees "not" / value aliases see "cannot".
    cleaned = re.sub(r"\bcan['’]t\b", "cannot", cleaned)
    cleaned = re.sub(r"n['’]t\b", " not", cleaned)
    cleaned = re.sub(r"[^a-z0-9\s]", "", cleaned)
    cleaned = re.sub(r"\bnot an?\b", "not", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def contains_phrase(normalized: str, phrase: str) -> bool:
    if not phrase:
        return False
    haystack = f" {normalized} "
    needle = f" {phrase} "
    return needle in haystack


def remove_phrases(normalized: str, phrases: tuple[str, ...]) -> str:
    remaining = f" {normalized} "
    for phrase in sorted((item for item in phrases if item), key=len, reverse=True):
        remaining = remaining.replace(f" {phrase} ", " ")
    return re.sub(r"\s+", " ", remaining).strip()


def polarity_of(text: str, ignore_phrases: tuple[str, ...] = ()) -> Polarity:
    remainder = remove_phrases(normalize_claim(text), ignore_phrases)
    if POLARITY_RE.search(remainder):
        return "negated"
    return "affirmative"


def polarity_negated(text: str, ignore_phrases: tuple[str, ...] = ()) -> bool:
    match polarity_of(text, ignore_phrases):
        case "negated":
            return True
        case "affirmative":
            return False
        case _ as unreachable:
            raise AssertionError(f"unhandled polarity: {unreachable}")


def split_sentences(text: str) -> list[str]:
    chunks = SENTENCE_SPLIT.split(text.strip())
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def looks_like_clause(text: str) -> bool:
    """True when text has an assertive/copula or '=', even with no left-edge subject.

    Elided tails (`and is…`, `, is…`) are clauses. Value lists still fail this
    test on the right (`finite depth`), so both-sides splitting keeps them intact.
    """
    bare = strip_citations(text).strip()
    if not bare:
        return False
    if "=" in bare:
        return True
    return bool(ASSERTIVE.search(bare))


def subject_of(text: str) -> str:
    bare = strip_citations(text).strip()
    if not bare:
        return ""
    if "=" in bare:
        left = bare.split("=", 1)[0].strip()
        return left if re.search(r"[A-Za-z0-9]", left) else ""
    match = ASSERTIVE.search(bare)
    if not match:
        return ""
    return bare[: match.start()].strip()


def _is_pronoun_subject(subject: str) -> bool:
    return bool(PRONOUN_SUBJECT.match(subject.strip()))


def _needs_subject_inherit(text: str) -> bool:
    subject = subject_of(text)
    if not subject:
        return bool(ASSERTIVE.search(strip_citations(text)) or "=" in text)
    return _is_pronoun_subject(subject)


def _bind_subject(clause: str, subject: str) -> str:
    current = subject_of(clause)
    if not current:
        return f"{subject} {clause.lstrip()}"
    match = re.search(re.escape(current), clause)
    if match is None:
        return f"{subject} {clause.lstrip()}"
    return f"{clause[: match.start()]}{subject}{clause[match.end():]}"


def _inherit_subjects(clauses: list[str]) -> list[str]:
    if not clauses:
        return []
    resolved = [clauses[0]]
    prior_subject = subject_of(clauses[0])
    if _is_pronoun_subject(prior_subject):
        prior_subject = ""
    for clause in clauses[1:]:
        if prior_subject and _needs_subject_inherit(clause):
            bound = _bind_subject(clause, prior_subject)
            resolved.append(bound)
            rebound = subject_of(bound)
            if rebound and not _is_pronoun_subject(rebound):
                prior_subject = rebound
            continue
        resolved.append(clause)
        next_subject = subject_of(clause)
        if next_subject and not _is_pronoun_subject(next_subject):
            prior_subject = next_subject
    return resolved


def _split_when_both_clauses(text: str, splitter: re.Pattern[str]) -> list[str]:
    tokens = splitter.split(text.strip())
    if len(tokens) == 1:
        return [tokens[0].strip()] if tokens[0].strip() else []
    clauses = [tokens[0]]
    index = 1
    while index < len(tokens):
        separator = tokens[index]
        right = tokens[index + 1] if index + 1 < len(tokens) else ""
        if looks_like_clause(clauses[-1]) and looks_like_clause(right):
            clauses.append(right)
        else:
            clauses[-1] = f"{clauses[-1]}{separator}{right}"
        index += 2
    return [part.strip() for part in clauses if part.strip()]


def split_clauses(sentence: str) -> list[str]:
    parts: list[str] = []
    for chunk in SEMICOLON_SPLIT.split(sentence.strip()):
        if not chunk.strip():
            continue
        for coordinated in _split_when_both_clauses(chunk, COORD_SPLIT):
            parts.extend(_split_when_both_clauses(coordinated, COMMA_SPLIT))
    return _inherit_subjects(parts)


def clause_key(text: str) -> str:
    return strip_citations(text).rstrip(".!?").strip()


def extract_claims(draft_text: str) -> list[Claim]:
    claims: list[Claim] = []
    index = 0
    for sentence in split_sentences(draft_text):
        for clause in split_clauses(sentence):
            bare = strip_citations(clause)
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
                    polarity=polarity_of(bare),
                )
            )
    return claims
