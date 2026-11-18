"""Replay the four fixed 400-token completion prompts recorded with the GLM recipe."""

import argparse
import json
import statistics
import time
import urllib.request
from pathlib import Path


def run_one(endpoint, model, case):
    body = {
        "model": model, "prompt": case["prompt"], "max_tokens": 400, "min_tokens": 400,
        "ignore_eos": True, "temperature": 0, "top_p": 1, "seed": case["seed"],
        "presence_penalty": 0, "frequency_penalty": 0, "stream": True,
        "stream_options": {"include_usage": True},
    }
    request = urllib.request.Request(endpoint, json.dumps(body).encode(), {"Content-Type": "application/json"})
    start = time.perf_counter()
    first = last = None
    usage = {}
    with urllib.request.urlopen(request, timeout=600) as response:
        for raw_line in response:
            line = raw_line.decode().strip()
            if not line.startswith("data:") or line[5:].strip() == "[DONE]":
                continue
            event = json.loads(line[5:])
            usage = event.get("usage") or usage
            choices = event.get("choices") or []
            if choices and choices[0].get("text"):
                now = time.perf_counter()
                if first is None:
                    first = now
                last = now
    if usage.get("completion_tokens") != 400 or first is None or last <= first:
        raise RuntimeError("Expected 400 output tokens and at least two timed text chunks.")
    return {"completion_tokens": 400, "ttft_s": first - start, "decode_tok_s": 399 / (last - first)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="Server root URL")
    parser.add_argument("--model", default="glm-5.3-flash")
    parser.add_argument("--out", required=True, type=Path, help="New per-call JSONL file")
    args = parser.parse_args()
    endpoint = args.base.rstrip("/") + "/v1/completions"
    cases = json.loads(Path(__file__).with_name("decode-prompts.json").read_text(encoding="utf-8"))
    medians = {}
    with args.out.open("x", encoding="utf-8") as output:
        for case in cases:
            speeds = []
            for repeat in range(4):
                result = run_one(endpoint, args.model, case)
                row = {"category": case["category"], "repeat": repeat, "warmup": repeat == 0, **result}
                output.write(json.dumps(row) + "\n")
                output.flush()
                if repeat:
                    speeds.append(result["decode_tok_s"])
            medians[case["category"]] = statistics.median(speeds)
    print(json.dumps({"per_prompt_median": medians, "mean_of_medians": statistics.mean(medians.values())}, indent=2))


if __name__ == "__main__":
    main()
