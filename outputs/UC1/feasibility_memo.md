## 1. Executive summary

**Verdict: feasible with conditions. The prototype can start on public data now. Production is gated by access approvals, a licence decision and data fixes.**

Facts that drive this:

1. **All three must needs (N1, N2, N3) have a candidate source, but each is conditional.** N1 prototype rests on UCI 360 (`link.uci_360`). N1 production rests on the city station feed (`internal.airq.station_readings`). N2 rests only on `internal.traffic.hourly_counts`. N3 rests only on `api.open_meteo_archive`, which is modelled grid data, not station readings.
2. **No source is rated fully feasible.** Every usable source needs at least one condition, and several conditions are access approvals that have not been granted. No data was read from any internal source.
3. **Three sources carry blocker-level licence flags but are still rated "with conditions".** These are `api.open_meteo_archive` (free tier non-commercial; the register and the terms conflict), `link.uci_360` (research-only text conflicts with CC BY 4.0), and `link.europa_sdg_11_52_099aa6` (licence not readable). The discovery rated these conditional under its calibration rules. Each needs a human licence decision before use. The reviewer should confirm the rating.
4. **Production data has known gaps.** Station VR-03 has no readings after 2024-06-30 (wiki), while the catalog still shows the network as active. Traffic counting changed on 2024-03-18, inside the production window. Neither the traffic counters nor the clinic districts can be joined to monitoring stations, because no key is documented.
5. **Two needs are not served.** N5 (patient-level records) is unmet under the clinic data policy, which allows only daily district counts. The Chicago link is not feasible: the host is not allowlisted, the licence is unknown, and the geography is US.

## 2. Need coverage

| need id | need | priority | status | best source(s) | gap |
|---|---|---|---|---|---|
| N1 | Hourly air-pollutant concentrations (NO2 or PM2.5) | must | met with conditions | `link.uci_360` (prototype); `internal.airq.station_readings` (production) | UCI: research-only licence conflict, -200 missing codes, one unnamed road-level device, stale vintage. Production: access not granted; VR-03 missing after 2024-06-30; coverage through 2025 unverified; no station coordinates. |
| N2 | Hourly vehicle traffic near monitoring stations | must | met with conditions | `internal.traffic.hourly_counts` | Access not granted. Counting method changed 2024-03-18 inside the production window, with no adjustment. No counter-to-station mapping. Timezone (ts_local) undocumented. |
| N3 | Hourly temperature and humidity | must | met with conditions | `api.open_meteo_archive` | Only source for both windows. Modelled grid, not station data. Valdena coordinates not confirmed. Free-tier licence is non-commercial, so production use needs a Legal decision or paid subscription. |
| N4 | Daily respiratory clinic visits by district | should | met with conditions | `internal.clinic.resp_visits_daily` | Access not granted. Diagnosis code set and district code list undocumented. Zero-day handling unknown. No key to station geography. Use limited by clinic data policy. |
| N5 | Patient-level clinic visit records | could | unmet | none | Clinic data policy allows only daily district counts. No patient-level source was assessed. |
| N6 | National yearly context: deaths linked to PM2.5 | could | partially met | `link.europa_sdg_11_52_099aa6` | Only 2005 overlaps the prototype window (fraction 0.24). No production coverage; series ends 2023-12-31. Licence unknown. Annual grain only. |

## 3. Source assessments

### 3.1 internal.airq.station_readings (with conditions)
- **What it is:** Hourly NO2 and PM2.5 (µg/m³) from the city's own stations, keyed by station_id and ts_utc. Catalog: about 4.2 million rows, start 2023-01-01, open-ended, hourly refresh, last refreshed 2026-10-14. Owner: Environment Monitoring Unit.
- **Verdict:** feasible with conditions. The only production N1 source.
- **Key flags:**
  - ACC-RESTRICTED (major, judgement): access by request; not tested; no sample read.
  - GOV-CATALOG-WIKI-CONFLICT (major): catalog says "active", end null. Wiki station_network (last edited 2024-07-01) says VR-03 stopped after 2024-06-30.
  - COV-PARTIAL-WINDOW (major): VR-03 gap; other stations' continuity only documented to July 2024.
  - INT-NO-JOIN-KEY (major): no station coordinates.
- **Conditions:** access approval; reconcile catalog and wiki on VR-03; obtain station list with coordinates; document and handle the VR-03 gap; the prototype N1 depends on UCI 360.

### 3.2 internal.clinic.resp_visits_daily (with conditions)
- **What it is:** Daily respiratory visit counts per district of residence, owned by Clinical Analytics. Catalog: about 40,000 rows, coverage from 2022-01-01, open-ended, daily refresh, no patient identifiers stated.
- **Verdict:** feasible with conditions, for N4 only.
- **Key flags:**
  - ACC-RESTRICTED (major, rule): auth required; not tested.
  - DQ-UNDOCUMENTED-SCHEMA (major): 3 columns; diagnosis and district code lists undocumented.
  - INT-NO-JOIN-KEY (major): no link from districts to stations.
  - GOV-PURPOSE-LIMITATION (major): clinic_data_policy (Data Protection Office, last edited 2025-02-01) allows only daily district counts for this purpose. Use in the warning service must be confirmed.
- **Conditions:** access approval; code lists and boundary history; zero-day and small-cell rules; DPO confirmation; no patient-level or postcode/age-band fields.

### 3.3 internal.traffic.hourly_counts (with conditions)
- **What it is:** Hourly vehicle counts per counter (counter_id, ts_local, vehicles), described as near the monitoring stations. Catalog: about 15 million rows, coverage from 2021-01-01, open-ended, hourly refresh, last refreshed 2026-10-12. Owner: Mobility Office.
- **Verdict:** feasible with conditions. The only N2 source.
- **Key flags:**
  - ACC-RESTRICTED (major, rule): auth required; not tested.
  - GOV-CATALOG-WIKI-CONFLICT (major): wiki counter_replacement_2024 (edited 2024-04-02) says counting changed on 2024-03-18, from per direction to both directions combined. Wiki says do not compare across the change without adjusting. Catalog has no note.
  - INT-NO-JOIN-KEY (major): no counter-to-station mapping or distances.
  - DQ-DST-ARTEFACTS (minor): ts_local; DST handling undocumented; the air source uses ts_utc.
- **Conditions:** access approval; adjust for or model the method break, or train only after it and document this; counter-to-station mapping; timezone conversion; hourly completeness check for 2024–2025.

### 3.4 link.uci_360 (with conditions, prototype only)
- **What it is:** Hourly readings from a road-level multisensor in one unnamed Italian city, with co-located reference analyser values. 9,357 rows; dates 2004-03-10 to 2005-04-04. Source: UCI dataset page, doi 10.24432/C59K5F. Metadata last updated 2024-03-10. Static; donated 2016-03-22.
- **Verdict:** feasible with conditions. Covers the whole prototype window for N1. It is not production evidence.
- **Key flags:**
  - LIC-NONCOMMERCIAL (blocker, judgement): "research purposes only; commercial purposes fully excluded". The same page also states CC BY 4.0.
  - GOV-PURPOSE-LIMITATION (major): use in a public-health warning service must count as research.
  - DQ-SENTINEL-VALUES (major): -200 is the missing code. C6H6(GT) has 366 values at -200 that the profiler did not flag.
  - DQ-METADATA-CONTRADICTION (major): the variables table says no missing values; the page says yes.
  - DQ-UNDOCUMENTED-SCHEMA (major): date format conflict (DD/MM documented, M/D parsed); recording period runs past the documented end; time format differs.
  - INT-REPRESENTATIVENESS (major): single unnamed device; no station ID or coordinates; documented sensor drift.
  - FRS-STALE (major, rule): record ends 21.5 years before the as-of date. Accepted for prototype use.
- **Conditions:** legal review of research use, recorded in decisions.md; recode -200 for all columns; use GT columns as targets; confirm date format; cite the dataset; prototype only.

### 3.5 api.open_meteo_archive (with conditions)
- **What it is:** Gridded historical weather reanalysis via REST API. Hourly 2 m temperature and relative humidity, UTC. Grid about 9 km from 2017 (ECMWF IFS) and 0.25° before (ERA5), per docs. Start 1940-01-01, open-ended, refresh cadence unknown. Both windows returned hourly values in probes, using Milan coordinates for testing only.
- **Verdict:** feasible with conditions. The only N3 source.
- **Key flags:**
  - LIC-NONCOMMERCIAL (blocker, judgement): free API "may only be used for non-commercial purposes" (terms page). The register lists "not_required_open_data", which conflicts with the terms. Whether a civic warning service is non-commercial is not stated in any source.
  - LIC-MIXED (major, rule): Copernicus C3S/ECMWF terms also apply.
  - COV-GEO-MISMATCH (major, judgement): Valdena coordinates not documented. decisions.md assumption not found.
  - DQ-UNDOCUMENTED-SCHEMA (minor, judgement): model version changes in 2017; model used per date not confirmed.
  - FRS-METADATA-DATE-MISLEADING (minor, judgement): metadata_last_updated 2026-11-11 is after the as-of date 2026-10-15. It describes the docs, not the data.
  - LIC-ATTRIBUTION (minor, rule): attribution required.
- **Conditions:** Legal decision or paid subscription before any production use; confirm coordinates and re-pull; check completeness (only 3 days per window probed) and the "GMT" label against ts_utc; attribution; document modelled data and the 2017 change.

### 3.6 link.europa_sdg_11_52_099aa6 (with conditions, context only)
- **What it is:** Eurostat SDG 11.52 (dataset sdg_11_52, source ESTAT). Annual premature deaths due to PM2.5, Italy only, in two units (NR and RT). 36 cells, 2005–2023, 2006 absent. Metadata last updated 2025-12-09.
- **Verdict:** feasible with conditions, for N6 context only. Cannot support hourly, district or clinic modelling.
- **Key flags:**
  - LIC-UNKNOWN (blocker, rule): no licence statement found; copyright page redirected to EU Login.
  - COV-PARTIAL-WINDOW (major, rule): prototype fraction 0.24; production 0.0.
  - DQ-SEMANTIC-ENCODING (major, judgement): unit NR vs RT must be filtered.
  - COV-GRAIN-MISMATCH (minor, judgement): annual only.
- **Conditions:** read the licence at source and record it; project lead sign-off because coverage is below 0.5; filter on unit; document the 2006 gap; national context only.

### 3.7 link.data_open_air_chicago_hour_aggre_d4970b (not feasible)
- **What it is:** Human-supplied link to a data.gov record, "Open Air Chicago hour aggregations". Described as hourly air-quality data from a US city. Nothing was read.
- **Verdict:** not feasible.
- **Key flags:**
  - ACC-UNREACHABLE (blocker, rule): DOMAIN_NOT_ALLOWLISTED for catalog.data.gov.
  - LIC-UNKNOWN (blocker, rule): licence not established.
  - COV-GEO-MISMATCH (major, judgement): US city; use case is Italy.
- **Conditions:** none. The refusal is recorded as a finding. Do not seek another route to this data. An allowlist change is not recommended, given the geography mismatch.

## 4. Red-flag register

| source_id | code | severity | evidence | raised by (rule or judgement) |
|---|---|---|---|---|
| api.open_meteo_archive | LIC-NONCOMMERCIAL | blocker | Free API non-commercial only; register says not_required_open_data; conflict unresolved | judgement |
| api.open_meteo_archive | LIC-MIXED | major | C3S/ECMWF terms plus CC BY 4.0; mixed_sources=true | rule |
| api.open_meteo_archive | COV-GEO-MISMATCH | major | Valdena coordinates not documented; Milan used for test only | judgement |
| api.open_meteo_archive | DQ-UNDOCUMENTED-SCHEMA | minor | 2017 model change; model per date unconfirmed | judgement |
| api.open_meteo_archive | FRS-METADATA-DATE-MISLEADING | minor | metadata date 2026-11-11 after as-of 2026-10-15 | judgement |
| api.open_meteo_archive | LIC-ATTRIBUTION | minor | CC BY 4.0 attribution required | rule |
| internal.airq.station_readings | ACC-RESTRICTED | major | Access by request; not tested | judgement |
| internal.airq.station_readings | GOV-CATALOG-WIKI-CONFLICT | major | Catalog active; wiki says VR-03 stopped 2024-06-30 | judgement |
| internal.airq.station_readings | COV-PARTIAL-WINDOW | major | VR-03 gap; coverage through 2025 unverified | judgement |
| internal.airq.station_readings | INT-NO-JOIN-KEY | major | No station coordinates | judgement |
| internal.clinic.resp_visits_daily | ACC-RESTRICTED | major | auth_required; reachable not tested | rule |
| internal.clinic.resp_visits_daily | DQ-UNDOCUMENTED-SCHEMA | major | 3 columns; no code lists; zero-day handling unknown | judgement |
| internal.clinic.resp_visits_daily | INT-NO-JOIN-KEY | major | No district-to-station key | judgement |
| internal.clinic.resp_visits_daily | GOV-PURPOSE-LIMITATION | major | Clinic policy allows daily district counts only | judgement |
| internal.traffic.hourly_counts | ACC-RESTRICTED | major | auth_required; reachable not tested | rule |
| internal.traffic.hourly_counts | GOV-CATALOG-WIKI-CONFLICT | major | Method break 2024-03-18 in wiki; absent from catalog | judgement |
| internal.traffic.hourly_counts | INT-NO-JOIN-KEY | major | No counter-to-station mapping | judgement |
| internal.traffic.hourly_counts | DQ-DST-ARTEFACTS | minor | ts_local; DST undocumented | judgement |
| link.uci_360 | LIC-NONCOMMERCIAL | blocker | Research-only text conflicts with CC BY 4.0 | judgement |
| link.uci_360 | GOV-PURPOSE-LIMITATION | major | Research use must be confirmed for warning service | judgement |
| link.uci_360 | DQ-SENTINEL-VALUES | major | -200 missing code; C6H6(GT) 366 unflagged | judgement |
| link.uci_360 | DQ-METADATA-CONTRADICTION | major | Missing-values flag conflicts with page | judgement |
| link.uci_360 | DQ-UNDOCUMENTED-SCHEMA | major | Date format; period end; time format; row count 9,357 vs 9,358 | judgement |
| link.uci_360 | INT-REPRESENTATIVENESS | major | Single unnamed road device; drift; no coordinates | judgement |
| link.uci_360 | FRS-STALE | major | Ends 2005-04-04; 21.5 years before as-of | rule |
| link.uci_360 | LIC-ATTRIBUTION | minor | Citation required | rule |
| link.europa_sdg_11_52_099aa6 | LIC-UNKNOWN | blocker | No licence statement; copyright page not readable | rule |
| link.europa_sdg_11_52_099aa6 | COV-PARTIAL-WINDOW | major | Prototype fraction 0.24; production 0.0 | rule |
| link.europa_sdg_11_52_099aa6 | DQ-SEMANTIC-ENCODING | major | NR and RT units mixed without filter | judgement |
| link.europa_sdg_11_52_099aa6 | COV-GRAIN-MISMATCH | minor | Annual only | judgement |
| link.data_open_air_chicago_hour_aggre_d4970b | ACC-UNREACHABLE | blocker | DOMAIN_NOT_ALLOWLISTED | rule |
| link.data_open_air_chicago_hour_aggre_d4970b | LIC-UNKNOWN | blocker | Page not read; licence null | rule |
| link.data_open_air_chicago_hour_aggre_d4970b | COV-GEO-MISMATCH | major | US city; use case is IT | judgement |

## 5. Conditions and owners

The discovery inputs name no resolver for any condition. The owners below come from the record owner fields or from the conditions text. "Not named" means no input names a resolver.

| condition | source(s) | who can resolve it | blocking which need |
|---|---|---|---|
| Approve access request before profiling values | internal.airq.station_readings | Environment Monitoring Unit (record owner) | N1 production |
| Approve access request before profiling values | internal.traffic.hourly_counts | Mobility Office (record owner) | N2 |
| Approve access request before profiling values | internal.clinic.resp_visits_daily | Clinical Analytics (record owner) | N4 |
| Reconcile VR-03 status in catalog with wiki; confirm continuity through 2025 | internal.airq.station_readings | Environment Monitoring Unit (not named) | N1 production |
| Provide station list with coordinates | internal.airq.station_readings | Environment Monitoring Unit (not named) | N1 join to N2, N3 |
| Adjust for or model 2024-03-18 method break | internal.traffic.hourly_counts | Mobility Office (not named); analytics lead to decide method | N2 |
| Provide counter-to-station mapping and distances | internal.traffic.hourly_counts | Mobility Office (not named) | N2 station-level use |
| Confirm ts_local timezone and DST handling | internal.traffic.hourly_counts | Mobility Office (not named) | N2 alignment |
| Provide diagnosis code set, district code list, boundary history, zero-day and small-cell rules | internal.clinic.resp_visits_daily | Clinical Analytics (not named) | N4 |
| Confirm daily district counts may be used for warning service | internal.clinic.resp_visits_daily | Data Protection Office (policy owner) | N4 |
| Legal decision or paid subscription for non-commercial terms | api.open_meteo_archive | Legal (named in conditions); paid subscription needs budget owner (not named) | N3 production |
| Confirm Valdena coordinates and re-run pull | api.open_meteo_archive | Health Office (not named) | N3 |
| Check completeness and hour alignment | api.open_meteo_archive | Analytics team (not named) | N3 |
| Legal review of research-only licence; record decision in decisions.md | link.uci_360 | Legal (named in conditions) | N1 prototype |
| Recode -200 and confirm date format | link.uci_360 | Analytics team; dataset owner for format check (not named) | N1 prototype |
| Read Eurostat reuse licence at source | link.europa_sdg_11_52_099aa6 | Analytics team (not named) | N6 |
| Project lead sign-off on coverage fraction 0.24 | link.europa_sdg_11_52_099aa6 | Project lead (named in conditions, not by name) | N6 |
| Allowlist decision for catalog.data.gov | link.data_open_air_chicago_hour_aggre_d4970b | Platform owner (not named); not recommended | None |

## 6. Recommended next steps

1. **Raise access requests now** to the Environment Monitoring Unit (station readings and station coordinates), the Mobility Office (traffic counts and counter mapping), and Clinical Analytics (daily district counts and code lists). Access is not tested and no data has been read.
2. **Start the Legal review of two licences:** the UCI 360 research-only restriction (needed for the prototype) and the Open-Meteo non-commercial terms (needed for production). Record both outcomes in decisions.md.
3. **Decide the Valdena location** and record it as an assumption in decisions.md. Re-run the Open-Meteo pull for that point. The Milan probe is not valid evidence.
4. **Ask the Data Protection Office** to confirm that daily district counts may be used for the warning service.
5. **Read the Eurostat licence at source.** Get project lead sign-off on the 0.24 prototype coverage if N6 is kept.
6. **Decide the method for the traffic break** on 2024-03-18 (adjust, model, or train only after the break).
7. **Decide the VR-03 treatment** (exclude or model separately) and get the catalog corrected.
8. **Once the gate is passed, profile first:** the UCI 360 file after -200 recoding, the date format, and the GT columns; then station-level completeness for 2024–2025 and the VR-03 gap; then traffic hourly completeness and the pre/post-break comparison; then clinic zero-day handling. Do not profile internal data before access is approved.

## 7. Open questions for the human reviewer

1. Which location should be used for Valdena? No source names the city, and decisions.md does not yet hold the assumption.
2. Does the Health Office's warning service count as non-commercial under the Open-Meteo free tier, or will a paid subscription be bought? Who decides?
3. Does research-only use of UCI 360 cover building a method that later feeds a live clinic warning? Who in Legal decides?
4. Should the three blocker-level licence flags (Open-Meteo, UCI 360, Eurostat) still be rated "with conditions", or should any be rated not feasible until resolved? The discovery applied its calibration rules, and the reviewer should confirm.
5. Is the Eurostat series worth keeping as N6 context, given it covers only 2005 of the prototype window and nothing in production?
6. Is station VR-03 still closed, and do the other stations report continuously through 2025-12-31? Who can confirm this in the Environment Monitoring Unit?
7. Can traffic counts be compared before and after 2024-03-18 with an agreed adjustment, or should training use only the post-break period?
8. Does the Data Protection Office accept daily district counts for this use, and will district-to-station mapping be provided, or should the analysis proceed without a station join?
9. How should zero-visit days and small cells be handled in the clinic counts?
10. Should anyone request an allowlist change for catalog.data.gov? The discovery does not recommend it.

---

## Human review gate

Draft generated by the discovery agents for UC1 on 2026-11-11T14:38:57Z (model claude-haiku-5-5). It is a draft for review, not a decision.

Before any profiling or pipeline work, the reviewer confirms:

- [ ] Each verdict is supported by the evidence cited
- [ ] Every licence was read at its source, and the attribution text is recorded
- [ ] Access requests for the feasible-with-conditions sources are raised with the named owners
- [ ] Consent and purpose limits are understood, and the target population is filtered accordingly

**Blocker flags on sources not rejected (resolve or justify):**

- api.open_meteo_archive: LIC-NONCOMMERCIAL
- link.europa_sdg_11_52_099aa6: LIC-UNKNOWN
- link.uci_360: LIC-NONCOMMERCIAL

**Open questions:**

1. Which location should be used for Valdena? No source names the city, and decisions.md does not yet hold the location assumption.
2. Does the Health Office's clinic warning service count as non-commercial under the Open-Meteo free tier, or will a paid subscription be bought? Who decides?
3. Does research-only use of UCI 360 cover building a method that later feeds a live clinic warning? Who in Legal decides?
4. Should the three blocker-level licence flags (Open-Meteo, UCI 360, Eurostat) stay rated 'feasible with conditions', or should any be rated not feasible until resolved?
5. Is the Eurostat SDG 11.52 series worth keeping as N6 context, given it covers only 2005 of the prototype window and nothing in production?
6. Is station VR-03 still closed after 2024-06-30, and do the other stations report continuously through 2025-12-31? Who in the Environment Monitoring Unit can confirm?
7. Can traffic counts be compared before and after the 2024-03-18 counting change with an agreed adjustment, or should training use only post-change data?
8. Will the Data Protection Office accept daily district counts for the warning service, and will a district-to-station mapping be provided, or should the analysis proceed without a station join?
9. How should zero-visit days and small cells be handled in the clinic counts?
10. Should anyone request an allowlist change for catalog.data.gov? The discovery does not recommend it.

Reviewer: ____________________   Date: __________   Decision: proceed / proceed with conditions / stop
