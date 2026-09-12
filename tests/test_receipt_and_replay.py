"""Receipt buckets stay separate; same inputs replay the same decision class."""

from __future__ import annotations

import json
from pathlib import Path

from adapter import MockAdapter
from constitution import constitution_version_hash
from pipeline import run


ROOT = Path(__file__).resolve().parents[1]


def test_receipt_separates_three_buckets() -> None:
    result = run(
        "What is the chemical formula of water?",
        adapter=MockAdapter(
            "Water's chemical formula is H2O. [source: stub:chemistry-allowlist]"
        ),
    )
    receipt = result.receipt
    factual_keys = set(receipt["factual_support"].keys())
    gov_keys = set(receipt["governance_compliance"].keys())
    prov_keys = set(receipt["execution_provenance"].keys())
    assert "claims" in factual_keys
    assert "decision" in gov_keys
    assert "model_id" in prov_keys
    assert "decision" not in factual_keys
    assert "claims" not in gov_keys
    assert receipt["constitution_version_hash"] == constitution_version_hash()
    for section in (
        "organ",
        "intent",
        "decision",
        "effect",
        "evidence",
        "replay",
        "continuity",
    ):
        assert section in receipt["organism_binding"]


def test_receipt_id_matches_schema_prefix() -> None:
    result = run(
        "What is the chemical formula of water?",
        adapter=MockAdapter(
            "Water's chemical formula is H2O. [source: stub:chemistry-allowlist]"
        ),
    )
    assert result.receipt["receipt_id"].startswith("cslm:")
    assert result.receipt["receipt_version"] == "cslm.receipt.v0"


def test_schema_file_declares_three_buckets() -> None:
    schema = json.loads((ROOT / "receipt.schema.json").read_text(encoding="utf-8"))
    required = set(schema["required"])
    assert {
        "factual_support",
        "governance_compliance",
        "execution_provenance",
        "constitution_version_hash",
    } <= required


def test_replay_same_inputs_same_decision_class() -> None:
    adapter = MockAdapter(
        "The lost city of Atlantis has a resident population of 12,403."
    )
    first = run("What is the population of Atlantis?", adapter=adapter)
    second = run("What is the population of Atlantis?", adapter=adapter)
    assert first.decision == second.decision
    assert (
        first.receipt["organism_binding"]["replay"]["decision_class"]
        == second.receipt["organism_binding"]["replay"]["decision_class"]
    )
    assert (
        first.receipt["organism_binding"]["replay"]["input_digest"]
        == second.receipt["organism_binding"]["replay"]["input_digest"]
    )
