"""Hierarchical autonomy demo: Jev (strategic) -> A* (tactical) -> MuJoCo flight control.

    python run_demo.py                 live Jev via OpenRouter (needs OPENROUTER_API_KEY), writes out/demo.mp4
    python run_demo.py --policy rules  hand-written dispatcher instead of Jev (offline)
    python run_demo.py --no-video      skip rendering (fast logic check)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from dotenv import load_dotenv

from jevplanner.jev_client import JevClient
from jevplanner.mission import Mission
from jevplanner.strategist import Strategist
from jevplanner.world import BOUNDS, CEILING

ROOT = Path(__file__).resolve().parent


def summary_plot(ms: Mission, path: Path):
    L = np.array(ms.log)
    t = L[:, 0]
    fig, ax = plt.subplots(2, 2, figsize=(15, 8.5), facecolor="#0a0f1c")
    for a in ax.flat:
        a.set_facecolor("#111a2e")
        for sp in a.spines.values(): sp.set_color("#2a3858")
        a.tick_params(colors="#9fb0d0"); a.xaxis.label.set_color("#9fb0d0"); a.yaxis.label.set_color("#9fb0d0"); a.title.set_color("#e8eefc")
    pal = {"clinic": "#ff6b6b", "cafe": "#ffd166", "apartment": "#06d6a0", "bakery": "#4dabf7", "depot": "#b388ff"}
    a = ax[0, 0]
    a.plot(t, L[:, 6], color="#66bb6a", lw=2, label="battery %")
    a.plot(t, L[:, 3] * 4, color="#4dd0e1", lw=1, label="altitude x4 (m)")
    segs = ms.timeline + [(t[-1], None)]
    for (t0, k), (t1, _) in zip(segs[:-1], segs[1:]):
        a.axvspan(t0, t1, color=pal[k], alpha=0.18)
        a.text((t0 + t1) / 2, 103, ms.jd[k].label, color=pal[k], ha="center", fontsize=8)
    for z in ms.zones:
        a.axvline(z.t_on, color="#ff5252", ls="--"); a.text(z.t_on + 0.4, 6, z.key, color="#ff5252", rotation=90, fontsize=8)
    a.set_ylim(0, 112); a.set_xlabel("time (s)"); a.set_title("Battery & Jev's job decisions (bands)"); a.legend(facecolor="#111a2e", labelcolor="#e8eefc", fontsize=7, loc="lower left")
    a = ax[0, 1]
    a.plot(t, L[:, 4], color="#69f0ae"); a.plot(t, L[:, 5] / 4, color="#ffd54f")
    a.set_title("Speed (m/s) and tilt/4 (deg)"); a.set_xlabel("time (s)")
    a = ax[1, 0]
    from matplotlib.patches import Rectangle, Circle
    for b in ms.buildings:
        a.add_patch(Rectangle((b.cx - b.hx, b.cy - b.hy), 2 * b.hx, 2 * b.hy, fc="#3a4a73" if b.h >= CEILING - 2 else "#6e83b5", ec="none"))
    for z in ms.zones:
        a.add_patch(Circle((z.cx, z.cy), z.r, fc="#ff3b3b", alpha=0.35))
    for j in ms.jobs:
        a.plot(j.x, j.y, "s" if j.kind == "depot" else "o", color=pal[j.key], ms=9, mec="white"); a.text(j.x + 2, j.y + 2, j.label, color="white", fontsize=8)
    sc = a.scatter(L[:, 1], L[:, 2], c=t, cmap="plasma", s=6)
    a.set_xlim(*BOUNDS); a.set_ylim(*BOUNDS); a.set_aspect("equal"); a.set_title("Ground track (colour = time)")
    a = ax[1, 1]
    a.axis("off")
    txt = ["MISSION SUMMARY", "", f"deliveries: {sum(j.done for j in ms.jobs if j.kind == 'deliver')}/4",
           f"duration: {ms.t:.1f} s    battery left: {ms.battery:.0f}%", f"Jev calls: {ms.strat.calls}   fallbacks: {ms.strat.fails}",
           f"job switches by Jev: {ms.switches}   A* plans: {ms.replans}", f"min clearance to buildings: {ms.min_clear:.1f} m",
           f"outcome: {'CRASH' if ms.crashed else ('COMPLETE' if ms.finished else 'TIMEOUT')}", "", "events:"] + [e for e in ms.events if " L3 " in e or "!!" in e or "L0" in e][-12:]
    a.text(0.0, 1.0, "\n".join(txt), color="#e8eefc", va="top", family="monospace", fontsize=8.5)
    fig.tight_layout(); fig.savefig(path, dpi=130, facecolor=fig.get_facecolor())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default="jev", choices=["jev", "rules", "greedy"])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    for p in (ROOT / ".env", ROOT.parent / ".env"):
        if p.exists():
            load_dotenv(p)
    out = ROOT / a.out; out.mkdir(exist_ok=True)
    client = None
    if a.policy == "jev":
        try:
            client = JevClient()
        except RuntimeError as e:
            sys.exit(f"error: {e}  (use --dry for the offline baseline)")
    from jevplanner.scenario import make_scenario
    ms = Mission(Strategist(client, a.policy), record=not a.no_video, out=out, scenario=make_scenario(a.seed))
    print(f"policy={a.policy} seed={a.seed}: flying the hierarchy\n")
    ms.run()
    done = sum(j.done for j in ms.jobs if j.kind == "deliver")
    print(f"\n{'CRASHED' if ms.crashed else ('COMPLETE' if ms.finished else 'TIMEOUT')}: {done}/4 deliveries in {ms.t:.1f}s, "
          f"battery {ms.battery:.0f}%, min building clearance {ms.min_clear:.1f} m, Jev calls {ms.strat.calls}, "
          f"A* plans {ms.replans}, job switches {ms.switches}")
    r = ms.result()
    print(f"oracle agreement {r['agree']}  mean regret {r['mean_regret']}  violations: building {r['bld_viol_s']}s zone {r['zone_viol_s']}s")
    (out / "decision_log.json").write_text(json.dumps(ms.decisions, indent=1))
    if ms.log:
        summary_plot(ms, out / "summary.png")
    print(f"outputs in {out}")


if __name__ == "__main__":
    main()
