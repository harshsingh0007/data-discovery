# UC1: Air quality and traffic

**Client:** Valdena Civic Health Office (fictional, northern Italy)
**Requested by:** Head of Public Health Surveillance
**As-of date for this discovery:** 2026-10-15

## Business problem
On poor-air days, respiratory patients who visit the clinic are more likely to be unwell. The Health Office wants to warn patients a day ahead when air quality is likely to be poor. Before anyone builds a model, it needs to know which data exists, what each dataset covers, and what must be fixed first.

## Decisions this discovery supports
1. Can the method be prototyped now on public hourly air-quality data, while the city's own station data is requested?
2. Does the city's own data cover two years of air quality, traffic and clinic visits at the needed grain?
3. Which data cannot be used at all, and why?
4. Which red flags must be resolved before profiling starts?

## Scope
- **Prototype window:** 2004-03-10 to 2005-04-04, on public hourly readings from an Italian city.
- **Production window:** 2024-01-01 to 2025-12-31, on the city's own data.
- **Geography:** Italy. No source names the client's city. Choose a location you can justify, record it as an assumption in `decisions.md`, and set those coordinates in the Open-Meteo call. The register's default (Lisbon) is not the client's location.
- **Out of scope:** individual patient records. The clinic may only share daily counts by district.

## Needs
The canonical list, with IDs, grains and windows, is in `UC1_air_quality.json`. In short:

| ID | Need | Priority |
|---|---|---|
| N1 | Hourly air-pollutant concentrations | must |
| N2 | Hourly vehicle traffic near the monitoring stations | must |
| N3 | Hourly temperature and humidity | must |
| N4 | Daily respiratory clinic visits, as counts by district | should |
| N5 | Patient-level clinic visit records | could |
| N6 | National yearly context: deaths linked to PM2.5 | could |

## Where to look
- The internal catalog export and the three wiki pages in `internal/UC1_valdena_health/`.
- The register: the weather API and the holiday API are tagged for this use case.
- The three dataset links in `links/UC1_example_links.json`.
