# Results

Monte-Carlo over randomised missions (storm/no-fly timing and size, deadline, start battery, wind). Every configuration flies the *same* scenario per seed, so comparisons are paired.

| configuration | n | success (clean) | deadline met | time, successes (s) | lowest battery | building / zone violation (s) | oracle agreement | mean regret (s) | $ / mission |
|---|---|---|---|---|---|---|---|---|---|
| Jev hierarchy (L0-L3) | 24 | 88% (69-96), clean 20/24 | 100% (86-100) | 131 | 10% | 0.0 / 0.6 | 84% | 9.4 | 0.0014 |
| Rule-based dispatcher | 24 | 96% (80-99), clean 21/24 | 92% (74-98) | 133 | 13% | 0.0 / 0.6 | 89% | 2.4 | 0.0000 |
| Greedy dispatcher | 24 | 0% (0-14), clean 0/24 | 100% (86-100) | nan | 0% | 0.0 / 0.4 | 65% | 31.3 | 0.0000 |
| Jev, no A* planner | 24 | 100% (86-100), clean 0/24 | 100% (86-100) | 98 | 16% | 24.7 / 3.2 | - | - | 0.0011 |
| Jev, no L0 safety | 24 | 88% (69-96), clean 19/24 | 100% (86-100) | 132 | 10% | 0.0 / 0.6 | 84% | 9.2 | 0.0014 |

Success intervals are 95% Wilson; time is a mean over successful runs.

## Paired comparisons (same seed)

- **Jev hierarchy (L0-L3) vs Greedy dispatcher** over 24 seeds: success 21 wins / 0 losses (sign test p=0.000); on the 0 seeds both finished, Jev hierarchy (L0-L3) was faster in 0, slower in 0 (mean time saved +nan s, 95% CI +nan..+nan; sign test p=1.000).
- **Jev hierarchy (L0-L3) vs Rule-based dispatcher** over 24 seeds: success 1 wins / 3 losses (sign test p=0.625); on the 20 seeds both finished, Jev hierarchy (L0-L3) was faster in 0, slower in 20 (mean time saved -2.7 s, 95% CI -4.5..-1.4; sign test p=0.000).
- **Jev hierarchy (L0-L3) vs Jev, no A* planner** over 24 seeds: success 0 wins / 3 losses (sign test p=0.250); on the 21 seeds both finished, Jev hierarchy (L0-L3) was faster in 0, slower in 21 (mean time saved -32.7 s, 95% CI -39.7..-25.3; sign test p=0.000).
- **Jev hierarchy (L0-L3) vs Jev, no L0 safety** over 24 seeds: success 0 wins / 0 losses (sign test p=1.000); on the 21 seeds both finished, Jev hierarchy (L0-L3) was faster in 2, slower in 3 (mean time saved +1.2 s, 95% CI -0.2..+3.9; sign test p=1.000).

## Calibration of Jev's decisions

Treating the oracle's best first job as ground truth, Jev's stated probability for the job it chose has **ECE 0.128** and **Brier 0.152** (0 = perfect). See the reliability diagram in `analysis.png`.
