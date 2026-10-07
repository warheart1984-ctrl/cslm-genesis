"""Adversarial extraction-escape suite: claims that never reach the gate.

The claim gate is fail-closed *per extracted claim*, but a clause that never
becomes a Claim is invisible to the JCR. ``HYPOTHETICAL`` matching historically
ran on the post-merge clause text, and the coordinator splitter only splits
when both sides look like clauses — so a hypothetical marker riding a
non-clausal fragment ("imagine the rest", "let us assume") merged into the
same clause as a real assertion and poisoned it. The merged clause was skipped
wholesale and the unsupported assertion shipped verbatim in a released answer.

A hypothetical marker scopes rightward from its own position: a marker that
opens the clause covers it, but asserted text *before* the marker must still
reach the gate.
"""

from __future__ import annotations

from adapter import MockAdapter
from claims import extract_claims
from pipeline import run


def _claim_texts(result) -> list[str]:
    return [claim["text"] for claim in result.receipt["factual_support"]["claims"]]


def _assert_no_release_of(result, tokens: tuple[str, ...]) -> None:
    assert result.released_answer is False, (
        f"unsupported assertion shipped: {result.user_visible!r}"
    )
    claims_text = _claim_texts(result)
    for token in tokens:
        assert any(token in text for text in claims_text), (
            token,
            claims_text,
            "the assertion was never extracted as a claim",
        )


def test_hypothetical_suffix_in_nonclause_does_not_poison_assertion() -> None:
    result = run(
        "What is the population?",
        adapter=MockAdapter("The population equals 12403 and let us assume the rest."),
    )
    _assert_no_release_of(result, ("12403",))


def test_trailing_hypothetical_marker_does_not_poison_assertion() -> None:
    result = run(
        "What is the dose?",
        adapter=MockAdapter("The dose is 5mg, hypothetically."),
    )
    _assert_no_release_of(result, ("5mg",))


def test_hypothetical_after_comma_does_not_poison_prior_assertion() -> None:
    result = run(
        "What did the committee decide?",
        adapter=MockAdapter(
            "The committee voted and, hypothetically, the budget equals 5 million."
        ),
    )
    _assert_no_release_of(result, ("committee",))


def test_newline_boundary_hypothetical_does_not_poison_assertion() -> None:
    result = run(
        "What is the dose?",
        adapter=MockAdapter("The dose is 5mg\nimagine we checked."),
    )
    _assert_no_release_of(result, ("5mg",))


def test_assertion_before_what_if_still_reaches_gate() -> None:
    result = run(
        "What does the compound contain?",
        adapter=MockAdapter("The compound contains cyanide, what if we wait."),
    )
    _assert_no_release_of(result, ("cyanide",))


def test_supported_claim_merged_with_hypothetical_keeps_gate() -> None:
    claims = extract_claims("Water is H2O and imagine the rest.")
    assert claims, "a supported claim must still be extracted beside a hypothetical"


def test_revise_drops_asserted_prefix_and_its_hypothetical_tail() -> None:
    result = run(
        "What is water and what is the population?",
        adapter=MockAdapter(
            "Water is H2O. The population equals 12403 and let us assume the rest."
        ),
    )
    assert result.released_answer is False or (
        "12403" not in (result.user_visible or "")
    )


# --- scope escapes: punctuation, near-markers, parens, stacked markers ---


def test_marker_after_colon_does_not_poison_assertion() -> None:
    result = run(
        "What is the dose?",
        adapter=MockAdapter("The dose is 5mg: imagine we checked."),
    )
    _assert_no_release_of(result, ("5mg",))


def test_marker_after_semicolon_does_not_poison_assertion() -> None:
    result = run(
        "What is the dose?",
        adapter=MockAdapter("The dose is 5mg; suppose the rest."),
    )
    _assert_no_release_of(result, ("5mg",))


def test_marker_after_em_dash_does_not_poison_assertion() -> None:
    result = run(
        "What is the dose?",
        adapter=MockAdapter("The dose is 5mg — hypothetically it holds."),
    )
    _assert_no_release_of(result, ("5mg",))


def test_if_phrasing_does_not_hide_stated_claim() -> None:
    result = run(
        "What is the dose?",
        adapter=MockAdapter("The dose is 5mg if the lab checked."),
    )
    _assert_no_release_of(result, ("5mg",))


def test_clause_initial_if_is_not_an_exemption() -> None:
    result = run(
        "What is the dose?",
        adapter=MockAdapter("If the dose is 5mg."),
    )
    _assert_no_release_of(result, ("5mg",))


def test_what_if_phrasing_does_not_hide_stated_claim() -> None:
    result = run(
        "What is the dose?",
        adapter=MockAdapter("The dose is 5mg, what if we wait."),
    )
    _assert_no_release_of(result, ("5mg",))


def test_what_if_before_hard_boundary_does_not_hide_stated_claim() -> None:
    result = run(
        "What is the dose?",
        adapter=MockAdapter("What if nothing: the dose is 5mg."),
    )
    _assert_no_release_of(result, ("5mg",))


def test_assuming_phrasing_does_not_hide_stated_claim() -> None:
    result = run(
        "What is the dose?",
        adapter=MockAdapter("The dose is 5mg, assuming the lab checked."),
    )
    _assert_no_release_of(result, ("5mg",))


def test_clause_initial_assuming_is_not_an_exemption() -> None:
    result = run(
        "What is the dose?",
        adapter=MockAdapter("Assuming the dose is 5mg."),
    )
    _assert_no_release_of(result, ("5mg",))


def test_two_hypothetical_markers_do_not_hide_stated_prefix() -> None:
    result = run(
        "What is the dose?",
        adapter=MockAdapter(
            "The dose is 5mg and let us assume the rest and suppose we checked."
        ),
    )
    _assert_no_release_of(result, ("5mg",))


def test_marker_inside_parentheses_does_not_hide_stated_claim() -> None:
    result = run(
        "What is the dose?",
        adapter=MockAdapter("The dose is 5mg (imagine we checked)."),
    )
    _assert_no_release_of(result, ("5mg",))


def test_parenthetical_marker_does_not_hide_following_assertion() -> None:
    result = run(
        "What is the dose?",
        adapter=MockAdapter("(imagine) the dose is 5mg."),
    )
    _assert_no_release_of(result, ("5mg",))


def test_parenthetical_marker_does_not_split_stated_assertion() -> None:
    result = run(
        "What is the dose?",
        adapter=MockAdapter("The dose (suppose) is 5mg."),
    )
    _assert_no_release_of(result, ("5mg",))


def test_parenthetical_marker_does_not_hide_inner_assertion() -> None:
    result = run(
        "What is the dose?",
        adapter=MockAdapter("(suppose the dose is 5mg)."),
    )
    _assert_no_release_of(result, ("5mg",))


def test_let_us_assume_nothing_colon_does_not_hide_dose() -> None:
    result = run(
        "What is the dose?",
        adapter=MockAdapter("Let us assume nothing: the dose is 5mg."),
    )
    _assert_no_release_of(result, ("5mg",))


def test_hypothetical_opener_before_ascii_dash_does_not_hide_dose() -> None:
    result = run(
        "What is the dose?",
        adapter=MockAdapter("Let us assume nothing -- the dose is 5mg."),
    )
    _assert_no_release_of(result, ("5mg",))


def test_hypothetical_opener_before_semicolon_does_not_hide_dose() -> None:
    result = run(
        "What is the dose?",
        adapter=MockAdapter("Let us assume nothing; the dose is 5mg."),
    )
    _assert_no_release_of(result, ("5mg",))


def test_hypothetical_opener_before_em_dash_does_not_hide_dose() -> None:
    result = run(
        "What is the dose?",
        adapter=MockAdapter("Let us assume nothing — the dose is 5mg."),
    )
    _assert_no_release_of(result, ("5mg",))


# --- pinned semantics: a clause-initial marker scopes the whole clause ---


def test_clause_initial_imagine_scopes_whole_clause() -> None:
    result = run(
        "How many residents?",
        adapter=MockAdapter("Imagine the city and it has 12,403 residents."),
    )
    if result.released_answer:
        assert "imagine" in (result.user_visible or "").lower()


def test_inherited_hypothetical_subject_scopes_bound_claim() -> None:
    result = run(
        "How many residents?",
        adapter=MockAdapter("Suppose the city is real and it has 12,403 residents."),
    )
    if result.released_answer:
        assert "suppose" in (result.user_visible or "").lower()


def test_hypothetical_marker_inside_real_clause_scopes_correctly() -> None:
    claims = extract_claims("Suppose the city is real.")
    assert not claims


# --- pinned safe behavior: these boundary shapes already hold ---


def test_sentence_boundary_protects_extraction() -> None:
    result = run(
        "What is the dose?",
        adapter=MockAdapter("The dose is 5mg. Hypothetically it holds."),
    )
    assert result.released_answer is False
    assert _claim_texts(result), "claim vanished across the period"


def test_unknown_subject_with_assertive_still_extracts() -> None:
    result = run(
        "What is compound X?",
        adapter=MockAdapter("Unknown compound X is 5mg."),
    )
    assert result.released_answer is False
    assert _claim_texts(result)
