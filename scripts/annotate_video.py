"""Burn explanatory annotations into the demo video (no simulation or API calls).

    python scripts/annotate_video.py out/demo.mp4 docs/demo.mp4

The captions below are tied to the recorded seed-0 live run: video time equals simulation time
(24 fps), and every caption is taken from that run's event log. If you re-record, update CAPTIONS.
Captions only describe what is observable; Jev returns probabilities, not reasons.
"""

from __future__ import annotations

import sys
from pathlib import Path

import imageio
import matplotlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
F = lambda sz, b=False: ImageFont.truetype(str(FONT_DIR / ("DejaVuSans-Bold.ttf" if b else "DejaVuSans.ttf")), sz)

W3D, H = 800, 720
C = {"L3": (179, 136, 255), "L2": (255, 183, 77), "L1": (105, 240, 174), "!!": (255, 82, 82), "L0": (255, 82, 82)}
# (start s, end s, tag, headline, body lines)
CAPTIONS = [
    (0.0, 3.0, "L3", "t=0 s  Jev chooses the first job: CLINIC (p = 0.94)",
     ["Jev is given text describing every option (route length, ETA, battery cost, deadline) and answers with a probability",
      "for each. The planner (L2) prices the chosen route at 93 m."]),
    (3.0, 14.0, "L2", "Following the A* route through the street canyons",
     ["Cyan line = planned route. Towers over 18 m cannot be overflown (20 m ceiling), so it threads the streets.",
      "The quadrotor tracks it at 7 m/s; yellow dots are the trail already flown."]),
    (14.0, 16.5, "!!", "t=14 s  Storm cell appears: a new no-fly zone (red cylinder)",
     ["The planner re-plans around it at once. Here the drone is already ~3 m from the clinic,",
      "so the route barely changes."]),
    (16.5, 19.0, "L1", "Delivering: hovering over the Clinic pad",
     ["The pad turns green when the package is dropped (t = 19.0 s; the deadline was 60 s)."]),
    (19.0, 27.9, "L3", "t=19 s  Next job: BAKERY, but Jev is unsure (p = 0.30)",
     ["Low confidence: several options are close. The purple pillar marks the current goal;",
      "L2 prices a 48 m route and the drone flies it."]),
    (27.9, 30.4, "L1", "Delivering: Bakery", ["Pad turns green."]),
    (30.4, 36.0, "L3", "t=30 s  Next job: CAFE (p = 0.56), speed mode ECO",
     ["ECO = 4.5 m/s instead of 7 m/s: slower and cheaper in battery. Watch the BATT bar on the right."]),
    (36.0, 39.8, "!!", "t=36 s  Police-helicopter no-fly zone appears (second red cylinder)",
     ["A* re-plans again (21 m route to the Cafe). The drone stays outside every red zone."]),
    (39.8, 42.3, "L1", "Delivering: Cafe", ["Pad turns green."]),
    (42.3, 54.2, "L3", "t=42 s  Jev sends the drone home to recharge: DEPOT (p = 0.97)",
     ["Three deliveries done, battery low. L2 prices a 52 m return; speed stays ECO."]),
    (54.2, 57.6, "L1", "Descending to land on the depot pad", ["Motors will cut at touchdown."]),
    (57.6, 63.6, "L1", "Recharging (motors off): battery reached 7% at touchdown",
     ["The L0 safety trip level is 8%, but the drone was already returning, so L0 never fired.",
      "That is a thin margin. The pad restores 100% in 6 s."]),
    (63.6, 80.8, "L3", "t=64 s  Last delivery: APARTMENT (p = 0.73), speed NORMAL",
     ["Fully charged. L2 prices a 100 m route; the drone flies it at 7 m/s."]),
    (80.8, 83.3, "L1", "Delivering: Apartment", ["Last pad turns green: 4 of 4 delivered."]),
    (83.3, 100.5, "L3", "t=83 s  All delivered: Jev sends the drone home (p = 1.00)",
     ["100 m return route. Mission rule: when every delivery is done, return to the depot and land."]),
    (100.5, 105.0, "L1", "Landing at the depot: MISSION COMPLETE",
     ["4/4 delivered in 104 s  |  35 Jev calls  |  8 A* plans  |  0 s inside a building  |  oracle agreement 86%"]),
]
# (time, color-tag) markers on the timeline bar
MARKS = [(0.0, "L3"), (19.0, "L3"), (30.4, "L3"), (42.3, "L3"), (63.6, "L3"), (83.3, "L3"),
         (14.0, "!!"), (36.0, "!!"), (19.0, "L1"), (30.4, "L1"), (42.3, "L1"), (83.3, "L1")]
TOTAL = 104.0

LEGEND = [
    ((38, 198, 218), "cyan line + dots", "A* route planned by L2"),
    ((255, 217, 51), "yellow dots", "path already flown"),
    ((200, 77, 255), "purple pillar", "current goal"),
    ((255, 60, 60), "red cylinder", "no-fly zone (storm, helicopter)"),
    ((255, 170, 30), "orange / green disc", "delivery pad pending / done"),
    ((79, 195, 247), "blue disc", "depot (landing + charging pad)"),
    ((90, 255, 140), "glowing sphere", "the drone (red when battery low)"),
]
HUD_KEY = [
    ("L3 purple card", "Jev: P(next job) for each option, speed mode, risk", C["L3"]),
    ("L2 amber card", "top-down map: cyan route, red no-fly, dots = pads", C["L2"]),
    ("L1 green card", "speed / altitude / tilt / battery + rotor thrust", C["L1"]),
    ("oracle: X MATCH", "exhaustive-search best first job; MATCH = Jev agrees", (200, 200, 220)),
]


def rrect(d, box, fill, r=8):
    d.rounded_rectangle(box, radius=r, fill=fill)


def build_static():
    img = Image.new("RGBA", (W3D, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # HUD key (top-left)
    rrect(d, (10, 46, 430, 46 + 24 + 17 * len(HUD_KEY) + 6), (8, 12, 24, 215))
    d.text((20, 52), "HOW TO READ THE RIGHT-HAND PANEL", font=F(10, True), fill=(160, 175, 205, 255))
    for i, (a, b, col) in enumerate(HUD_KEY):
        y = 72 + 17 * i
        d.rectangle((20, y + 3, 28, y + 11), fill=col + (255,))
        d.text((34, y), a, font=F(10.5, True), fill=(235, 240, 255, 255))
        d.text((152, y), b, font=F(10.5), fill=(190, 200, 225, 255))
    # 3D legend (bottom-left, above caption)
    top = 612 - 22 - 16 * len(LEGEND)
    rrect(d, (10, top, 372, 606), (8, 12, 24, 205))
    d.text((20, top + 5), "3D VIEW KEY", font=F(10, True), fill=(160, 175, 205, 255))
    for i, (col, a, b) in enumerate(LEGEND):
        y = top + 22 + 16 * i
        d.rectangle((20, y + 3, 30, y + 11), fill=col + (255,))
        d.text((38, y), a, font=F(10.5, True), fill=(235, 240, 255, 255))
        d.text((190, y), b, font=F(10.5), fill=(190, 200, 225, 255))
    return img


def build_caption(tag, head, body):
    img = Image.new("RGBA", (W3D, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    col = C[tag]
    rrect(d, (10, 618, W3D - 10, 700), (8, 12, 24, 232), r=10)
    d.rectangle((10, 626, 15, 692), fill=col + (255,))
    label = {"L3": "L3 JEV", "L2": "L2 PLANNER", "L1": "L1 CONTROL", "!!": "EVENT", "L0": "L0 SAFETY"}[tag]
    d.text((24, 624), label, font=F(9, True), fill=col + (255,))
    d.text((24, 637), head, font=F(13, True), fill=(240, 244, 255, 255))
    for i, line in enumerate(body[:2]):
        d.text((24, 657 + 15 * i), line, font=F(10.5), fill=(190, 202, 228, 255))
    return img


def main(src, dst):
    reader = imageio.get_reader(src)
    fps = reader.get_meta_data()["fps"]
    writer = imageio.get_writer(dst, fps=fps, codec="libx264", pixelformat="yuv420p", macro_block_size=1,
                                ffmpeg_params=["-crf", "23", "-preset", "medium", "-movflags", "+faststart"])
    static = build_static()
    caps = [(a, b, build_caption(tag, h, bd)) for a, b, tag, h, bd in CAPTIONS]
    clock_f, n = F(12, True), 0
    bar_x0, bar_x1, bar_y = 16, W3D - 16, 708
    for frame in reader:
        t = n / fps
        base = Image.fromarray(frame).convert("RGBA")
        left = base.crop((0, 0, W3D, H))
        left = Image.alpha_composite(left, static)
        for a, b, ov in caps:
            if a <= t < b:
                left = Image.alpha_composite(left, ov)
                break
        d = ImageDraw.Draw(left)
        rrect(d, (10, 10, 430, 40), (8, 12, 24, 215))
        d.text((20, 17), f"t = {t:5.1f} s", font=clock_f, fill=(255, 255, 255, 255))
        d.text((110, 18), "live Jev run, seed 0  |  video time = simulation time", font=F(10), fill=(170, 185, 215, 255))
        d.rectangle((bar_x0, bar_y, bar_x1, bar_y + 4), fill=(40, 52, 80, 255))
        for mt, tag in MARKS:
            x = bar_x0 + (bar_x1 - bar_x0) * mt / TOTAL
            d.rectangle((x - 1, bar_y - 3, x + 1, bar_y + 7), fill=C[tag] + (255,))
        px = bar_x0 + (bar_x1 - bar_x0) * min(t, TOTAL) / TOTAL
        d.rectangle((bar_x0, bar_y, px, bar_y + 4), fill=(255, 255, 255, 120))
        d.ellipse((px - 4, bar_y - 2, px + 4, bar_y + 6), fill=(255, 255, 255, 255))
        out = base.copy()
        out.paste(left.convert("RGB"), (0, 0))
        writer.append_data(np.asarray(out.convert("RGB")))
        n += 1
    writer.close()
    print(f"annotated {n} frames -> {dst}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
