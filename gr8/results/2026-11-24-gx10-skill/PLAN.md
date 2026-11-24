# GLM-5.3-Flash (GR8, EXLR8 bit201) on GX10: inference-optimisation skill run (2026-11-24)

Skill: sybil-solutions/inference-optimisation-skill @ fda968e (0xSero). Harness: the skill's bench.py, unchanged.
Targets: c1 decode (primary), prefill 4K/32K, startup. cN skipped (the recipe's own replay covers 1-8 sessions).
Constraints: lossless only (draft-side changes; the target decides every token); boot needs 108 GiB MemAvailable;
watchdog trips under 1.5 GiB available or on swap growth. Decode panel at temperature 0, thinking on (GLM default).
Baseline: github sxuff/glm53-flash-single-spark 915b084, gr8/ (turn-tail on): the exact `docker run` of
glm53f-gr8.service (gr8-tail:2, SESS=8, CAP=327680, --pf-lanes 1 --prefill 2048, GLMTAIL=1, INT4 KV, adaptive
DFlash2 + MTP 1), fresh prompt/home volumes per arm, port 18100.
Prior work (~/v2/glm-gr8/sweep.log, Nov 2026; do not rerun without a new reason): MTP=2 (40.2), MTP=3 (39.7),
DFLASH_SEL=0 (39.7), DSEL_MODEL=1 (39.3) vs base 39.3 (single runs, recipe m400 panel); prefill 1024 vs 2048;
SESS 4 vs 8; MTP_KSTOPB with MTP 2/3 (agent replay only); turn-tail on/off; quality 49/50 GSM8K, 20/20 HumanEval.
Not tried before: DRAFT_HEAD_I4, DRAFT_PAR, solo MTP_KSTOP, SPEC_LEVELS, DFLASH_K (all defaults at TP=4, unset at TP=1).

## Ceilings (THEORY)
45 layers (3 dense), 288 routed experts top-8 + 1 shared, hidden 4096, vocab 154,880, 1 MTP layer.
Routed experts 73.2 GiB (~2.01 bits) -> 8/288 = ~2.0 GiB/token; dense 6.5 GiB. Recipe's measured byte model
(TensorFold notes): ~5.5 GB shared per verify pass + ~2.0 GB per extra row -> ~32 tok/s without drafting at 244 GB/s.
Drafting: DFlash2 body ~1.2 GB/round + MTP step (draft lm_head 154,880 x 4096: ~1.27 GB at BF16, ~0.36 GB INT4 g32).
Published 40.7 tok/s (mean of 4 medians) ~ 70-75% of the bandwidth bound at the observed tokens/step.
DRAFT_HEAD_I4 saves ~0.9 GB per draft step (~5% of a step's bytes) -> first lever.

## Queue 1: ctl-a dhi4 ctl-b dpar ctl-c m2ks ctl-d
- First attempt (16:16): every arm died at boot. Debug boot (logs/debug-boot.container.txt): MemAvailable 112.3 GiB
  at start; "7.70 GiB left after the weights and part of a KV pool of 327680 tokens; the rest of the boot needs 8.0".
  The published CAP=327680 no longer fits this box's current memory (0.3 GiB short; Hermes 1.7 GiB, slab 0.9 GiB).
  All arms, controls included, now run CAP=262144 (one full 262,144-token request still fits). Queue restarted.
- Queue 1 (CAP 262144): ctl-a 31.34, ctl-b 31.58 (startup 52 s, prefill ~865 @2.8K / ~985 @21.5K). Every other arm died
  at boot on the memory edge: boots that started with 113.5-113.6 GiB free passed, 113.3-113.4 failed (7.98-7.99 GiB left,
  8.0 needed). m2ks (MTP=2 + MTP_KSTOP=2): 7.02 GiB left -> MTP=2 costs ~1 GiB more at boot (KDA slots: SESS x (MTP+1)
  x 153 MB at TP=1, docs/FLASH.md).
- Finding: GR8's launcher maps DRAFT_HEAD_I4 / DRAFT_PAR / MTP_KSTOP only for GLM-5.3 (engine_args.sh: engine_env ->
  flash_env returns before them); for Flash they are silently ignored (dhi4-c128 = control to the hundredth). The Flash
  binary does read the GR8_* variables, so queue 3 passed them through EXTRA_ENV.
- Queue 2 (CAP 131072, MAX_MODEL_LEN 131058): ctl-e 31.54, dhi4 (no-op) 31.56, ctl-f 31.59, dpar (no-op) 31.58,
  ctl-g 31.21, m2ks BOOT FAIL (7.60 GiB left at 131K: needs CAP ~40K with SESS=8 -> REJECTED, does not fit), ctl-h 31.62.
  CAP does not change single-stream decode (31.3-31.6 at 262K and 131K).
- Queue 3 (EXTRA_ENV, CAP 131072): ctl-i 31.51; dflh GR8_DFL_HEAD_I4=1: REJECTED, engine refuses at TP=1 ("G.lm_head.mx.gv
  is not this rank's [vn/16][192][528] MXFP8 slice"); ctl-j 31.54; dpare GR8_DRAFT_PAR=2 (reached the worker): 31.71,
  +0.5% over both neighbours, all 6 prompts +0.4-0.9%: INSIDE NOISE (controls 31.20-31.62), not adopted without a repeat;
  ctl-k 31.55; dhe GR8_DRAFT_HEAD_I4=1 (reached the worker): 31.55 = control, REJECTED (a lone session drafts with
  DFlash2; the MTP head is rarely on the path); ctl-l 31.20.
- Queue 4 (temp 0.7): ctl-t07 31.64; rej-t07 --spec-accept rejection: REJECTED, engine refuses ("Flash serve supports no
  prefix reuse or rejection sampling"). Rest of the queue stopped (nothing left to compare). Inkling restored 17:18,
  verified answering at 17:19.

## STATUS (plateau: no lever left at TP=1 that the Flash engine accepts and that moves decode)
Best = recipe as published. c1 31.5 tok/s on the skill panel (thinking on), startup 52 s, prefill ~840 / ~935 tok/s.
Already in place: CUDA graphs per row count, cost-aware adaptive draft count (spec_len.h: the most expected tokens per
ms each round, levels 1..7) and the DFlash2/MTP drafter choice (GR8_S2_DSEL): the built-in form of Hy4's p-min win.
Limits: ~70-75% of the bandwidth bound; the INT4 head / parallel-draft / rejection paths are TP>1-only or unsupported
on Flash; memory: the box no longer has room for the published CAP=327680 with SESS=8.
Operational finding (worth a recipe note): on this GX10 today (112.8-113.7 GiB available at boot) CAP=327680 never boots
and CAP=262144 boots about half the time; CAP=131072 (MAX_MODEL_LEN=131058) or SESS=4 (~1.2 GB fewer KDA slots) boot reliably.
Remaining levers (ranked): SESS=4 + CAP 327680 for single-user use (memory, not speed); DFlash2 head INT4 at TP=1 (engine
code); n-gram draft source (GR8_NGRAM, needs a distilled table).
