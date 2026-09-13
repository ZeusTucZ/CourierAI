# Smart V2 Diagnostic

## 1. Changes Made

Smart v2 separates idle full-order scoring from batching marginal scoring. It adds a progressive commitment penalty, explicit per-route SLA margins, a soft SLA-risk penalty, accurate internal causes, and diagnostic-only route economics.

Skip pressure is absent from the production decision flow and remains absent here. The configured reservation wage is unchanged. No automatic tuning was performed.

## 2. Idle Scoring

`final_score = net_pay + dropoff_value - opportunity_cost - commitment_penalty - reservation_wage × service_time / 60`

## 3. Commitment Penalty

`max(0, commitment_horizon_min - 25) × 2 MXN/min`

## 4. Batch Marginal Scoring

`final_score = incremental_net_pay - reservation_wage × incremental_time / 60 - sla_risk_penalty`

Incremental net pay is candidate gross pay minus incremental route operating cost. Total existing-route time does not enter the batch value-of-time charge.

## 5. SLA Margin

Each insertion computes `deadline - predicted_arrival` for every active and candidate order and uses the minimum. Negative margin is infeasible. Otherwise risk is `max(0, 10 - minimum_margin) × 2 MXN/min`.

## 6. Current vs Improved Results

| Metric | Current | Improved |
|---|---:|---:|
| Acceptance rate | 7.83% | 6.51% |
| Skip rate | 92.17% | 93.49% |
| Mean net earnings/shift | 935.02 | 759.13 |
| Completed orders/shift | 9.50 | 7.90 |
| Mean accepted service min | 28.62 | 25.70 |
| Mean accepted adjusted MXN/h | 205.57 | 221.99 |
| Mean commitment horizon min | 29.21 | 26.33 |
| Mean missed while busy | 7.12 | 6.27 |
| Mean / max skip streak | 11.08 / 35 | 13.20 / 55 |
| SLA/stacking skips | 654 (58.45%) | 475 (41.85%) |
| Late deliveries | 3 | 0 |
| Safety violations | 0 | 0 |

## 7. Decision Examples

### Example A — long order rejected by commitment penalty

`{"commitment_horizon_min": 69.96132716666666, "commitment_penalty_mxn": 89.92265433333333, "decision": "SKIP", "final_score_mxn": -218.51023662816652, "incremental_distance_km": 19.700552988749894, "incremental_time_min": 69.96132716666666, "minimum_sla_margin_min": 0.0, "mode": "idle", "order_id": "ORD-00011", "reason": "Skipped: 70.0 min idle commitment loses value after a MXN 89.9 commitment penalty.", "seed": 1, "service_time_min": 69.96132716666666, "source": null}`

### Example B — nearby batch accepted on small marginal cost

`{"commitment_horizon_min": 34.0, "commitment_penalty_mxn": 0.0, "decision": "ACCEPT", "final_score_mxn": 35.65, "incremental_distance_km": 0.5, "incremental_time_min": 5.0, "minimum_sla_margin_min": 36.0, "mode": "batching", "order_id": "SYN-SMALL-BATCH", "reason": "Accepted: batch adds 5.0 min and 0.5 km while preserving SLA margin.", "seed": 9002, "service_time_min": 5.0, "source": "controlled synthetic scenario, not tuning evidence"}`

### Example C — batch rejected by infeasible SLA

`{"commitment_horizon_min": 65.30942496666667, "commitment_penalty_mxn": null, "decision": "SKIP", "final_score_mxn": null, "incremental_distance_km": null, "incremental_time_min": null, "minimum_sla_margin_min": -28.349894300000003, "mode": "batching", "order_id": "ORD-00002", "reason": "Skipped: no insertion preserves every active and candidate SLA deadline.", "seed": 1, "service_time_min": 36.959530666666666, "source": null}`

### Example D — high-value long order accepted

`{"commitment_horizon_min": 55.0, "commitment_penalty_mxn": 60.0, "decision": "ACCEPT", "final_score_mxn": 185.14999999999998, "incremental_distance_km": 3.0, "incremental_time_min": 55.0, "minimum_sla_margin_min": 0.0, "mode": "idle", "order_id": "SYN-LONG-HIGH", "reason": "Accepted: 55.0 min idle commitment has strong net value after commitment risk.", "seed": 9001, "service_time_min": 55.0, "source": "controlled synthetic scenario, not tuning evidence"}`

## 8. Long-order Lock-in

Accepted >40 min: Current 2, Improved 0. Accepted >60 min: Current 0, Improved 0.

Per-order downstream arrivals, missed orders, and newly infeasible offers are included in `decision_diff.csv`.

## 9. Batch Performance

`{"count": 10, "mean_incremental_distance_km": 4.749379039635451, "mean_incremental_net_pay_mxn": 93.33738485243747, "mean_incremental_time_min": 23.35250969333333, "minimum_sla_margin_min": 0.9779644166666667}`

## 10. Safety

Safety violations remained 0. Hard constraints run before strategic scoring.

Regression suite: 338 pre-existing tests + 12 added Smart v2 tests = 350 passing tests.

## 11. Limitations

These are ten tuning seeds from the same simulator. SLA and opportunity models remain synthetic/calibrated assumptions. The insertion heuristic is bounded and no solver was added. Results are diagnostic, not held-out evidence.

## 12. Recommendation

The fixed Smart v2 logic did not improve mean tuning net earnings. Do not promote it; inspect decision diffs before changing parameters.
