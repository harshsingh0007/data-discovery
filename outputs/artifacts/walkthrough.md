# Walkthrough — UC1

Reviewer: Harsh  
Date: 2026-11-11  
Files cited: `discovery_agent/risk_rules.py`, `outputs/UC1/signoff.json`, `outputs/UC1/records/internal.airq.station_readings.json`, `outputs/artifacts/decisions.md`, `outputs/UC1/feasibility_memo.md`

---

## 1. One rule I wrote: `rule_temporal_coverage`

File: `discovery_agent/risk_rules.py`, function `rule_temporal_coverage`.

The rule computes how much of each target window is covered by the record's `temporal.start` and `temporal.end`. If `end` is null it treats the source as still updating (covered up to `as_of`). If all window fractions are zero it raises `COV-OUT-OF-WINDOW`; if any fraction is below the threshold in `config/settings.json` it raises `COV-PARTIAL-WINDOW`; if `end` is set and more than `stale_after_years` before `as_of` it raises `FRS-STALE`.

I accepted this design after checking the edge cases: an open-ended source (null end) should not be flagged stale, so staleness only fires when `end` is explicitly set. The UCI dataset ends in 2005, which is 21 years before `as_of` 2026 — `FRS-STALE` fires correctly and matches the memo's finding that UCI is a historical benchmark, not a current source.

---

## 2. One claim in `signoff.json` traced to its record field

`outputs/UC1/signoff.json`, `traced_conclusion`:

```json
{
  "source_id": "internal.airq.station_readings",
  "record_field": "temporal.start",
  "could_change_if": "If the Environment Monitoring Unit provides a backfill of station readings before 2023-01-01, the prototype window gap for N1 could be partially closed..."
}
```

The claim traces directly to `outputs/UC1/records/internal.airq.station_readings.json`, field `temporal.start: "2023-01-01"`. The prototype window for N1 runs from 2023-06-01 to 2024-05-31. Because the station data only starts 2023-01-01, it covers the full prototype window — but nothing before that. If the Environment Monitoring Unit backfills readings before 2023-01-01, that `temporal.start` date would move earlier and the source could also serve older analysis periods. The traced conclusion is a direct function of that one field value.

---

## 3. One rejected source and why

Source: EEA AirBase v8 — `https://www.eea.europa.eu/data-and-maps/data/airbase-the-european-air-quality-database-8`  
Recorded in: `outputs/artifacts/decisions.md`, "Source suggestions" table.

I rejected it because the UCI 360 link already covers N1 for the prototype window. AirBase v8 covers the same need (hourly air-quality readings) but would add a second source for the same need with no additional coverage. The UCI link was already accepted at the gate and allowlisted. Adding AirBase would not close any unmet need and would increase pipeline cost with no benefit.

---

## 4. One memo conclusion

From `outputs/UC1/feasibility_memo.md`, section on `link.europa_sdg_11_52_099aa6`:

The memo concludes that the Eurostat SDG 11.52 source is `feasible_with_conditions` for N6, but the series ends in 2023, leaving the production window (2024–2025) with no coverage. This conclusion was not reachable before G3 was implemented. Before the fix, the profiler returned `NOT_IMPLEMENTED` for `summarize_jsonstat` and could not decode the JSON-stat dimensions — year coverage was listed as "not established." After implementing G3, the record correctly shows 36 cells covering 2005–2023, 2006 absent. The memo conclusion (COV-PARTIAL-WINDOW on the production window) is a direct result of the G3 fix. The G7 evidence for this is in `outputs/artifacts/decisions.md` under "G7: One agent failure, fixed at its cause."
