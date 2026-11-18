#!/usr/bin/env python3
"""Run the two nonce-prefixed, one-output-token HTTP prefill probes used before the replay."""

import argparse
import json
import time
import urllib.request
import uuid
from pathlib import Path

from fixtures import DEFAULT_CACHE, sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="Server root, without /v1")
    parser.add_argument("--model", default="glm-5.3-flash")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--out", type=Path, required=True, help="New JSON file for the two probe results")
    args = parser.parse_args()
    if args.out.exists():
        parser.error(f"Output already exists: {args.out}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    _, _, source = sources(args.cache)
    results = []
    for _ in range(2):
        nonce = str(uuid.uuid4())
        prompt = f"[gMASK]<sop><|user|>{nonce}\n{source}\nSummarize.<|assistant|><think>"
        body = {"model": args.model, "prompt": prompt, "max_tokens": 1, "temperature": 0}
        request = urllib.request.Request(args.base.rstrip("/") + "/v1/completions", json.dumps(body).encode(),
                                         {"Content-Type": "application/json"})
        start = time.perf_counter()
        with urllib.request.urlopen(request, timeout=900) as response:
            result = json.load(response)
        elapsed = time.perf_counter() - start
        n = result["usage"]["prompt_tokens"]
        if not n or result["usage"]["completion_tokens"] != 1:
            raise RuntimeError(f"Unexpected probe usage: {result['usage']!r}")
        results.append({"n": n, "s": elapsed, "tok_s": n / elapsed, "nonce": nonce})
    with args.out.open("x", encoding="utf-8") as output:
        json.dump({"prefill": results}, output, indent=1)
    print(json.dumps(results), flush=True)


if __name__ == "__main__":
    main()
