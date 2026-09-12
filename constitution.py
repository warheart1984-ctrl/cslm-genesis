"""Load the checked-in constitution and its version hash."""

from __future__ import annotations

from pathlib import Path

from canonical import sha256_hex

CONSTITUTION_ID = "cslm-genesis.constitution.v0"
CONSTITUTION_VERSION = "0.0.1"
CONSTITUTION_PATH = Path(__file__).resolve().parent / "CONSTITUTION.md"

JCR_AUTHORITY = "cslm-genesis.jcr.v0"

RULE_NO_CLAIM_WITHOUT_SUPPORT = "no_factual_claim_without_support_or_uncertainty"
RULE_NO_RELEASE_WITHOUT_DECISION = "no_release_without_governance_decision"
APPLICABLE_RULES = (
    RULE_NO_CLAIM_WITHOUT_SUPPORT,
    RULE_NO_RELEASE_WITHOUT_DECISION,
)


def constitution_text() -> str:
    return CONSTITUTION_PATH.read_text(encoding="utf-8")


def constitution_version_hash() -> str:
    return "sha256:" + sha256_hex(constitution_text())
