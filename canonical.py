"""Canonical JSON + digests. Same byte rules as organism_receipt.v1."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    if value is None or isinstance(value, (str, int, float, bool)):
        return json_dumps_scalar(value)
    if isinstance(value, list):
        return "[" + ",".join(canonical_json(item) for item in value) + "]"
    return (
        "{"
        + ",".join(
            f"{json_dumps_scalar(str(key))}:{canonical_json(value[key])}"
            for key in sorted(value.keys(), key=str)
        )
        + "}"
    )


def json_dumps_scalar(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def digest_of(value: Any) -> str:
    return "sha256:" + sha256_hex(canonical_json(value))
