# UC2: Ice-cream sales, weather and holidays

**Client:** Valdena Gelato Shop (fictional, northern Italy)
**Requested by:** Shop owner
**As-of date for this discovery:** 2026-10-15

## Business problem
The shop orders ice cream a week ahead. It over-orders on quiet days and runs out on hot days and holidays. The owner wants to know whether hot days and public holidays raise sales enough to plan orders around them.

## Decisions this discovery supports
1. Is there enough daily sales history to measure the effect of weather and holidays?
2. Can the product codes be matched across the 2024 code change? If not, which products can be compared?
3. Which red flags must be resolved before a forecast is built?

## Scope
- **History window:** 2023-06-01 to 2025-05-31, two summers of daily sales.
- **Recent window:** 2025-06-01 to 2026-03-31.
- **Geography:** Italy. No source names the shop's city. Choose a location you can justify, record it as an assumption in `decisions.md`, and set those coordinates in the Open-Meteo call.
- **Out of scope:** customer-level data. The shop does not record it.

## Needs
The canonical list, with IDs, grains and windows, is in `UC2_ice_cream.json`. In short:

| ID | Need | Priority |
|---|---|---|
| N1 | Daily ice-cream sales by product | must |
| N2 | Mapping of product codes before and after the 2024 code change | must |
| N3 | Daily maximum temperature | must |
| N4 | Public holidays in Italy | should |
| N5 | Shop opening days and local events | should |

## Where to look
- The internal catalog export and the two wiki pages in `internal/UC2_valdena_gelato/`.
- The register: the weather API and the holiday API are tagged for this use case.
- This use case has no dataset links. Weather and holidays come from the register APIs.
