"""Monte-Carlo rollouts of the hierarchy under randomised scenarios (parallel + resumable).

    python rollout.py --configs jev,rules,greedy,jev_noplan,jev_nosafety --seeds 1-24 --workers 6

Each (config, seed) writes results/raw/<config>_<seed>.json, so an interrupted run (or a
pre-empted spot VM) simply resumes. CPU/API bound: a GPU is not used.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent

#            policy   planner     L0 safety supervisor
CONFIGS = {
    "jev":          ("jev",    "astar",    True),
    "rules":        ("rules",  "astar",    True),
    "greedy":       ("greedy", "astar",    True),
    "jev_noplan":   ("jev",    "straight", True),    # ablation: remove the L2 planner
    "jev_nosafety": ("jev",    "astar",    False),   # ablation: remove the L0 supervisor
}


def run_one(job):
    cfg, seed, outdir = job
    path = Path(outdir) / "raw" / f"{cfg}_{seed}.json"
    if path.exists():
        return cfg, seed, "cached", None
    try:
        from dotenv import load_dotenv
        for p in (ROOT / ".env", ROOT.parent / ".env"):
            if p.exists():
                load_dotenv(p)
        from jevplanner.jev_client import JevClient
        from jevplanner.mission import Mission
        from jevplanner.scenario import make_scenario
        from jevplanner.strategist import Strategist

        policy, planner, safety = CONFIGS[cfg]
        client = JevClient() if policy == "jev" else None
        t0 = time.time()
        ms = Mission(Strategist(client, policy), record=False, out=Path(outdir), scenario=make_scenario(seed),
                     planner_mode=planner, safety=safety, verbose=False)
        ms.run()
        r = ms.result()
        r["config"], r["wall_s"] = cfg, round(time.time() - t0, 1)
        path.write_text(json.dumps(r))
        return cfg, seed, r["outcome"], r
    except Exception:
        return cfg, seed, "ERROR " + traceback.format_exc(limit=3).replace("\n", " | "), None


def parse_seeds(s):
    out = []
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", default="jev,rules,greedy,jev_noplan,jev_nosafety")
    ap.add_argument("--seeds", default="1-24")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    ap.add_argument("--out", default="results")
    a = ap.parse_args()
    out = ROOT / a.out
    (out / "raw").mkdir(parents=True, exist_ok=True)
    cfgs = a.configs.split(",")
    jobs = [(c, s, str(out)) for s in parse_seeds(a.seeds) for c in cfgs]
    print(f"{len(jobs)} rollouts on {a.workers} workers -> {out}", flush=True)
    done = 0
    t0 = time.time()
    with Pool(a.workers) as pool:
        for cfg, seed, status, r in pool.imap_unordered(run_one, jobs):
            done += 1
            extra = "" if r is None else f"  {r['deliveries']}/4 in {r['t_total']:.0f}s batt_end {r['battery_end']:.0f}% wall {r['wall_s']}s"
            print(f"[{done:3d}/{len(jobs)}] {cfg:13s} seed {seed:3d}  {status}{extra}", flush=True)
    print(f"finished in {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
