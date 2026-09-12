"""Live governance eval is observational. Mock expected outcomes stay untouched."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from adapter import Draft, select_adapter
from dlt_eval import (
    LIVE_NOTES,
    decision_histogram,
    live_endpoint_reachable,
    main,
    run_live_suite,
    run_suite,
)
from envload import load_dotenv
from pipeline import run


class RecordingAdapter:
    """Live-shaped adapter for tests: records prompts and never uses case drafts."""

    model_id = "llama3.2:3b"
    model_version = "llama3.2:3b"

    def __init__(self, text: str) -> None:
        self.text = text
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> Draft:
        self.prompts.append(prompt)
        return Draft(
            text=self.text,
            model_id=self.model_id,
            model_version=self.model_version,
            generation_id="gen:openai:test-live",
        )


def _write_cases(path: Path, cases: list[dict]) -> Path:
    path.write_text(
        json.dumps({"suite_id": "test.live", "cases": cases}, indent=2),
        encoding="utf-8",
    )
    return path


def test_mock_suite_still_scores_checked_in_expect() -> None:
    rows = run_suite()
    assert rows
    assert all("expect" in row and "pass" in row for row in rows)
    assert all(row["pass"] for row in rows)


def test_live_uses_prompts_not_case_drafts(tmp_path: Path, isolate_receipt_log: Path) -> None:
    forbidden = "THIS_DRAFT_MUST_NOT_BE_USED as an established universal Faraday result."
    cases_path = _write_cases(
        tmp_path / "cases.json",
        [
            {
                "id": "c1",
                "class": "x",
                "prompt": "What is water?",
                "draft": forbidden,
                "expect": "not_release",
            }
        ],
    )
    adapter = RecordingAdapter("Water is H2O.")
    report = run_live_suite(cases_path, adapter=adapter, include_extra=False)
    assert adapter.prompts == ["What is water?"]
    row = report["rows"][0]
    assert row["prompt"] == "What is water?"
    assert row["model_id"] == "llama3.2:3b"
    assert row["decision"] == "release"
    assert row["released_answer"] is True
    assert row["receipt_id"].startswith("cslm:")
    assert "H2O" in row["claim_summary"]
    assert forbidden not in row["claim_summary"]
    assert row["receipt_id"] in isolate_receipt_log.read_text(encoding="utf-8")
    assert "expect" not in row
    assert "pass" not in row
    assert "passed" not in report
    assert report["deterministic"] is False
    assert row["deterministic"] is False
    assert "Not Faraday" in report["notes"]


def test_live_extra_prompts_are_optional(tmp_path: Path) -> None:
    cases_path = _write_cases(
        tmp_path / "cases.json",
        [{"id": "c1", "class": "x", "prompt": "What is water?"}],
    )
    extra_path = _write_cases(
        tmp_path / "extra.json",
        [{"id": "live_smuggle", "class": "smuggle", "prompt": "Water and Atlantis?"}],
    )
    adapter = RecordingAdapter("Water is H2O.")
    without = run_live_suite(cases_path, adapter=adapter, include_extra=False)
    adapter.prompts.clear()
    with_extra = run_live_suite(
        cases_path,
        adapter=adapter,
        extra_path=extra_path,
        include_extra=True,
    )
    assert [row["id"] for row in without["rows"]] == ["c1"]
    assert [row["id"] for row in with_extra["rows"]] == ["c1", "live_smuggle"]
    assert [row["source"] for row in with_extra["rows"]] == ["protocol", "live_extra"]
    assert adapter.prompts == ["What is water?", "Water and Atlantis?"]


def test_decision_histogram_counts_known_classes() -> None:
    histogram = decision_histogram(
        [
            {"decision": "release"},
            {"decision": "release"},
            {"decision": "block"},
            {"decision": "uncertainty_statement"},
        ]
    )
    assert histogram == {
        "release": 2,
        "revise": 0,
        "block": 1,
        "uncertainty_statement": 1,
    }


def test_live_cli_does_not_score_expect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    fake = {
        "mode": "live",
        "deterministic": False,
        "notes": LIVE_NOTES,
        "model_id": "llama3.2:3b",
        "histogram": {
            "release": 1,
            "revise": 0,
            "block": 0,
            "uncertainty_statement": 0,
        },
        "rows": [
            {
                "id": "c1",
                "prompt": "What is water?",
                "model_id": "llama3.2:3b",
                "decision": "release",
                "released_answer": True,
                "receipt_id": "cslm:test",
                "claim_summary": "supported: Water is H2O.",
                "deterministic": False,
            }
        ],
    }

    def _fake_live(**kwargs):
        return fake

    monkeypatch.setattr("dlt_eval.live_endpoint_reachable", lambda: True)
    monkeypatch.setattr("dlt_eval.run_live_suite", _fake_live)
    assert main(["--live"]) == 0
    out, err = capsys.readouterr()
    payload = json.loads(out)
    assert payload["deterministic"] is False
    assert "passed" not in payload
    assert "decision histogram" in err
    assert "release: 1" in err


def test_live_cli_exits_when_endpoint_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("dlt_eval.live_endpoint_reachable", lambda: False)

    def _must_not_run(**kwargs):
        raise AssertionError("live suite must not run when Ollama is down")

    monkeypatch.setattr("dlt_eval.run_live_suite", _must_not_run)
    assert main(["--live"]) == 2


@pytest.mark.live
def test_live_ollama_one_governance_observation() -> None:
    if not live_endpoint_reachable():
        pytest.skip("project Ollama not reachable on 127.0.0.1:11435")
    load_dotenv()
    result = run("What is the chemical formula of water?", adapter=select_adapter())
    replay = result.receipt["organism_binding"]["replay"]
    assert replay["deterministic"] is False
    assert result.receipt["receipt_id"].startswith("cslm:")
    assert result.decision in {"release", "revise", "block", "uncertainty_statement"}
