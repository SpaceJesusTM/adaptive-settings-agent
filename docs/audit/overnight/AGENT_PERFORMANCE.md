# Local reasoning and performance

All timing in this report comes from the development Mac, an Apple M4 with 24 GB of unified memory. The installed Ollama 0.40.17 served **gemma4:12b-it-q4_K_M** with local identifier **6114515d63c1**. Comparisons use temperature 0.2, 8192 context, thinking disabled, a 150-second turn deadline and a 90-second configured Ollama request timeout on the continuation runner. Local comparisons ran sequentially. Repetitions within a run may reuse the model and cached prefixes and the two separate run series share no randomized order. The simulator's mock NVIDIA setting-availability profile is independent of the machine running inference.

| Mode and paired evidence | Wall time on M4 | Model attempts and reported tokens | Quality and generalization |
| --- | --- | --- | --- |
| First audit composition, 12 live turns | 68.8 s median, 150.2 s peak including fallback | 11 recorded successful calls. 23,088 prompt and 5,906 output tokens. One timed-out turn is absent from these call and token totals. | 39/45 frozen checks. A2 8/8 in all three runs. B2 7/8 in all three. One mixed turn used fallback. Ambient Occlusion link in one of three. |
| Compact pilot, 12 live turns | 22.3 s median, 113.1 s peak | 13 measured calls, including one repair. 12,327 prompt and 3,161 output tokens. | 40/45. A2 7/8 once and 8/8 twice. B2 retained its 7/8 and visibility aids. One mixed turn omitted the setup proposal. All three simple Ambient Occlusion responses linked the setting. |
| Overnight legacy on four broader probes | 46.2 s median | 4 calls, 7,202 prompt and 1,742 output tokens. | 9/10. Passed the split change, explanation and memory turn, the actual visibility trade-off, and the exact comparison. Missed the implicit visual ask. |
| Final optional intent pass on two implicit visual requests, two repetitions each | 48.4 s median, 59.8 s peak | 8 calls, 8,102 prompt and 1,339 output tokens. Median provider prefill and generation per call were 8.35 s and 15.34 s. | Staged eligible options in 4/4 turns, with no protected change. Legacy staged none in its single run of each prompt. Broader workflow and other-game evidence remain limited. |

Compact selection reuses the deterministic coverage audit, removes unnecessary tools and avoids asking the model to repeat IDs, candidate rationales and full values in its JSON. This makes the path cheaper even when generation is already fast. Ordinals can still be missing, a worthwhile option can be omitted, and the broad candidate window can leave some cases unreviewed. The plan labels that finite window and still uses the existing validation path. Empty or incomplete selection and repair costs are part of the measured trade-off. The equivalent B2 run had a repair at 113.1 seconds, which argues against using compact as the default before the talk.

## What the clock measured

| Metric | First audit | Compact pilot |
| --- | ---: | ---: |
| Median reported wall per model call | 61.5 s | 20.9 s |
| Median provider prompt evaluation | unavailable | 0.50 s |
| Median provider generation | 57.5 s | 14.9 s |
| Median provider load | 1 ms | 1 ms |
| First call provider load | 9.83 s | 9.12 s |
| Median generation rate over reported calls | 8.5 tokens/s | 13.4 tokens/s |
| Recorded workflow and model-requested tool lookups | 33 | 12 |
| Median wall outside measured model invocations | unavailable from frozen phase records | 68 ms |

The compact sequence includes reused prompt prefixes. Very high warm-prefill ratios are descriptive of those calls and unsuitable as uncached device throughput. The report retains both token counts and durations per call. Generation duration dominates most baseline turns on this Mac. Latency around the model includes orchestration, SQLite, response serialization and completion, while prompt evaluation and generation use Ollama's fields. Phase **prepare** includes the interpretation time when that stage is used, so the two should not be added. Streaming was not enabled for these structured calls, so time to first token is unavailable. Cancellations and timeout attempts remain in the new trace even when the provider does not return token counts. [Ollama chat timing fields](https://docs.ollama.com/api/chat)

## Progress and inference budgets

Catalogue-backed literal requests and several explanation pairs run before inference. The contrastive example completed in about 4 ms in the isolated API replay. The default graph retains usable completed batches if a subsequent call exhausts the remaining turn allowance. The controlled test times out a second call and stages two checked options from the first batch with a partial-coverage notice. The first call failing still invokes the normal labelled fallback. The test covers a delayed model stand-in, not a forced timeout on the real GPU. Partial proposals still go through current-state checks and explicit Apply. [Timeout and concurrent edit tests](../../../backend/tests/test_overnight.py)

## Reproduce on the RTX 4080 SUPER

The target desktop has an RTX 4080 SUPER and 16 GB of dedicated VRAM. Generation speed, prompt evaluation, cold load and model residency are hardware- and runtime-sensitive. The measured call count, output budgets, catalogue behavior, and proposal checks are architectural evidence. Faster inference could make an extra reasoning stage or conservative repair practical. It would not fix a semantic misclassification or a missing selection. No desktop was accessed and no desktop throughput or latency is assumed.

Use the same installed digest, backend dependencies and recorded configuration. Run one series at a time and record Ollama version, driver, context, model residency from **ollama ps**, warm or cold start, and any other activity. Preserve both quality and runtime rows. The runner uses fresh temporary SQLite for every case and ignores checkout environment files. The commands are PowerShell from the overnight checkout after setting up the repository Python environment.

```powershell
$env:OLLAMA_MODEL = "gemma4:12b-it-q4_K_M"
$env:OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:OLLAMA_TEMPERATURE = "0.2"
$env:OLLAMA_NUM_CTX = "8192"
$env:OLLAMA_THINK = "false"
$env:AGENT_DEADLINE_S = "150"
$env:AGENT_FAST_PATH = "true"
$env:AGENT_MAX_TOOL_ROUNDS = "2"
$env:OLLAMA_TIMEOUT = "90"
$env:AGENT_DISCOVERY_POLICY = "current"
$env:AGENT_REASONING_MODE = "legacy"
python scripts/run_overnight_benchmark.py --repo . --mode local --machine-label RTX-4080-SUPER-16GB --cases live_a2 live_b2 frozen_mixed frozen_explain_ao --repeat 3 --out data/local/desktop-legacy.json
$env:AGENT_REASONING_MODE = "compact"
python scripts/run_overnight_benchmark.py --repo . --mode local --machine-label RTX-4080-SUPER-16GB --cases live_a2 live_b2 frozen_mixed frozen_explain_ao --repeat 3 --out data/local/desktop-compact.json
$env:AGENT_REASONING_MODE = "semantic"
python scripts/run_overnight_benchmark.py --repo . --mode local --machine-label RTX-4080-SUPER-16GB --cases current_visual distant_textures --repeat 3 --out data/local/desktop-semantic.json
```

For exact historic comparisons pass the first audit checkout to the frozen runner and use **4a614b4** for the measured compact pilot. The overnight report identifies later semantic revisions per run. Change the model only after completing the matched comparison. The model choice remains configurable via **OLLAMA_MODEL**.
