# Baseline Audit (Snapshot: 2026-03-04)

## Delivery Metrics
- Lead time (days): Not yet instrumented in repo telemetry.
- Throughput (items/week): 34 commits in last 7 days (`git rev-list --count --since='7 days ago' HEAD`).
- Carry-over ratio: Not yet instrumented in repo telemetry.

## Quality Metrics
- Escaped defects/week: Not yet instrumented; no failed checks in current validation run.
- Regression count/week: Not yet instrumented; local regression signal currently 0 failing tests.
- Test pass rate: 100% (248/248 passing via `pytest -q`).

## Operations Metrics
- Policy violations/week: 10 strict-policy violations across 6 organs (snapshot from `conductor policy simulate --bundle strict --format json`).
- Observability warnings/week: 0 warn/critical trend states; trend status is `ok` with 1.63% overall failure rate and 8% recent-window failure rate.
- Incident count/week: Not yet instrumented as a weekly metric.

## Friction Points
- Bottleneck 1: Strict policy limits currently exceeded in multiple organs (promotion hygiene debt).
- Bottleneck 2: Plugin provider load/cluster errors remain in observability failure buckets.
- Bottleneck 3: Delivery metrics (lead time, carry-over, incidents) are not yet tracked with first-class artifacts.

## Priority Fixes
1. Add weekly sprint reports and scorecards as required release artifacts to instrument lead time/carry-over.
2. Burn down strict-policy violations by promotion-state cleanup per organ.
3. Reduce plugin provider failure buckets and add a weekly recovery drill log.
