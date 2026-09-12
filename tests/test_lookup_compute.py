"""Support comes from lookup or compute — not from the model's wording."""

from __future__ import annotations

from adapter import MockAdapter
from compute import check_compute
from lookup import check_lookup
from pipeline import run


def test_lookup_supports_paraphrase_without_model_citation() -> None:
    result = run(
        "What is the chemical formula of water?",
        adapter=MockAdapter("The chemical formula for water is H2O."),
    )
    assert result.decision == "release"
    assert result.released_answer is True
    claim = result.receipt["factual_support"]["claims"][0]
    assert claim["status"] == "supported"
    assert claim["sources"] == ["lookup:chemistry.water.formula"]
    assert "lookup" in claim["reason"]


def test_lookup_contradiction_does_not_release() -> None:
    result = run(
        "How many moons does Mars have?",
        adapter=MockAdapter("Mars has seventeen moons."),
    )
    assert result.decision != "release"
    assert result.released_answer is False
    claim = result.receipt["factual_support"]["claims"][0]
    assert claim["status"] == "unsupported"
    assert "contradict" in claim["reason"]


def test_compute_supports_correct_arithmetic() -> None:
    result = run(
        "What is 2 + 2?",
        adapter=MockAdapter("2 + 2 equals 4."),
    )
    assert result.decision == "release"
    claim = result.receipt["factual_support"]["claims"][0]
    assert claim["status"] == "supported"
    assert claim["sources"][0].startswith("compute:")


def test_compute_rejects_wrong_arithmetic() -> None:
    result = run(
        "What is 2 + 2?",
        adapter=MockAdapter("2 + 2 equals 5."),
    )
    assert result.decision != "release"
    assert result.released_answer is False
    claim = result.receipt["factual_support"]["claims"][0]
    assert "contradict" in claim["reason"]


def test_unknown_fact_stays_unsupported() -> None:
    outcome = check_lookup("The lost city of Atlantis has a resident population of 12403.")
    assert outcome.kind == "unknown"


def test_revise_drops_unsupported_sentence_then_releases_rest() -> None:
    result = run(
        "What is the chemical formula of water?",
        adapter=MockAdapter(
            "The chemical formula for water is H2O. "
            "Atlantis has a resident population of 12403."
        ),
    )
    assert result.decision == "release"
    assert result.user_visible is not None
    assert "H2O" in result.user_visible
    assert "12403" not in result.user_visible
    statuses = {c["status"] for c in result.receipt["factual_support"]["claims"]}
    assert statuses == {"supported"}


def test_compute_unit_on_raw_expression() -> None:
    ok = check_compute("2 plus 2 equals 4.")
    assert ok is not None
    assert ok.kind == "supported"
    bad = check_compute("10 divided by 2 equals 3.")
    assert bad is not None
    assert bad.kind == "contradicted"
