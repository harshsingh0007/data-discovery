# UC2 Feasibility Memo: Ice-cream sales, weather and holidays

As of 2026-10-15. Client: Valdena Gelato Shop (fictional, northern Italy). Discovery generated 2026-11-11 by model claude-haiku-5-5.

## 1. Executive summary

**Verdict: feasible with conditions. No source is blocked, but the must-have product-code mapping (N2) is only partly met and is the critical path.**

Facts that drive the verdict:

1. **No blocker.** No source is unreachable, unlicensed, or out of window. Every must need (N1, N2, N3) has at least one candidate source, but each depends on conditions.
2. **Product-level sales (N1) are restricted.** `internal.sales.daily_by_product` requires a request to Retail Operations. Access is not yet approved and reachability was not tested. No data values were sampled.
3. **The 2024 code change breaks the join (N2).** Codes ending in "L" were retired on 2024-04-01 and replaced. The wiki (`product_codes_2024`) says no mapping table exists. Old and new codes can only be matched by name, and some names are not unique. The current product list does not hold old codes. So N2 is **partially met**. The sources as they stand cannot answer decision 2 for all products.
4. **Weather (N3) is available but needs a location decision and sign-off.** Open-Meteo archive is the only source for daily maximum temperature. The shop's coordinates are not stated anywhere. The Milan point used in probes is a probe only. Data is modelled reanalysis, not station data. Legal sign-off is needed for production.
5. **Known sales gap.** No sales exist from 2024-02-05 to 2024-03-10 (wiki `till_migration_2024`). These days must be treated as missing, not zero. The shop calendar (N5) is needed to tell closed days from missing data, and its row count does not match its declared coverage.

## 2. Need coverage

| need id | need | priority | status | best source(s) | gap |
|---|---|---|---|---|---|
| N1 | Daily ice-cream sales by product | must | met with conditions | internal.sales.daily_by_product | Access not approved; reachability untested; start date 2022-01-01 unverified; no rows 2024-02-05 to 2024-03-10 |
| N2 | Mapping of product codes before and after the 2024 code change | must | **partially met** | internal.sales.daily_by_product; internal.sales.products | No mapping table; retired "L" codes have no link to current codes; name matching ambiguous (non-unique names) |
| N3 | Daily maximum temperature | must | met with conditions | api.open_meteo_archive | Shop coordinates not chosen; full history window not probed; reanalysis, not station data; Legal sign-off for production |
| N4 | Public holidays in Italy | should | met with conditions | api.nager_public_holidays | Full IT list not confirmed (truncated in probes); regional entries and Pasquetta unverified; data-level licence and official-source check outstanding |
| N5 | Shop opening days and local events | should | met with conditions | internal.store.calendar | Row count (1500) does not match declared coverage from 2022; is_open meaning around the till gap and holidays undocumented; access not verified |

## 3. Source assessments

### api.nager_public_holidays
- **What it is:** Open REST API returning the public-holiday calendar for a year and country code. For IT, the probes returned about 13 to 14 dated entries per year. Grain is one record per holiday date (record summary).
- **Verdict:** feasible with conditions.
- **Key flags:**
  - DQ-METADATA-CONTRADICTION (minor, judgement). The record summary calls the IT list "short." The discovery notes it was truncated in probes ("... 10 more items" in 2025, "... 11 more" in 2026). `has_missing_values` is null. Completeness is unverified.
  - GOV-CATALOG-WIKI-CONFLICT (minor, judgement). The register and repository do not confirm an official Italian calendar as the source.
- **Licence and owner:** Record summary gives MIT. The discovery says this is the code repository licence only, and the LICENSE text did not render. The data-level licence is not confirmed. Owner is null. Refresh cadence is unknown. The discovery rationale says the source is approved for "prototyping and production," but no fetched source states this. Treat it as unconfirmed.
- **Conditions:** Re-probe the full IT list for 2023, 2025 and 2026. Check Pasquetta and any regional entries. Confirm the data licence. Verify dates against an official Italian source. Documentation host nagerholidays.com is not allowlisted. Do not work around this.

### api.open_meteo_archive
- **What it is:** Modelled historical weather (reanalysis), served per coordinate. The daily variable `temperature_2m_max` (°C) gives a daily maximum temperature series for any latitude, longitude and timezone (record summary).
- **Verdict:** feasible with conditions.
- **Key flags:**
  - LIC-ATTRIBUTION (minor, rule). Licence CC BY 4.0. Attribution text: "Weather data by Open-Meteo.com."
  - LIC-MIXED (major, rule). The upstream source is Copernicus C3S. Its specific licence is not named in the fetched licence page. Major, but not a blocker.
- **Coverage:** Probes confirmed responses at the ends of the recent window only (2025-06-01 to 2025-06-03; 2026-03-29 to 2026-03-31) at the Milan probe point. The full history window was not probed. Archive start date: unknown (no source states it).
- **Owner:** null in record.
- **Conditions:** Cite Open-Meteo.com and C3S in all outputs. Read the C3S licence. Legal must confirm production use and commercial use under CC BY 4.0 (policy.open_data_links). Choose and justify the shop's coordinates and record them as an assumption. Use timezone Europe/Rome. Probe the full window and check for gaps. Treat as modelled data, not station data.

### internal.sales.daily_by_product
- **What it is:** Units sold and revenue (EUR) per product code per day, from the till system, in warehouse table `sales.daily_by_product` (about 310,000 rows, approximate). One row per sale_date and product_code. No store or geography column (record summary).
- **Verdict:** feasible with conditions.
- **Key flags:**
  - ACC-RESTRICTED (major, rule). Classification confidential. Access by request to Retail Operations. Reachability not tested.
  - INT-JOIN-KEY-MISMATCH (major, judgement). Codes ending in "L" were replaced from 2024-04-01. No mapping table exists (wiki `product_codes_2024`, dated 2024-04-02). Product codes were re-keyed.
  - DQ-SEMANTIC-ENCODING (minor, judgement). The meaning of the "L" suffix is only in the wiki. Timezone of sale_date is undocumented.
- **Coverage and freshness:** Catalog start 2022-01-01, open-ended, refreshed daily, last refreshed 2026-10-14. The 2022 start has not been verified. No values were sampled.
- **Licence and owner:** internal; owner Retail Operations.
- **Conditions:** Get access approved before profiling. Build a documented old-to-new code mapping with Retail Operations and the steward. Treat 2024-02-05 to 2024-03-10 as missing. Confirm whether closed days have no rows. Confirm the start date and timezone from a bounded sample after access.

### internal.sales.products
- **What it is:** Static master list of current product codes, names and categories, about 64 rows. It describes only codes in use now, with no effective dates (record summary).
- **Verdict:** feasible with conditions. It supports N2 but cannot satisfy it alone.
- **Key flags:**
  - ACC-RESTRICTED (major, rule). Classification internal. Request process: open to analytics roles. Not tested.
  - INT-NO-JOIN-KEY (major, judgement). The catalog says it "lists only the current codes." It has no old-code or mapping column. No key links retired codes to it.
- **Metadata:** last updated 2025-03-31; refresh on change; owner Retail Operations.
- **Conditions:** Get access approved. Use only as a name reference for the N2 mapping. Search for any pre-2024 product list or code history table. This was not searched.

### internal.store.calendar
- **What it is:** Daily calendar of the shop. One row per day with `calendar_date`, an `is_open` flag and a free-text `event_name` (record summary).
- **Verdict:** feasible with conditions.
- **Key flags:**
  - ACC-RESTRICTED (major, rule). Classification internal. Role membership not verified.
  - DQ-METADATA-CONTRADICTION (major, judgement). Catalog row count is about 1500. Declared coverage from 2022-01-01 is about 1744 to 1749 days. About 244 rows are missing, or the count is stale. No sample read.
  - DQ-SENTINEL-VALUES (minor, judgement). `is_open` for 2024-02-05 to 2024-03-10 is unknown and could be read as closed. Semantics for holidays and partial days are undocumented.
- **Metadata:** last refreshed 2026-10-10; refresh weekly; owner Store Operations.
- **Conditions:** Get access approved. Check row completeness and reconcile the count. Confirm `is_open` for the till gap and for holidays. Store Operations to document `is_open` and `event_name`.

## 4. Red-flag register

| source_id | code | severity | evidence | raised by |
|---|---|---|---|---|
| api.nager_public_holidays | DQ-METADATA-CONTRADICTION | minor | List truncated in probes ("... 10 more" 2025; "... 11 more" 2026); has_missing_values null | judgement (not raised as a flag; noted) |
| api.nager_public_holidays | GOV-CATALOG-WIKI-CONFLICT | minor | Official Italian calendar not confirmed by register or repository | judgement (not raised; noted) |
| api.open_meteo_archive | LIC-ATTRIBUTION | minor | CC BY 4.0; attribution "Weather data by Open-Meteo.com" | rule |
| api.open_meteo_archive | LIC-MIXED | major | Upstream Copernicus C3S licence not named in fetched text; mixed_sources true | rule |
| internal.sales.daily_by_product | ACC-RESTRICTED | major | auth_required true; confidential; request to Retail Operations; untested | rule |
| internal.sales.daily_by_product | INT-JOIN-KEY-MISMATCH | major | Codes ending "L" re-keyed 2024-04-01; no mapping table (wiki product_codes_2024) | judgement |
| internal.sales.daily_by_product | DQ-SEMANTIC-ENCODING | minor | "L" suffix meaning only in wiki; sale_date timezone undocumented | judgement |
| internal.sales.products | ACC-RESTRICTED | major | auth_required true; internal; access not tested | rule |
| internal.sales.products | INT-NO-JOIN-KEY | major | Current codes only; no old-code or mapping column | judgement |
| internal.store.calendar | ACC-RESTRICTED | major | auth_required true; internal; role not verified | rule |
| internal.store.calendar | DQ-METADATA-CONTRADICTION | major | Row count about 1500 vs about 1744 days from 2022-01-01 | judgement |
| internal.store.calendar | DQ-SENTINEL-VALUES | minor | is_open unknown for 2024-02-05 to 2024-03-10; holiday semantics undocumented | judgement |

No red flag is a blocker. Rule-raised flags were kept. Discovery notes no rule warnings and no dismissed flags.

## 5. Conditions and owners

Discovery returned no named resolvers (`who_can_resolve` is empty for every source). The owners below come from catalog metadata. Confirm them with the data owners.

| condition | source(s) | who can resolve it | blocking which need |
|---|---|---|---|
| Access request approved and reachability tested | internal.sales.daily_by_product; internal.store.calendar; internal.sales.products | Retail Operations (sales, products); Store Operations (calendar) | N1, N2, N5 |
| Old-to-new product code mapping built and documented | internal.sales.daily_by_product; internal.sales.products | Retail Operations and the data steward (not named) | N2 |
| Search for pre-2024 product list or code history | internal.sales.products | Retail Operations | N2 |
| Treat 2024-02-05 to 2024-03-10 as missing; confirm is_open for that window | internal.sales.daily_by_product; internal.store.calendar | Retail Operations; Store Operations | N1, N5 |
| Reconcile calendar row count (1500 vs about 1744) and check completeness | internal.store.calendar | Store Operations | N5 |
| Document is_open and event_name semantics | internal.store.calendar | Store Operations | N5 |
| Confirm 2022-01-01 start and sale_date timezone | internal.sales.daily_by_product | Retail Operations (after access) | N1, N2 |
| Choose and justify shop coordinates (recorded in decisions.md) | api.open_meteo_archive | Shop owner / analytics lead (not named in sources) | N3 |
| Probe full history window and check gaps | api.open_meteo_archive | Analytics team (no external approval needed per record) | N3 |
| Legal sign-off for production use; confirm commercial use under CC BY 4.0 and the C3S upstream licence | api.open_meteo_archive | Legal | N3 (production) |
| Confirm data-level licence and commercial-use status of holiday data | api.nager_public_holidays | Legal, or the analytics lead (not named in sources) | N4 |
| Re-probe full IT holiday list; check Pasquetta and regional entries | api.nager_public_holidays | Analytics team | N4 |
| Verify holiday dates against an official Italian source | api.nager_public_holidays | Analytics team | N4 |
| Documentation host access (nagerholidays.com not allowlisted) | api.nager_public_holidays | Only if needed; request approval, do not work around | N4 (optional) |

## 6. Recommended next steps

1. **Raise access requests now.** Ask Retail Operations for access to `sales.daily_by_product` and `internal.sales.products`. Ask Store Operations for access to the shop calendar. Test reachability once approved.
2. **Start the N2 mapping work with Retail Operations.** This is the critical path. Ask whether a pre-2024 product list or code history exists. Agree a name-based mapping method and a manual rule for non-unique names. Record the result in decisions.md.
3. **Ask Legal for a production sign-off on Open-Meteo.** Ask them to read the C3S upstream licence and confirm commercial use under CC BY 4.0. Prototyping is permitted now.
4. **Decide the shop's location.** Choose coordinates, justify them, and record them as an assumption in decisions.md. Use timezone Europe/Rome.
5. **Probe the Open-Meteo history window** (2023-06-01 to 2025-05-31) for nulls and gaps. Record the archive start date.
6. **Re-probe the Nager.Date IT list** for 2023, 2025 and 2026 without truncation. Check Pasquetta and regional entries. Confirm the data licence. Verify dates against an official Italian source.
7. **Decide how to treat the till gap** (2024-02-05 to 2024-03-10) as missing, not zero, and document that decision.
8. **Once the gate is passed, profile in this order:**
   - Sales: check the 2022 start, the sale_date timezone, and row patterns around 2024-04-01 (code change) and the 2024-02-05 to 2024-03-10 gap.
   - Calendar: check row completeness against the 2022-01-01 start and how closed days appear.
   - Weather: check nulls and gaps across the full history window.
   - Holidays: check the full list for each year.

## 7. Open questions for the human reviewer

1. Is a "partially met" status acceptable for a must need (N2)? Discovery's overall verdict is "feasible with conditions," but the must-have mapping is not yet possible. Can the business proceed with product-level analysis only for products whose codes can be matched?
2. Which shop location should be used for temperature (N3)? Who makes that call, and what justification is acceptable?
3. Does Legal approve Open-Meteo for production use, including commercial use and the C3S upstream licence? When?
4. Is the Nager.Date data licence (MIT on the repository only) acceptable, or does the team need a data-level licence confirmation first?
5. The discovery rationale for `internal.sales.daily_by_product` says ACC-RESTRICTED is the only flag above minor. The same record lists INT-JOIN-KEY-MISMATCH as major. Is the join-key issue a major flag for the gate, as the record says?
6. The shop calendar row count (about 1500) does not match the declared coverage (about 1744 days). Is the calendar stale or incomplete? Which is correct?
7. Does a pre-2024 product list or code history table exist, and who holds it?
8. Who is the named data steward for the sales table, the product list and the calendar? The discovery returned no named resolvers.
9. Does the shop record closed days as no rows in sales, or as `is_open = false` in the calendar? How are public holidays flagged?
10. Is the 2022-01-01 start date for sales and the calendar confirmed? The discovery did not verify it.
11. Should holiday dates be checked against an official Italian source before use? Who will do that?

---

## Human review gate

Draft generated by the discovery agents for UC2 on 2026-11-11T14:50:32Z (model claude-haiku-5-5). It is a draft for review, not a decision.

Before any profiling or pipeline work, the reviewer confirms:

- [ ] Each verdict is supported by the evidence cited
- [ ] Every licence was read at its source, and the attribution text is recorded
- [ ] Access requests for the feasible-with-conditions sources are raised with the named owners
- [ ] Consent and purpose limits are understood, and the target population is filtered accordingly

**Open questions:**

1. Is a 'partially met' status acceptable for a must need (N2), given the mapping gap? Can the business proceed with product-level analysis only for products whose codes can be matched?
2. Which shop location should be used for temperature (N3)? Who decides, and what justification is acceptable?
3. Does Legal approve Open-Meteo for production use, including commercial use under CC BY 4.0 and the Copernicus C3S upstream licence? When?
4. Is the Nager.Date data licence acceptable, given only the repository MIT licence was found and the data-level licence is unconfirmed?
5. The discovery rationale for internal.sales.daily_by_product says ACC-RESTRICTED is the only flag above minor, yet INT-JOIN-KEY-MISMATCH is recorded as major. Is the join-key issue a gate blocker or a condition?
6. The shop calendar catalog row count (about 1500) does not match the declared coverage from 2022-01-01 (about 1744 days). Is the calendar stale or incomplete?
7. Does a pre-2024 product list or code history table exist, and who holds it?
8. Who are the named data stewards for the sales table, product list and shop calendar? Discovery returned no named resolvers.
9. Does the shop record closed days as missing rows in sales, or as is_open = false in the calendar? How are public holidays flagged?
10. Are the 2022-01-01 start date for sales and the calendar confirmed? Discovery did not verify them.
11. Who will verify holiday dates against an official Italian source before production use?

Reviewer: ____________________   Date: __________   Decision: proceed / proceed with conditions / stop
