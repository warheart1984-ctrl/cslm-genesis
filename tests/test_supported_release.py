"""Happy path: a supported stub claim may release with a three-bucket receipt."""

from __future__ import annotations

from adapter import MockAdapter
from pipeline import run


SUPPORTED_DRAFT = (
    "Water's chemical formula is H2O. [source: stub:chemistry-allowlist]"
)


def test_supported_stub_claim_releases_with_receipt() -> None:
    result = run(
        "What is the chemical formula of water?",
        adapter=MockAdapter(SUPPORTED_DRAFT),
    )

    assert result.decision == "release"
    assert result.released_answer is True
    assert result.user_visible is not None
    assert "H2O" in result.user_visible
    receipt = result.receipt
    assert "factual_support" in receipt
    assert "governance_compliance" in receipt
    assert "execution_provenance" in receipt
    assert receipt["governance_compliance"]["decision"] == "release"
    statuses = {c["status"] for c in receipt["factual_support"]["claims"]}
    assert "supported" in statuses
    assert "unsupported" not in statuses


def test_model_written_citation_is_not_automatic_evidence() -> None:
    result = run(
        "What is the population of Atlantis?",
        adapter=MockAdapter(
            "The lost city of Atlantis has a resident population of 12,403. "
            "[source: https://example.invalid/made-up]"
        ),
    )

    assert result.decision == "block"
    assert result.released_answer is False
    assert result.user_visible is None
    claim = result.receipt["factual_support"]["claims"][0]
    assert "model-written citation" in claim["reason"]
