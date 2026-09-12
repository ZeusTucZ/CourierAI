# Courier — MVP 3: calibrated simulation and interpretable strategy

MVP 3 extends the existing engine, event loop, state, constraints and replay. It adds
offline calibration, zone/hour predictions, snapshot updates, repositioning, bounded
pickup/delivery insertion, fixed delivery SLAs, exceptional cancellation, held-out
evaluation and component ablations. `/decide` still returns ACCEPT/SKIP and does not
load data, train models, call APIs or update strategies during a request.

**The included calibrated profile is fitted to synthetic tuning history, not real
delivery observations.** This validates the experiment pipeline and mechanics. It
does not establish that the policy earns these amounts in a real delivery market.
No external dataset was supplied or downloaded. CSV/JSON/JSONL and a Solomon adapter
are available for subsequent external calibration. No MVP 4 features were added.

## Reproduce

From the repository root with Python 3.11+ and `requirements-dev.txt` installed:

```bash
python -m scripts.prepare_mvp3_data
python -m scripts.run_tuning
python -m scripts.run_ablations
python -m scripts.run_heldout_evaluation
python -m scripts.benchmark_mvp3 --iterations 1000
python -m pytest -q
python -m scripts.replay_shift evaluation/heldout_results/seed-10001/SmartAgent.jsonl
python validate_format.py --event-log evaluation/heldout_results/seed-10001/SmartAgent.jsonl
```

On this checkout use `.venv/bin/python` instead of `python`, or activate `.venv`.
Generated datasets, models, manifests, benchmarks and logs are ignored by Git and
are recreated by these commands. No additional runtime dependency is required.

The optional MVP 3 HTTP startup reads a precomputed snapshot once at startup:

```bash
python -m scripts.benchmark_mvp3 --iterations 1000  # also exports strategy_snapshot.json
python -m uvicorn scripts.serve_mvp3:app --host 127.0.0.1 --port 8000
python validate_format.py --endpoint http://127.0.0.1:8000/decide
```

`app.main:app` still provides the original default strategy. The live endpoint is
stateless with respect to courier execution, as in MVP 1: callers provide overrides.
The simulation uses an in-memory service and owns execution state. `GET /decisions/{id}`
exposes recorded economics including opportunity cost, zone value, skip penalty and
stacking time. Simulated decisions additionally record SLA and planned-route details.

## Data calibration and provenance

`app/calibration/profiles.py` defines immutable `SimulationProfile`, `SyntheticProfile`
and `CalibratedProfile`. The generator consumes a profile, not a dataset loader.
Leaving `ShiftConfig.profile=None` preserves the original MVP 2 random sequence.
With a profile, empirical bootstrap supplies pickup/delivery distances, preparation,
base pay, tip, weight and volume; paired zone counts supply pickup/dropoff transitions.
Interarrival time is exponential using the overall rate and current-hour factor.
All randomness uses the generator's local `Random(seed)`.

`prepare_mvp3_data` creates 1,217 records from tuning seeds 1–10, on ten prior dates
in February 2026, each covering 15:00–23:00. The original MVP 2 generator creates the
history. There are 80 hours of declared exposure and 10 exposure hours per observed
hour bucket. The fitted overall rate is 15.2125 orders/hour. Current evaluated shifts
start March 21, 2026. Predictions reject query times at/before the training cutoff.

Artifacts:

- `artifacts/synthetic_tuning_history.json`: normalized synthetic input.
- `artifacts/calibrated_profile.json`: distributions, provenance and training seeds.
- `artifacts/calibration_report.json`: counts, means/medians/p95, missingness and frequencies.
- `artifacts/calibration_manifest.json`: source hash, field transformations, fallbacks,
  exposure, fitted distributions and classification per parameter.
- `artifacts/historical_model.json`: immutable aggregate model with cutoff and source hash.

For a custom or public delivery table:

```bash
python -m scripts.calibrate_dataset deliveries.csv --columns mapping.json \
  --exposure-hours 80 --hour-exposure exposure_by_hour.json
```

`mapping.json` maps internal names to external columns, for example
`{"timestamp":"created_at","distance_km":"delivery_km","base_pay_mxn":"pay"}`.
Input timestamps must be ISO 8601; units must explicitly be km, minutes, kg, liters,
and MXN. `exposure_by_hour.json` maps hours to observed duration, e.g. `{"18":10}`.
Supplying hourly exposure also exports a historical model. Adapters do not silently
convert foreign currencies, coordinate distances, volumes or demand units.

```bash
python -m scripts.calibrate_dataset c101.txt --adapter solomon \
  --demand-to-kg 0.1 --service-to-minutes 1
```

Those conversion factors are examples, not verified Solomon-to-delivery conversions.
The Solomon adapter reads customer rows `id x y demand ready due service`, excludes
the depot, and only maps demand/service when conversions are explicitly supplied.
Coordinates are not road kilometers; ready/due are not historical timestamps.
Therefore routing instances alone cannot calibrate hourly demand or courier pay.

Missing values remain `None`. Statistics and fits exclude them per field. If a
distribution has no observations, the manifest records the configured synthetic
fallback; an absent service-time distribution stays absent. Overall demand requires
declared observation exposure. Hourly counts alone are not interpreted as rates.
Unknown hourly exposure uses factor 1; an observed hour with zero events uses 0.
Service duration is reported and used for historical cycle rates; the generator
derives travel from distance/speed instead of sampling a contradictory total duration.

Classification vocabulary:

| Classification | Meaning in this implementation |
|---|---|
| Observed | A nonmissing measurement supplied by an external table; none in the bundled experiment |
| Derived | A documented calculation from external records and declared exposure |
| Assumed/configured | Physics, policy, unit conversions and missing-field fallbacks |
| Synthetic | All records and fitted measurements used for the bundled evaluation |
| Official constraint | The five safety rules; they are never fitted or relaxed |

## Historical prediction and strategy snapshots

`HistoricalDemandModel` holds frozen zone × hour aggregates. It has no reference to
a running simulator, its stream, pending offers, shocks or random generator. It uses
only fitted history, explicit observation exposure and `(zone, sim_time, vehicle)`.

For a sufficiently populated bucket (default minimum 5 complete economic records):

```text
orders_rate = count_of_orders / observed_hours
expected_wait_min = 60 / orders_rate
expected_net_pay = mean_gross_pay - mean_total_distance * configured_vehicle_cost_per_km
expected_net_rate = max(0, expected_net_pay) * 60 / (mean_service_min + expected_wait_min)
```

Sparse or unseen zones fall back to the mean of available buckets at that hour,
then all buckets. Empty models yield zero values and low confidence. Confidence is
`min(1, exact_bucket_sample_count / min_samples)`. Missing economic records are
excluded from pay/cycle estimates. The current model uses the default vehicle cost
profiles; service durations are historical averages without vehicle-specific fitting.

`StrategyUpdater` executes at start and every 30 minutes of sim_time. It publishes a
new immutable snapshot through `StrategyStore`, outside the decision window:

```text
reference = mean(expected_net_rate over configured zones)
zone_value[z] = clip(expected_net_rate[z] - reference, -50, +50) MXN/hour
reservation_wage = clip(165 + 0.1 * reference
                       - 20 * max(0, 1 - remaining_minutes / 60), 80, 250)
target_zone = highest predicted rate, ties broken by lowest zone ID
```

With prediction disabled, predictions/zone values are empty; the same wage rule uses
reference zero. `SmartNoZoneValue` clears only zone scoring; predictions remain
available to reposition and opportunity cost. A failed updater retains the last
snapshot's numeric parameters and marks it stale. Recovery publishes a fresh snapshot.
The tests simulate an unavailable update between successful updates; `/decide`
continues immediately with `degraded=true`, then returns to `false`.

## Economics and opportunity cost

The central formula lives in `app/strategy/opportunity_cost.py`:

```text
opportunity_cost_mxn = max(0, expected_zone_net_rate) * committed_minutes / 60 * fraction
```

The configurable fraction is 0.25 in the experiment. The fast path reads the
precomputed prediction for the pickup zone, since the official request does not
carry current position. The simulation's reposition/cancellation layer has actual
synthetic current position. Score units remain MXN/hour:

```text
adjusted_rate = new_order_net_pay / total_committed_minutes * 60
                + dropoff_zone_value
                + (skip_penalty - opportunity_cost) / total_committed_minutes * 60
ACCEPT iff adjusted_rate >= reservation_wage, subject to feasibility
```

The default MVP 1/2 snapshot leaves economics V2 disabled. V2 retains the conservative
committed-time denominator and adds explicit opportunity cost; these can overlap as
penalties for occupied time and require later economic validation. No accepted-order
revenue is counted again. The fast reason remains under 40 words.

## Repositioning and fair world comparison

When idle and not on break, Smart compares WAIT to candidate zones over a configured
30-minute horizon, limited by remaining shift time:

```text
gain[z] = predicted_rate[z] * max(0, horizon - travel_minutes) / 60
          - current_zone_rate * horizon / 60 - travel_operating_cost
```

Move only when gain exceeds MXN 5 and at least 30 minutes have elapsed since the
previous move ended. Equal values select the lowest zone ID. Distances use an explicit
synthetic grid with four columns and 0.5 km spacing; zone IDs are not real geography.
Time, distance, cost and continuous riding are charged during travel. Hard constraints
are checked before moving. An arriving offer is skipped while the move reserves
availability; elapsed move costs remain charged if rain interrupts it. Interrupted
moves retain the last known zone, an approximation without coordinates.

Both agents consume the identical immutable source stream. MVP 3 adds the same grid
distance function from each courier's independently evolved position to the quoted
local pickup distance. Their effective pickup travel may therefore differ, while the
source order, pay, destination and shocks remain identical. This explicit spatial
assumption permits repositioning to influence future pickup costs. It is not a
geographic route model and does not change which platform offers each courier sees.

`reposition_count`, distance and costs are observed metrics. The field
`net_gain_after_reposition` is realized shift net after movement costs when a move
occurred, **not a causal treatment effect**. Use the matched `SmartNoReposition`
ablation to estimate the contribution within this simulator.

## Batching and SLA

The insertion heuristic preserves existing phase order and never preempts the current
phase. It inserts a new pickup/preparation block and a delivery/padding block at
separate positions, with pickup before delivery. It considers at most 32 candidates
and at most 4 accepted active orders (hard configurable caps 64/6). FIFO is always the
first candidate; feasible candidates minimize summed completion times with stable ties.
No OR-Tools dependency or unbounded enumeration is used.

Each candidate checks the shared five hard constraints, reserved weight/volume of
all accepted orders, shift end and **every** active order's fixed SLA. Load is reserved
at acceptance rather than only at pickup, which is conservative. Quoted leg distances
and durations remain synthetic and additive; insertion does not claim road savings
or solve geographic VRPTW. A controlled test shows insertion completing an urgent B
before A's delivery while preserving both SLAs, where FIFO must skip B.

The configured SLA function is centralized in `strategy/sla.py`:

```text
delivery_deadline = offer_time
                    + 1.5 * max(1, pickup_minutes + prep_minutes + delivery_minutes)
                    + 10 minutes
```

This is an assumed policy, not an industry measurement. The travel estimates include
currently visible shocks. The resulting deadline is stored at acceptance and never
moved later to hide a miss. `/decide`'s `decision_deadline` remains unrelated.

SLA/active-order limits have no dedicated official binding enum. The simulation
returns SKIP with `reservation_wage` as the allowed policy bucket and explicitly names
the insertion/SLA limit in its reason and detailed log. It does not invent a sixth
official safety constraint. `/decide` alone retains its conservative timing adapter;
optimized route evaluation runs in the simulator around the same fast engine.

## Shocks and exceptional cancellation

MVP 2 surge/rain/closure/delay mechanics remain in use. Rain rescales remaining travel;
delay/closure add waiting and update the route. Safety-infeasible execution is held,
as in MVP 2. Fixed SLA misses on previously accepted work carry a disruption marker
when that work was exposed to an actual closure, delay or rain. The original ACCEPT
remains in the log. Queue propagation also records the visible triggering shock when
an order's ETA worsens, without rewriting the original decision.

Cancellation is evaluated only after visible eligible disruptions and only for exposed
accepted work now late or safety-infeasible:

```text
released_value = opportunity_cost(expected_current_zone_rate, remaining_service_minutes)
continue_value = remaining_gross_pay - remaining_distance_cost
                 - lateness_minutes * lateness_penalty - released_value
cancel_value = -cancellation_penalty + released_value
CANCEL iff cancel_value > continue_value + cancellation_min_gain
```

The experiment uses skip penalty MXN 0, cancellation penalty MXN 20, lateness value
MXN 1/minute, and minimum cancellation gain MXN 5. These are independent, assumed
parameters. The model intentionally exposes how released capacity is valued; its
weights have not been empirically estimated. It does not implement real platform
refunds, reassignment or physical return of already collected goods.

Cancellation removes remaining work, charges its penalty once, retains incurred
travel costs and credits no delivery income. The internal trace and public
`position_update(action=order_cancelled)` record cause, triggering shock, continue and
cancel values. SKIP and CANCEL have separate counters and monetary totals.

## Evaluation, ablations and replay

`evaluation/tuning_seeds.txt`: 1–10. `evaluation/heldout_seeds.txt`: 10001–10010.
Overlap, duplicates and calibration/model seeds outside tuning cause a failure.
Held-out requires at least ten seeds. No fitting or parameter search happens in either
evaluation runner. The profile/model/policy are immutable and fingerprinted before and
after every shift; each result directory includes their complete frozen copies.
Scheduled snapshot updates apply the same already frozen rule during both sets.

Any execution exception reports seed, agent, state and recent events. Any nonzero
safety count fails the run; the CLI writes `FAILED.json` and returns nonzero.
The current seed provenance is explicit metadata: external dataset authorization
must still be established by the operator, and a deliberately falsified manifest
cannot be detected from statistical values alone.

`run_ablations` uses tuning seeds only. Variants differ by exactly one flag:
SmartFull, SmartNoZoneValue, SmartNoReposition, SmartNoImprovedBatching and
SmartNoHistoricalPrediction. It reports mean net and differences from Full/baseline.
The included experiment keeps Full even when an ablation performs better.

`artifacts/results_mvp3.csv` matches the official template's columns and includes
GreedyRate and OurAgent, the policies actually executed. Unimplemented oracle or other
baseline results are not fabricated. Completed orders/deadline misses are totals;
deadhead includes executed pickup and reposition kilometers, including partial travel.

Public JSONL uses only official event types. `strategy_update` is already an official
type; reposition/cancellation use additional fields on `position_update`. A separate
`*.trace.jsonl` contains more detailed internal records. Public logs embed the initial
snapshot, model, policy, source stream, strategy updates and failure schedule. Replay
dispatches by simulator version and reconstructs the full run from those inputs;
it ignores measured latency only. Tampered strategy updates fail replay.

## Remaining assumptions and limits

- There is no external empirical validation. Bootstrap marginals lose correlations
  between pay, distance, preparation, demand and time; paired zone transitions alone
  preserve one joint relationship. Hourly arrival-rate changes are approximated at
  event boundaries, and every nonzero-demand shift starts with a ping.
- Costs, speeds, capacities, zone geography, wait/service assumptions, threshold,
  SLA, clipping, penalties and reposition rules are configured rather than measured.
- The default safety zones are synthetic examples. The five official limits remain
  fixed in code and are never learned.
- Held-out seeds test independent random streams from the same fitted synthetic
  family; they do not establish geographic, temporal or market generalization.
- Insertion improves scheduling under quoted legs; it does not optimize real streets.
  Predictive economics and cancellation need external sensitivity analysis.
- No cloud deployment, frontend, real traffic/climate API, LLM, mobile integration,
  Snowflake or ElevenLabs was added.

Measured outcomes and checks are recorded in `MVP3_VERIFICATION.md`.
