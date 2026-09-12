# Jarvis Memoryboard for CSLM-Genesis

Continuity / provenance board adapted from Jarvis Memoryboard architecture.
**Not a trained CSLM. Not a substitute for the evidence library or JCR.**

## Concept map (Jarvis → CSLM)

| Jarvis | Meaning in source | CSLM module |
|--------|-------------------|-------------|
| **AMUL** | LTM *substrate*: append-only artifacts, lineage, verify/drift (Architect). RAG/LLM docs also expand A/M/U/L as Adaptive/Modular/Universal/Logical. | [`amul.py`](amul.py) |
| **EMR** | Excitation / Memory Recall — governed activation \(A = Q \cdot R \cdot P \cdot e^{-D \Delta t}\). **Excited ≠ Authorized.** Never invents LTM truth. | [`emr.py`](emr.py) |
| **STM** | Budgeted *working-set view* (session). Eviction ≠ forgetting. | [`stm.py`](stm.py) (+ session notes on [`board.py`](board.py)) |
| **LTM** | Continuity Ledger / durable SoT via Memoryboard access API | [`ltm.py`](ltm.py) |
| **Memoryboard** | Access layer over the stack | [`board.py`](board.py) `JarvisBoard` |

Source references used (architecture only, not vendored):

- `/media/jon/DEEA8E6FEA8E442D/Project-Infinity/services/jarvis-memoryboard/docs/CONSTITUTIONAL_MEMORY_CONTRACT.md`
- `/home/jon/dev/jarvis-memoryboard/` and `/home/jon/dev/persistence-memory/app/{amul,emr}.py`

## CSLM law overlays

1. Board memory is **continuity**, not factual support.
2. LTM / STM / EMR reads may inform session audit or context hints; **release still requires** independent lookup / compute / JCR.
3. **STM → LTM** promote is allowed only when `status == "released"` **and** `receipt_id` is set.
4. Direct LTM writes use the same rule.
5. EMR `excite()` does not mutate LTM bytes.

## Python usage

```python
from pathlib import Path
from memory import JarvisBoard, PromotionDenied

board = JarvisBoard(
    "sess-demo",
    ltm_path=Path("/tmp/cslm-ltm.jsonl"),
    amul_path=Path("/tmp/cslm-amul.jsonl"),
)

# Session working memory
stm = board.store("user asked about water", tier="stm", kind="task")

# After a real JCR release (receipt_id from pipeline/session):
released = board.ingest_released_claim(
    claim_text="Water is H2O.",
    receipt_id="cslm:deadbeef",
    turn=1,
)
ltm = board.promote_stm_to_ltm(released.memory_id)

# EMR activation (continuity only)
view = board.excite("water formula", theta_promote=0.05)
assert view.note.startswith("EMR activation")

# Draft STM cannot promote
try:
    board.promote_stm_to_ltm(stm.memory_id)
except PromotionDenied:
    pass
```

With `CSLMSession`:

```python
from adapter import MockAdapter
from memory import JarvisBoard
from session import CSLMSession

board = JarvisBoard("sess-1", ltm_path=..., amul_path=...)
session = CSLMSession("sess-1", MockAdapter("unused"), board=board)
result = session.turn("What is water?", draft="Water is H2O.")
# Released claims land in STM; call board.promote_stm_to_ltm(...) explicitly.
```

## Live data

Default paths under `memory/data/` are gitignored. Override with:

- `CSLM_LTM_PATH`
- `CSLM_AMUL_PATH`

## What this is not

- Not automatic evidence for claims
- Not a trained memory model
- Not a multi-tenant gateway / auth rewrite
- Not a dump of the Jarvis UI or full FastAPI service
