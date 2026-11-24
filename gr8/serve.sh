#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mode="${1:-on}"
container="${CONTAINER:-sxuff-glm53f-tail}"
image="${IMAGE:-sxuff/glm53f-gr8-tail:2}"
port="${PORT:-8000}"
owner=io.github.sxuff.glm-turn-tail
if [[ "$#" -gt 1 || ( "$mode" != on && "$mode" != off && "$mode" != stop ) ]]; then
  echo "Usage: bash serve.sh [on|off|stop]" >&2
  exit 2
fi
if [[ "$mode" == stop ]]; then
  if [[ "$(docker inspect --type container --format "{{index .Config.Labels \"$owner\"}}" "$container")" != 1 ]]; then
    echo "Container $container does not have this recipe's label." >&2
    exit 1
  fi
  exec docker stop -t 30 "$container"
fi
if docker inspect --type container "$container" >/dev/null 2>&1; then
  echo "Container $container already exists. Stop the running recipe with: bash serve.sh stop" >&2
  exit 1
fi
if ! docker image inspect "$image" >/dev/null; then
  echo "Build the patched image with bash build.sh, or set IMAGE to its local tag." >&2
  exit 1
fi
if [[ ! "$port" =~ ^[0-9]{1,5}$ ]] || (( 10#$port < 1 || 10#$port > 65535 )); then
  echo "PORT must be an integer from 1 through 65535." >&2
  exit 2
fi
if [[ -n "$(ss -H -ltn "sport = :$port")" ]]; then
  echo "PORT=$port already has a listener. Stop that service or choose an unused PORT." >&2
  exit 1
fi
if [[ "$(uname -m)" != aarch64 ]] || ! nvidia-smi --query-gpu=name --format=csv,noheader | grep -qi 'GB10'; then
  echo "This recipe requires a Linux aarch64 GB10 host." >&2
  exit 1
fi
avail_kib="$(awk '$1 == "MemAvailable:" {print $2}' /proc/meminfo)"
if (( avail_kib < 108 * 1024 * 1024 )); then
  echo "The measured launcher requires 108 GiB MemAvailable before boot. Available: $((avail_kib / 1024 / 1024)) GiB." >&2
  exit 1
fi

model_cache="${MODEL_VOLUME:-glm53f-cache}"
# The engine persists aligned checkpoints. Give each mode separate storage so
# switching profiles never accidentally imports the other profile's cache.
prompt_cache="${PROMPT_VOLUME:-sxuff-glm53f-prompts-$mode}"
home_volume="${RUN_VOLUME:-sxuff-glm53f-home-$mode}"
tail_flag=0
if [[ "$mode" == on ]]; then tail_flag=1; fi
# CAP and SESS default to the measured settings. When the boot stops at "... GiB left after the weights and part of
# a KV pool ...; the rest of the boot needs 8.0", lower one of them: CAP=131072 (the KV pool the sessions share; the
# longest request follows it) or SESS=4 (four session slots, about 1.2 GB less). See README.md, "If the boot runs out
# of memory".
cap="${CAP:-327680}"
sess="${SESS:-8}"
if [[ ! "$cap" =~ ^[0-9]+$ || ! "$sess" =~ ^[1-8]$ ]]; then
  echo "CAP must be a whole number of tokens and SESS 1 through 8." >&2
  exit 2
fi
# The image serves requests up to 262,144 tokens and refuses a CAP below that unless MAX_MODEL_LEN fits it:
# CAP less DFlash2's 14 guard rows (the image's knobs.sh, TUNE=context).
len_env=()
if (( 10#$cap < 262144 )); then len_env=(-e "MAX_MODEL_LEN=$((10#$cap - 14))"); fi
docker run --detach --rm --name "$container" --label "$owner=1" \
  --gpus all --network host --pid host --ulimit memlock=-1 --ulimit core=0 \
  --cap-drop ALL --cap-add IPC_LOCK --security-opt no-new-privileges \
  --read-only --tmpfs /tmp:size=1g,mode=1777 --init --oom-score-adj 1000 \
  -e "PORT=$port" -e "CAP=$cap" -e "SESS=$sess" "${len_env[@]}" -e 'EXTRA_ARGS=--pf-lanes 1 --prefill 2048' \
  -e "EXTRA_ENV=GLMTAIL=$tail_flag" \
  -v "$model_cache:/var/lib/gr8/cache" -v "$prompt_cache:/var/lib/gr8/prompts" \
  -v "$home_volume:/var/lib/gr8/home" -v "$here/kv-store.yaml:/etc/gr8/kv-store.yaml:ro" "$image"
printf 'Starting %s with turn-tail %s. Follow the first download and boot with docker logs -f %q\n' "$container" "$mode" "$container"
printf 'Verify the engine and a chat response with: python3 %q %s --container %q --port %s\n' "$here/smoke.py" "$mode" "$container" "$port"
