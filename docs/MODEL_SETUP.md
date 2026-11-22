# Local model setup and verification

The original Windows project uses `gemma4:12b-it-q4_K_M`. Both its local configuration and `ollama list` report that exact tag. `ollama show` identifies it as Gemma 4 instruct with 11.9B parameters and Q4_K_M quantization, and lists tools and thinking among its capabilities. The earlier project setup recorded the choice of this 12B model when the requested “Gemma 14B Q4” could not be identified. No installed Gemma 14B tag was found on Windows.

## Configure a checkout

Start the Ollama app or run `ollama serve`, then check the installed models.

```text
ollama list
ollama show gemma4:12b-it-q4_K_M
```

If you want that same model and it is missing, explicitly run `ollama pull gemma4:12b-it-q4_K_M`. Ollama reports an 8.0 GB download for that tag. See the [Ollama model page](https://ollama.com/library/gemma4:12b-it-q4_K_M) and the [macOS requirements](https://docs.ollama.com/macos).

Set these values in the root `.env` and restart the backend. Defaults in [.env.example](../.env.example) start with `OLLAMA_TIMEOUT=90` and `AGENT_DEADLINE_S=150`; on Apple Silicon macOS (`arm64`), raising timeouts prevents multi-category JSON generation from timing out mid-turn:

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=gemma4:12b-it-q4_K_M
OLLAMA_TIMEOUT=180
AGENT_DEADLINE_S=360
```

Process environment variables take precedence over `.env` for the same key. The old `OLLAMA_TIMEOUT_S` name works when `OLLAMA_TIMEOUT` is absent or empty. Leave `OLLAMA_MODEL` empty to use the labelled offline fallback.

## Verified macOS (`arm64`) observations (`2026-11-22`)

- **Model & Ollama:** Verified on macOS `Darwin 27.0.0` (`arm64`) with Ollama `0.40.15` and `gemma4:12b-it-q4_K_M` (`11.9B`, `Q4_K_M`).
- **Observed latency & deadline behavior:** The single structured-output smoke probe completes in `10.3 s`, while full LangGraph chat turns (read-only tool calls + candidate-filtered JSON compose) take `~133–284 s` (median `150.3 s`) on local Apple Silicon hardware. Multi-batch full-game setup generation (`cs2_full_setup`) hit the `360 s` `AGENT_DEADLINE_S` boundary and cleanly fell back to the labelled rule-based recommender (`21` categorized CS2 items, `valuesUnchanged = True`).
- **macOS Playwright browser channel:** If Playwright's downloaded Chromium is absent locally while Google Chrome is installed, run browser tests with `PW_CHANNEL=chrome` (`PW_CHANNEL=chrome npm --prefix frontend run e2e`).

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

The smoke check sends one schema-constrained request. The evaluation script exercises the complete LangGraph path with synthetic goals. LangGraph limits read-only tool rounds and attempts one repair after invalid output. Traces and evaluation output stay local under `docs/evidence/`. The test suite uses mocked model calls or offline rules. See the [original Windows research test summary](TEST_SUMMARY.md) for the earlier evaluation and its limitations.
