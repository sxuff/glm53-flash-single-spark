#!/usr/bin/env bash
# Reproduce the off/on comparison on an idle single GB10.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out="${1:-$PWD/glm-4g-$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -- "$out"
out="$(cd "$out" && pwd)"
port="${PORT:-18100}"
tag="glm-paired-$(date -u +%s)-$$"
label="io.github.sxuff.glm-paired=$tag"
container="$tag"
cd "$root"

cleanup() {
  local cid vol
  cid="$(docker ps -aq --filter "name=^/${container}$" --filter "label=io.github.sxuff.glm-turn-tail=1")"
  if [[ -n "$cid" ]]; then
    docker stop -t 30 "$cid" >/dev/null
    for _ in {1..50}; do
      docker inspect --type container "$cid" >/dev/null 2>&1 || break
      sleep 0.2
    done
  fi
  while IFS= read -r vol; do
    if [[ -n "$vol" ]]; then docker volume rm "$vol" >/dev/null; fi
  done < <(docker volume ls -q --filter "label=$label")
}

if docker inspect --type container "$container" >/dev/null 2>&1; then
  echo "Choose another run time; container name already in use: $container" >&2
  exit 1
fi
python3 bench/fixtures.py
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
for mode in off on; do
  dir="$out/$mode"
  mkdir "$dir"
  weight_cache="${MODEL_VOLUME:-glm53f-cache}"
  prompts="$tag-$mode-prompts"
  runtime="$tag-$mode-home"
  for volume in "$prompts" "$runtime"; do
    if docker volume inspect "$volume" >/dev/null 2>&1; then
      echo "Scratch volume already exists: $volume" >&2
      exit 1
    fi
    docker volume create --label "$label" "$volume" >/dev/null
  done
  CONTAINER="$container" PORT="$port" MODEL_VOLUME="$weight_cache" PROMPT_VOLUME="$prompts" RUN_VOLUME="$runtime" bash serve.sh "$mode"
  # The HTTP model catalog can respond while the GPU worker is still loading.
  deadline=$((SECONDS + 3600))
  until docker logs "$container" 2>&1 | grep -F 'serving: http' >/dev/null; do
    if [[ "$(docker inspect --format '{{.State.Running}}' "$container" 2>/dev/null || true)" != true || $SECONDS -ge $deadline ]]; then
      echo "Engine did not become ready; inspect $dir/startup.log" >&2
      docker logs "$container" >"$dir/startup.log" 2>&1 || true
      exit 1
    fi
    sleep 3
  done
  python3 smoke.py "$mode" --container "$container" --port "$port" --engine-only >"$dir/settings.json"
  endpoint="http://127.0.0.1:$port"
  python3 bench/prefill.py --base "$endpoint" --out "$dir/prefill.json"
  python3 bench/replay.py --base "$endpoint" --out "$dir/turns.json"
  python3 bench/decode.py --base "$endpoint" --out "$dir/decode.jsonl" | tee "$dir/decode-summary.json"
  cleanup
  if [[ "$mode" == off ]]; then
    # The next boot uses the same pre-launch headroom as the first.
    deadline=$((SECONDS + 310))
    until awk '/^MemAvailable:/ {exit !($2 >= 108*1024*1024)}' /proc/meminfo; do
      if (( SECONDS >= deadline )); then echo "Waiting for 108 GiB of available memory timed out." >&2; exit 1; fi
      sleep 3
    done
  fi
done
printf 'Both arms completed. Measurements are in %s\n' "$out"
