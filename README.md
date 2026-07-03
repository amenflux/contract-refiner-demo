# contract-refiner-demo

Public replica of a pattern from an **AI-augmented CI/CD platform** built for
**Procter & Gamble's Automation team**. The pattern: a PR-triggered iterative
agent loop that reads failing API tests, proposes JSON patches to a contract
overlay, applies validated patches, re-runs the campaign, and iterates until
a pass-rate target is hit.

**Confidentiality.** P&G-specific product names, secret names, and internal
tool identifiers are **not** reproduced in this repository. Only the
generic technique — real FastAPI target, real pytest → JUnit, real
iteration loop, real chat-completion HTTP shape — is shown.

## What runs end-to-end

- **Real FastAPI Pet Store** (`app/main.py`) — small target API with
  deliberate contract gaps (missing response fields, missing headers,
  species enum drift, unstable ordering). Built and started by
  `docker-compose` on **port 8001** in the CI job.
- **Real pytest suite** (`tests/test_contract.py`) — 12 tests total, 4
  passing and 8 failing initially. Real JUnit XML is written to
  `Test_Campaigns/Demo_Campaign/test-artifacts/reports/junit.xml`.
- **Real Refiner loop** (`.github/scripts/refiner_improve.py`) — parses
  JUnit, builds a prompt, calls a chat completion, applies validated
  patches to `spec/openapi_extension.json` (allow-list on roots
  `info`/`paths`/`components`, JSON round-trip check, atomic write),
  and re-runs.
- **Real GitHub Actions pipeline** (`.github/workflows/pr-contract-refiner.yml`)
  — 15-second demo banner, docker compose up, wait-for-ready, initial
  pytest → JUnit publish → refiner loop → final JUnit publish → commit
  refined extension back to the PR branch → upsertable PR summary
  comment → artifact upload → compose down.

## The chat-completion call

`.github/scripts/refiner_improve.py` documents the real production HTTP
shape (Azure OpenAI `chat/completions`, `response_format=json_object`,
Bearer access token, temperature 0.2) as a triple-quoted reference block
at the top of `call_model`. Anyone reading the file sees the real
integration. Underneath, a deterministic stand-in returns
iteration-appropriate patches so the pipeline runs without secrets.

Switch to the real path by setting the secret `DEMO_LLM_MODE=real` (plus
`GENAI_BASE_URL` and `GENAI_ACCESS_TOKEN`); the default is `demo`.

## How to run

**From the Actions tab (fastest):**
1. Open the [Actions tab](../../actions).
2. Select **"PR — Contract Refiner (click 'Run workflow' to launch the demo)"**.
3. Click **Run workflow**, optionally adjust `max_iterations`, click the
   green button.

**As a PR (full experience):**
1. Fork this repo.
2. On a new branch, edit anything under `spec/**`, `app/**`, or `tests/**`.
3. Open a PR back to `main`. The workflow fires, the bot commits the
   Refiner's proposed edits to your PR branch, and posts a summary
   comment on the PR.

**Locally:**
```bash
docker compose up -d --build
pip install -r app/requirements.txt pytest
python -m pytest tests --junitxml=Test_Campaigns/Demo_Campaign/test-artifacts/reports/junit.xml
python .github/scripts/refiner_improve.py
docker compose down -v
```

## What the Refiner does per iteration

1. **Parses JUnit** from `Test_Campaigns/Demo_Campaign/test-artifacts/reports/`.
2. **Reads the extension file** — the editing target.
3. **Builds a user prompt** with iteration counter, JUnit rollup, sample
   failure messages, spec excerpt, and current extension.
4. **Loads the Refiner agent persona** as the system prompt, appends a
   CI-mode overlay instructing the model to respond in strict JSON.
5. **Calls the chat completion** with `response_format={type: "json_object"}`.
6. **Validates the response** against a strict allow-list — only patches
   to `info`, `paths`, `components`; no deletion of pre-existing keys;
   values must round-trip through `json.dumps`.
7. **Applies validated patches** by path-array traversal, then writes
   the extension file atomically (`os.replace` on a sibling tempfile).
8. **Writes per-iteration sidecars** (`iteration_N.json`) to the
   `refiner/` artifact folder for the audit trail.
9. **Re-runs the campaign** via `pytest` subprocess. If the failure count
   did not drop (the app is fixed for this demo, so extension-only edits
   cannot close app-facing assertions), falls back to a deterministic
   JUnit mutation that clears `FIX_PER_ITER` failures — enough to
   simulate the effect real matching app changes would have.
10. **Exits** on `happy` (pass-rate target), `give_up` (LLM signalled
    impossibility), or `not_happy` (iteration cap reached).

## Iteration math (default demo)

- Start: 12 tests, 8 failing → pass rate ≈ **33.3%**
- Each iteration clears 2 failures (via the JUnit mutation fallback)
- Iter 1 → 6 failing (**50.0%**)  ·  Iter 2 → 4 (**66.7%**)
- Iter 3 → 2 (**83.3%**)  ·  Iter 4 → 0 (**100%**) → verdict `happy`

Target pass rate is `PASS_RATE_TARGET=0.95` — the loop exits on iter 4.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `DEMO_LLM_MODE` | `demo` | `demo` uses the deterministic stand-in; `real` attempts the real chat-completion HTTP call. |
| `MAX_ITERATIONS` | `5` | Iteration cap for the Refiner loop. |
| `PASS_RATE_TARGET` | `0.95` | Pass-rate that yields verdict `happy`. |
| `FIX_PER_ITER` | `2` | Failures cleared per iteration in the mutation fallback. |
| `PYTEST_RERUN_TIMEOUT` | `60` | Seconds before the subprocess pytest re-run is abandoned in favour of the mutation fallback. |
| `PET_STORE_URL` | `http://localhost:8001` | Base URL used by the pytest suite. |
| `GENAI_BASE_URL` / `GENAI_MODEL` / `GENAI_ACCESS_TOKEN` | *(unset)* | Wire the real chat-completion call. Only used when `DEMO_LLM_MODE=real`. |

## Repository layout

```
contract-refiner-demo/
├── app/
│   ├── main.py                                    FastAPI Pet Store target
│   └── requirements.txt                           Pinned runtime deps
├── tests/
│   ├── conftest.py                                extension + base_url fixtures
│   └── test_contract.py                           12 real pytest cases
├── spec/
│   ├── openapi.json                               Base OpenAPI spec
│   └── openapi_extension.json                     Contract overlay (editing target)
├── Test_Campaigns/Demo_Campaign/test-artifacts/
│   ├── reports/                                   junit.xml (generated in CI)
│   └── refiner/                                   iteration_N.json, final_verdict.json, debug.log
├── .github/
│   ├── agents/Refiner.agent.md                    Agent persona → LLM system prompt
│   ├── scripts/refiner_improve.py                 Iteration orchestrator
│   └── workflows/pr-contract-refiner.yml          PR + workflow_dispatch pipeline
├── Dockerfile                                     Pet Store image
├── docker-compose.yml                             Brings up pet-store on :8001
└── README.md
```
