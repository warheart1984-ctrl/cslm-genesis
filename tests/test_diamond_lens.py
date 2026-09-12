"""Diamond Lens governance: established mechanisms may leave; overclaims may not."""

from __future__ import annotations

from dlt_eval import run_suite


def test_diamond_lens_governance_suite() -> None:
    rows = run_suite()
    failed = [row["id"] for row in rows if not row["pass"]]
    assert failed == [], f"governance failures: {failed}"
