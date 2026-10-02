"""L1 - flight control: MuJoCo quadrotor + geometric SO(3) cascade controller.

500 Hz rigid-body physics with four rotor thrusts, yaw reaction torque and first-order
motor lag. The controller (100 Hz) turns a position target into a desired attitude and
collective thrust, then body torques, then four rotor commands through the mixer.
"""

from __future__ import annotations

import numpy as np

from .world import CENTERS, HALF, HEIGHTS, Building, Job, Zone

MASS = 1.5
INERTIA = np.array([0.0125, 0.0125, 0.022])
ARM, KYAW, MAX_F, MOTOR_TAU, G = 0.2, 0.016, 8.0, 0.03, 9.81
SIM_DT, CTRL_EVERY = 0.002, 5
ROTORS = [(+ARM, +ARM, +1), (+ARM, -ARM, -1), (-ARM, -ARM, +1), (-ARM, +ARM, -1)]
MIX = np.array([[1, 1, 1, 1], [y for _, y, _ in ROTORS], [-x for x, _, _ in ROTORS],
                [s * KYAW for _, _, s in ROTORS]], dtype=float)
MIX_INV = np.linalg.inv(MIX)
KP, KD, KR, KW = 6.0, 4.0, 60.0, 10.0
MAX_TILT = 38.0


def _tower_rgba(h: float):
    t = (h - 12) / 18.0
    return (0.28 + 0.22 * t, 0.36 + 0.14 * t, 0.52 + 0.20 * t, 1)


def build_xml(buildings, jobs, zones) -> str:
    bld = ""
    for b in buildings:
        r, g, bl, _ = _tower_rgba(b.h)
        bld += (f'<geom type="box" pos="{b.cx} {b.cy} 0.1" size="{HALF + 1.4} {HALF + 1.4} 0.1" rgba=".42 .44 .47 1" contype="0" conaffinity="0"/>'
                f'<geom type="box" pos="{b.cx} {b.cy} {b.h / 2}" size="{b.hx} {b.hy} {b.h / 2}" rgba="{r} {g} {bl} 0.62" contype="0" conaffinity="0"/>'
                f'<geom type="box" pos="{b.cx} {b.cy} {b.h + 0.12}" size="{b.hx + 0.25} {b.hy + 0.25} 0.12" rgba=".8 .85 .95 1" contype="0" conaffinity="0"/>')
        # window bands
        for k in range(1, 0):
            z = k * 5.0
            bld += (f'<geom type="box" pos="{b.cx} {b.cy} {z}" size="{b.hx + 0.04} {b.hy + 0.04} 0.28" rgba="1 .86 .55 .35" contype="0" conaffinity="0"/>')
    pads = ""
    for j in jobs:
        rgba = "0.2 0.55 1 1" if j.kind == "depot" else "1 0.7 0.1 1"
        pads += f'<geom name="pad_{j.key}" type="cylinder" pos="{j.x} {j.y} 0.05" size="3 0.05" rgba="{rgba}" contype="0" conaffinity="0"/>'
    zs = "".join(f'<geom name="zone_{z.key}" type="cylinder" pos="{z.cx} {z.cy} 20" size="{z.r} 20" rgba="1 .15 .15 0" contype="0" conaffinity="0"/>'
                 for z in zones)
    arms = "".join(
        f'<geom type="capsule" fromto="0 0 0 {x} {y} 0" size="0.012" rgba=".15 .15 .18 1"/>'
        f'<geom type="cylinder" pos="{x} {y} 0.012" size="0.09 0.006" rgba="{"1 .3 .2 1" if s > 0 else ".2 .6 1 1"}"/>'
        f'<site name="r{i}" pos="{x} {y} 0"/>' for i, (x, y, s) in enumerate(ROTORS))
    motors = "".join(f'<motor name="m{i}" site="r{i}" gear="0 0 1 0 0 {s * KYAW}" ctrlrange="0 {MAX_F}"/>'
                     for i, (_, _, s) in enumerate(ROTORS))
    return f"""
<mujoco model="city">
  <option timestep="{SIM_DT}" gravity="0 0 -{G}"/>
  <visual><global offwidth="800" offheight="720"/><quality shadowsize="4096"/>
          <headlight ambient=".35 .35 .4" diffuse=".5 .5 .55"/></visual>
  <asset>
    <texture type="skybox" builtin="gradient" rgb1=".95 .62 .42" rgb2=".07 .09 .22" width="512" height="512"/>
    <texture name="asph" type="2d" builtin="checker" rgb1=".13 .14 .17" rgb2=".16 .17 .2" width="256" height="256"/>
    <material name="asph" texture="asph" texrepeat="40 40" reflectance=".08"/>
  </asset>
  <worldbody>
    <light pos="-60 -40 90" dir="0.5 0.4 -1" diffuse="1 .85 .7" specular=".3 .3 .3" castshadow="true"/>
    <light pos="80 90 60" dir="-0.4 -0.5 -1" diffuse=".35 .4 .6" castshadow="false"/>
    <geom type="plane" pos="39 39 0" size="120 120 .1" material="asph"/>
    {bld}{pads}{zs}
    <body name="quad" pos="0 0 0.08">
      <freejoint/>
      <inertial pos="0 0 0" mass="{MASS}" diaginertia="{INERTIA[0]} {INERTIA[1]} {INERTIA[2]}"/>
      <geom type="box" size=".07 .07 .025" rgba=".2 .2 .25 1" contype="0" conaffinity="0"/>
      <geom type="box" pos=".09 0 0" size=".03 .015 .01" rgba="1 .8 0 1" contype="0" conaffinity="0"/>
      {arms}
    </body>
  </worldbody>
  <actuator>{motors}</actuator>
</mujoco>"""


def vee(M):
    return np.array([M[2, 1], M[0, 2], M[1, 0]])


def controller(pos, vel, R, omega, target, v_lim):
    """Geometric position/attitude controller -> four rotor thrusts (N)."""
    err = target - pos
    L = v_lim * KD / KP
    n = np.linalg.norm(err)
    if n > L:
        err = err * L / n
    a = KP * err - KD * vel
    amax = G * np.tan(np.radians(MAX_TILT))
    h = np.linalg.norm(a[:2])
    if h > amax:
        a[:2] *= amax / h
    a[2] = np.clip(a[2], -6.0, 8.0)
    a_des = a + np.array([0, 0, G])
    zb = a_des / np.linalg.norm(a_des)
    # yaw follows the direction of travel loosely (looks natural, costs nothing)
    yb = np.cross(zb, [1.0, 0.0, 0.0]); yb /= np.linalg.norm(yb)
    xb = np.cross(yb, zb)
    Rd = np.column_stack([xb, yb, zb])
    eR = 0.5 * vee(Rd.T @ R - R.T @ Rd)
    T = max(0.0, MASS * float(a_des @ R[:, 2]))
    tau = INERTIA * (-KR * eR - KW * omega) + np.cross(omega, INERTIA * omega)
    f = MIX_INV @ np.array([T, *tau])
    return np.clip(f, 0.0, MAX_F)
