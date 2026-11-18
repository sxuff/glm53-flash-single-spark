"""Summarize a directory containing the off and on results from compare.sh."""

import argparse
import json
import statistics
from pathlib import Path

LEVELS = (1, 2, 4, 8)


def arm(path):
    rows = json.loads((path / "turns.json").read_text(encoding="utf-8"))
    expected = {(n, s, t) for n in LEVELS for s in range(1, n + 1) for t in range(1, 7)}
    keys = {(r["level"], r["session"], r["turn"]) for r in rows}
    if keys != expected or len(rows) != len(expected):
        raise ValueError(f"Incomplete six-turn replay in {path}")
    levels = {}
    for n in LEVELS:
        group = [r for r in rows if r["level"] == n]
        if any(r.get("gpu_shared") or not r["finish_reason"] or not r["ttft_s"] for r in group):
            raise ValueError(f"Shared GPU or incomplete timing in {path}, concurrency {n}")
        prompt = sum(r["prompt_tokens"] for r in group)
        cached = sum(r["cached_tokens"] for r in group)
        generated = sum(r["completion_tokens"] for r in group)
        wall = max(r["end_s"] for r in group)
        levels[str(n)] = {
            "turns": len(group),
            "median_first_token_s": statistics.median(r["ttft_s"] for r in group),
            "cached_input_tokens": cached,
            "input_tokens": prompt,
            "cached_fraction": cached / prompt,
            "output_tokens": generated,
            "wall_s": wall,
            "aggregate_output_tok_s": generated / wall,
            "length_capped_turns": sum(r["finish_reason"] == "length" for r in group),
        }
    decode = [json.loads(line) for line in (path / "decode.jsonl").read_text(encoding="utf-8").splitlines()]
    categories = ("code", "math", "prose", "structured")
    if (len(decode) != 16 or any(r["completion_tokens"] != 400 for r in decode)
        or {(r["category"], r["repeat"]) for r in decode} != {(c,i) for c in categories for i in range(4)}):
        raise ValueError(f"Invalid matched400 results in {path}")
    speeds = {c: statistics.median(r["decode_tok_s"] for r in decode if r["repeat"] and r["category"] == c)
              for c in categories}
    probes = json.loads((path / "prefill.json").read_text(encoding="utf-8"))["prefill"]
    if len(probes) != 2 or any(not r["n"] or r["s"] <= 0 for r in probes):
        raise ValueError(f"Invalid prefill results in {path}")
    fixture_identity = {(r["level"],r["session"],r["turn"]):(r["file"],r["prompt_tokens"]) for r in rows}
    return {
        "levels": levels, "prefill_tok_s": [r["n"] / r["s"] for r in probes],
        "decode_by_prompt_tok_s": speeds, "decode_mean_of_medians_tok_s": statistics.mean(speeds.values()),
    }, fixture_identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    off, off_inputs = arm(args.results / "off")
    on, on_inputs = arm(args.results / "on")
    if off_inputs != on_inputs:
        raise ValueError("The two arms received different replay inputs")
    print(json.dumps({"off": off, "on": on}, indent=2))


if __name__ == "__main__":
    main()
