"""Receipt buckets stay separate; same inputs replay the same decision class."""

from __future__ import annotations

import json
from pathlib import Path

from adapter import Draft, MockAdapter
from claims import extract_claims
from constitution import constitution_version_hash
from jcr import decide
from lookup import library_binding
from pipeline import run
from receipt import build_receipt
from replay import replay_receipt
from store import load_receipt
from verifier import check_claims


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
    provenance_required = set(schema["properties"]["execution_provenance"]["required"])
    assert "library_hash" in provenance_required


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


def test_receipt_written_with_library_hash(isolate_receipt_log: Path) -> None:
    result = run(
        "What is the chemical formula of water?",
        adapter=MockAdapter("Water's chemical formula is H2O."),
    )
    assert isolate_receipt_log.is_file()
    lines = isolate_receipt_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    stored = json.loads(lines[0])
    lib_hash = result.receipt["execution_provenance"]["library_hash"]
    expected = library_binding().content_hash
    assert lib_hash == expected
    assert stored["receipt_id"] == result.receipt["receipt_id"]
    assert stored["execution_provenance"]["library_hash"] == lib_hash
    assert result.receipt["organism_binding"]["replay"]["library_hash"] == lib_hash
    assert result.receipt["organism_binding"]["continuity"]["library_hash"] == lib_hash
    assert result.receipt["organism_binding"]["replay"]["prompt"]
    assert result.receipt["organism_binding"]["replay"]["draft"]
    assert result.receipt["organism_binding"]["replay"]["deterministic"] is True
    assert load_receipt(result.receipt["receipt_id"])["receipt_id"] == result.receipt["receipt_id"]


def test_cli_replay_same_decision_class(isolate_receipt_log: Path) -> None:
    from cli import main

    first = run(
        "What is the chemical formula of water?",
        adapter=MockAdapter("Water's chemical formula is H2O."),
    )
    assert main(["replay", first.receipt["receipt_id"]]) == 0


def test_replay_store_keeps_decision_class(isolate_receipt_log: Path) -> None:
    first = run(
        "What is the population of Atlantis?",
        adapter=MockAdapter("The lost city of Atlantis has a resident population of 12,403."),
    )
    outcome = replay_receipt(first.receipt["receipt_id"])
    assert outcome["pass"] is True
    assert outcome["replayed_decision"] == first.decision
    assert outcome["stored_decision"] == first.receipt["organism_binding"]["replay"]["decision_class"]


def test_receipt_log_is_append_only(isolate_receipt_log: Path) -> None:
    first = run(
        "What is the chemical formula of water?",
        adapter=MockAdapter("Water's chemical formula is H2O."),
    )
    first_bytes = isolate_receipt_log.read_text(encoding="utf-8")
    run(
        "What is the population of Atlantis?",
        adapter=MockAdapter("The lost city of Atlantis has a resident population of 12,403."),
    )
    later = isolate_receipt_log.read_text(encoding="utf-8")
    assert later.startswith(first_bytes)
    assert later.count("\n") == 2
    assert first.receipt["receipt_id"] in first_bytes


def test_live_draft_is_not_marked_deterministic() -> None:
    draft_text = "Water's chemical formula is H2O."
    claims = extract_claims(draft_text)
    support = check_claims(claims, draft_text)
    receipt = build_receipt(
        prompt="What is the chemical formula of water?",
        draft=Draft(
            text=draft_text,
            model_id="llama3.2:3b",
            model_version="llama3.2:3b",
            generation_id="gen:openai:not-mock",
        ),
        claims=claims,
        support=support,
        decision=decide(support),
        request_id="req:test-live",
        started_utc="2026-01-01T00:00:00+00:00",
        released_answer=True,
        payload_kind="answer",
    )
    replay = receipt["organism_binding"]["replay"]
    assert replay["deterministic"] is False
    assert "not deterministic" in replay["deterministic_reason"]
