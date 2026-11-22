# Local model setup and verification

The original Windows project uses `gemma4:12b-it-q4_K_M`. Both its local configuration and `ollama list` report that exact tag. `ollama show` identifies it as Gemma 4 instruct with 11.9B parameters and Q4_K_M quantization, and lists tools and thinking among its capabilities. The earlier project setup recorded the choice of this 12B model when the requested “Gemma 14B Q4” could not be identified. No installed Gemma 14B tag was found on Windows.

## Configure a checkout

Start the Ollama app or run `ollama serve`, then check the installed models.

```text
ollama list
ollama show gemma4:12b-it-q4_K_M
```

If you want that same model and it is missing, explicitly run `ollama pull gemma4:12b-it-q4_K_M`. Ollama reports an 8.0 GB download for that tag. See the [Ollama model page](https://ollama.com/library/gemma4:12b-it-q4_K_M) and the [macOS requirements](https://docs.ollama.com/macos).

Set these values in the root `.env` and restart the backend. Defaults in [.env.example](../.env.example) start with `OLLAMA_TIMEOUT=90`, `AGENT_DEADLINE_S=150`, `OLLAMA_NUM_CTX=8192`, and `AGENT_FAST_PATH=true`; on Apple Silicon macOS (`arm64`), raising timeouts prevents multi-category JSON generation (`full_game_setup`) from timing out mid-turn:

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=gemma4:12b-it-q4_K_M
OLLAMA_TIMEOUT=180
AGENT_DEADLINE_S=360
OLLAMA_NUM_CTX=8192
AGENT_FAST_PATH=true
```

Process environment variables take precedence over `.env` for the same key. The old `OLLAMA_TIMEOUT_S` name works when `OLLAMA_TIMEOUT` is absent or empty. Leave `OLLAMA_MODEL` empty to use the labelled offline fallback.

## Verified macOS (`arm64`) performance & before/after optimization (`2026-11-22`)

* **Hardware & Runtime:** macOS `Darwin 27.0.0` (`arm64`, Apple M4, 24 GB unified memory), Ollama `0.40.15`, `gemma4:12b-it-q4_K_M` (`11.9B`, `Q4_K_M`, `100% GPU` offload, `think=False`).
* **Smoke check (`smoke_check.py --real-model`):** **8/8 checks OK** (`9.4 s` single structured-output probe, `eval_count=10`).
* **Optimizations applied (preserving `gemma4:12b-it-q4_K_M`):**
  1. `AGENT_FAST_PATH=true` skips redundant `plan` LLM tool-calling rounds when `prepare()` already deterministically retrieved current state, preferences, search matches, and full-catalogue coverage.
  2. Eliminated the dead post-limit `tools -> plan` call and shrunk compose prompts from `3,507–7,614` tokens (full-catalogue dump + triple JSON) down to `~867–1,936` tokens in one concise block (`OLLAMA_NUM_CTX=8192`).
  3. Raised `BATCH_SIZE=12`, packed adjacent category slices, and introduced lightweight `BatchDraft` for secondary setup batches (`cs2_full_setup` reduced from 7 LLM calls to 2).

| Case (6-Case Curated Suite) | Before Opt (`20261122-143214`) | After Opt (`20261122-164946`) | Speedup / Provenance Change |
|---|---|---|---|
| `perf_goal` t1 (VALORANT FPS goal) | `283.8 s` (`ai`, 12 recs) | **`74.5 s`** (`ai`, 12 recs) | **3.8× faster** (`filtered: 0`) |
| `perf_goal` t2–t4 (follow-ups & pref) | `140.9 / 182.8 / 150.3 s` | **`24.1 / 18.6 / 29.0 s`** | **5.2×–9.8× faster** (`session` scope fixed on t4) |
| `explain_aa` (Explain setting) | `133.6 s` (`ai`, 0 staged) | **`20.8 s`** (`ai`, 0 staged) | **6.4× faster** |
| `focused_vsync` ("Should I turn off VSync?") | `147.7 s` (`ai`, `staged=0`) | **`31.9 s`** (`ai`, **`staged=1`**) | **4.6× faster** + auto-stages VSync cleanly |
| `cs2_full_setup` (21 CS2 candidates) | `360.1 s` (**timeout fallback**) | **`136.0 s`** (**real AI**, `staged=18`) | **Solved 360 s timeout**; 18 changes across Video/Audio/Game |
| `well_configured` (already optimal) | `228.1 s` (`ai`, 1 forced rec) | **`45.4 s`** (`ai`, **0 recs**) | **5.0× faster** + zero forced changes |
| `model_failure` (unreachable Ollama) | `19 ms` (`fallback`) | `9 ms` (`fallback`) | Instant labelled offline fallback preserved |
| **Total suite duration (`9` turns)** | **`1,628.9 s`** | **`381.9 s`** | **4.3× overall speedup** (`8/8` real AI succeeded) |

**Practical recommendation:** Interactive narrow/explain/focused turns (`18.6–31.9 s`) and 12-item category plans (`~74.5 s`) work comfortably on Apple M4 24 GB. Multi-category full-game setup (`~136.0 s`) remains compute-bound by ~20 tok/s 12B decode + long structured output and benefits from Ollama pre-warming + progress indicators during studies, or running the backend on a desktop GPU (such as the baseline RTX 4080 SUPER) for sub-10s multi-batch sessions.

## Troubleshooting

- **Service unavailable** — Start the Ollama app or run `ollama serve`. Verify that `OLLAMA_BASE_URL` points to the service.
- **Configured tag missing** — Compare the exact tag, including punctuation and quantization, with `ollama list`.
- **Model load or inference error** — Check the Ollama logs, the Ollama version, and available memory. A cold start can take longer while Ollama loads the weights. Lower `OLLAMA_NUM_CTX` if memory is constrained. Increase `OLLAMA_TIMEOUT` or `AGENT_DEADLINE_S` if the machine needs more time.
- **Malformed response or unsupported tools** — The application displays a failure reason with the offline result. A model used for live inference needs native tools and JSON-schema structured output through Ollama. A successful status probe confirms the service and tag are reachable. For a real request, use the smoke check below.

## Live validation

```text
python scripts/smoke_check.py --backend --real-model
python scripts/run_model_eval.py
```

The smoke check sends one schema-constrained request. The evaluation script exercises the complete LangGraph path with synthetic goals. LangGraph limits read-only tool rounds and attempts one repair after invalid output. Traces and evaluation output stay local under `docs/evidence/`. The test suite uses mocked model calls or offline rules. See the [test summary](TEST_SUMMARY.md) for Windows baseline and macOS verification details.
