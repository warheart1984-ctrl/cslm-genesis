"""Independent arithmetic check. The model does not get to grade its own math."""

from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass
from typing import Literal

ComputeKind = Literal["supported", "contradicted", "unknown"]

_OPS: dict[type[ast.operator], object] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_WORDS = (
    (re.compile(r"\bdivided by\b", re.I), "/"),
    (re.compile(r"\bmultiplied by\b", re.I), "*"),
    (re.compile(r"\btimes\b", re.I), "*"),
    (re.compile(r"\bplus\b", re.I), "+"),
    (re.compile(r"\bminus\b", re.I), "-"),
)

_CLAIM = re.compile(
    r"^(?P<expr>.+?)\s*(?:=|equals|is)\s*(?P<result>-?\d+(?:\.\d+)?)\s*\.?\s*$",
    re.I,
)


@dataclass(frozen=True)
class ComputeOutcome:
    kind: ComputeKind
    source: str
    reason: str


def _rewrite_words(text: str) -> str:
    rewritten = text
    for pattern, symbol in _WORDS:
        rewritten = pattern.sub(symbol, rewritten)
    return rewritten


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_safe_eval(node.operand)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        op = _OPS[type(node.op)]
        return float(op(_safe_eval(node.left), _safe_eval(node.right)))  # type: ignore[operator]
    raise ValueError("unsupported expression")


def evaluate_expression(expr: str) -> float:
    tree = ast.parse(expr, mode="eval")
    return _safe_eval(tree)


def _close(left: float, right: float) -> bool:
    return abs(left - right) <= 1e-9 * max(1.0, abs(left), abs(right))


def check_compute(claim_text: str) -> ComputeOutcome | None:
    rewritten = _rewrite_words(claim_text.strip().rstrip("."))
    match = _CLAIM.match(rewritten)
    if match is None:
        return None
    expr = match.group("expr").strip()
    claimed = float(match.group("result"))
    if re.search(r"[a-zA-Z]", expr):
        return None
    try:
        actual = evaluate_expression(expr)
    except (ValueError, SyntaxError, ZeroDivisionError):
        return None
    source = f"compute:{expr.replace(' ', '')}->{actual:g}"
    if _close(actual, claimed):
        return ComputeOutcome(
            "supported",
            source,
            f"independent compute matched {expr} = {actual:g}",
        )
    return ComputeOutcome(
        "contradicted",
        source,
        f"independent compute contradicted the claim ({expr} = {actual:g}, draft said {claimed:g})",
    )
