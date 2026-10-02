"""Mutation check: do the tests actually notice when the code is wrong?

Each "mutant" is the project with ONE deliberate bug. The suite is run against it; a mutant is
"caught" if at least one test fails. A mutant that survives means the tests are blind to that bug.

    python scripts/mutation_check.py

Mutants are applied to a throw-away copy under .tmp/, never to your working tree.
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".tmp" / "mutation_work"
COPY = ["jevplanner", "tests", "scripts", "analyze.py", "rollout.py", "pytest.ini"]

# (description, file, original text, buggy text)
MUTANTS = [
    ("planner: no safety margin around buildings", "jevplanner/planner.py", "margin: float = 2.5", "margin: float = 0.0"),
    ("planner: vertical moves cost nothing", "jevplanner/planner.py", "(1.6 * dz) ** 2", "(0.0 * dz) ** 2"),
    ("rules: ignore the battery reserve", "jevplanner/strategist.py", "battery - o.need - o.home >= 10", "battery - o.need - o.home >= -999"),
    ("prompt: drop the 'safety first' rule", "jevplanner/strategist.py", "SAFETY IS A HARD CONSTRAINT", "NOTE"),
    ("L0: trip level 8% -> 0%", "jevplanner/mission.py", "SAFETY_BATT = 8.0", "SAFETY_BATT = 0.0"),
    ("L0: override never latches", "jevplanner/mission.py", "self.l0_latch = True", "self.l0_latch = False"),
    ("controller: yaw sign error in the mixer", "jevplanner/physics.py", "[s * KYAW for _, _, s in ROTORS]], dtype=float)", "[-s * KYAW for _, _, s in ROTORS]], dtype=float)"),
    ("controller: tilt limit removed", "jevplanner/physics.py", "MAX_TILT = 38.0", "MAX_TILT = 89.0"),
    ("oracle: battery reserve removed", "jevplanner/oracle.py", "CHARGE_S, RESERVE = 6.0, 1.75, 6.0, 10.0", "CHARGE_S, RESERVE = 6.0, 1.75, 6.0, -50.0"),
    ("stats: sign test not doubled (one-sided)", "analyze.py", "return min(1.0, 2 * sum(", "return min(1.0, 1 * sum("),
    ("client: API cost never accumulated", "jevplanner/jev_client.py", "self.total_cost += float(", "_ = float("),
    ("scenario: pad-clearance check disabled", "jevplanner/scenario.py", "if clear:", "if True:"),
]


def pytest_in(work: Path):
    return subprocess.run([sys.executable, "-m", "pytest", "-x", "-q", "-W", "ignore", "-p", "no:cacheprovider"],
                          cwd=work, capture_output=True, text=True, timeout=600)


def main():
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    for item in COPY:
        src = ROOT / item
        if src.is_dir():
            shutil.copytree(src, WORK / item, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy(src, WORK / item)

    base = pytest_in(WORK)
    if base.returncode != 0:
        sys.exit("baseline suite fails on the unmodified copy; fix that before mutating\n" + base.stdout[-800:])
    print("baseline: all tests pass on the unmodified copy\n")

    caught = 0
    for name, rel, old, new in MUTANTS:
        target = WORK / rel
        original = target.read_text(encoding="utf-8")
        if old not in original:
            print(f"SKIP    {name} (pattern not found; update MUTANTS)")
            continue
        target.write_text(original.replace(old, new, 1), encoding="utf-8")
        r = pytest_in(WORK)
        target.write_text(original, encoding="utf-8")
        killed = r.returncode != 0
        caught += killed
        first = next((l for l in r.stdout.splitlines() if l.startswith("FAILED")), "")
        print(f"{'CAUGHT' if killed else 'SURVIVED':8s}{name:46s} {first[7:100]}")
    print(f"\n{caught}/{len(MUTANTS)} mutants caught")
    shutil.rmtree(WORK, ignore_errors=True)
    sys.exit(0 if caught == len(MUTANTS) else 1)


if __name__ == "__main__":
    main()
