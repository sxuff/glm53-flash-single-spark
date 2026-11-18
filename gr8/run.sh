#!/usr/bin/env bash
# Build if needed, start the selected profile and wait for one verified chat.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
mode="${1:-on}"
[[ $# -le 1 ]] || { echo "Expected at most one argument" >&2; exit 2; }
case "$mode" in
  --stop) exec bash serve.sh stop ;;
  --help|-h) echo "Usage: bash run.sh [on|off|--stop]"; exit 0 ;;
  on|off) ;;
  *) echo "Usage: bash run.sh [on|off|--stop]" >&2; exit 2 ;;
esac
export IMAGE="${IMAGE:-sxuff/glm53f-gr8-tail:2}"
container="${CONTAINER:-sxuff-glm53f-tail}"
port="${PORT:-8000}"
docker info >/dev/null
if docker inspect --type container "$container" >/dev/null 2>&1; then
  owner=$(docker inspect --type container --format '{{index .Config.Labels "io.github.sxuff.glm-turn-tail"}}' "$container")
  running=$(docker inspect --type container --format '{{.State.Running}}' "$container")
  current=$(docker inspect --type container --format '{{.Image}}' "$container")
  expected=$(docker image inspect --format '{{.Id}}' "$IMAGE")
  if [[ "$owner" != 1 || "$running" != true || "$current" != "$expected" ]]; then
    echo "The container named $container already exists with a different owner, state or image." >&2
    exit 1
  fi
  if ! docker inspect --type container --format '{{range .Config.Env}}{{println .}}{{end}}' "$container" | grep -Fx "PORT=$port" >/dev/null; then
    echo "The running recipe has a different HTTP port." >&2
    exit 1
  fi
else
  docker image inspect "$IMAGE" >/dev/null 2>&1 || bash build.sh
  bash serve.sh "$mode"
fi
exec python3 smoke.py "$mode" --container "$container" --port "$port"
