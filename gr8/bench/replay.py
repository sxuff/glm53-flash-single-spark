#!/usr/bin/env python3
"""Replay the GLM six-turn code-review workload against an OpenAI-compatible endpoint."""

import argparse
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fixtures import DEFAULT_CACHE, sources

SYSTEM_PREFIX = ("You are a careful coding agent reviewing the Flare inference server for correctness bugs. "
                 "The user shows you one source file at a time. After each file, list anything suspicious "
                 "with the line it is on, say how confident you are, and name the file you want to read next. "
                 "Use the tools when you need more context. Keep answers short and concrete.\n\n"
                 "# Repository guidance (AGENTS.md)\n\n")
TOOL_SPECS = [
    ("read_file", "Read a file from the repository.", {"path": {"type": "string"}}),
    ("search", "Search the repository with a regular expression.", {"pattern": {"type": "string"}}),
    ("edit_file", "Replace text in a file.",
     {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}),
    ("run_command", "Run a shell command in the repository.", {"command": {"type": "string"}}),
]
TOOLS = [{"type": "function", "function": {"name": name, "description": description, "parameters":
          {"type": "object", "properties": props, "required": list(props)}}}
         for name, description, props in TOOL_SPECS]
TURNS = 6


def post_stream(base, model, messages, seed):
    body = {
        "model": model, "messages": messages, "tools": TOOLS, "max_tokens": 256, "seed": seed,
        "stream": True, "stream_options": {"include_usage": True, "continuous_usage_stats": True},
        "temperature": 0,
    }
    req = urllib.request.Request(base + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    start = time.monotonic()
    first = last = first_count = finish = None
    usage = {}
    max_gap = 0.0
    with urllib.request.urlopen(req, timeout=900) as resp:
        for raw in resp:
            line = raw.decode().strip()
            if not line.startswith("data:") or line[5:].strip() == "[DONE]":
                continue
            event = json.loads(line[5:])
            if event.get("error"):
                raise RuntimeError(f"Server reported {event['error']}")
            now = time.monotonic()
            usage = event.get("usage") or usage
            for choice in event.get("choices") or []:
                finish = choice.get("finish_reason") or finish
                delta = choice.get("delta") or {}
                if any(value for key, value in delta.items() if key != "role"):
                    if first is None:
                        first, first_count = now, usage.get("completion_tokens")
                    else:
                        max_gap = max(max_gap, now - last)
                    last = now
    end = time.monotonic()
    count = usage.get("completion_tokens")
    prompt = usage.get("prompt_tokens")
    if not count or not prompt or first is None or not finish:
        raise RuntimeError(f"Incomplete streaming result: usage={usage!r}, finish={finish!r}")
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
    if cached is None:
        raise RuntimeError("Server omitted prompt_tokens_details.cached_tokens")
    if first_count is None:
        first_count = 1
    return {
        "t0": start, "end": end, "ttft_s": first - start, "latency_s": end - start,
        "decode_tps": (count - first_count) / (last - first) if last > first else None,
        "prompt_tokens": prompt, "cached_tokens": cached, "completion_tokens": count,
        "finish_reason": finish, "max_gap_s": max_gap,
    }


def session(base, model, system, level, sid, chunks, start_at):
    msgs = [{"role": "system", "content": system}]
    rows = []
    while time.monotonic() < start_at:
        time.sleep(0.0005)
    for turn, (path, code) in enumerate(chunks, 1):
        intro = f"Review session L{level}-R1-S{sid}. " if turn == 1 else ""
        msgs.append({"role": "user", "content": f"{intro}Contents of {path}:\n```\n{code}\n```"})
        row = post_stream(base, model, msgs, seed=1000 * level + 100 + 10 * sid + turn)
        msgs.append({"role": "assistant", "content": "Noted. Show me the next file."})
        row["start_s"] = row.pop("t0") - start_at
        row["end_s"] = row.pop("end") - start_at
        row["new_prompt_tokens"] = row["prompt_tokens"] - row["cached_tokens"]
        row.update(level=level, rep=1, session=sid, turn=turn, file=path)
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="http://127.0.0.1:8000", help="Server root, without /v1")
    ap.add_argument("--model", default="glm-5.3-flash")
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--levels", nargs="+", type=int, default=[1, 2, 4, 8], choices=[1, 2, 4, 8])
    ap.add_argument("--out", required=True, type=Path, help="New JSON file for the completed run")
    args = ap.parse_args()
    if args.out.exists():
        ap.error(f"Output already exists: {args.out}")
    if len(args.levels) != len(set(args.levels)):
        ap.error("Each concurrency level may appear once per run")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    base = args.base.rstrip("/")
    guidance, chunks, _ = sources(args.cache)
    system = SYSTEM_PREFIX + guidance
    warm = post_stream(base, args.model, [{"role": "system", "content": system},
                      {"role": "user", "content": "Ready?"}], seed=1)
    print("warmup", {k: warm[k] for k in ("prompt_tokens", "cached_tokens", "latency_s")}, flush=True)
    next_chunk = 0
    all_rows = []
    for level in args.levels:
        start_at = time.monotonic() + 0.5
        with ThreadPoolExecutor(max_workers=level) as pool:
            futures = []
            for sid in range(1, level + 1):
                prompts = chunks[next_chunk:next_chunk + TURNS]
                next_chunk += TURNS
                futures.append(pool.submit(session, base, args.model, system, level, sid, prompts, start_at))
            rows = [row for future in futures for row in future.result()]
        if len(rows) != TURNS * level:
            raise RuntimeError(f"Expected {TURNS * level} complete turns, received {len(rows)}")
        wall = max(row["end_s"] for row in rows)
        throughput = sum(row["completion_tokens"] for row in rows) / wall
        print(f"rep 1 level {level}: {len(rows)} turns, wall {wall:.1f}s, output {throughput:.1f} tok/s",
              flush=True)
        all_rows.extend(sorted(rows, key=lambda row: row["end_s"]))
        time.sleep(5)
    with args.out.open("x", encoding="utf-8") as output:
        json.dump(all_rows, output, indent=1)
    print(f"ALL_DONE {len(all_rows)}", flush=True)


if __name__ == "__main__":
    main()
