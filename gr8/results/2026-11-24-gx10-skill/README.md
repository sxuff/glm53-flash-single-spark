# GR8 settings hill-climb on one GX10, 2026-11-24

A run of [0xSero](https://github.com/0xSero)'s
[inference-optimisation skill](https://github.com/sybil-solutions/inference-optimisation-skill) (commit `fda968e`)
on this recipe, on the same ASUS GX10 that produced the November 18 results. The skill's method ran as written
(ceilings first, one change per run, a control on both sides of every candidate, every run logged) and its benchmark
(`bench.py`: six fixed chat prompts, 512 tokens, greedy, thinking on, single stream) ran unchanged. Its numbers are not
comparable with the 40.7 tok/s of the recipe's own 400-token decode suite.

## Result: no faster setting on one box; the published memory settings no longer fit

**Decode.** Nothing beat the recipe. Fifteen completed runs; the ten greedy controls (the published turn-tail-on serve) gave 31.20–31.62 tok/s:

| Run | Change | c1 median | Verdict |
|---|---|---:|---|
| ctl ×10 | the recipe (CAP 262,144 or 131,072, see below) | 31.20–31.62 | baseline (±0.7%) |
| dhi4, dpar | `DRAFT_HEAD_I4=1`, `DRAFT_PAR=2` as knobs | 31.56, 31.58 | no-ops: GR8's launcher maps these only for GLM-5.3, not Flash (`scripts/engine_args.sh`: `engine_env` returns from `flash_env` before them) |
| dpare | `GR8_DRAFT_PAR=2` through `EXTRA_ENV` (reached the worker) | 31.71 | +0.5% over both neighbours, inside noise; not adopted |
| dhe | `GR8_DRAFT_HEAD_I4=1` through `EXTRA_ENV` (reached the worker) | 31.55 | no change: a lone session drafts with DFlash2, so the MTP head is rarely used |
| dflh | `GR8_DFL_HEAD_I4=1` through `EXTRA_ENV` | — | the engine refuses it at TP=1 (the INT4 copy expects a rank's slice of the head) |
| m2ks | `MTP=2` + `MTP_KSTOP=2` | — | does not boot with eight sessions: ~1 GiB more KDA state (`SESS × (MTP + 1)` slots of 153 MB) |
| rej-t07 | `--spec-accept rejection` at temperature 0.7 | — | the engine refuses it: "Flash serve supports no prefix reuse or rejection sampling" |

GR8 already does what the skill's speculative-decoding levers aim for: `--spec-adaptive` picks each round's draft
count (1–7) with the most expected tokens per millisecond, and the drafter choice switches to MTP rounds where they
commit more. CUDA graphs are captured per row count at boot. Against the recipe's own byte model (about 5.5 GB shared
per verify pass plus about 2.0 GB per extra row, so ~32 tok/s without drafting at the 244 GB/s measured on this box),
the published 40.7 tok/s sits at roughly 70–75% of the bandwidth bound. What is left is engine work (an INT4 DFlash2
head at TP=1, a distilled n-gram draft source), not settings.

**Memory.** The published `CAP=327680` with eight sessions did not boot once on this day. The box had 112.8–113.7 GiB
available at engine start (desktop, Docker and an agent running), and the boot needs about 113.5 GiB:

- `CAP=327680`: `7.70 GiB left after the weights and part of a KV pool of 327680 tokens; the rest of the boot needs 8.0`.
- `CAP=262144`: booted when 113.5–113.6 GiB was available and stopped at 7.98–7.99 GiB left when 113.3–113.4 GiB was.
- `CAP=131072` with `MAX_MODEL_LEN=131058`: booted every time the setting itself was accepted (13 of 13).
- Single-stream decode is the same at 262,144 and 131,072 (31.3–31.6 tok/s), so CAP only sets the longest request and
  the pool the sessions share. `SESS=4` frees about 1.2 GB instead (FLASH.md: 153 MB per KDA state slot at TP=1).

`serve.sh` now takes `CAP` and `SESS` from the environment (the defaults stay 327,680 and 8) and sets `MAX_MODEL_LEN`
when `CAP` is below 262,144; `smoke.py` checks the values it was given.

## Files

- [`PLAN.md`](PLAN.md): every queue, run, verdict and the ceilings, in order.
- [`ledger.jsonl`](ledger.jsonl): one line per completed run from the skill's `bench.py` (c1 per prompt, prefill
  at ~2.8K and ~21.5K tokens, startup, peak host memory).
- [`boot-failures.txt`](boot-failures.txt): the engine's own message for every run that did not boot.
- `tools/`: the run as it was done, with home shown as `~`. `glm-launch.sh` is this recipe's `docker run` plus one
  change, with fresh prompt and home volumes per run; it records the worker's real flags and `GR8_*` environment so a
  setting that was dropped shows up. `hostmem.sh` is the memory probe (host MemAvailable, trips on swap growth),
  `queue3.sh` runs the queue behind a lock and always restores the box's other service.
