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

Replay: same prompt + draft → same decision class (`organism_binding.replay.input_digest`).

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

Lineage (not proof): [`provenance/LINEAGE.md`](provenance/LINEAGE.md). Constraints: [`constraints/dlt.md`](constraints/dlt.md).

## Limits (read these)

- The evidence library is a small checked-in file, not the web
- A `[source: …]` tag the model invents is **not** support
- Protocol hypotheses are not established physical facts
- There is no token-level causality claim and no trained evidence head
- Fine-tune later, and only after this gate catches real failures. Keep an **independent** verifier outside the model.
