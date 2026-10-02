"""Mission: the closed loop that wires L3 Jev -> L2 A* -> L1 MuJoCo control (+ L0 safety)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import imageio
import mujoco
import numpy as np

from .hud import Hud
from .oracle import Oracle
from .physics import CTRL_EVERY, MOTOR_TAU, SIM_DT, build_xml, controller
from .planner import PathFollower, Planner, path_length
from .scenario import Scenario, make_scenario
from .strategist import SPEED_MODES, Option, Strategist
from .world import make_buildings, make_jobs, make_zones

FPS, DECIDE_EVERY, T_MAX = 24, 2.5, 220.0
DRAIN_PER_N = 0.105          # % battery per (N * s) of total rotor thrust  (~1.5 %/s hovering)
V_EST, RATE_EST = 6.0, 1.75  # planning-time speed and drain estimates used in Jev's job descriptions
CHARGE_S = 6.0
SAFETY_BATT = 8.0


class Mission:
    def __init__(self, strat: Strategist, record: bool, out: Path, scenario: Optional[Scenario] = None,
                 planner_mode: str = "astar", use_oracle: bool = True, safety: bool = True, verbose: bool = True):
        self.verbose = verbose
        self.strat, self.record, self.out = strat, record, out
        self.sc = scenario or make_scenario(0)
        self.planner_mode, self.safety_on = planner_mode, safety
        self.buildings, self.jobs, self.zones = make_buildings(), make_jobs(), make_zones()
        self.zones[0].cx, self.zones[0].cy = self.sc.storm_xy
        self.zones[0].r, self.zones[0].t_on = self.sc.storm_r, self.sc.storm_t
        self.zones[1].cx, self.zones[1].cy = self.sc.heli_xy
        self.zones[1].r, self.zones[1].t_on = self.sc.heli_r, self.sc.heli_t
        self.jobs[0].deadline = self.sc.deadline
        self.jd = {j.key: j for j in self.jobs}
        self.planner = Planner(self.buildings)
        self.oracle = Oracle(self.planner, self.jobs) if (use_oracle and planner_mode == "astar") else None
        self.bld_viol = self.zone_viol = 0.0
        self.min_batt, self.safety_overrides, self.clinic_t = 100.0, 0, None
        self.battery = self.sc.battery0
        self.model = mujoco.MjModel.from_xml_string(build_xml(self.buildings, self.jobs, self.zones))
        self.data = mujoco.MjData(self.model)
        self.data.qpos[:3] = [0, 0, 0.08]
        mujoco.mj_forward(self.model, self.data)
        self.t = 0.0
        self.f_cmd = np.zeros(4); self.f_act = np.zeros(4)
        self.phase, self.current = "transit", None
        self.path, self.follower = None, None
        self.speed_name, self.risk, self.probs = "normal", "low", {}
        self.source, self.latency, self.confidence = "-", 0.0, 0.0
        self.events, self.switches, self.replans = [], 0, 0
        self.timeline, self.log, self.trail = [], [], []
        self.hold_t0 = self.charge_t0 = 0.0
        self.charge_b0 = 100.0
        self.next_decide, self.force = 0.0, True
        self.finished = self.crashed = False
        self.decisions = []
        self.oracle_info = {}
        self.l0_latch = False
        self.route_len = 0.0
        self.step_i = 0
        self.min_clear = 1e9
        self.flash = {}
        self.pos = self.data.qpos[:3].copy()
        if record:
            self.renderer = mujoco.Renderer(self.model, 720, 800, max_geom=4000)
            self.hud = Hud(self.buildings, self.jobs, self.zones)
            self.writer = imageio.get_writer(out / "demo.mp4", fps=FPS, macro_block_size=1, quality=8)
            self.cam = mujoco.MjvCamera(); self.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
            self.cam.distance, self.cam.elevation = 128.0, -44.0
            self.look = np.array([10.0, 10.0, 6.0])
            self.hud_img = None

    # ---------- helpers ----------
    def ev(self, layer, msg):
        s = f"{self.t:5.1f}s {layer} {msg}"
        self.events.append(s)
        if self.verbose:
            print(s)
        self.flash[layer] = self.t

    def goal(self, key):
        j = self.jd[key]
        return np.array([j.x, j.y, 4.0])

    def pending(self):
        return [j for j in self.jobs if j.kind == "deliver" and not j.done]

    def plan(self, start, goal):
        if self.planner_mode == "straight":
            return np.array([np.array(start, float), np.array(goal, float)])
        return self.planner.plan(start, goal)

    def build_options(self):
        opts, paths = {}, {}
        cands = self.pending() + [self.jd["depot"]]
        for j in cands:
            p = self.plan(self.pos, self.goal(j.key))
            if p is None:
                opts[j.key] = Option(j.key, j.label, j.note, float("nan"), 0, 0, 0, reachable=False, is_depot=j.kind == "depot")
                continue
            L = path_length(p)
            drive = L / V_EST
            eta = drive + 3.0
            if j.kind == "depot":
                home = 0.0
            elif self.oracle is not None:
                home = self.oracle.home_need(j.key)
                home = 99.0 if not math.isfinite(home) else home
            else:
                home = (math.hypot(j.x, j.y) * 1.4 / V_EST) * RATE_EST
            dl = None if j.deadline is None else j.deadline - self.t
            opts[j.key] = Option(j.key, j.label, j.note, L, eta, eta * RATE_EST, home, dl, True, j.kind == "depot")
            paths[j.key] = p
        return opts, paths

    def hazards_text(self):
        act = [z for z in self.zones if z.active]
        return "none" if not act else "; ".join(f"{z.label} active around ({z.cx:.0f},{z.cy:.0f}), radius {z.r:.0f} m (no-fly)" for z in act)

    def set_path(self, p):
        self.path = p
        self.follower = PathFollower(p) if p is not None and len(p) > 1 else None
        self.route_len = path_length(p) if p is not None else 0.0

    def replan(self, why):
        if not self.current:
            return
        p = self.plan(self.pos, self.goal(self.current))
        self.set_path(p)
        self.replans += 1
        self.ev("L2", f"A* re-plan ({why}): {self.route_len:.0f} m, {self.planner.expanded} nodes" if p is not None
                else f"A* re-plan ({why}): NO ROUTE")

    # ---------- L3 ----------
    def decide(self):
        opts, paths = self.build_options()
        all_done = not self.pending()
        dec = self.strat.decide(self.t, self.pos, self.battery, sum(j.done for j in self.jobs if j.kind == "deliver"),
                                4, opts, self.current, self.hazards_text(), all_done)
        self.flash["L3"] = self.t
        self.probs, self.speed_name, self.risk = dec.probs, dec.speed, dec.risk
        self.source, self.latency, self.confidence = dec.source, dec.latency, dec.confidence
        cur_ok = self.current in opts and opts[self.current].reachable and (self.current == "depot" or not self.jd[self.current].done)
        new = dec.choice
        switch = None
        if self.l0_latch:
            switch = None  # safety supervisor owns the vehicle until it has recharged
        elif self.current is None or not cur_ok:
            switch = new
        elif new != self.current and dec.probs.get(new, 0) >= dec.probs.get(self.current, 0) + 0.15:
            switch = new
        orc = {}
        if self.oracle is not None:
            dl = {j.key: j.deadline - self.t for j in self.pending() if j.deadline is not None}
            orc = self.oracle.evaluate(opts, self.battery, [j.key for j in self.pending()], dec.choice, dl)
        self.oracle_info = orc
        self.decisions.append({"t": round(self.t, 1), "battery": round(self.battery, 1), "choice": dec.choice, "applied": switch,
                               "conf": round(dec.probs.get(dec.choice, 0.0), 4), "oracle_first": orc.get("best_first"),
                               "agree": orc.get("agree"), "regret": round(orc.get("regret", 0.0), 2), "latency": round(dec.latency, 2),
                               "probs": {k: round(v, 3) for k, v in dec.probs.items()}, "speed": dec.speed, "risk": dec.risk,
                               "source": dec.source, "state": dec.state_text})
        if switch and switch != self.current:
            if self.current is not None:
                self.switches += 1
            self.current = switch
            self.set_path(paths.get(switch))
            self.replans += 1
            self.ev("L3", f"{'Jev' if self.strat.policy == 'jev' else self.strat.policy} -> {self.jd[switch].label.upper()} (p={dec.probs.get(switch, 0):.2f}, risk {dec.risk}, {dec.speed})")
            self.ev("L2", f"A* route: {self.route_len:.0f} m")
            self.timeline.append((self.t, switch))

    # ---------- main loop ----------
    def run(self):
        d, m = self.data, self.model
        next_frame, next_trail = 0.0, 0.0
        while self.t < T_MAX and not self.finished and not self.crashed:
            self.pos = d.qpos[:3].copy()
            pos, vel = self.pos, d.qvel[:3].copy()
            R = np.zeros(9); mujoco.mju_quat2Mat(R, d.qpos[3:7]); R = R.reshape(3, 3)
            omega = d.qvel[3:6].copy()
            tilt = float(np.degrees(np.arccos(np.clip(R[2, 2], -1, 1))))

            for z in self.zones:  # world events
                if not z.active and self.t >= z.t_on:
                    z.active = True
                    m.geom_rgba[m.geom(f"zone_{z.key}").id] = [1, .15, .15, .30]
                    self.planner.set_zones(self.zones)
                    self.ev("!!", f"{z.label.upper()} appears at ({z.cx:.0f},{z.cy:.0f}) r={z.r:.0f} m")
                    self.force = True
                    if self.current and self.planner_mode == "astar":
                        self.replan("new no-fly zone")

            # L0 safety supervisor
            if self.safety_on and self.battery < SAFETY_BATT and self.current != "depot" and self.phase in ("transit", "hold"):
                self.safety_overrides += 1
                self.l0_latch = True
                self.current = "depot"; self.phase = "transit"
                self.ev("L0", f"SAFETY OVERRIDE: battery {self.battery:.0f}% -> forcing return to depot")
                self.replan("safety override")

            # L3 decision cadence
            if self.phase in ("transit",) and (self.force or self.t >= self.next_decide):
                self.decide()
                self.force, self.next_decide = False, self.t + DECIDE_EVERY

            # L2 path health check
            if self.planner_mode == "astar" and self.phase == "transit" and self.path is not None and self.step_i % 250 == 0:
                if self.planner.path_blocked(self.path, self.follower.idx if self.follower else 0):
                    self.replan("route blocked")

            v_mode = SPEED_MODES.get(self.speed_name, 7.0)
            target, v_lim, hover = pos.copy(), 1.0, False
            if self.phase == "transit":
                if self.follower is not None and self.current:
                    la = float(np.clip(0.6 * v_mode, 3.0, 6.0))
                    carrot, rem = self.follower.carrot(pos, la)
                    target, v_lim = carrot, min(v_mode, math.sqrt(2 * 1.4 * max(rem, 0)) + 0.7)
                    if rem < 1.0 and np.linalg.norm(vel) < 2.0 and np.linalg.norm(pos - self.goal(self.current)) < 2.5:
                        if self.jd[self.current].kind == "deliver":
                            self.phase, self.hold_t0 = "hold", self.t
                            self.ev("L1", f"arrived over {self.jd[self.current].label}, delivering")
                        else:
                            self.phase = "landing"
                            self.ev("L1", "over depot, descending to land")
                else:
                    target = np.array([pos[0], pos[1], max(pos[2], 4.0)])
            elif self.phase == "hold":
                target, v_lim = self.goal(self.current), 1.5
                if self.t - self.hold_t0 > 2.5:
                    j = self.jd[self.current]
                    j.done = True
                    if j.key == "clinic":
                        self.clinic_t = self.t
                    m.geom_rgba[m.geom(f"pad_{j.key}").id] = [.3, 1, .45, 1]
                    self.ev("L1", f"package delivered: {j.label}")
                    self.current, self.path, self.follower, self.phase, self.force = None, None, None, "transit", True
            elif self.phase == "landing":
                j = self.jd["depot"]
                target, v_lim = np.array([j.x, j.y, -0.3]), 1.2
                if pos[2] < 0.14:
                    if not self.pending():
                        self.phase, self.finished = "finished", True
                        self.ev("L1", "landed at depot - MISSION COMPLETE")
                    else:
                        self.phase, self.charge_t0, self.charge_b0 = "charging", self.t, self.battery
                        self.ev("L1", f"landed, recharging from {self.battery:.0f}%")
            elif self.phase == "charging":
                frac = min(1.0, (self.t - self.charge_t0) / CHARGE_S)
                self.battery = self.charge_b0 + (100 - self.charge_b0) * frac
                if frac >= 1.0:
                    self.l0_latch = False
                    self.ev("L1", "battery 100%, taking off")
                    self.current, self.path, self.follower, self.phase, self.force = None, None, None, "transit", True

            if self.phase != "charging":
                if self.step_i % CTRL_EVERY == 0:
                    self.f_cmd = controller(pos, vel, R, omega, target, v_lim)
                self.f_act += (self.f_cmd - self.f_act) * SIM_DT / MOTOR_TAU
                d.ctrl[:] = self.f_act
                self.battery = max(0.0, self.battery - DRAIN_PER_N * self.f_act.sum() * SIM_DT)
            else:
                self.f_act[:] = 0; d.ctrl[:] = 0
            d.xfrc_applied[1, :3] = [self.sc.wind * (0.5 + 0.3 * math.sin(0.5 * self.t)), -0.4 * self.sc.wind, 0.0]
            mujoco.mj_step(m, d)
            self.t += SIM_DT; self.step_i += 1
            if self.battery <= 0.0 and self.phase != "charging":
                self.crashed = True
                self.ev("L1", "BATTERY EMPTY - crash")

            if self.step_i % 25 == 0:
                self.log.append((self.t, *pos, float(np.linalg.norm(vel)), tilt, self.battery))
                cl = self.clearance(pos)
                self.min_clear = min(self.min_clear, cl)
                if cl < 0:
                    self.bld_viol += 0.05
                if any(z.active and math.hypot(pos[0] - z.cx, pos[1] - z.cy) < z.r for z in self.zones):
                    self.zone_viol += 0.05
                if self.phase != "charging":
                    self.min_batt = min(self.min_batt, self.battery)
            if self.t >= next_trail:
                next_trail += 0.25; self.trail.append(pos.copy())
            if self.record and self.t >= next_frame:
                next_frame += 1.0 / FPS
                self.render_frame(pos, vel, tilt)
        if self.record:
            self.writer.close()

    def result(self) -> dict:
        n_done = sum(j.done for j in self.jobs if j.kind == "deliver")
        ds = [d for d in self.decisions if d.get("agree") is not None]
        lat = self.strat.latencies
        return dict(
            seed=self.sc.seed, policy=self.strat.policy, planner=self.planner_mode, safety=self.safety_on,
            outcome="complete" if self.finished else ("crash" if self.crashed else "timeout"),
            success=bool(self.finished and n_done == 4), deliveries=n_done, t_total=round(self.t, 2),
            clinic_t=None if self.clinic_t is None else round(self.clinic_t, 2), deadline=round(self.sc.deadline, 1),
            deadline_met=bool(self.clinic_t is not None and self.clinic_t <= self.sc.deadline),
            battery_end=round(self.battery, 1), min_battery=round(self.min_batt, 1), battery0=round(self.sc.battery0, 1),
            min_clear=round(self.min_clear, 2), bld_viol_s=round(self.bld_viol, 2), zone_viol_s=round(self.zone_viol, 2),
            replans=self.replans, switches=self.switches, safety_overrides=self.safety_overrides,
            n_decisions=len(self.decisions), agree=(float(np.mean([d["agree"] for d in ds])) if ds else None),
            mean_regret=(float(np.mean([d["regret"] for d in ds])) if ds else None),
            jev_calls=self.strat.calls, jev_fallbacks=self.strat.fails,
            lat_mean=(float(np.mean(lat)) if lat else None),
            cost=getattr(getattr(self.strat, "client", None), "total_cost", 0.0), decisions=self.decisions)

    def clearance(self, p):
        c = 1e9
        for b in self.buildings:
            dx = max(abs(p[0] - b.cx) - b.hx, 0); dy = max(abs(p[1] - b.cy) - b.hy, 0); dz = max(p[2] - b.h, 0) if p[2] > 0 else 0
            c = min(c, math.sqrt(dx * dx + dy * dy + dz * dz) if (dx > 0 or dy > 0 or dz > 0) else -1.0)
        return c

    # ---------- rendering ----------
    def render_frame(self, pos, vel, tilt):
        cam = self.cam
        cam.lookat[:] = np.array([39.0, 33.0, 4.0])
        cam.azimuth = 205.0 + 0.3 * self.t
        r = self.renderer
        r.update_scene(self.data, cam)
        sc = r.scene

        def add(kind, size, p, rgba):
            if sc.ngeom >= sc.maxgeom - 2:
                return None
            g = sc.geoms[sc.ngeom]
            mujoco.mjv_initGeom(g, kind, np.array(size, float), np.array(p, float), np.eye(3).flatten(), np.array(rgba, dtype=np.float32))
            sc.ngeom += 1
            return g

        for p in self.trail[-260:]:
            add(mujoco.mjtGeom.mjGEOM_SPHERE, [0.4, 0, 0], p, [1, .85, .2, .9])
        if self.path is not None and len(self.path) > 1:
            for a, b in zip(self.path[:-1], self.path[1:]):
                g = add(mujoco.mjtGeom.mjGEOM_CAPSULE, [0.2, 0, 0], a, [.15, .85, .95, .75])
                if g is not None:
                    mujoco.mjv_connector(g, mujoco.mjtGeom.mjGEOM_CAPSULE, 0.4, a, b)
            for q in self.path:
                add(mujoco.mjtGeom.mjGEOM_SPHERE, [0.8, 0, 0], q, [.15, .95, 1, .95])
        if self.current:
            gp = self.goal(self.current)
            g = add(mujoco.mjtGeom.mjGEOM_CAPSULE, [0.3, 0, 0], gp, [.9, .3, 1, .55])
            if g is not None:
                mujoco.mjv_connector(g, mujoco.mjtGeom.mjGEOM_CAPSULE, 0.6, np.array([gp[0], gp[1], 0.3]), np.array([gp[0], gp[1], 30.0]))
        add(mujoco.mjtGeom.mjGEOM_SPHERE, [2.6, 0, 0], pos, [.2, 1, .5, .35] if self.battery > 18 else [1, .25, .2, .45])
        left = r.render()
        self.hud_img = self.hud_frame(pos, vel, tilt)
        self.writer.append_data(np.hstack([left, self.hud_img]))

    def hud_frame(self, pos, vel, tilt):
        for layer, t0 in self.flash.items():
            if layer in ("L3", "L2", "L1", "L0"):
                self.hud.flash(layer, t0)
        self.hud.flash("L1", self.t if self.phase != "charging" else -9)
        done = sum(j.done for j in self.jobs if j.kind == "deliver")
        rem = self.follower.total - self.follower.progress(pos) if self.follower else 0.0
        d = dict(t=self.t, source=self.source, calls=self.strat.calls, latency=self.latency, current=self.current,
                 probs=self.probs, speed=self.speed_name, v_lim=SPEED_MODES.get(self.speed_name, 7.0), risk=self.risk,
                 done=done, total=4, switches=self.switches, zones={z.key: z.active for z in self.zones},
                 trail=np.array(self.trail) if self.trail else np.zeros((0, 3)),
                 path=self.path, pos=pos, phase=self.phase.upper(), route_len=self.route_len, remain=max(rem, 0.0),
                 replans=self.replans, expanded=self.planner.expanded,
                 zone_names=", ".join(z.key for z in self.zones if z.active), speed_now=float(np.linalg.norm(vel)),
                 tilt=tilt, battery=self.battery, rotors=self.f_act.copy(), events=self.events, oracle=self.oracle_info)
        return self.hud.frame(d)


