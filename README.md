# CSLM-Genesis

A **language organ**: a base LM may draft, but nothing is a released answer until the Judicial Control Record (JCR) decides.

This is a **production-mode prototype**, not a trained CSLM. The weights are interchangeable. CSLM-Genesis owns the release path.

**Mind** is a project metaphor only. It does not claim consciousness or reliable introspection.

## Constitution (v0)

Checked in as [`CONSTITUTION.md`](CONSTITUTION.md):

1. No factual claim without identified support or explicit uncertainty.
2. No released response without a recorded governance decision.

The receipt stores `constitution_id` plus `constitution_version_hash` (SHA-256 of that file).

## What this is not

- Not training a foundation model from scratch
- Not a claim that every token has faithful causal justification
- Not treating model-written explanations or invented citations as evidence
- Not “audit after release” — JCR can `block` / `revise` / emit `uncertainty_statement` **before** any user-visible answer

Constitutional AI put rules into training. This wedge is **enforceable contracts + evidence records + replay**.

## Pipeline

```
User prompt
  → Base LM draft (local Ollama by default, or a mock `--draft`)
  → Claim extract (asserted facts only)
  → Support check (stub allowlist; no citation → unsupported)
  → JCR decision (release | revise | block | uncertainty_statement)
  → Receipt emit (three buckets)
  → Only then return a payload
```

### Three record kinds (never conflate)

1. **Factual support** — sources or explicit uncertainty for claims
2. **Governance compliance** — constitution version, rules, JCR decision + reasons
3. **Execution provenance** — model id/version, config, timestamps, ids

`organism_binding` maps this organ onto the existing organism / VOSS shape (organ → intent → decision → effect → evidence → replay → continuity). It is a binding, not a fourth evidence kind.

## Success metric

**Unsupported factual claims never leave as a released answer.**

Demo:

```bash
python3 cli.py "What is the population of Atlantis?" \
  --draft "The lost city of Atlantis has a resident population of 12,403."

python3 cli.py "What is the chemical formula of water?" \
  --draft "Water's chemical formula is H2O. [source: stub:chemistry-allowlist]"
```

First call must not `release` (expect `uncertainty_statement` + receipt). Second may `release` with a receipt.

Replay: same prompt + draft → same decision class (`organism_binding.replay.input_digest`). Receipts are appended to `receipts/log.jsonl` with the library hash. Re-check a stored id without calling Ollama:

```bash
python3 cli.py replay cslm:<hex>
```

Optional ledger export:

- `CSLM_LEDGER_EXPORT_LOG=/abs/path/to/ledger.jsonl` mirrors each emitted receipt as a ledger-friendly NDJSON event
- `CSLM_LEDGER_SESSION_EXPORT_DIR=/abs/path/to/session-bundles` writes the latest full session bundle on each session save
- `python3 cli.py export-receipt cslm:<hex>` prints a single receipt export event
- `python3 cli.py export-session <session_id>` prints a full session export bundle

## Run

```bash
python3 -m pytest
python3 http_app.py   # POST /v0/complete  (binds 0.0.0.0:$PORT, default 8080)
```

## Local base LM (Ollama)

This box has 4 GB VRAM and a full system disk. Use a **3B** model and keep weights on the 4TB drive.

```bash
chmod +x scripts/start-local-lm.sh
./scripts/start-local-lm.sh
python3 cli.py "What is the chemical formula of water?"
```

Defaults (also in `.env`):

- `CSLM_ADAPTER=openai_compat`
- `CSLM_BASE_LM_BASE_URL=http://127.0.0.1:11435` (project-local; system Ollama already owns 11434)
- `CSLM_BASE_LM_MODEL=llama3.2:3b`
- `OLLAMA_MODELS=/media/jon/DEEA8E6FEA8E442D/ollama-models`

`--draft` still bypasses Ollama for the deterministic gate tests.

## How a claim becomes supported

The verifier never trusts the model. It runs tools, then JCR reads the tool result:

1. **Compute** — arithmetic in the claim is evaluated with a safe expression checker
2. **Lookup** — the claim is checked against [`evidence/library.json`](evidence/library.json), a store the model cannot write
3. Otherwise **unsupported** (a model-written `[source: …]` is still not evidence)

Supported means “we looked it up or computed it,” not “the draft sounded sure.”

## Diamond Lens protocols

Preregistered cases in [`protocols/cases.json`](protocols/cases.json) watch governance, not the base LM. Established mechanisms may `release`. Phase 6, Faraday–KTHNY membership, a universal deception penalty, and physical Phase-9 closure may not leave as facts.

```bash
python3 dlt_eval.py
```

That mock suite is the CI law. It uses the checked-in `--draft` strings and expected decisions. Do not replace those expected outcomes with live model text.

### Live Ollama governance eval

```bash
./scripts/start-local-lm.sh
python3 dlt_eval.py --live
# equivalent: python3 cli.py eval --live
# protocol prompts only (skip smuggle / negation / invented-citation extras):
python3 dlt_eval.py --live --no-extra
```

`--live` sends the protocol **prompts** (and an optional extra set in [`protocols/live_extra.json`](protocols/live_extra.json)) through llama3.2:3b. It does **not** feed mock drafts. Each row records prompt, model_id, decision, released_answer, receipt_id, and a short claim summary, then prints a decision histogram. Live drafts are marked **non-deterministic**. Receipts still append to the existing store.

These runs are **governance observations** of JCR on whatever the 3B actually drafts. They are **not** Faraday or DLT science results, not a pass-rate, and not a reason to rewrite `expect` in `cases.json`. CI (`python3 -m pytest` / `python3 dlt_eval.py`) must not require Ollama.

Lineage (not proof): [`provenance/LINEAGE.md`](provenance/LINEAGE.md). Constraints: [`constraints/dlt.md`](constraints/dlt.md).

## Limits (read these)

- The evidence library is a small checked-in file, not the web
- A `[source: …]` tag the model invents is **not** support
- Protocol hypotheses are not established physical facts
- `dlt_eval.py --live` is a JCR observation of live drafts, not Faraday/DLT evidence
- There is no token-level causality claim and no trained evidence head
- Fine-tune later, and only after this gate catches real failures. Keep an **independent** verifier outside the model.
