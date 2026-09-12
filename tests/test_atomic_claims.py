"""Clause-level claims: conjunctions strip, negations do not invert support."""

from __future__ import annotations

from adapter import MockAdapter
from claims import extract_claims, normalize_claim, polarity_of, split_clauses
from lookup import check_lookup
from pipeline import run


def test_split_does_not_cut_hyphenated_and() -> None:
    parts = split_clauses("Bond-orientational order is algebraic.")
    assert parts == ["Bond-orientational order is algebraic."]


def test_conjunction_water_atlantis_strips_unsupported_clause() -> None:
    result = run(
        "What is water, and what is the population of Atlantis?",
        adapter=MockAdapter("Water is H2O and Atlantis has a resident population of 12403."),
    )
    assert result.decision == "release"
    assert result.released_answer is True
    assert result.user_visible is not None
    assert "H2O" in result.user_visible
    assert "12403" not in result.user_visible
    texts = [claim["text"] for claim in result.receipt["factual_support"]["claims"]]
    assert texts == ["Water is H2O."]


def test_negation_of_water_formula_does_not_release() -> None:
    result = run(
        "What is the chemical formula of water?",
        adapter=MockAdapter("Water is not H2O."),
    )
    assert result.decision != "release"
    assert result.released_answer is False
    claim = result.receipt["factual_support"]["claims"][0]
    assert claim["status"] == "unsupported"
    assert "negation" in claim["reason"]


def test_contraction_negations_do_not_release_as_supported() -> None:
    for draft in (
        "Water isn't H2O.",
        "Water's chemical formula isn't H2O.",
        "Water doesn’t have formula H2O.",
        "Water doesn't have formula H2O.",
    ):
        assert "not" in normalize_claim(draft), draft
        assert polarity_of(draft) == "negated", draft
        assert extract_claims(draft)[0].polarity == "negated", draft
        result = run(
            "What is the chemical formula of water?",
            adapter=MockAdapter(draft),
        )
        assert result.decision != "release", draft
        assert result.released_answer is False, draft


def test_floquet_cant_contraction_still_releases() -> None:
    for draft in (
        "Linear Floquet analysis can't predict the selected spatial pattern.",
        "Linear Floquet analysis cannot predict the selected spatial pattern.",
    ):
        assert normalize_claim(draft).startswith(
            "linear floquet analysis cannot predict"
        ), draft
        outcome = check_lookup(draft)
        assert outcome.kind == "supported", draft
        assert outcome.fact_id == "physics.faraday.floquet_not_pattern", draft
        result = run(
            "Does linear Floquet analysis select the Faraday pattern?",
            adapter=MockAdapter(draft),
        )
        assert result.decision == "release", draft
        assert result.released_answer is True, draft
        assert result.user_visible is not None
        assert "Floquet" in result.user_visible


def test_one_sentence_faraday_and_phase6_strips_overclaim() -> None:
    result = run(
        "Summarize Faraday onset and Phase 6.",
        adapter=MockAdapter(
            "The primary Faraday instability is typically a subharmonic response "
            "and Phase 6 is an established universal Faraday result."
        ),
    )
    assert result.decision == "release"
    assert result.user_visible is not None
    assert "subharmonic" in result.user_visible
    assert "established universal" not in result.user_visible


def _not_release_or_stripped(result, *, must_exclude: tuple[str, ...], must_include: tuple[str, ...] = ()) -> None:
    if result.decision == "release":
        assert result.released_answer is True
        assert result.user_visible is not None
        visible = result.user_visible
        for token in must_include:
            assert token in visible
        for token in must_exclude:
            assert token not in visible
        return
    assert result.released_answer is False


def test_elided_and_is_faraday_overclaim_does_not_ride_out() -> None:
    draft = (
        "The primary Faraday instability is typically a subharmonic response "
        "and is an established universal Faraday result."
    )
    assert split_clauses(draft) == [
        "The primary Faraday instability is typically a subharmonic response",
        "The primary Faraday instability is an established universal Faraday result.",
    ]
    result = run(
        "Summarize Faraday onset and Phase 6.",
        adapter=MockAdapter(draft),
    )
    _not_release_or_stripped(
        result,
        must_include=("subharmonic",),
        must_exclude=("established universal",),
    )


def test_elided_and_is_atlantis_capital_does_not_release() -> None:
    draft = "Water is H2O and is the capital of Atlantis."
    assert split_clauses(draft) == [
        "Water is H2O",
        "Water is the capital of Atlantis.",
    ]
    result = run(
        "What is water, and what is the population of Atlantis?",
        adapter=MockAdapter(draft),
    )
    _not_release_or_stripped(
        result,
        must_include=("H2O",),
        must_exclude=("Atlantis", "capital"),
    )
    if result.decision == "release":
        texts = [claim["text"] for claim in result.receipt["factual_support"]["claims"]]
        assert texts == ["Water is H2O."]


def test_relative_which_is_does_not_smuggle_wet() -> None:
    draft = "Water, which is H2O, is wet."
    parts = split_clauses(draft)
    assert parts == ["Water, which is H2O", "Water, which is wet."]
    assert not any("H2O" in part and "wet" in part for part in parts)
    result = run(
        "What is the chemical formula of water?",
        adapter=MockAdapter(draft),
    )
    _not_release_or_stripped(result, must_exclude=("wet",))
    if result.decision == "release":
        texts = [claim["text"] for claim in result.receipt["factual_support"]["claims"]]
        assert all("wet" not in claim for claim in texts)


def test_lookup_requires_more_than_subject_and_value() -> None:
    outcome = check_lookup("water h2o")
    assert outcome.kind == "unknown"


def test_lookup_faraday_still_matches_subject_predicate_value() -> None:
    outcome = check_lookup("The primary Faraday instability is typically a subharmonic response.")
    assert outcome.kind == "supported"
    assert outcome.fact_id == "physics.faraday.primary_response"


def test_extract_splits_conjunction_into_clause_claims() -> None:
    claims = extract_claims("Water is H2O and Atlantis has a resident population of 12403.")
    assert [claim.text for claim in claims] == [
        "Water is H2O",
        "Atlantis has a resident population of 12403.",
    ]
    assert claims[0].polarity == "affirmative"
    assert extract_claims("Water is not H2O.")[0].polarity == "negated"


def test_semicolon_keeps_two_lawful_clauses() -> None:
    draft = "DLT-003 is a falsifiable causal-state test; inconclusive is a lawful outcome."
    parts = split_clauses(draft)
    assert parts == [
        "DLT-003 is a falsifiable causal-state test",
        "inconclusive is a lawful outcome.",
    ]
    result = run(
        "Is Phase 9 closure already physical?",
        adapter=MockAdapter(draft),
    )
    assert result.decision == "release"
    assert result.released_answer is True
    assert result.user_visible is not None
    assert "falsifiable causal-state test" in result.user_visible
    assert "inconclusive is a lawful outcome" in result.user_visible
    claims = result.receipt["factual_support"]["claims"]
    assert len(claims) == 2
    assert {claim["status"] for claim in claims} == {"supported"}


def test_list_and_does_not_fragment_value_list() -> None:
    draft = (
        "The gravity-capillary dispersion relation includes gravity, "
        "surface tension, and finite depth."
    )
    assert split_clauses(draft) == [draft]
    claims = extract_claims(draft)
    assert [claim.text for claim in claims] == [draft]
    result = run(
        "What enters the gravity-capillary dispersion relation?",
        adapter=MockAdapter(draft),
    )
    assert result.decision == "release"
    assert result.user_visible is not None
    assert "finite depth" in result.user_visible
    assert "surface tension" in result.user_visible
    texts = [claim["text"] for claim in result.receipt["factual_support"]["claims"]]
    assert texts == [draft]


def test_mixed_and_still_strips_unsupported_clause() -> None:
    result = run(
        "What is water, and what is the population of Atlantis?",
        adapter=MockAdapter("Water is H2O and Atlantis has 12403."),
    )
    assert result.decision == "release"
    assert result.user_visible is not None
    assert "H2O" in result.user_visible
    assert "12403" not in result.user_visible
    assert "Atlantis" not in result.user_visible


def test_comma_splice_splits_two_clauses() -> None:
    draft = "Water is H2O, Atlantis has 12403."
    assert split_clauses(draft) == ["Water is H2O", "Atlantis has 12403."]
    claims = extract_claims(draft)
    assert [claim.text for claim in claims] == ["Water is H2O", "Atlantis has 12403."]
    result = run(
        "What is water, and what is the population of Atlantis?",
        adapter=MockAdapter(draft),
    )
    assert result.decision == "release"
    assert result.user_visible is not None
    assert "H2O" in result.user_visible
    assert "12403" not in result.user_visible
    assert "Atlantis" not in result.user_visible
    texts = [claim["text"] for claim in result.receipt["factual_support"]["claims"]]
    assert texts == ["Water is H2O."]


def test_pronoun_tail_kept_when_lawful() -> None:
    it_draft = "DLT-003 is a falsifiable causal-state test; it is a lawful outcome."
    this_draft = "DLT-003 is a falsifiable causal-state test; this is a lawful outcome."
    assert split_clauses(it_draft) == [
        "DLT-003 is a falsifiable causal-state test",
        "DLT-003 is a lawful outcome.",
    ]
    assert split_clauses(this_draft) == [
        "DLT-003 is a falsifiable causal-state test",
        "DLT-003 is a lawful outcome.",
    ]
    for draft in (it_draft, this_draft):
        result = run(
            "Is Phase 9 closure already physical?",
            adapter=MockAdapter(draft),
        )
        assert result.decision == "release"
        assert result.released_answer is True
        assert result.user_visible is not None
        assert "falsifiable causal-state test" in result.user_visible
        assert "lawful outcome" in result.user_visible
        claims = result.receipt["factual_support"]["claims"]
        assert len(claims) == 2
        assert {claim["status"] for claim in claims} == {"supported"}


def test_or_colon_emdash_split_clauses() -> None:
    drafts = (
        "Water is H2O or Atlantis has 12403.",
        "Water is H2O: Atlantis has 12403.",
        "Water is H2O — Atlantis has 12403.",
        "Water is H2O -- Atlantis has 12403.",
        "Water is H2O nor Atlantis has 12403.",
        "Water is H2O as well as Atlantis has 12403.",
    )
    for draft in drafts:
        assert split_clauses(draft) == ["Water is H2O", "Atlantis has 12403."], draft
        result = run(
            "What is water, and what is the population of Atlantis?",
            adapter=MockAdapter(draft),
        )
        assert result.decision == "release", draft
        assert result.user_visible is not None
        assert "H2O" in result.user_visible
        assert "12403" not in result.user_visible
        assert "Atlantis" not in result.user_visible


def test_list_or_does_not_fragment_value_list() -> None:
    draft = (
        "The gravity-capillary dispersion relation includes gravity, "
        "surface tension, or finite depth."
    )
    assert split_clauses(draft) == [draft]
    claims = extract_claims(draft)
    assert [claim.text for claim in claims] == [draft]
    result = run(
        "What enters the gravity-capillary dispersion relation?",
        adapter=MockAdapter(draft),
    )
    assert result.decision == "release"
    assert result.user_visible is not None
    assert "finite depth" in result.user_visible
    assert "surface tension" in result.user_visible
    texts = [claim["text"] for claim in result.receipt["factual_support"]["claims"]]
    assert texts == [draft]
