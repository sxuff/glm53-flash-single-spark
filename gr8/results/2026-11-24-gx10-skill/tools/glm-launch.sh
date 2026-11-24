#!/usr/bin/env bash
# Start one GLM-5.3-Flash GR8 arm: the recipe's turn-tail-on `docker run` from ~/.config/systemd/user/glm53f-gr8.service
# (gr8-tail:2, SESS=8, CAP=327680, --pf-lanes 1 --prefill 2048, GLMTAIL=1, the shared glm53f-cache weights), plus the
# arm's own KNOB=VALUE environment, on port 18100, with fresh per-arm prompt and home volumes (as bench/compare.sh does).
# Returns once a real chat completion answers (the catalog appears before the GPU worker), then records the worker's
# actual flags and GR8_* environment so a knob that was silently ignored shows up.
# CAP: the recipe's 327680 no longer boots on this box (2026-11-24: 112.3 GiB available at start, the engine
# stopped at "7.70 GiB left ... the rest of the boot needs 8.0"), so every arm, control included, runs CAP=262144
# (still one full 262,144-token request; the KV pool the 8 session slots share). HC_CAP overrides it.
#   glm-launch.sh ARM [KNOB=VALUE ...]
set -euo pipefail
arm=$1; shift
H=~/hillclimb/glm; mkdir -p "$H/logs"
envs=(); for kv in "$@"; do envs+=(-e "$kv"); done
cap=${HC_CAP:-262144}
# A CAP below the image's MAX_MODEL_LEN (262144) is refused unless MAX_MODEL_LEN fits it: CAP less DFlash2's 14
# guard rows (the image's knobs.sh, TUNE=context: 700032 -> 700018).
[ "$cap" -lt 262158 ] && envs+=(-e "MAX_MODEL_LEN=$((cap - 14))")
bash ~/v2/glm-gr8/wait-mem.sh 108
docker run -d --rm --name hc-glm --label io.github.sxuff.hillclimb=1 --gpus all --network host --pid host \
  --ulimit memlock=-1 --ulimit core=0 --cap-drop ALL --cap-add IPC_LOCK \
  --security-opt no-new-privileges --read-only --tmpfs /tmp:size=1g,mode=1777 --init --oom-score-adj 1000 \
  -e PORT=18100 -e "CAP=$cap" -e SESS=8 -e "EXTRA_ARGS=--pf-lanes 1 --prefill 2048" -e EXTRA_ENV=GLMTAIL=1 "${envs[@]}" \
  -v glm53f-cache:/var/lib/gr8/cache -v "hc-glm-prompts-$arm:/var/lib/gr8/prompts" -v "hc-glm-home-$arm:/var/lib/gr8/home" \
  -v ~/v2/glm-gr8/kv-store.yaml:/etc/gr8/kv-store.yaml:ro gr8-tail:2 >/dev/null
# --rm removes a container that dies during boot, with its log: stream the log to a file from the start.
setsid nohup docker logs -f hc-glm > "$H/logs/$arm.boot.txt" 2>&1 < /dev/null &
body='{"model":"glm-5.3-flash","messages":[{"role":"user","content":"Say ok."}],"max_tokens":8,"temperature":0}'
for i in $(seq 1 600); do
  if curl -s -m 120 127.0.0.1:18100/v1/chat/completions -H 'Content-Type: application/json' -d "$body" | grep -q '"choices"'; then break; fi
  docker ps -q -f name='^hc-glm$' | grep -q . || { echo "hc-glm exited during boot" >&2; exit 1; }
  [ "$i" = 600 ] && { echo "no chat answer after 30 min" >&2; exit 1; }
  sleep 3
done
pid=$(docker top hc-glm -eo pid,args | awk '$2 ~ /g6m4_flash-int4$/ {print $1}' | head -1)
tr '\0' '\n' < "/proc/$pid/cmdline" > "$H/logs/$arm.worker-argv.txt" 2>/dev/null || docker exec hc-glm cat "/proc/$pid/cmdline" | tr '\0' '\n' > "$H/logs/$arm.worker-argv.txt"
docker exec hc-glm sh -c "tr '\000' '\n' < /proc/$pid/environ" 2>/dev/null | grep -E '^(GR8_|GLMTAIL|MTP|DRAFT|DFLASH|SPEC|KV_)' | sort > "$H/logs/$arm.worker-env.txt" || true
