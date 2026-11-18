# GLM-5.3 Flash turn-tail comparison on one GX10

Measured November 18, 2026 on one ASUS Ascent GX10 (NVIDIA GB10, 128 GB unified memory). Both runs used the same local image and a fresh 4G persistent SSD prompt-cache volume. The engine worker reported `GLMTAIL=0` in the first run and `GLMTAIL=1` in the second.

## Scripted six-turn code review

| Simultaneous sessions | Turns | Median first token, off → on | Cached input, off → on | Time for all turns, off → on | Aggregate output, off → on |
|---:|---:|---:|---:|---:|---:|
| 1 | 6 | 3.46 → 2.17 s | 72.7% → 84.6% | 41.8 → 42.5 s | 19.2 → 22.6 tok/s |
| 2 | 12 | 4.04 → 2.74 s | 74.3% → 84.9% | 77.2 → 68.6 s | 20.6 → 25.6 tok/s |
| 4 | 24 | 4.92 → 3.45 s | 74.8% → 85.0% | 125.9 → 108.9 s | 23.0 → 28.0 tok/s |
| 8 | 48 | 6.88 → 5.74 s | 75.5% → 74.5% | 249.4 → 268.8 s | 32.4 → 32.2 tok/s |

Cache reuse is the fraction of all prompt tokens reported as cached, weighted by prompt length. Time to first token is measured to the first nonempty streamed field other than the role, which can be reasoning or a tool call. Wall time runs from the shared release of the sessions to the end of the last turn. Aggregate output includes waits and prefill.

## Two cold-prefill probes and single-stream decode

| Probe | Tail off | Tail on |
|---|---:|---:|
| ~33K input, probe 1 | 950 tok/s | 953 tok/s |
| ~33K input, probe 2 | 960 tok/s | 935 tok/s |
| Code decode | 33.88 tok/s | 33.70 tok/s |
| Math decode | 37.21 tok/s | 37.73 tok/s |
| Prose decode | 29.14 tok/s | 28.36 tok/s |
| Structured decode | 63.09 tok/s | 63.05 tok/s |
| **Decode mean of four medians** | **40.83 tok/s** | **40.71 tok/s** |

Prefill is prompt tokens divided by HTTP wall time with one output token. Each probe starts with a fresh UUID. The decode suite forces 400 tokens on each of four raw prompts. After one warm-up per prompt, the table uses the median of three measurements of (400 − 1) / (time of last text chunk − time of first text chunk).

## Conditions and scope

- Ubuntu 24.04.4 LTS, kernel 6.17.0-1026-nvidia, NVIDIA driver 580.159.03, Docker 29.2.1, aarch64.
- Same model, model-cache volume, image, quant, drafter, eight slots, one prefill lane, 2,048-row prefill, INT4 KV, capacity setting 327,680 and 4G SSD tier in both arms. Each arm started a new process with fresh prompt and runtime volumes.
- One off/on pair, fixed order. Each arm ran two prefill probes, one shared-prefix warm-up, the 1/2/4/8-session replay and then the fixed-length decode suite. All 90 measured replay turns per arm completed. Prompt file paths and token counts matched across arms. The original runner monitored GPU processes during replay.
- Each scripted session has six turns. The harness supplies fixed assistant history, uses greedy sampling and caps replies at 256 tokens. It times serving behavior. Code-review accuracy and free-running tool execution need a separate evaluation.
- Across the 48-turn eight-session replay the off arm generated 8,081 tokens and the on arm generated 8,661. Respectively 27 and 28 replies reached the token cap. A single replay per arm does not estimate run-to-run variance.
- At eight sessions, every opening turn reused 4,096 tokens with the patch off and zero with it on. The median first token for those eight opening turns was 10.04 s off and 49.91 s on. Later turns usually recovered substantial cache reuse. This level followed the 1/2/4-session levels on the same prompt store. The timing receipts do not identify which checkpoint was evicted or replaced.

[Summary JSON](summary.json) · [Off-arm turns](off/turns.json) · [On-arm turns](on/turns.json) · [Off worker settings](off/worker-verified.json) · [On worker settings](on/worker-verified.json)

Each arm also includes its prefill probes, individual decode timings, replay log, and exact launch settings. The decode receipts store a SHA-256 of each generated output. Run `python3 bench/summarize.py results/2026-11-18-gx10` from the recipe root to recompute the summary.
