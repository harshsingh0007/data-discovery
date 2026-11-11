# Memo review — UC2

Reviewer: Harsh  
Date: 2026-11-11

## Overall verdict agreement

I agree with **feasible_with_conditions**. No source is blocked or out of window, but the must-have product-code mapping (N2) is the critical path. The N2 mapping gap is the critical path. No production analysis should run until Retail Operations confirms whether a mapping table exists or can be built.

## Per-source review

**internal.sales.daily_by_product** — Verdict correct. Access restricted and the 2024 code re-keying is the real risk. INT-JOIN-KEY-MISMATCH is a major flag, not just a minor condition. No mapping table means any product-level analysis crossing the 2024 boundary will have gaps. Retail Operations must attempt a mapping before production.

**internal.sales.products** — Verdict correct. Current codes only, no old-code column, no effective dates. Useful as a name reference for the N2 mapping but cannot satisfy N2 alone. Access request to Retail Operations is the first step.

**internal.store.calendar** — Verdict correct. Row count (~1500) does not match declared coverage (~1744 days from 2022-01-01). That gap must be reconciled with Store Operations before the calendar is used to distinguish closed days from missing data.

**api.open_meteo_archive** — Verdict correct. CC BY 4.0 with an upstream Copernicus C3S licence that was not confirmed. Legal must sign off before production. Analytics lead decides the shop coordinates. Coordinates must be chosen and recorded in decisions.md before any real Open-Meteo probe runs.

**api.nager_public_holidays** — Verdict correct. Data-level licence is unconfirmed (only repository MIT found). IT list was truncated in probes. Pasquetta and regional entries unverified. Re-probe the full list and confirm the licence before use.

## N2 — partially met

Acceptable for prototype. We can proceed knowing product-level analysis crossing the 2024 boundary will have gaps. Retail Operations must attempt a mapping before production.

## Flags I checked

- INT-JOIN-KEY-MISMATCH on sales.daily_by_product: wiki product_codes_2024 confirms codes ending "L" were retired 2024-04-01 with no mapping table. Flag is correct and major.
- DQ-METADATA-CONTRADICTION on store.calendar: row count ~1500 vs ~1744 days from 2022-01-01. Flag is correct.
- ACC-RESTRICTED on all three internal sources: none tested for reachability. Flags are correct.
- LIC-MIXED on Open-Meteo: Copernicus C3S licence not named in fetched text. Flag is correct.

## Open questions I am deferring

- Q1: N2 partially met is acceptable for prototype (answered above).
- Q2: Analytics lead decides shop coordinates. Must be recorded in decisions.md before any probe (answered above).
- Q3: Legal to confirm Open-Meteo production use and C3S licence. Not answerable during discovery.
- Q4: Legal or analytics lead to confirm Nager.Date data-level licence. Not answerable during discovery.
- Q5–Q11: Deferred to Retail Operations, Store Operations, and the analytics lead as named in the memo.
