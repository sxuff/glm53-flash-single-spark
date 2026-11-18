"""Retrieve the public source files used as inert benchmark inputs and verify their hashes."""

import argparse
import hashlib
import json
import os
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

LOCK = json.loads(Path(__file__).with_name("fixtures.lock.json").read_text(encoding="utf-8"))
DEFAULT_CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "glm-gr8-replay"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def obtain(record, repo, commit, upstream_path, cache):
    checksum = record["sha256"]
    dest = cache / checksum
    if dest.is_file():
        content = dest.read_bytes()
        if digest(content) == checksum:
            return content.decode("utf-8")
    url = f"https://raw.githubusercontent.com/{repo}/{commit}/{upstream_path}"
    with urllib.request.urlopen(url, timeout=90) as response:
        content = response.read()
    if digest(content) != checksum:
        raise ValueError(f"SHA-256 mismatch for {url}")
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=cache, delete=False) as tmp:
        tmp.write(content)
    tmp_path = Path(tmp.name)
    try:
        os.replace(tmp_path, dest)
    finally:
        tmp_path.unlink(missing_ok=True)
    return content.decode("utf-8")


def sources(cache):
    pillow, flare = LOCK["pillow"], LOCK["flare"]
    jobs = []
    for entry in pillow["files"]:
        jobs.append((entry, pillow["repo"], pillow["commit"], "src/PIL/" + Path(entry["path"]).name, cache))
    for entry in [flare["guidance"], *flare["prefill"]]:
        jobs.append((entry, flare["repo"], flare["commit"], entry["path"], cache))
    with ThreadPoolExecutor(max_workers=6) as pool:
        pending = {job[0]["path"]: pool.submit(obtain, *job) for job in jobs}
        texts = {name: result.result() for name, result in pending.items()}
    width = LOCK["chunk_chars"]
    chunks = []
    for entry in pillow["files"]:
        name = entry["path"]
        source = texts[name]
        for i in range(0, len(source) - width + 1, width):
            chunks.append((name, source[i:i + width]))
    chunks = chunks[:LOCK["n_chunks"]]
    packed = json.dumps(chunks, separators=(",", ":"), ensure_ascii=True).encode()
    prefill = "".join(texts[entry["path"]] for entry in flare["prefill"])
    if digest(packed) != LOCK["chunks_sha256"] or digest(prefill.encode()) != LOCK["prefill_sha256"]:
        raise ValueError("Assembled replay inputs differ from the measured GX10 inputs.")
    return texts[flare["guidance"]["path"]], chunks, prefill


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    guidance, chunks, prefill = sources(parser.parse_args().cache)
    print(f"Verified {len(chunks)} review turns, {len(guidance)} guidance characters, "
          f"and {len(prefill)} cold-prefill characters.")
