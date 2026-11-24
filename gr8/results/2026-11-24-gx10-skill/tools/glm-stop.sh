#!/usr/bin/env bash
# Stop the hill-climb GLM container (30 s graceful, as the recipe's service) and drop its per-arm volumes.
docker stop -t 30 hc-glm >/dev/null 2>&1
for i in $(seq 1 30); do docker ps -aq -f name='^hc-glm$' | grep -q . || break; sleep 1; done
for v in $(docker volume ls -q --filter name='^hc-glm-'); do docker volume rm "$v" >/dev/null 2>&1; done
true
