# Results

Monte-Carlo over randomised missions (storm/no-fly timing and size, deadline, start battery, wind). Every configuration flies the *same* scenario per seed, so comparisons are paired.

| configuration | n | success (clean) | deadline met | time, successes (s) | lowest battery | building / zone violation (s) | oracle agreement | mean regret (s) | $ / mission |
|---|---|---|---|---|---|---|---|---|---|
| Jev hierarchy (L0-L3) | 24 | 96% (80-99), clean 19/24 | 92% (74-98) | 139 | 11% | 0.0 / 0.6 | 86% | 8.2 | 0.0016 |
| Rule-based dispatcher | 24 | 100% (86-100), clean 20/24 | 92% (74-98) | 129 | 14% | 0.1 / 0.6 | 89% | 1.9 | 0.0000 |
| Greedy dispatcher | 24 | 0% (0-14), clean 0/24 | 100% (86-100) | nan | 0% | 0.0 / 0.7 | 62% | 36.3 | 0.0000 |
| Jev, no A* planner | 24 | 100% (86-100), clean 0/24 | 100% (86-100) | 106 | 20% | 27.5 / 7.3 | - | - | 0.0012 |
| Jev, no L0 safety | 24 | 96% (80-99), clean 19/24 | 92% (74-98) | 138 | 11% | 0.0 / 0.6 | 85% | 8.5 | 0.0016 |

Success intervals are 95% Wilson; time is a mean over successful runs.

## Paired comparisons (same seed)

- **Jev hierarchy (L0-L3) vs Greedy dispatcher** over 24 seeds: success 23 wins / 0 losses (sign test p=0.000); on the 0 seeds both finished, Jev hierarchy (L0-L3) was faster in 0, slower in 0 (mean time saved +nan s, 95% CI +nan..+nan; sign test p=1.000).
- **Jev hierarchy (L0-L3) vs Rule-based dispatcher** over 24 seeds: success 0 wins / 1 losses (sign test p=1.000); on the 23 seeds both finished, Jev hierarchy (L0-L3) was faster in 1, slower in 20 (mean time saved -8.5 s, 95% CI -15.8..-1.8; sign test p=0.000).
- **Jev hierarchy (L0-L3) vs Jev, no A* planner** over 24 seeds: success 0 wins / 1 losses (sign test p=1.000); on the 23 seeds both finished, Jev hierarchy (L0-L3) was faster in 0, slower in 23 (mean time saved -32.0 s, 95% CI -39.3..-24.8; sign test p=0.000).
- **Jev hierarchy (L0-L3) vs Jev, no L0 safety** over 24 seeds: success 0 wins / 0 losses (sign test p=1.000); on the 23 seeds both finished, Jev hierarchy (L0-L3) was faster in 5, slower in 5 (mean time saved -0.4 s, 95% CI -1.3..+0.2; sign test p=1.000).

## Calibration of Jev's decisions

Treating the oracle's best first job as ground truth, Jev's stated probability for the job it chose has **ECE 0.061** and **Brier 0.114** (0 = perfect). See the reliability diagram in `analysis.png`.
