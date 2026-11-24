#!/usr/bin/env python3
"""Check the actual GR8 engine arguments, its tail switch, and a short API reply."""
import argparse
import json
import os
from pathlib import PurePosixPath
import subprocess
import time
from urllib import error, request


def effective_arg(argv, flag):
    for idx in range(len(argv) - 2, -1, -1):
        if argv[idx] == flag:
            return argv[idx + 1]
    return None


def engine_settings(container, mode):
    listing = subprocess.check_output(["docker", "top", container, "-eo", "pid,args"], text=True)
    workers = []
    for line in listing.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 2 and PurePosixPath(fields[1]).name == "g6m4_flash-int4":
            workers.append(fields[0])
    if not workers:
        return None  # The HTTP catalog can come up well before the GPU worker.
    if len(workers) != 1:
        raise RuntimeError(f"Expected one GR8 Flash INT4 worker in {container}, found {len(workers)}")
    pid = workers[0]
    prefix = ["docker", "exec", container]
    argv = subprocess.check_output(prefix + ["cat", f"/proc/{pid}/cmdline"]).decode().rstrip("\0").split("\0")
    expected_flags = {
        # serve.sh's CAP and SESS overrides (README.md, "If the boot runs out of memory")
        "--cap": os.environ.get("CAP", "327680"), "--s2-sessions": os.environ.get("SESS", "8"), "--pf-lanes": "1",
        "--prefill": "2048", "--kv-format": "int4", "--mtp": "1",
    }
    flags = {flag: effective_arg(argv, flag) for flag in (*expected_flags, "--kv-store")}
    for flag, expected in expected_flags.items():
        if flags[flag] != expected:
            raise RuntimeError(f"Expected {flag} {expected}, got {flags[flag]!r}")
    manifest = effective_arg(argv, "--v2-widths") or ""
    draft = effective_arg(argv, "--dflash-manifest") or ""
    if not manifest.endswith("/901ad084f0afd2400820504910d3e684133ce183/manifests/exlr8-manifest-bit201.json"):
        raise RuntimeError(f"Unexpected target manifest: {manifest}")
    if "--spec-adaptive" not in argv or not draft.endswith("/bf582e4eacc1810f76656d1811693ff6c6737d2a/tp1/dflash.r0.manifest.json"):
        raise RuntimeError(f"Expected the pinned adaptive DFlash2 drafter, got {draft}")
    kv = set((flags["--kv-store"] or "").split(","))
    if not {"ssd:/var/lib/gr8/prompts", "size=4G", "persist=on", "spare_ram_cache=on", "spare_ram_floor=2G"} <= kv:
        raise RuntimeError(f"Unexpected KV store: {flags['--kv-store']!r}")
    read_tail = r"""test -r "$1" || exit 1; tr '\000' '\n' < "$1" | grep '^GLMTAIL=' || true"""
    tail = subprocess.check_output(prefix + ["sh", "-c", read_tail, "sh", f"/proc/{pid}/environ"]).strip()
    if tail != (b"GLMTAIL=1" if mode == "on" else b"GLMTAIL=0"):
        raise RuntimeError(f"Worker has {tail!r}, expected turn-tail {mode}")
    return {"turn_tail": mode, **flags}


def smoke(args):
    url = f"http://127.0.0.1:{args.port}/v1/chat/completions"
    chat = {
        "model": "glm-5.3-flash",
        "messages": [{"role": "user", "content": "What is 2 plus 2? Reply with only the digit."}],
        "temperature": 0,
        "max_tokens": 1024,
    }
    req = request.Request(url, data=json.dumps(chat).encode(), headers={"Content-Type": "application/json"})
    deadline = time.monotonic() + args.wait
    while True:
        report = engine_settings(args.container, args.mode)
        if report is not None:
            if args.engine_only:
                break
            try:
                with request.urlopen(req, timeout=120) as r:
                    answer = json.load(r)["choices"][0]["message"]["content"]
            except error.HTTPError as exc:
                if exc.code not in (502, 503, 504):
                    raise
            except error.URLError as exc:
                if not isinstance(exc.reason, ConnectionRefusedError):
                    raise
            else:
                if not isinstance(answer, str) or answer.strip().rstrip(".") != "4":
                    raise RuntimeError(f"Unexpected visible reply: {answer!r}")
                report["chat_reply"] = answer.strip()
                break
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Timed out waiting for a ready worker in {args.container}; check docker logs {args.container}")
        time.sleep(3)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["on", "off"])
    parser.add_argument("--container", default=os.environ.get("CONTAINER", "sxuff-glm53f-tail"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    parser.add_argument("--wait", type=int, default=1800, help="seconds to wait for a ready inference worker")
    parser.add_argument("--engine-only", action="store_true", help="inspect the running worker without sending a request")
    try:
        smoke(parser.parse_args())
    except (RuntimeError, subprocess.CalledProcessError, error.URLError) as exc:
        parser.exit(1, f"Smoke check failed: {exc}\n")
