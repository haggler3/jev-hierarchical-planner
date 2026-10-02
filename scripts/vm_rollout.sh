#!/usr/bin/env bash
# Run the Monte-Carlo rollouts on a Linux VM (e.g. the n1-standard-4 spot VM in ../infra).
# This workload is CPU + API bound - MuJoCo, A*, and HTTP calls to Jev. The T4 GPU is not used,
# so a plain 8-16 vCPU spot instance is the better (cheaper) fit if you rent one for this.
#
#   export OPENROUTER_API_KEY=sk-or-...
#   bash scripts/vm_rollout.sh 1-96 8          # seeds 1..96, 8 workers
set -euo pipefail
SEEDS="${1:-1-24}"
WORKERS="${2:-$(nproc)}"

cd "$(dirname "$0")/.."
python3 -m venv .venv
. .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

# MuJoCo is headless here (no rendering is needed for rollouts).
python -u rollout.py --seeds "$SEEDS" --workers "$WORKERS" --out results
python analyze.py --results results
echo "done: docs/analysis.png, docs/RESULTS.md, results/summary.csv"

# Spot pre-emption safe: results/raw/<config>_<seed>.json are written per rollout, so simply
# re-run this script after a restart and finished rollouts are skipped.
