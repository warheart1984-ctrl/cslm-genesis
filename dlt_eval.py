"""Run preregistered Diamond Lens governance cases through JCR."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, TextIO

from adapter import DEFAULT_BASE_URL, BaseLMAdapter, MockAdapter, select_adapter
from envload import load_dotenv
from pipeline import PipelineResult, run

CASES_PATH = Path(__file__).resolve().parent / "protocols" / "cases.json"
LIVE_EXTRA_PATH = Path(__file__).resolve().parent / "protocols" / "live_extra.json"

DECISION_ORDER = ("release", "revise", "block", "uncertainty_statement")

LIVE_NOTES = (
    "Governance observations of JCR on live drafts. "
    "Not Faraday or DLT science results. "
    "Mock expected decisions are not rewritten from live outcomes."
)


def _ok(case: dict, result) -> bool:
    expect = case["expect"]
    answer = result.user_visible or ""
    match expect:
        case "release":
            return result.decision == "release" and result.released_answer
        case "not_release":
            return result.decision != "release" and not result.released_answer
        case "block":
            return result.decision == "block" and not result.released_answer
        case "release_stripped":
            return (
                result.decision == "release"
                and case.get("must_include", "") in answer
                and case.get("must_exclude", "") not in answer
            )
        case _ as unreachable:
            raise AssertionError(f"unhandled expect: {unreachable}")


def run_suite(path: Path | None = None) -> list[dict]:
    payload = json.loads((path or CASES_PATH).read_text(encoding="utf-8"))
    rows = []
    for case in payload["cases"]:
        result = run(case["prompt"], adapter=MockAdapter(case["draft"]))
        rows.append(
            {
                "id": case["id"],
                "class": case["class"],
                "expect": case["expect"],
                "decision": result.decision,
                "released_answer": result.released_answer,
                "pass": _ok(case, result),
                "user_visible": result.user_visible,
            }
        )
    return rows


def live_endpoint_reachable(base_url: str | None = None, timeout: float = 1.5) -> bool:
    load_dotenv()
    url = (base_url or os.environ.get("CSLM_BASE_LM_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
    try:
        urllib.request.urlopen(f"{url}/api/tags", timeout=timeout)
    except (urllib.error.URLError, TimeoutError, OSError):
        return False
    return True


def decision_histogram(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {key: 0 for key in DECISION_ORDER}
    for row in rows:
        decision = str(row.get("decision") or "unknown")
        counts[decision] = counts.get(decision, 0) + 1
    return counts


def _claim_summary(result: PipelineResult, limit: int = 4, clip: int = 80) -> str:
    claims = result.receipt.get("factual_support", {}).get("claims") or []
    if not claims:
        return "(no factual claims)"
    parts: list[str] = []
    for item in claims[:limit]:
        status = item.get("status") or "?"
        text = " ".join(str(item.get("text") or "").split())
        if len(text) > clip:
            text = text[: clip - 3] + "..."
        parts.append(f"{status}: {text}")
    extra = len(claims) - len(parts)
    summary = "; ".join(parts)
    if extra > 0:
        summary += f" (+{extra} more)"
    return summary


def _live_row(case: dict[str, Any], result: PipelineResult) -> dict[str, Any]:
    provenance = result.receipt.get("execution_provenance") or {}
    return {
        "id": case["id"],
        "class": case.get("class", ""),
        "source": case.get("source", "protocol"),
        "prompt": case["prompt"],
        "model_id": provenance.get("model_id") or "",
        "decision": result.decision,
        "released_answer": result.released_answer,
        "receipt_id": result.receipt.get("receipt_id") or "",
        "claim_summary": _claim_summary(result),
        "deterministic": False,
    }


def _load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload["cases"])


def run_live_suite(
    path: Path | None = None,
    *,
    adapter: BaseLMAdapter | None = None,
    extra_path: Path | None = None,
    include_extra: bool = True,
) -> dict[str, Any]:
    """Send protocol prompts through a live adapter. Never uses mock --draft text."""
    load_dotenv()
    live_adapter = adapter or select_adapter()
    cases: list[dict[str, Any]] = []
    for case in _load_cases(path or CASES_PATH):
        cases.append({**case, "source": "protocol"})
    extra = LIVE_EXTRA_PATH if extra_path is None else extra_path
    if include_extra and extra.is_file():
        for case in _load_cases(extra):
            cases.append({**case, "source": case.get("source", "live_extra")})

    rows = []
    total = len(cases)
    for index, case in enumerate(cases, start=1):
        sys.stderr.write(f"live [{index}/{total}] {case['id']}\n")
        sys.stderr.flush()
        result = run(case["prompt"], adapter=live_adapter)
        rows.append(_live_row(case, result))

    return {
        "mode": "live",
        "deterministic": False,
        "notes": LIVE_NOTES,
        "model_id": getattr(live_adapter, "model_id", ""),
        "histogram": decision_histogram(rows),
        "rows": rows,
    }


def print_histogram(histogram: dict[str, int], out: TextIO | None = None) -> None:
    handle = sys.stderr if out is None else out
    handle.write("decision histogram (live, non-deterministic):\n")
    for decision, count in histogram.items():
        handle.write(f"  {decision}: {count}\n")
    handle.flush()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Diamond Lens governance eval. "
            "The mock suite is CI law. --live is a governance observation, not science."
        )
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Send protocol prompts through the live adapter (no mock drafts). Not CI.",
    )
    parser.add_argument(
        "--no-extra",
        action="store_true",
        help="Skip the optional live extra set (smuggle / negation / invented citation).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.live:
        if not live_endpoint_reachable():
            sys.stderr.write(
                "live endpoint is down; start project Ollama with scripts/start-local-lm.sh "
                "(127.0.0.1:11435). Mock suite remains: python3 dlt_eval.py\n"
            )
            return 2
        report = run_live_suite(include_extra=not args.no_extra)
        json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        print_histogram(report["histogram"])
        return 0

    rows = run_suite()
    failed = [row for row in rows if not row["pass"]]
    json.dump({"passed": len(rows) - len(failed), "failed": len(failed), "rows": rows}, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
