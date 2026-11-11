# Memo review — UC1

Reviewer: Harsh  
Date: 2026-11-11

## Overall verdict agreement

I agree with **feasible_with_conditions**. No must need is fully blocked, but none is unconditionally met either. The prototype can start on UCI 360 while internal access requests are raised.

## Per-source review

**link.uci_360** — Verdict correct. Single road-level device, research-only restriction conflicts with CC BY 4.0. -200 sentinel values and NMHC nearly 90% missing are real data quality issues. Use for method-building only; Legal must resolve the licence conflict before any further use.

**internal.airq.station_readings** — Verdict correct. Access pending. VR-03 closure is a genuine catalog/wiki conflict that must be resolved. No station coordinates means no join to traffic or weather data. Conditions are achievable via the Environment Monitoring Unit.

**internal.traffic.hourly_counts** — Verdict correct. The 2024-03-18 method change with no adjustment documented is the largest single risk. No counter-to-station mapping means N2 cannot be joined to N1 without further work from the Mobility Office.

**api.open_meteo_archive** — Verdict correct. The non-commercial flag on a must need is a blocker for production. Prototype use depends on Legal's reading of the terms. Valdena coordinates must be recorded before any real probe.

**internal.clinic.resp_visits_daily** — Verdict correct. Daily district counts are within policy. Undocumented diagnosis codes and suppression rule are real gaps. Access request to Clinical Analytics is the first step.

**link.europa_sdg_11_52_099aa6** — Verdict correct. Licence unknown is a blocker for anything beyond context use. JSON-stat dimensions not decoded means year coverage is unconfirmed.

**link.data_open_air_chicago_hour_aggre_d4970b** — Verdict correct. Host refused, US geography, not relevant. Guardrail finding recorded.

## Flags I checked

- LIC-NONCOMMERCIAL on UCI 360 and Open-Meteo: both are real. The UCI page says "research purposes only" and Open-Meteo free tier says non-commercial. Both need Legal decisions.
- COV-PARTIAL-WINDOW on airq.station_readings: VR-03 closed 2024-06-30 is confirmed in the wiki. Flag is correct.
- GOV-CATALOG-WIKI-CONFLICT on traffic: wiki explicitly says "do not compare counts across the change." Flag is correct.
- FRS-STALE on UCI 360: data ends 2005, as-of 2026, 21+ years. Flag correct; acceptable for prototype only.
- ACC-UNREACHABLE on Chicago: host not allowlisted by design. Recording as guardrail finding, not adding the host.

## Open questions I am deferring

Questions 1–10 from the memo are deferred to the named owners (Legal, Environment Monitoring Unit, Mobility Office, Clinical Analytics). No answer can be supplied during discovery.
