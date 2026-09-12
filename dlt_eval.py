"""Run preregistered Diamond Lens governance cases through JCR."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from adapter import MockAdapter
from pipeline import run

CASES_PATH = Path(__file__).resolve().parent / "protocols" / "cases.json"


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


def main() -> int:
    rows = run_suite()
    failed = [row for row in rows if not row["pass"]]
    json.dump({"passed": len(rows) - len(failed), "failed": len(failed), "rows": rows}, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
