# Reproduce the turn-tail comparison

The replay sends scripted six-turn code-review conversations to an already running GLM server. It varies concurrency across 1, 2, 4 and 8 sessions. Each arm sends 90 measured chat requests in total. Use the hardware settings, cache state and run order in the recipe's results section for the published comparison.

## Prepare the inputs

Python 3.9 or later is sufficient. Run this from the recipe root before timing. It downloads the public input files once, verifies their hashes and caches them locally. Subsequent runs use the same files offline.

```sh
python3 bench/fixtures.py
```

The fixtures contain the measured NVIDIA Flare repository guidance, 90 consecutive 5,200-character excerpts from Pillow 12.3.0, and the Rust sources for the prefill probe. The paths in the chat prompts deliberately include the original environment's relative `.venv` path. The files are used as prompt text. Their locations, immutable upstream revisions and SHA-256 digests are in [fixtures.lock.json](fixtures.lock.json). Each script accepts `--cache DIRECTORY` to override the default fixture cache.

## Measure an arm

Start the intended engine with a fresh benchmark prompt-cache volume. Choose a new local output directory for each arm.

```sh
results=results/my-tail-on-run
endpoint=http://127.0.0.1:8000
mkdir -p "$results"
python3 bench/prefill.py --base "$endpoint" --out "$results/prefill.json"
python3 bench/replay.py --base "$endpoint" --out "$results/turns.json"
python3 bench/decode.py --base "$endpoint" --out "$results/decode.jsonl"
```

The prefill probe begins each request with a fresh UUID and generates a single token. It reports input tokens per second using elapsed HTTP time. Then the replay sends one shared-system-prompt warm-up, starts each concurrency level from a common clock, and waits five seconds after each level. `ALL_DONE 90` confirms that all 90 measured turns completed. For a six-turn smoke run, pass `--levels 1` and choose a different output file and cache state from the measured run.

Run the fixed 400-token decode suite last. For each of the four prompts it sends one warm-up and three measured completions. The reported decode rate is 399 divided by elapsed seconds from the first to the last text-bearing streamed chunk. The suite takes the median for each prompt, then reports the arithmetic mean of those four medians. In total each full arm sends 2 prefill requests, 1 chat warm-up, 90 scripted turns and 16 decode requests.

Every chat request sends temperature zero, a per-turn seed, tool schemas, and a 256-token reply limit. To keep the prompts equivalent between arms, subsequent turns insert a fixed assistant acknowledgment. The replay measures serving performance. Tool execution and answer quality require separate tests.

## Interpret the measurements

* Median time to first token uses `ttft_s`, from sending a request to the first nonempty streamed delta other than a role. This can include reasoning or a tool call.
* Cache reuse at one concurrency level is the sum of `cached_tokens` divided by the sum of `prompt_tokens` across that level.
* Wall time at one level is the latest `end_s`, measured from the common start time. Aggregate output tok/s is the sum of `completion_tokens` divided by that wall time.
* Each row records the finish reason, so changes in output length and replies that reached the token cap can be reported alongside timing.

The request format and timing definitions come from [sxuff's pinned agent benchmark](https://github.com/sxuff/qwen38-flash-next-flare/blob/d37c2628e06e10848e8c4ad2c6bdc86988bdca80/bench/agents_bench.py). Its MIT notice is in [LICENSE](LICENSE). Sources fetched by the fixture loader retain their upstream licenses. [NVIDIA Flare source](https://github.com/NVIDIA/flare-local-inference/tree/ca1f960edbf67d624f2d2948d2c111e8a6c8eb3c) · [Pillow source](https://github.com/python-pillow/Pillow/tree/bb1d8e8ab8d29048624d96e3ee53cecf7c13d13d)
