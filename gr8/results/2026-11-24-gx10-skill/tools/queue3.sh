#!/usr/bin/env bash
# Serial A/B queue for GLM-5.3-Flash GR8 (inference-optimisation skill rules: one GPU job at a time, one change per arm,
# controls between candidates). Drains and stops live Inkling first; ALWAYS restores it on exit,
# with a 4-hour systemd fallback timer in case this script dies without running its trap.
#   queue2.sh ARM...   ARM = config name | eq:NAME (greedy capture from the running server) | long:CONFIG[:N] (bench + N-token needle, default 100000)
set -u
H=~/hillclimb/glm; cd "$H"; mkdir -p logs
exec 9>/tmp/gb10-hillclimb.lock
flock -n 9 || { echo "another GPU queue holds /tmp/gb10-hillclimb.lock"; exit 1; }

restore() {
  bash "$H/glm-stop.sh"
  sleep 3
  systemctl --user reset-failed inkling2-mini.service 2>/dev/null   # a quick stop/start cycle can hit the start limit
  systemctl --user start inkling2-mini.service
  systemctl --user stop inkling-fallback-restore.timer 2>/dev/null
  echo "$(date +%T) RESTORED inkling2-mini.service: $(systemctl --user is-active inkling2-mini.service)"
}
trap restore EXIT

systemd-run --user --on-active=4h --unit inkling-fallback-restore \
  systemctl --user start inkling2-mini.service >/dev/null 2>&1

# Drain: wait (up to 5 min) until live Inkling has no running requests, then stop it.
for i in $(seq 100); do
  r=$(curl -s -m 3 127.0.0.1:19020/metrics | awk '/^vllm:num_requests_running/{s+=$2} END{print s+0}')
  [ "${r:-0}" = 0 ] && break; sleep 3
done
echo "$(date +%T) stopping inkling2-mini.service (running requests: ${r:-0})"
systemctl --user stop inkling2-mini.service
for i in $(seq 60); do docker ps -q -f name='^inkling2-mini-gx10$' | grep -q . || break; sleep 2; done
docker ps -q -f name='^inkling2-mini-gx10$' | grep -q . && { echo "inkling container still up, aborting"; exit 1; }

awk '/^SwapTotal:/{t=$2} /^SwapFree:/{f=$2} END{print (t-f)*1024}' /proc/meminfo > .swap0
echo "$(date +%T) START free=$(awk '/^MemAvailable:/{printf "%.1f", $2/1048576}' /proc/meminfo) GiB, gpu procs: $(nvidia-smi --query-compute-apps=pid --format=csv,noheader | wc -l)"

for c in "$@"; do
  echo "$(date +%T) === $c"
  case "$c" in
    eq:*)  # greedy equivalence capture against the server the previous arm left running
      n=${c#eq:}
      python3 eq.py save "$n" http://127.0.0.1:18100 glm-5.3-flash > "logs/eq-$n.txt" 2>&1
      echo "  eq-$n saved: $(wc -l < "logs/eq-$n.txt") prompts"; continue;;
    long:*) c=${c#long:}; n=100000; case "$c" in *:*) n=${c#*:}; c=${c%%:*};; esac; L="--long $n";;
    *) L="";;
  esac
  pre=$(curl -s -m 3 127.0.0.1:11434/api/ps | grep -o '"name"' | wc -l)
  python3 bench.py run "configs/$c.json" --reps 6 --skip-cN $L > "logs/$c.txt" 2>&1
  post=$(curl -s -m 3 127.0.0.1:11434/api/ps | grep -o '"name"' | wc -l)
  grep -E "healthy|c1 median|prefill ~|EXCEEDED|error|long " "logs/$c.txt" | cut -c1-240
  docker logs hc-glm > "logs/$c.container.txt" 2>&1
  echo "  worker: $(grep -E '^(GR8_(DRAFT|MTP|DFL|SPEC)|GLMTAIL)' "logs/$c.worker-env.txt" 2>/dev/null | paste -sd' ') | mtp $(grep -A1 -xF -- '--mtp' "logs/$c.worker-argv.txt" 2>/dev/null | tail -1) | accept $(grep -A1 -xF -- '--spec-accept' "logs/$c.worker-argv.txt" 2>/dev/null | tail -1)"
  if [ "$pre$post" != "00" ]; then echo "VOID $c: ollama had a model loaded during the run"; fi
done
bash "$H/glm-stop.sh"
echo "$(date +%T) QUEUE DONE"
