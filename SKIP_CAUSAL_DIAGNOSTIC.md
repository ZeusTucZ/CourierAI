# SKIP Causal Diagnostic

## 1. Executive Summary

Across 10 tuning seeds, Old accepted 7.83% and reconstructed New accepted 8.40%. New's skips are 0.72% reservation wage, 4.50% busy/commitment, 86.24% SLA/stacking, and 8.54% hard constraints. Safety skips are reported separately and are not treated as strategic rejection failures.

This checkout does not reproduce the stated premise that New accepts less: it accepts 7 more orders, while earning materially less. That discrepancy is evidence and is not normalized away. No recommendations appear before the interpretation sections below.

## 2. Configurations Compared

- Old: base reservation wage 165 MXN/h; all calibrated policy fields unchanged.
- New: diagnostic reconstruction of base 60 MXN/h, `min(20, consecutive_skips × 2.5)` pressure, effective floor 40 MXN/h; streak resets after ACCEPT.
- Seeds: tuning 1–10 only. Official held-out seeds were neither read by the runner nor executed.
- Repository caveat: the checked-out production code has no skip-pressure implementation or New artifacts; therefore New is reproduced only in this isolated diagnostic runner.

## 3. Overall Acceptance / Skip Metrics

| metric | Old | New |
|---|---|---|
| orders offered | 1214 | 1214 |
| acceptance rate | 7.83% | 8.40% |
| skip rate | 92.17% | 91.60% |
| mean idle min/shift | 207.54 | 54.90 |
| total net earnings | 9350.18 | 7918.32 |
| mean net/shift | 935.02 | 791.83 |

## 4. Skip Cause Breakdown

| config | cause | count | % skips | % orders |
|---|---|---|---|---|
| old | sla_infeasible | 597 | 53.35 | 49.18 |
| old | reservation_wage | 412 | 36.82 | 33.94 |
| old | shift_end_infeasible | 46 | 4.11 | 3.79 |
| old | stacking_infeasible | 39 | 3.49 | 3.21 |
| old | active_commitment_infeasible | 18 | 1.61 | 1.48 |
| old | flagged_zone_night | 7 | 0.63 | 0.58 |
| new | sla_infeasible | 930 | 83.63 | 76.61 |
| new | mandatory_break | 54 | 4.86 | 4.45 |
| new | active_commitment_infeasible | 50 | 4.50 | 4.12 |
| new | shift_end_infeasible | 37 | 3.33 | 3.05 |
| new | stacking_infeasible | 29 | 2.61 | 2.39 |
| new | reservation_wage | 8 | 0.72 | 0.66 |
| new | flagged_zone_night | 4 | 0.36 | 0.33 |

Important attribution finding: when insertion fails, `StrategicSimulator._offer` exposes `binding_constraint=reservation_wage` even though its reason says SLA/active commitment. The table uses reconstructed insertion exits, not that ambiguous public enum.

## 5. Reservation Wage Analysis

Old margin distribution (adjusted rate − effective threshold):
| P10 | P25 | P50 | P75 | P90 | mean | n |
|---|---|---|---|---|---|---|
| -122.51 | -105.87 | -75.68 | -44.37 | -16.59 | -74.12 | 412 |

Offline only; number of the observed economic skips whose adjusted rate meets each threshold:
| threshold | orders crossing |
|---|---|
| 165 | 0 |
| 125 | 92 |
| 100 | 161 |
| 80 | 234 |
| 60 | 307 |
| 40 | 375 |

New margin distribution (adjusted rate − effective threshold):
| P10 | P25 | P50 | P75 | P90 | mean | n |
|---|---|---|---|---|---|---|
| -24.70 | -23.91 | -22.90 | -14.75 | -5.47 | -18.18 | 8 |

Offline only; number of the observed economic skips whose adjusted rate meets each threshold:
| threshold | orders crossing |
|---|---|
| 165 | 0 |
| 125 | 0 |
| 100 | 0 |
| 80 | 0 |
| 60 | 0 |
| 40 | 1 |

In New, skip pressure was nonzero for 1102 offers (90.77%), averaged 13.66 MXN/h when active, reached 20.00, and put 991 offers at the 40 MXN/h floor. 3 accepts crossed the live decision boundary only because pressure lowered the nominal threshold. Threshold crossing counts above are static post-hoc checks, not replays.

## 6. Busy / Commitment Analysis

Busy/commitment accounts for 1.61% of Old skips and 4.50% of New skips. `not_actionable_while_busy` means no agent choice occurred (reposition reservation or max-active gate); `active_commitment_infeasible` means every insertion would break an already accepted deadline.
Mean skipped arrivals during each accepted order's occupied window: Old 7.12, New 9.99. Detailed work, route distance, SLA, projected completion, and reason fields are retained in the diagnostic event rows summarized in `summary.json`; worst lock-ins are in `long_order_lockin.csv`.

## 7. SLA / Stacking Analysis

SLA/stacking accounts for 56.84% of Old skips and 86.24% of New skips. `sla_infeasible` means every candidate route misses the new order's deadline; `stacking_infeasible` means no route jointly preserves all deadlines.

## 8. Skip Streak Analysis

| metric | Old | New |
|---|---|---|
| mean | 11.08 | 10.49 |
| median | 10.00 | 10.00 |
| P90 | 20.00 | 16.50 |
| max | 35 | 28 |

## 9. Old vs New Decision Transitions

Transitions: {"ACCEPT->SKIP": 74, "SKIP->ACCEPT": 81}. Per-order rates, durations, distances, missed real-replay opportunities, and post-hoc economic impact are in `decision_transitions.csv`.

## 10. Long-order Lock-in

Ten New accepts with the most skipped arrivals during their occupied windows:
| seed | order | occupied min | arrivals | busy skips | order net |
|---|---|---|---|---|---|
| 2 | ORD-00001 | 75.82 | 27 | 27 | 95.64 |
| 2 | ORD-00055 | 76.49 | 24 | 24 | 49.61 |
| 9 | ORD-00084 | 75.22 | 22 | 22 | 90.01 |
| 10 | ORD-00074 | 68.43 | 22 | 22 | 95.81 |
| 8 | ORD-00002 | 65.17 | 18 | 18 | 84.04 |
| 9 | ORD-00046 | 54.72 | 18 | 18 | 103.07 |
| 7 | ORD-00073 | 46.79 | 18 | 17 | 41.12 |
| 6 | ORD-00064 | 59.44 | 17 | 16 | 73.27 |
| 7 | ORD-00056 | 59.08 | 16 | 16 | 72.23 |
| 8 | ORD-00034 | 55.31 | 16 | 16 | 71.12 |

## 11. Economic Consequences

| metric | Old | New |
|---|---|---|
| mean accepted adjusted rate | 205.57 | 129.19 |
| mean accepted service time | 28.62 | 40.19 |
| total net earnings | 9350.18 | 7918.32 |

Worst New-only accepts by order net minus accepted Old opportunities during the actual New occupied window:
| seed | order | order net | lost opps | lost MXN | impact |
|---|---|---|---|---|---|
| 10 | ORD-00048 | 56.55 | 2 | 233.95 | -177.40 |
| 8 | ORD-00034 | 71.12 | 2 | 216.03 | -144.92 |
| 6 | ORD-00010 | 53.01 | 2 | 196.67 | -143.66 |
| 9 | ORD-00084 | 90.01 | 2 | 230.22 | -140.21 |
| 7 | ORD-00056 | 72.23 | 2 | 202.60 | -130.37 |
| 4 | ORD-00034 | 97.45 | 2 | 226.31 | -128.86 |
| 7 | ORD-00103 | 47.50 | 2 | 173.06 | -125.56 |
| 2 | ORD-00055 | 49.61 | 2 | 171.54 | -121.93 |
| 7 | ORD-00019 | 89.87 | 2 | 201.11 | -111.24 |
| 4 | ORD-00091 | 87.69 | 2 | 194.72 | -107.03 |

- Seed 10 / ORD-00048: gained 56.55 MXN, overlapped 2 Old accepts worth 233.95 MXN, for post-hoc impact -177.40 MXN.
- Seed 8 / ORD-00034: gained 71.12 MXN, overlapped 2 Old accepts worth 216.03 MXN, for post-hoc impact -144.92 MXN.
- Seed 6 / ORD-00010: gained 53.01 MXN, overlapped 2 Old accepts worth 196.67 MXN, for post-hoc impact -143.66 MXN.
- Seed 9 / ORD-00084: gained 90.01 MXN, overlapped 2 Old accepts worth 230.22 MXN, for post-hoc impact -140.21 MXN.
- Seed 7 / ORD-00056: gained 72.23 MXN, overlapped 2 Old accepts worth 202.60 MXN, for post-hoc impact -130.37 MXN.
- Seed 4 / ORD-00034: gained 97.45 MXN, overlapped 2 Old accepts worth 226.31 MXN, for post-hoc impact -128.86 MXN.
- Seed 7 / ORD-00103: gained 47.50 MXN, overlapped 2 Old accepts worth 173.06 MXN, for post-hoc impact -125.56 MXN.
- Seed 2 / ORD-00055: gained 49.61 MXN, overlapped 2 Old accepts worth 171.54 MXN, for post-hoc impact -121.93 MXN.
- Seed 7 / ORD-00019: gained 89.87 MXN, overlapped 2 Old accepts worth 201.11 MXN, for post-hoc impact -111.24 MXN.
- Seed 4 / ORD-00091: gained 87.69 MXN, overlapped 2 Old accepts worth 194.72 MXN, for post-hoc impact -107.03 MXN.

This opportunity calculation is descriptive post-hoc attribution over the two real replays. It is not a new predictive model and is not an independent intervention estimate when occupied windows overlap.

## 12. Rerouting Observations

No reroute rows can be truthfully produced by this replay path. `StrategicSimulator` represents closures as abstract delays and does not emit `closure_id`, old/new route, distance, or ETA. `rerouting_effects.csv` therefore contains its schema and zero fabricated observations.

## 13. Root Cause Interpretation

The largest New skip family is SLA/stacking. Lowering the economic gate changes which orders enter the active route; those acceptances change future feasibility, so acceptance rate is not monotone in a threshold under a stateful replay. The cause mix and transition rows show whether economic skips were exchanged for non-actionable/busy and SLA skips.

### Answers to the ten main questions

1. Reservation wage: 0.72% of New skips.
2. Busy/commitment: 4.50%.
3. SLA/stacking: 86.24%.
4. Hard constraints: 8.54%.
5. It did not reduce acceptance in the reproducible checkout: reconstructed New accepted 102 versus Old's 95. It did reduce earnings because accepted work became longer and lower-rate, and changed the future feasibility path.
6. The ten largest observed losses are listed in Section 11 and `decision_transitions.csv`.
7. Yes, but narrowly: 3 accepts crossed only because of pressure; pressure was nonzero on 90.77% of offers and was frequently capped by the floor.
8. The before/after mix is economic 36.82%→0.72% and busy 1.61%→4.50%.
9. The current bottleneck is SLA/stacking.
10. The true problem is the largest reconstructed gate above, not the simulator's ambiguous public `reservation_wage` fallback label.

## 14. Possible Next Experiments

- Replay one-at-a-time decision interventions for the worst New-only accepts while freezing all exogenous events.
- Add first-class insertion-failure enums and route-before/after closure telemetry, then repeat this same frozen diagnostic.
- Run an ablation of skip pressure with the New base/floor on tuning seeds only; do not use it as tuning until the causal attribution is reviewed.

No experiment above was implemented by this task.

## 15. Limitations

- New was reconstructed because the requested configuration is absent from the checked-out code and Git history available locally.
- The pressure reset convention (after ACCEPT) is an explicit assumption; the requested formula did not specify reset semantics.
- Opportunity loss uses observed replay windows and cannot isolate interacting or overlapping acceptances.
- Abstract synthetic routing cannot support the requested geospatial rerouting fields.

## Required Final Summary

| required metric | Old | New |
|---|---|---|
| acceptance rate | 7.83% | 8.40% |
| skip rate | 92.17% | 91.60% |
| % skips reservation wage | 36.82% | 0.72% |
| % skips busy/commitment | 1.61% | 4.50% |
| % skips SLA/stacking | 56.84% | 86.24% |
| % skips hard constraints | 4.74% | 8.54% |
| mean accepted adjusted rate | 205.57 | 129.19 |
| mean accepted service time | 28.62 | 40.19 |
| mean missed orders while busy | 7.12 | 9.99 |
| mean skip streak | 11.08 | 10.49 |
| max skip streak | 35 | 28 |
| net earnings (10 shifts) | 9350.18 | 7918.32 |

"The dominant cause of excessive skipping is SLA/stacking feasibility."
