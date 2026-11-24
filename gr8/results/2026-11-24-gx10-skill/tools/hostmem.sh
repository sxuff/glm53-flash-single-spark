#!/usr/bin/env bash
# Memory probe for bench.py's watchdog on GB10 (unified memory): prints host-wide used bytes
# (MemTotal - MemAvailable). GPU allocations come out of MemAvailable on GB10, and nvidia-smi
# reports per-process memory as [N/A], so the skill's container probe (mem.sh) reads ~0 here.
# Swap growth of more than 256 MiB over the baseline in .swap0 adds 1 PiB, so it always trips the cap.
set -euo pipefail
d=$(cd "$(dirname "$0")" && pwd)
read -r tot avail st sf < <(awk '/^MemTotal:/{t=$2} /^MemAvailable:/{a=$2} /^SwapTotal:/{s=$2} /^SwapFree:/{f=$2} END{print t, a, s, f}' /proc/meminfo)
used=$(( (tot - avail) * 1024 )); swap=$(( (st - sf) * 1024 ))
base=$(cat "$d/.swap0" 2>/dev/null || echo "$swap")
if [ $(( swap - base )) -gt $(( 256 * 1024 * 1024 )) ]; then used=$(( used + (1 << 50) )); fi
echo "$used"
