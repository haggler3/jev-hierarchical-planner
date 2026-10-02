"""Draws docs/architecture.png (the layered control diagram used in the README)."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

BG, CARD, TXT, DIM = "#0a0f1c", "#111a2e", "#e8eefc", "#8fa0c4"
fig, ax = plt.subplots(figsize=(13, 7.4), facecolor=BG)
ax.set_xlim(0, 130); ax.set_ylim(0, 74); ax.axis("off")


def box(x, y, w, h, color, title, lines, rate):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=2", fc=CARD, ec=color, lw=2.2))
    ax.text(x + 2.5, y + h - 3.4, title, color=color, fontsize=13, weight="bold", va="center")
    ax.text(x + w - 2.5, y + h - 3.4, rate, color=DIM, fontsize=9.5, va="center", ha="right")
    for i, s in enumerate(lines):
        ax.text(x + 2.5, y + h - 8.2 - i * 3.9, s, color=TXT, fontsize=9.6, va="center")


box(4, 50, 82, 21, "#b388ff", "L3  JEV  -  strategic dispatcher", [
    "reads a live text description of every option (route, ETA, battery, deadline)",
    "returns TYPED answers + calibrated probabilities: next_job, speed, risk",
    "decides WHAT to do and WHY - never touches a motor or a waypoint"], "~0.4 Hz  |  ~0.4 s / call")
box(4, 27, 82, 20, "#ffb74d", "L2  PLANNER  -  tactical", [
    "3D weighted A* over a voxel city: towers, canyons, ceiling, no-fly zones",
    "line-of-sight smoothing, lookahead carrot, automatic re-plan when a zone appears",
    "prices every candidate goal and reports the cost back up to L3"], "on demand  |  ~60 ms")
box(4, 4, 82, 20, "#69f0ae", "L1  CONTROL  -  flight", [
    "geometric SO(3) controller: position -> attitude -> body torque -> 4-rotor mixer",
    "MuJoCo rigid-body physics: rotor thrust + yaw torque, motor lag, wind",
    "tracks the path at the speed mode L3 asked for"], "100 Hz ctrl  |  500 Hz physics")

# L0 + oracle on the right
ax.add_patch(FancyBboxPatch((94, 36), 32, 35, boxstyle="round,pad=0,rounding_size=2", fc=CARD, ec="#ff5252", lw=2.2))
ax.text(97, 67.6, "L0  SAFETY", color="#ff5252", fontsize=13, weight="bold", va="center")
for i, s in enumerate(["battery < 8% ?", "-> override L3,", "   latch 'return to depot'", "   until recharged", "", "deterministic, cannot be", "talked out of it"]):
    ax.text(97, 62.5 - i * 3.9, s, color=TXT, fontsize=9.6, va="center")
ax.add_patch(FancyBboxPatch((94, 4), 32, 28, boxstyle="round,pad=0,rounding_size=2", fc=CARD, ec="#4dd0e1", lw=2.2, ls="--"))
ax.text(97, 28.6, "ORACLE (analysis)", color="#4dd0e1", fontsize=11.5, weight="bold", va="center")
for i, s in enumerate(["exhaustive search over all", "job orders + recharge stops", "", "scores every L3 decision:", "agreement, regret, calibration"]):
    ax.text(97, 23.5 - i * 3.9, s, color=TXT, fontsize=9.6, va="center")


def arrow(p, q, color, label=None, rad=0.0, lx=2.0, ly=0.0, ha="left"):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=18, lw=2, color=color, connectionstyle=f"arc3,rad={rad}"))
    if label:
        ax.text(max(p[0], q[0]) + lx if ha == "left" else min(p[0], q[0]) + lx, (p[1] + q[1]) / 2 + ly, label, color=color, fontsize=8.8, ha=ha, va="center", weight="bold")


arrow((14, 50), (14, 47), "#b388ff", "goal job + speed mode")
arrow((56, 47), (56, 50), "#ffb74d", "route length, ETA, feasibility")
arrow((14, 27), (14, 24), "#ffb74d", "path + carrot")
arrow((56, 24), (56, 27), "#69f0ae", "pose, speed, battery")
arrow((86, 52), (94, 56), "#ff5252")
arrow((94, 42), (86, 36), "#ff5252", "override", lx=-8, ly=-3.5, ha="left")
arrow((94, 22), (86, 56), "#4dd0e1", rad=-0.25)

ax.text(65, 72.6, "Hierarchical autonomy: a language-grounded decision model above a classical planner and flight controller",
        color=TXT, fontsize=13, weight="bold", ha="center")
Path(__file__).resolve().parent.parent.joinpath("docs").mkdir(exist_ok=True)
fig.savefig(Path(__file__).resolve().parent.parent / "docs" / "architecture.png", dpi=140, facecolor=BG, bbox_inches="tight")
print("ok")
