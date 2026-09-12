# Receipt store

Append-only JSONL log of issued receipts. The adapter never writes here; the pipeline appends after JCR.

## Files

- `log.jsonl` — live append-only log (gitignored; it grows)
- This README — schema and replay notes

Override the log path with `CSLM_RECEIPTS_LOG`.

## Line schema

Each line is one complete receipt (`cslm.receipt.v0`). Replay needs:

- `organism_binding.replay.prompt`
- `organism_binding.replay.draft`
- `organism_binding.replay.decision_class`
- `organism_binding.replay.library_hash` (`store_id` + `evidence/library.json` content)
- `constitution_version_hash`

`execution_provenance.library_hash` and `organism_binding.continuity.library_hash` carry the same library binding.

## Rules

- Append only. Never rewrite or delete a past line.
- Live Ollama drafts are not marked `deterministic`. Replay mocks the **stored** draft and does not call the model.
- Model-written justifications stay out of the factual bucket.

## Replay

```bash
python3 cli.py replay cslm:<hex>
python3 replay.py cslm:<hex>
```

Same stored `decision_class` is a pass.
