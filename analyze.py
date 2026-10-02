"""Analysis of Monte-Carlo rollouts -> docs/analysis.png, docs/RESULTS.md, results/summary.csv

    python analyze.py [--results results]
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
ORDER = ["jev", "rules", "greedy", "jev_noplan", "jev_nosafety"]
LABEL = {"jev": "Jev hierarchy (L0-L3)", "rules": "Rule-based dispatcher", "greedy": "Greedy dispatcher",
         "jev_noplan": "Jev, no A* planner", "jev_nosafety": "Jev, no L0 safety"}
SHORT = {"jev": "Jev", "rules": "Rules", "greedy": "Greedy", "jev_noplan": "Jev\nno planner", "jev_nosafety": "Jev\nno safety"}
COL = {"jev": "#b388ff", "rules": "#ffb74d", "greedy": "#90a4ae", "jev_noplan": "#4dd0e1", "jev_nosafety": "#f48fb1"}
BG, CARD, TXT, DIM = "#0a0f1c", "#111a2e", "#e8eefc", "#8fa0c4"


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, c - h), min(1.0, c + h)


def boot_ci(x, n=3000, seed=0):
    x = np.asarray(x, float)
    if len(x) == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    m = rng.choice(x, size=(n, len(x))).mean(axis=1)
    return float(x.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def sign_test(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def style(ax, title):
    ax.set_facecolor(CARD)
    for sp in ax.spines.values():
        sp.set_color("#2a3858")
    ax.tick_params(colors=DIM, labelsize=8)
    ax.set_title(title, color=TXT, fontsize=10.5, loc="left", pad=8, weight="bold")
    ax.yaxis.label.set_color(DIM); ax.xaxis.label.set_color(DIM)
    ax.grid(axis="y", color="#1d2944", lw=0.8); ax.set_axisbelow(True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    ap.add_argument("--docs", default="docs")
    a = ap.parse_args()
    res = ROOT / a.results
    rows = {c: [] for c in ORDER}
    for f in glob.glob(str(res / "raw" / "*.json")):
        r = json.loads(Path(f).read_text())
        if r["config"] in rows:
            rows[r["config"]].append(r)
    cfgs = [c for c in ORDER if rows[c]]
    for c in cfgs:
        rows[c].sort(key=lambda r: r["seed"])
    N = {c: len(rows[c]) for c in cfgs}
    docs = ROOT / a.docs; docs.mkdir(parents=True, exist_ok=True)
    for c in cfgs:
        for r in rows[c]:
            r["clean"] = bool(r["success"] and r["bld_viol_s"] < 0.5 and r["zone_viol_s"] < 2.0)

    # ---------- summary table ----------
    summ = []
    for c in cfgs:
        R = rows[c]
        succ = [r for r in R if r["success"]]
        dec = [d for r in R for d in r["decisions"] if d.get("agree") is not None]
        s = dict(config=c, n=len(R), success=sum(r["success"] for r in R), crash=sum(r["outcome"] == "crash" for r in R),
                 deadline=sum(r["deadline_met"] for r in R),
                 t_mean=boot_ci([r["t_total"] for r in succ])[0] if succ else float("nan"),
                 min_batt=float(np.mean([r["min_battery"] for r in R])),
                 bld=float(np.mean([r["bld_viol_s"] for r in R])), zone=float(np.mean([r["zone_viol_s"] for r in R])),
                 agree=(float(np.mean([d["agree"] for d in dec])) if dec else float("nan")),
                 regret=(float(np.mean([d["regret"] for d in dec])) if dec else float("nan")),
                 n_dec=len(dec), cost=float(np.mean([r["cost"] for r in R])), fallbacks=sum(r["jev_fallbacks"] for r in R))
        summ.append(s)
    with open(res / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summ[0].keys())); w.writeheader(); w.writerows(summ)

    # ---------- figure ----------
    fig = plt.figure(figsize=(18, 11.5), facecolor=BG)
    gs = fig.add_gridspec(3, 3, hspace=0.42, wspace=0.26, left=0.05, right=0.985, top=0.9, bottom=0.07)
    x = np.arange(len(cfgs))
    xl = [SHORT[c] for c in cfgs]

    def bars_ci(ax, key, title):
        style(ax, title)
        for i, c in enumerate(cfgs):
            k = sum(bool(r[key]) for r in rows[c]); p, lo, hi = wilson(k, N[c])
            ax.bar(i, p * 100, color=COL[c], alpha=0.9, width=0.62)
            ax.errorbar(i, p * 100, yerr=[[p * 100 - lo * 100], [hi * 100 - p * 100]], color="white", capsize=4, lw=1.4)
            ax.text(i, min(p * 100 + 9, 104), f"{k}/{N[c]}", ha="center", color=TXT, fontsize=8.5)
        ax.set_xticks(x); ax.set_xticklabels(xl); ax.set_ylim(0, 112); ax.set_ylabel("% of scenarios (95% Wilson CI)")

    ax0 = fig.add_subplot(gs[0, 0])
    bars_ci(ax0, "success", "Mission success (light) and CLEAN success (solid)")
    for i, c in enumerate(cfgs):
        k = sum(r["clean"] for r in rows[c]); p_ = k / N[c] * 100
        ax0.bar(i, p_, color=COL[c], width=0.62, edgecolor="white", lw=1.2)
        ax0.text(i, max(p_ - 9, 3), f"{k}", ha="center", color="#0a0f1c", fontsize=9, weight="bold")
    ax0.set_xlabel("clean = all delivered + landed, never inside a building, <2 s in a no-fly zone", fontsize=8)
    bars_ci(fig.add_subplot(gs[0, 1]), "deadline_met", "Urgent medical delivery met its deadline")

    ax = fig.add_subplot(gs[0, 2]); style(ax, "Mission time (successful runs only)")
    for i, c in enumerate(cfgs):
        ts = [r["t_total"] for r in rows[c] if r["success"]]
        if ts:
            bp = ax.boxplot([ts], positions=[i], widths=0.5, patch_artist=True, showfliers=False,
                            medianprops=dict(color="white"), whiskerprops=dict(color=DIM), capprops=dict(color=DIM))
            bp["boxes"][0].set(facecolor=COL[c], alpha=0.55, edgecolor=COL[c])
            ax.scatter(np.full(len(ts), i) + np.random.default_rng(i).uniform(-0.14, 0.14, len(ts)), ts, s=14, color=COL[c], zorder=3)
        ax.text(i, ax.get_ylim()[0] if False else 0, "", color=TXT)
    ax.set_xticks(x); ax.set_xticklabels(xl); ax.set_ylabel("seconds")

    ax = fig.add_subplot(gs[1, 0]); style(ax, "Lowest battery reached (safety margin)")
    for i, c in enumerate(cfgs):
        v = [r["min_battery"] for r in rows[c]]
        bp = ax.boxplot([v], positions=[i], widths=0.5, patch_artist=True, showfliers=False, medianprops=dict(color="white"),
                        whiskerprops=dict(color=DIM), capprops=dict(color=DIM))
        bp["boxes"][0].set(facecolor=COL[c], alpha=0.55, edgecolor=COL[c])
        ax.scatter(np.full(len(v), i) + np.random.default_rng(i).uniform(-0.14, 0.14, len(v)), v, s=14, color=COL[c], zorder=3)
    ax.axhline(8, color="#ff5252", ls="--", lw=1); ax.text(len(cfgs) - 0.5, 9.5, "L0 trip level", color="#ff5252", fontsize=8, ha="right")
    ax.set_xticks(x); ax.set_xticklabels(xl); ax.set_ylabel("battery %")

    ax = fig.add_subplot(gs[1, 1]); style(ax, "Airspace violations per mission (seconds)")
    bw = 0.36
    for i, c in enumerate(cfgs):
        b = np.mean([r["bld_viol_s"] for r in rows[c]]); z = np.mean([r["zone_viol_s"] for r in rows[c]])
        ax.bar(i - bw / 2, b, bw, color="#ff8a65", label="inside a building" if i == 0 else None)
        ax.bar(i + bw / 2, z, bw, color="#ef5350", label="inside a no-fly zone" if i == 0 else None)
        ax.text(i - bw / 2, b + 0.4, f"{b:.1f}", ha="center", color=TXT, fontsize=8); ax.text(i + bw / 2, z + 0.4, f"{z:.1f}", ha="center", color=TXT, fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels(xl); ax.legend(facecolor=CARD, labelcolor=TXT, fontsize=8, edgecolor="#2a3858")

    ax = fig.add_subplot(gs[1, 2]); style(ax, "Per-decision agreement with the exhaustive oracle")
    pcfg = [c for c in ["jev", "rules", "greedy"] if c in cfgs]
    for i, c in enumerate(pcfg):
        d = [dd for r in rows[c] for dd in r["decisions"] if dd.get("agree") is not None]
        k = sum(bool(dd["agree"]) for dd in d); p, lo, hi = wilson(k, len(d))
        ax.bar(i, p * 100, color=COL[c], width=0.6)
        ax.errorbar(i, p * 100, yerr=[[p * 100 - lo * 100], [hi * 100 - p * 100]], color="white", capsize=4)
        reg = np.mean([dd["regret"] for dd in d]) if d else 0
        ax.text(i, 8, f"mean regret\n{reg:.1f} s", ha="center", color="#0a0f1c", fontsize=8.5, weight="bold")
        ax.text(i, p * 100 + 4, f"{p * 100:.0f}%  (n={len(d)})", ha="center", color=TXT, fontsize=8.5)
    ax.set_xticks(range(len(pcfg))); ax.set_xticklabels([SHORT[c] for c in pcfg]); ax.set_ylim(0, 115); ax.set_ylabel("% of decisions")

    ax = fig.add_subplot(gs[2, 0]); style(ax, "Is Jev's confidence calibrated?")
    ece = brier = float("nan")
    if "jev" in rows:
        d = [dd for r in rows["jev"] for dd in r["decisions"] if dd.get("agree") is not None and dd["source"] == "jev"]
        if d:
            conf = np.array([dd["conf"] for dd in d]); ok = np.array([float(bool(dd["agree"])) for dd in d])
            edges = [0.0, 0.5, 0.7, 0.85, 0.95, 0.99, 1.0001]
            mc, acc, cnt = [], [], []
            for lo, hi in zip(edges[:-1], edges[1:]):
                m = (conf >= lo) & (conf < hi)
                if m.sum():
                    mc.append(conf[m].mean()); acc.append(ok[m].mean()); cnt.append(int(m.sum()))
            ax.plot([0, 1], [0, 1], "--", color=DIM, lw=1)
            ax.plot(mc, acc, "o-", color=COL["jev"], lw=2, ms=8)
            for xx, yy, n in zip(mc, acc, cnt):
                ax.text(xx, yy - 0.075, f"n={n}", ha="center", color=TXT, fontsize=8)
            ece = float(sum(c * abs(a_ - m_) for c, a_, m_ in zip(cnt, acc, mc)) / sum(cnt))
            brier = float(np.mean((conf - ok) ** 2))
            ax.text(0.03, 0.93, f"ECE {ece:.3f}   Brier {brier:.3f}\n{len(d)} decisions", transform=ax.transAxes, color=TXT, fontsize=9, va="top")
    ax.set_xlim(0, 1.02); ax.set_ylim(-0.05, 1.05); ax.set_xlabel("Jev's stated probability for its chosen job"); ax.set_ylabel("fraction matching oracle")

    ax = fig.add_subplot(gs[2, 1]); style(ax, "Decision regret (seconds lost vs. oracle) - CDF")
    for c in pcfg:
        rg = np.sort([dd["regret"] for r in rows[c] for dd in r["decisions"] if dd.get("agree") is not None])
        if len(rg):
            ax.step(rg, np.arange(1, len(rg) + 1) / len(rg) * 100, where="post", color=COL[c], lw=2, label=LABEL[c])
    ax.set_xscale("symlog", linthresh=1); ax.set_xlabel("regret (s, symlog)"); ax.set_ylabel("% of decisions"); ax.set_ylim(0, 102)
    ax.legend(facecolor=CARD, labelcolor=TXT, fontsize=8, edgecolor="#2a3858", loc="lower right")

    ax = fig.add_subplot(gs[2, 2]); style(ax, "Jev call latency & cost")
    lat = [dd["latency"] for r in rows.get("jev", []) for dd in r["decisions"] if dd.get("source") == "jev" and dd.get("latency")]
    if lat:
        ax.hist(lat, bins=24, color=COL["jev"], alpha=0.85)
        cost = np.mean([r["cost"] for r in rows["jev"]]); calls = np.mean([r["jev_calls"] for r in rows["jev"]])
        ax.text(0.97, 0.95, f"median {np.median(lat) * 1000:.0f} ms   p95 {np.percentile(lat, 95) * 1000:.0f} ms\n"
                f"{calls:.0f} calls / mission\n${cost:.4f} / mission", transform=ax.transAxes, ha="right", va="top", color=TXT, fontsize=9)
    ax.set_xlabel("seconds per decision call (3 typed questions)"); ax.set_ylabel("count")

    fig.suptitle(f"Hierarchical autonomy with Jev as the strategic layer - Monte-Carlo over randomised city missions "
                 f"({max(N.values())} scenarios x {len(cfgs)} configurations)", color=TXT, fontsize=14, weight="bold", y=0.975)
    fig.savefig(docs / "analysis.png", dpi=125, facecolor=BG)

    # ---------- markdown ----------
    L = ["# Results", "", f"Monte-Carlo over randomised missions (storm/no-fly timing and size, deadline, start battery, wind). "
         "Every configuration flies the *same* scenario per seed, so comparisons are paired.", "",
         "| configuration | n | success (clean) | deadline met | time, successes (s) | lowest battery | building / zone violation (s) | oracle agreement | mean regret (s) | $ / mission |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for s in summ:
        s["clean"] = sum(r["clean"] for r in rows[s["config"]])
        p, lo, hi = wilson(s["success"], s["n"]); pd_, dlo, dhi = wilson(s["deadline"], s["n"])
        L.append(f"| {LABEL[s['config']]} | {s['n']} | {p * 100:.0f}% ({lo * 100:.0f}-{hi * 100:.0f}), clean {s['clean']}/{s['n']} | {pd_ * 100:.0f}% ({dlo * 100:.0f}-{dhi * 100:.0f}) | "
                 f"{s['t_mean']:.0f} | {s['min_batt']:.0f}% | {s['bld']:.1f} / {s['zone']:.1f} | "
                 f"{'-' if math.isnan(s['agree']) else format(s['agree'] * 100, '.0f') + '%'} | "
                 f"{'-' if math.isnan(s['regret']) else format(s['regret'], '.1f')} | {s['cost']:.4f} |")
    L += ["", "Success intervals are 95% Wilson; time is a mean over successful runs.", "", "## Paired comparisons (same seed)", ""]

    def by_seed(c):
        return {r["seed"]: r for r in rows.get(c, [])}

    def paired(a_, b_):
        A, B = by_seed(a_), by_seed(b_)
        seeds = sorted(set(A) & set(B))
        if not seeds:
            return
        sw = sum(1 for s in seeds if A[s]["success"] and not B[s]["success"]); sl = sum(1 for s in seeds if B[s]["success"] and not A[s]["success"])
        both = [s for s in seeds if A[s]["success"] and B[s]["success"]]
        dt = np.array([B[s]["t_total"] - A[s]["t_total"] for s in both])
        tw = int((dt > 0).sum()); tl = int((dt < 0).sum())
        m, lo, hi = boot_ci(dt) if len(dt) else (float("nan"),) * 3
        L.append(f"- **{LABEL[a_]} vs {LABEL[b_]}** over {len(seeds)} seeds: success {sw} wins / {sl} losses (sign test p={sign_test(sw, sl):.3f}); "
                 f"on the {len(both)} seeds both finished, {LABEL[a_]} was faster in {tw}, slower in {tl} "
                 f"(mean time saved {m:+.1f} s, 95% CI {lo:+.1f}..{hi:+.1f}; sign test p={sign_test(tw, tl):.3f}).")

    for a_, b_ in [("jev", "greedy"), ("jev", "rules"), ("jev", "jev_noplan"), ("jev", "jev_nosafety")]:
        if a_ in rows and b_ in rows:
            paired(a_, b_)
    if not math.isnan(ece):
        L += ["", f"## Calibration of Jev's decisions", "",
              f"Treating the oracle's best first job as ground truth, Jev's stated probability for the job it chose has "
              f"**ECE {ece:.3f}** and **Brier {brier:.3f}** (0 = perfect). See the reliability diagram in `analysis.png`."]
    (docs / "RESULTS.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\nwrote {docs / 'analysis.png'} and {docs / 'RESULTS.md'}")


if __name__ == "__main__":
    main()
