#!/usr/bin/env python3
"""bench.py configs for GLM-5.3-Flash GR8 arms. Each arm = the recipe's turn-tail-on serve + ONE change (knob env)."""
import json, os, sys
H = '~/hillclimb/glm'
ARMS = {
    'ctl': [],
    'dhi4': ['DRAFT_HEAD_I4=1'],          # MTP draft lm_head on INT4 g32 copies (drafts only; TP=4 default)
    'dpar': ['DRAFT_PAR=2'],              # drafter step on its own high-priority stream (bit-exact; TP=4 default)
    'm2ks': ['MTP=2', 'MTP_KSTOP=2'],     # 2 MTP drafts, chained only while confident (TP=4 default with MTP 2+)
    # GR8's launcher maps DRAFT_HEAD_I4 / DRAFT_PAR / MTP_KSTOP only for GLM-5.3, not Flash (engine_args.sh: engine_env
    # -> flash_env), but the Flash binary reads the GR8_* variables: pass them through EXTRA_ENV (appended for Flash).
    'dflh': ['EXTRA_ENV=GLMTAIL=1 GR8_DFL_HEAD_I4=1'],     # DFlash2 drafter's lm_head on INT4 copies (drafts only)
    'dhe': ['EXTRA_ENV=GLMTAIL=1 GR8_DRAFT_HEAD_I4=1'],    # MTP draft lm_head on INT4 copies (drafts only)
    'dpare': ['EXTRA_ENV=GLMTAIL=1 GR8_DRAFT_PAR=2'],      # drafter step on its own high-priority stream (bit-exact)
    'rej': ['EXTRA_ARGS=--pf-lanes 1 --prefill 2048 --spec-accept rejection'],  # temp > 0: rejection sampling of drafts
}
mem_total_gib = int(open('/proc/meminfo').read().split()[1]) / 2**20

def cfg(name, arm, temperature=0.0, cap=None):
    pre = ['env', f'HC_CAP={cap}'] if cap else []
    return {
        'name': name, 'base_url': 'http://127.0.0.1:18100', 'model': 'glm-5.3-flash',
        'launch': [*pre, 'bash', f'{H}/glm-launch.sh', name, *ARMS[arm]],
        'stop': ['bash', f'{H}/glm-stop.sh'], 'health_timeout_s': 1900,
        'concurrency': 4, 'prefill_lengths': [4096, 32768], 'temperature': temperature,
        # GR8 keeps MemAvailable above its 2 GiB spare-RAM floor; trip if it falls under 1.5 GiB or swap grows.
        'memory': {'cap_gib': round(mem_total_gib - 1.5, 1), 'probe': ['bash', f'{H}/hostmem.sh'], 'interval_s': 3},
        'require_ac': True,
    }

if __name__ == '__main__':
    name, arm = sys.argv[1], sys.argv[2]
    t = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
    cap = int(sys.argv[4]) if len(sys.argv) > 4 else None   # gen.py NAME ARM TEMP CAP
    os.makedirs(f'{H}/configs', exist_ok=True); os.makedirs(f'{H}/logs', exist_ok=True)
    json.dump(cfg(name, arm, t, cap), open(f'{H}/configs/{name}.json', 'w'), indent=1)
    print(name)
