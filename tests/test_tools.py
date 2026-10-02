"""Statistics helpers, rollout seed parsing and the video-annotation tables."""

import importlib.util
import math
from pathlib import Path

import numpy as np
import pytest

import analyze
import rollout

ROOT = Path(__file__).resolve().parent.parent


# ---------- Wilson interval ----------
def test_wilson_all_successes_matches_the_known_interval():
    p, lo, hi = analyze.wilson(10, 10)
    assert p == 1.0 and hi == pytest.approx(1.0) and lo == pytest.approx(0.7225, abs=2e-3)


def test_wilson_no_successes_mirrors_it():
    p, lo, hi = analyze.wilson(0, 10)
    assert p == 0.0 and lo == pytest.approx(0.0, abs=1e-9) and hi == pytest.approx(0.2775, abs=2e-3)


def test_wilson_is_symmetric_around_half_and_bounded():
    p, lo, hi = analyze.wilson(12, 24)
    assert p == 0.5 and lo + hi == pytest.approx(1.0)
    for k in range(0, 25):
        _, l, h = analyze.wilson(k, 24)
        assert 0.0 <= l <= k / 24 <= h <= 1.0


def test_wilson_interval_narrows_with_more_data():
    w = lambda n: analyze.wilson(n // 2, n)[2] - analyze.wilson(n // 2, n)[1]
    assert w(400) < w(40) < w(10)


def test_wilson_with_no_trials_is_zeroes():
    assert analyze.wilson(0, 0) == (0.0, 0.0, 0.0)


# ---------- sign test ----------
def test_sign_test_extremes():
    assert analyze.sign_test(0, 0) == 1.0
    assert analyze.sign_test(5, 5) == 1.0
    assert analyze.sign_test(10, 0) == pytest.approx(2 / 1024)
    assert analyze.sign_test(0, 10) == pytest.approx(2 / 1024)


def test_sign_test_is_symmetric_and_a_probability():
    for w in range(0, 15):
        for l in range(0, 15):
            p = analyze.sign_test(w, l)
            assert 0.0 <= p <= 1.0 and p == pytest.approx(analyze.sign_test(l, w))


def test_sign_test_matches_the_exact_binomial_for_a_known_case():
    # 9 wins / 1 loss: 2 * (1 + 10) / 1024
    assert analyze.sign_test(9, 1) == pytest.approx(22 / 1024)


# ---------- bootstrap ----------
def test_bootstrap_mean_lies_inside_its_interval_and_is_reproducible():
    x = np.arange(1.0, 21.0)
    m, lo, hi = analyze.boot_ci(x)
    assert m == pytest.approx(10.5) and lo < m < hi
    assert analyze.boot_ci(x) == (m, lo, hi)


def test_bootstrap_of_a_constant_is_degenerate_and_empty_is_nan():
    assert analyze.boot_ci([3.0, 3.0, 3.0]) == (3.0, 3.0, 3.0)
    assert all(math.isnan(v) for v in analyze.boot_ci([]))


# ---------- rollout ----------
def test_parse_seeds_handles_ranges_lists_and_mixes():
    assert rollout.parse_seeds("1-3") == [1, 2, 3]
    assert rollout.parse_seeds("5") == [5]
    assert rollout.parse_seeds("1-3,7,10-11") == [1, 2, 3, 7, 10, 11]


def test_rollout_configs_cover_the_ablations_with_expected_switches():
    c = rollout.CONFIGS
    assert c["jev"] == ("jev", "astar", True)
    assert c["jev_noplan"][1] == "straight" and c["jev_nosafety"][2] is False
    assert c["greedy"][0] == "greedy" and c["rules"][0] == "rules"


# ---------- video annotation tables ----------
@pytest.fixture(scope="module")
def ann():
    spec = importlib.util.spec_from_file_location("annotate_video", ROOT / "scripts" / "annotate_video.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_captions_tile_the_timeline_without_gaps_or_overlaps(ann):
    caps = sorted(ann.CAPTIONS)
    assert caps[0][0] == 0.0
    for prev, nxt in zip(caps[:-1], caps[1:]):
        assert prev[1] == nxt[0]                  # contiguous
    assert caps[-1][1] >= ann.TOTAL


def test_every_caption_tag_has_a_colour_and_at_most_two_body_lines(ann):
    for start, end, tag, head, body in ann.CAPTIONS:
        assert tag in ann.C and start < end and head and 1 <= len(body) <= 2


def test_marks_are_inside_the_video_and_use_known_tags(ann):
    assert all(0.0 <= t <= ann.TOTAL and tag in ann.C for t, tag in ann.MARKS)


def test_overlays_are_rendered_at_the_3d_panel_size(ann):
    assert ann.build_static().size == (ann.W3D, ann.H)
    start, end, tag, head, body = ann.CAPTIONS[0]
    assert ann.build_caption(tag, head, body).size == (ann.W3D, ann.H)
