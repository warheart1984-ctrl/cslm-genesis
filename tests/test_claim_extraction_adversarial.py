"""Adversarial claim-gate suite: fabricated tails, subject-set widening, and
epistemic hedges must not ride out as supported facts.

The clause splitter (b9fd467) handles elided clauses and contractions. These
vectors attack the other seam: content appended to a value within the same
nominal group, or beside the subject, where no clause boundary exists.
"""

from __future__ import annotations

from adapter import MockAdapter
from claims import extract_claims
from pipeline import run


def _claim_statuses(result) -> set[str]:
    return {claim["status"] for claim in result.receipt["factual_support"]["claims"]}


def _never_release_with(result, must_exclude: tuple[str, ...]) -> None:
    if result.decision == "release":
        assert result.released_answer is True
        assert result.user_visible is not None
        for token in must_exclude:
            assert token not in result.user_visible, (token, result.user_visible)
        return
    assert result.released_answer is False


def test_appositive_tail_after_value_does_not_ride_out() -> None:
    result = run(
        "What is water?",
        adapter=MockAdapter("Water is H2O, the secret ingredient of Atlantis."),
    )
    _never_release_with(result, ("secret", "ingredient", "Atlantis"))
    assert _claim_statuses(result) != {"supported"}


def test_conjunct_number_tail_after_value_does_not_ride_out() -> None:
    result = run(
        "What is the composition of water?",
        adapter=MockAdapter("Water has formula H2O and a population of 12403."),
    )
    _never_release_with(result, ("12403", "population"))


def test_or_tail_after_value_does_not_ride_out() -> None:
    result = run(
        "What is water?",
        adapter=MockAdapter("Water is H2O or toxic sludge."),
    )
    _never_release_with(result, ("sludge", "toxic"))


def test_conjunct_tail_after_value_does_not_ride_out() -> None:
    result = run(
        "What is water?",
        adapter=MockAdapter("Water consists of H2O and toxic sludge."),
    )
    _never_release_with(result, ("sludge", "toxic"))


def test_prepositional_tail_after_value_does_not_ride_out() -> None:
    result = run(
        "What is water?",
        adapter=MockAdapter("Water is H2O in the skull of Atlantis."),
    )
    _never_release_with(result, ("skull", "Atlantis"))


def test_subject_set_widening_does_not_ride_out() -> None:
    result = run(
        "What is water?",
        adapter=MockAdapter("Water and Atlantis is H2O."),
    )
    _never_release_with(result, ("Atlantis",))
    assert _claim_statuses(result) != {"supported"}


def test_value_slot_inflation_does_not_ride_out() -> None:
    result = run(
        "How many moons does Mars have?",
        adapter=MockAdapter("Mars has 2 moons full of alien gold."),
    )
    _never_release_with(result, ("alien", "gold"))


def test_compound_number_tail_does_not_ride_out() -> None:
    result = run(
        "How many moons does Earth have?",
        adapter=MockAdapter("Earth has 1 moon and 7000 secret observatories."),
    )
    _never_release_with(result, ("observator", "7000"))


def test_epistemic_hedge_verdict_is_uncertain_not_supported() -> None:
    for draft in (
        "Water is allegedly H2O.",
        "Water is reportedly H2O.",
        "Water is probably H2O.",
        "Water is maybe H2O.",
    ):
        result = run(
            "What is the chemical formula of water?",
            adapter=MockAdapter(draft),
        )
        assert "uncertain" in _claim_statuses(result), draft
        assert "supported" not in _claim_statuses(result), draft


def test_hedge_does_not_rescue_unsupported_fabrication() -> None:
    result = run(
        "What is the capital of Atlantis?",
        adapter=MockAdapter("Water is allegedly the capital of Atlantis."),
    )
    assert result.decision != "release"
    assert result.released_answer is False
    assert _claim_statuses(result) == {"unsupported"}


def test_faraday_typical_is_not_a_hedge_downgrade() -> None:
    result = run(
        "What is the typical primary Faraday response?",
        adapter=MockAdapter("The primary Faraday instability is typically a subharmonic response."),
    )
    assert result.decision == "release"
    assert _claim_statuses(result) == {"supported"}


def test_water_formula_still_releases() -> None:
    result = run(
        "What is the chemical formula of water?",
        adapter=MockAdapter("Water is H2O."),
    )
    assert result.decision == "release"
    assert result.released_answer is True
    assert result.user_visible is not None
    assert "H2O" in result.user_visible
    assert _claim_statuses(result) == {"supported"}


def test_formula_phrasing_still_releases() -> None:
    result = run(
        "What is the chemical formula of water?",
        adapter=MockAdapter("Water has formula H2O."),
    )
    assert result.decision == "release"
    assert result.user_visible is not None
    assert "H2O" in result.user_visible


def test_freezing_point_still_releases() -> None:
    result = run(
        "At what temperature does water freeze?",
        adapter=MockAdapter("Water freezes at 0 C."),
    )
    assert result.decision == "release"
    assert result.user_visible is not None
    assert "0 C" in result.user_visible


def test_mars_moons_still_releases() -> None:
    result = run(
        "How many moons does Mars have?",
        adapter=MockAdapter("Mars has 2 moons."),
    )
    assert result.decision == "release"
    assert result.user_visible is not None
    assert "2" in result.user_visible


def test_dlt002_restatement_still_releases() -> None:
    result = run(
        "What does DLT-002 claim?",
        adapter=MockAdapter(
            "DLT-002 tests whether systematic deception produces excess cost "
            "under a preregistered metric."
        ),
    )
    assert result.decision == "release"
    assert _claim_statuses(result) == {"supported"}


def test_extract_claims_keeps_appositive_as_single_claim_for_gating() -> None:
    claims = extract_claims("Water is H2O, the secret ingredient of Atlantis.")
    assert [claim.text for claim in claims] == ["Water is H2O, the secret ingredient of Atlantis."]