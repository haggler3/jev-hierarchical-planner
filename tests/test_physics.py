import mujoco
import numpy as np
import pytest

from jevplanner import physics as P
from jevplanner.world import make_buildings, make_jobs, make_zones


def make_model():
    return mujoco.MjModel.from_xml_string(P.build_xml(make_buildings(), make_jobs(), make_zones()))


def state_of(data):
    R = np.zeros(9)
    mujoco.mju_quat2Mat(R, data.qpos[3:7])
    return data.qpos[:3].copy(), data.qvel[:3].copy(), R.reshape(3, 3), data.qvel[3:6].copy()


def test_xml_compiles_with_four_rotors_and_named_scene_objects():
    m = make_model()
    assert m.nu == 4
    for name in ("pad_clinic", "pad_depot", "zone_storm", "zone_heli"):
        assert m.geom(name).id >= 0


def test_zone_cylinders_start_invisible():
    m = make_model()
    assert m.geom_rgba[m.geom("zone_storm").id][3] == 0.0


def test_mixer_is_invertible_and_round_trips():
    assert np.allclose(P.MIX @ P.MIX_INV, np.eye(4), atol=1e-9)
    f = np.array([3.0, 4.0, 3.5, 4.5])
    assert np.allclose(P.MIX_INV @ (P.MIX @ f), f)


def test_equal_rotor_thrust_gives_pure_collective_thrust():
    out = P.MIX @ np.full(4, 3.0)
    assert out[0] == pytest.approx(12.0) and np.allclose(out[1:], 0.0, atol=1e-9)


def test_controller_hover_command_balances_weight_equally():
    pos = np.array([5.0, 5.0, 6.0])
    f = P.controller(pos, np.zeros(3), np.eye(3), np.zeros(3), pos.copy(), v_lim=3.0)
    assert f.sum() == pytest.approx(P.MASS * P.G, rel=1e-6)
    assert np.allclose(f, f[0], atol=1e-6)


def test_controller_output_respects_rotor_limits_for_extreme_requests():
    pos = np.zeros(3)
    for target in ([500, 0, 0], [0, 0, 500], [0, 0, -500], [-300, 200, 100]):
        f = P.controller(pos, np.zeros(3), np.eye(3), np.zeros(3), np.array(target, float), v_lim=9.5)
        assert (f >= 0).all() and (f <= P.MAX_F).all()


def test_controller_pitches_toward_a_forward_target():
    pos = np.array([0.0, 0.0, 6.0])
    f = P.controller(pos, np.zeros(3), np.eye(3), np.zeros(3), pos + [10, 0, 0], v_lim=5.0)
    front, back = f[0] + f[1], f[2] + f[3]      # rotors at +x vs -x
    assert back > front                          # nose-down: more thrust at the back


def test_speed_limit_scales_the_commanded_acceleration():
    pos = np.array([0.0, 0.0, 6.0])
    slow = P.controller(pos, np.zeros(3), np.eye(3), np.zeros(3), pos + [50, 0, 0], v_lim=1.0)
    fast = P.controller(pos, np.zeros(3), np.eye(3), np.zeros(3), pos + [50, 0, 0], v_lim=9.0)
    assert abs((fast[2] + fast[3]) - (fast[0] + fast[1])) > abs((slow[2] + slow[3]) - (slow[0] + slow[1]))


@pytest.mark.slow
def test_closed_loop_hover_is_stable_for_two_seconds():
    m = make_model()
    d = mujoco.MjData(m)
    d.qpos[:3] = [5.0, 5.0, 6.0]
    mujoco.mj_forward(m, d)
    target = d.qpos[:3].copy()
    f_act = np.full(4, P.MASS * P.G / 4)
    f_cmd = f_act.copy()
    for k in range(1000):
        pos, vel, R, om = state_of(d)
        if k % P.CTRL_EVERY == 0:
            f_cmd = P.controller(pos, vel, R, om, target, v_lim=2.0)
        f_act += (f_cmd - f_act) * P.SIM_DT / P.MOTOR_TAU
        d.ctrl[:] = f_act
        mujoco.mj_step(m, d)
    pos, vel, R, om = state_of(d)
    assert np.linalg.norm(pos - target) < 0.05 and np.linalg.norm(vel) < 0.05
    assert np.degrees(np.arccos(np.clip(R[2, 2], -1, 1))) < 1.0


@pytest.mark.slow
def test_closed_loop_reaches_a_waypoint_within_tilt_and_speed_limits():
    m = make_model()
    d = mujoco.MjData(m)
    d.qpos[:3] = [5.0, 5.0, 6.0]
    mujoco.mj_forward(m, d)
    target = np.array([15.0, 5.0, 6.0])
    f_act = np.full(4, P.MASS * P.G / 4)
    f_cmd = f_act.copy()
    max_tilt = max_speed = 0.0
    for k in range(5000):          # 10 s
        pos, vel, R, om = state_of(d)
        if k % P.CTRL_EVERY == 0:
            f_cmd = P.controller(pos, vel, R, om, target, v_lim=4.0)
        f_act += (f_cmd - f_act) * P.SIM_DT / P.MOTOR_TAU
        d.ctrl[:] = f_act
        mujoco.mj_step(m, d)
        max_tilt = max(max_tilt, np.degrees(np.arccos(np.clip(R[2, 2], -1, 1))))
        max_speed = max(max_speed, np.linalg.norm(vel))
    pos, vel, _, _ = state_of(d)
    assert np.linalg.norm(pos - target) < 0.3
    assert max_tilt < 45 and max_speed < 6.0
