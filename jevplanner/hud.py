"""Three-layer HUD rendered with matplotlib (480x720) and composited next to the 3D view."""

from __future__ import annotations

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle

from .world import BOUNDS, CEILING

W, H = 480, 720
BG, CARD, TXT, DIM = "#0a0f1c", "#111a2e", "#e8eefc", "#7d8bab"
C3, C2, C1, C0 = "#b388ff", "#ffb74d", "#69f0ae", "#ff5252"      # Jev / planner / control / safety
KEYS = ["clinic", "cafe", "apartment", "bakery", "depot"]
NAMES = {"clinic": "Clinic (urgent)", "cafe": "Cafe", "apartment": "Apartment", "bakery": "Bakery", "depot": "Depot / recharge"}


class Hud:
    def __init__(self, buildings, jobs, zones):
        self.fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor=BG)
        self.bg = self.fig.add_axes([0, 0, 1, 1]); self.bg.set_xlim(0, W); self.bg.set_ylim(0, H); self.bg.axis("off")
        self.jobs = {j.key: j for j in jobs}
        self.cards = {}
        for name, (y0, y1, col) in {"L3": (402, 672, C3), "L2": (208, 394, C2), "L1": (74, 200, C1)}.items():
            p = FancyBboxPatch((10, y0), W - 20, y1 - y0, boxstyle="round,pad=0,rounding_size=12", fc=CARD, ec=col, lw=1.3, alpha=0.98)
            self.bg.add_patch(p); self.cards[name] = (p, col)
        self.t(W / 2, 700, "JEV  HIERARCHICAL AUTOPILOT", 12.5, TXT, "center", "bold")
        self.t(W / 2, 683, "typed strategic decisions  >  3D route planning  >  rigid-body flight control", 6.8, DIM, "center")
        # ---- L3
        self.t(24, 652, "L3  JEV  strategic", 10, C3, weight="bold")
        self.l3_state = self.t(456, 652, "", 7, DIM, "right")
        self.job_txt = self.t(24, 627, "", 11, TXT, weight="bold")
        self.bars_ax = self.fig.add_axes([150 / W, 462 / H, 290 / W, 132 / H], facecolor=CARD)
        self.bars = self.bars_ax.barh(range(5), [0] * 5, color=C3, height=0.62)
        self.bars_ax.set_xlim(0, 1); self.bars_ax.set_ylim(4.6, -0.6)
        self.bars_ax.set_yticks(range(5)); self.bars_ax.set_yticklabels([NAMES[k] for k in KEYS], color=TXT, fontsize=7.5)
        self.bars_ax.tick_params(axis="x", colors=DIM, labelsize=6, length=2); self.bars_ax.tick_params(axis="y", length=0)
        for sp in self.bars_ax.spines.values(): sp.set_visible(False)
        self.bars_ax.set_title("P(next job)  - calibrated, from Jev", color=DIM, fontsize=7, loc="left")
        self.ptxt = [self.bars_ax.text(0.0, i, "", color=TXT, fontsize=7, va="center") for i in range(5)]
        self.speed_txt = self.t(24, 440, "", 8.5, TXT)
        self.orc_txt = self.t(456, 440, "", 7.4, DIM, "right")
        self.risk_txt = self.t(24, 420, "", 8.5, TXT)
        self.stat_txt = self.t(456, 420, "", 7, DIM, "right")
        # ---- L2
        self.t(24, 374, "L2  PLANNER  3D A*", 10, C2, weight="bold")
        self.map = self.fig.add_axes([24 / W, 216 / H, 144 / W, 144 / H], facecolor="#0c1424")
        m = self.map
        m.set_xlim(BOUNDS[0], BOUNDS[1]); m.set_ylim(BOUNDS[0], BOUNDS[1]); m.set_aspect("equal"); m.set_xticks([]); m.set_yticks([])
        for sp in m.spines.values(): sp.set_color("#25324d")
        for b in buildings:
            tall = b.h >= CEILING - 2
            m.add_patch(Rectangle((b.cx - b.hx, b.cy - b.hy), 2 * b.hx, 2 * b.hy, fc="#3a4a73" if tall else "#6e83b5", ec="none"))
        self.zone_p = {}
        for z in zones:
            p = Circle((z.cx, z.cy), z.r, fc="#ff3b3b", ec="#ff8a80", alpha=0.0, lw=1); m.add_patch(p); self.zone_p[z.key] = p
        self.pad_p = {}
        for j in jobs:
            self.pad_p[j.key], = m.plot(j.x, j.y, "s" if j.kind == "depot" else "o", color="#4fc3f7" if j.kind == "depot" else "#ffb74d", ms=5, mec="white", mew=0.6)
        self.trail, = m.plot([], [], "-", color="#fff176", lw=0.8, alpha=0.7)
        self.pathl, = m.plot([], [], "-", color="#26c6da", lw=1.6)
        self.drone, = m.plot([], [], "^", color="white", ms=7, mec=C3, mew=1.2)
        self.l2_txt = self.t(184, 345, "", 8.2, TXT, va="top", mono=True)
        # ---- L1
        self.t(24, 180, "L1  CONTROL  500 Hz physics", 10, C1, weight="bold")
        self.g = {}
        for i, (nm, mx, col) in enumerate([("SPEED", 10, C1), ("ALT", CEILING, "#4dd0e1"), ("TILT", 38, "#ffd54f"), ("BATT", 100, "#66bb6a")]):
            y = 154 - i * 21
            self.t(24, y + 5, nm, 7.5, DIM)
            self.bg.add_patch(Rectangle((70, y), 200, 10, fc="#1d2944", ec="none"))
            bar = Rectangle((70, y), 0, 10, fc=col, ec="none"); self.bg.add_patch(bar)
            val = self.t(278, y + 5, "", 7.5, TXT)
            self.g[nm] = (bar, mx, val, col)
        self.t(350, 160, "ROTOR THRUST (N)", 6.8, DIM)
        self.motor_bars = []
        for i in range(4):
            x = 352 + i * 26
            self.bg.add_patch(Rectangle((x, 84), 16, 62, fc="#1d2944", ec="none"))
            b = Rectangle((x, 84), 16, 0, fc=C1, ec="none"); self.bg.add_patch(b); self.motor_bars.append(b)
        # ---- ticker
        self.tick_txt = self.t(14, 56, "", 7.3, TXT, va="top", mono=True)
        self.layer_flash = {"L3": -9, "L2": -9, "L1": 0, "L0": -9}

    def t(self, x, y, s, size, color, ha="left", weight="normal", va="center", mono=False):
        return self.bg.text(x, y, s, fontsize=size, color=color, ha=ha, va=va, weight=weight, family="monospace" if mono else "DejaVu Sans")

    def flash(self, layer, t):
        self.layer_flash[layer] = t

    def frame(self, d):
        t = d["t"]
        for name, (p, col) in self.cards.items():
            age = t - self.layer_flash.get(name, -9)
            p.set_linewidth(1.3 + 3.0 * max(0.0, 1 - age / 0.9)); p.set_edgecolor(col)
            p.set_alpha(1.0)
        self.l3_state.set_text(f"source: {d['source']}   calls: {d['calls']}   {d['latency']:.1f}s")
        cj = d["current"]
        self.job_txt.set_text(("NOW  >  " + NAMES.get(cj, cj).upper()) if cj else "NOW  >  (deciding)")
        for i, k in enumerate(KEYS):
            p = d["probs"].get(k, 0.0)
            done = self.jobs[k].done and k != "depot"
            self.bars[i].set_width(0.0 if done else p)
            self.bars[i].set_color("#4caf50" if done else (C3 if k == cj else "#6b5b95"))
            self.ptxt[i].set_x(max(p, 0.0) + 0.02 if not done else 0.02)
            self.ptxt[i].set_text("DONE" if done else (f"{p:.2f}" if p > 0.004 else ""))
        self.speed_txt.set_text(f"speed mode: {d['speed'].upper()}  ({d['v_lim']:.1f} m/s)")
        rc = {"low": "#69f0ae", "moderate": "#ffd54f", "high": "#ff9800", "critical": C0}[d["risk"]]
        o = d.get("oracle") or {}
        if o:
            ok = o.get("agree")
            self.orc_txt.set_text(f"oracle: {NAMES.get(o.get('best_first'), o.get('best_first'))}  " + ("MATCH" if ok else "regret %.0fs" % o.get("regret", 0)))
            self.orc_txt.set_color("#69f0ae" if ok else "#ffb74d")
        self.risk_txt.set_text(f"mission risk: {d['risk'].upper()}"); self.risk_txt.set_color(rc)
        self.stat_txt.set_text(f"done {d['done']}/{d['total']}   switches {d['switches']}")
        # L2
        for k, p in self.zone_p.items():
            p.set_alpha(0.45 if d["zones"].get(k) else 0.0)
        for k, pt in self.pad_p.items():
            if self.jobs[k].done and k != "depot": pt.set_color("#66bb6a")
        tr = d["trail"]
        if len(tr): self.trail.set_data(tr[:, 0], tr[:, 1])
        pa = d["path"]
        if pa is not None: self.pathl.set_data(pa[:, 0], pa[:, 1])
        else: self.pathl.set_data([], [])
        self.drone.set_data([d["pos"][0]], [d["pos"][1]])
        self.l2_txt.set_text(f"phase:   {d['phase']}\nroute:   {d['route_len']:.0f} m\nremain:  {d['remain']:.0f} m\n"
                             f"replans: {d['replans']}\nA* nodes:{d['expanded']:>6}\nno-fly:  {d['zone_names'] or '-'}")
        # L1
        v = d["speed_now"]
        for nm, val, txt in [("SPEED", v, f"{v:.1f} m/s"), ("ALT", d["pos"][2], f"{d['pos'][2]:.1f} m"),
                             ("TILT", d["tilt"], f"{d['tilt']:.0f} deg"), ("BATT", d["battery"], f"{d['battery']:.0f} %")]:
            bar, mx, valt, col = self.g[nm]
            bar.set_width(200 * float(np.clip(val / mx, 0, 1)))
            c = col if nm != "BATT" else ("#66bb6a" if d["battery"] > 35 else ("#ffb300" if d["battery"] > 18 else C0))
            bar.set_facecolor(c); valt.set_text(txt)
        for b, f in zip(self.motor_bars, d["rotors"]):
            b.set_height(62 * float(np.clip(f / 8.0, 0, 1)))
        lines = d["events"][-3:]
        self.tick_txt.set_text("\n".join(f"{e}" for e in lines))
        self.fig.canvas.draw()
        return np.asarray(self.fig.canvas.buffer_rgba())[..., :3].copy()
