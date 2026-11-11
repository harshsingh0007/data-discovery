"""Deterministic red-flag rules, run on every catalog record before the Risk Assessor agent.

Why rules and an agent? Rules are cheap, repeatable and testable, and they catch what can be
read from structured fields. The agent adds judgement flags (conflicts, consent gaps,
representativeness, ...) and may dismiss a rule flag only with a written reason, and the
orchestrator enforces that.

Each rule: (record, candidate, use_case, settings) -> list of {"code", "evidence"}.
"""
from __future__ import annotations

import re
from datetime import date

Flag = dict

GRAIN_ORDER = ["minute", "15min", "30min", "hourly", "daily", "weekly", "monthly", "quarterly", "annual"]
INACTIVE_STATUSES = {"deprecated", "archived", "frozen", "retired", "decommissioned", "superseded"}


def _flag(code: str, evidence: str) -> Flag:
    return {"code": code, "evidence": evidence}


def _d(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Provided rules (read these as worked examples)
# ---------------------------------------------------------------------------
def rule_licence(record: dict, candidate: dict, uc: dict, settings: dict) -> list[Flag]:
    if record["kind"] == "internal":
        return []
    lic = record.get("licence") or {}
    name = (lic.get("name") or "").strip()
    flags = []
    if not name or name.lower() in {"unknown", "none", "null", "not found", "n/a"}:
        flags.append(_flag("LIC-UNKNOWN", f"No licence established. Evidence field: {lic.get('evidence')!r}"))
    elif re.search(r"\bNC\b|non[- ]?commercial", name, re.I):
        flags.append(_flag("LIC-NONCOMMERCIAL", f"Licence {name!r} restricts commercial use"))
    elif re.search(r"\bBY\b|attribution|OGL|open government", name, re.I):
        flags.append(_flag("LIC-ATTRIBUTION", f"Licence {name!r} requires attribution"))
    if lic.get("mixed_sources"):
        flags.append(_flag("LIC-MIXED", "Record states that parts come from upstream providers with different terms"))
    return flags


def rule_agreement(record: dict, candidate: dict, uc: dict, settings: dict) -> list[Flag]:
    status = ((record.get("licence") or {}).get("agreement_status") or "").lower()
    if record["kind"] == "vendor_feed" and status not in {"active", "signed"}:
        return [_flag("LIC-AGREEMENT-NOT-ACTIVE", f"Vendor feed with agreement_status={status or 'unknown'!r}")]
    return []


def rule_access(record: dict, candidate: dict, uc: dict, settings: dict) -> list[Flag]:
    acc = record.get("access") or {}
    flags = []
    if acc.get("auth_required") or (acc.get("classification") or "").lower() == "restricted":
        flags.append(_flag("ACC-RESTRICTED", f"auth_required={acc.get('auth_required')}, "
                                             f"classification={acc.get('classification')}, process={acc.get('request_process')!r}"))
    if (acc.get("method") or "").lower() in {"manual_export", "manual", "spreadsheet", "email"}:
        flags.append(_flag("ACC-MANUAL", f"Access method {acc.get('method')!r}"))
    if acc.get("reachable") is False:
        flags.append(_flag("ACC-UNREACHABLE", "Record states the source could not be reached or restored"))
    return flags


def rule_payload(record: dict, candidate: dict, uc: dict, settings: dict) -> list[Flag]:
    size = (record.get("access") or {}).get("approx_size_bytes")
    limit = settings["rules"]["large_payload_bytes"]
    if isinstance(size, int) and size > limit:
        return [_flag("OPS-LARGE-PAYLOAD", f"approx_size_bytes={size:,} > {limit:,}")]
    return []


def rule_pii(record: dict, candidate: dict, uc: dict, settings: dict) -> list[Flag]:
    pii_fields = [f["name"] for f in (record.get("schema") or {}).get("fields", []) if f.get("pii") is True]
    declared = (record.get("declared_metadata") or {}).get("contains_pii")
    if pii_fields or declared is True:
        return [_flag("GOV-PII", f"PII fields: {pii_fields or 'declared contains_pii=true'}")]
    return []


def rule_owner(record: dict, candidate: dict, uc: dict, settings: dict) -> list[Flag]:
    if record["kind"] == "internal" and not ((record.get("ownership") or {}).get("owner") or "").strip():
        return [_flag("GOV-OWNER-UNKNOWN", "Internal source with no recorded owner")]
    return []


def rule_status(record: dict, candidate: dict, uc: dict, settings: dict) -> list[Flag]:
    status = (record.get("status") or "").lower()
    if status in INACTIVE_STATUSES:
        return [_flag("GOV-DEPRECATED", f"status={status!r}")]
    return []


# ---------------------------------------------------------------------------
# LEARNER TODO (G4): three rules. tests/test_learner_gaps.py::test_g4_* checks them.
# ---------------------------------------------------------------------------
def rule_temporal_coverage(record: dict, candidate: dict, uc: dict, settings: dict) -> list[Flag]:
    """Coverage of the candidate's target windows, plus staleness.

    - Skip records whose temporal.grain is "static", or whose start is unknown.
    - Treat a null end as "still updating", i.e. covered up to uc["as_of"].
    - For each window id in candidate["target_windows"], compute the fraction of that window
      (uc["windows"], inclusive dates) covered by [start, end].
        all fractions == 0                                      -> COV-OUT-OF-WINDOW
        otherwise any fraction < settings["rules"]["partial_window_threshold"] -> COV-PARTIAL-WINDOW
    - FRS-STALE if end is not null and end is more than settings["rules"]["stale_after_years"]
      years before uc["as_of"].
    Evidence strings must name the window(s) and the dates you compared.
    """
    temporal = record.get("temporal") or {}
    grain = (temporal.get("grain") or "").lower()
    if grain == "static":
        return []
    rec_start = _d(temporal.get("start"))
    if rec_start is None:
        return []
    as_of = _d(uc.get("as_of")) or date.today()
    rec_end = _d(temporal.get("end")) or as_of

    threshold = settings["rules"]["partial_window_threshold"]
    stale_years = settings["rules"]["stale_after_years"]
    windows_by_id = {w["id"]: w for w in uc.get("windows", [])}

    fractions: list[tuple[str, float]] = []
    for wid in candidate.get("target_windows", []):
        w = windows_by_id.get(wid)
        if not w:
            continue
        w_start = _d(w["start"])
        w_end = _d(w["end"])
        if w_start is None or w_end is None:
            continue
        window_days = (w_end - w_start).days + 1
        if window_days <= 0:
            continue
        overlap_start = max(rec_start, w_start)
        overlap_end = min(rec_end, w_end)
        overlap_days = max(0, (overlap_end - overlap_start).days + 1)
        fractions.append((wid, overlap_days / window_days))

    flags: list[Flag] = []
    if fractions:
        all_zero = all(f == 0 for _, f in fractions)
        windows_str = ", ".join(wid for wid, _ in fractions)
        if all_zero:
            flags.append(_flag("COV-OUT-OF-WINDOW",
                               f"No overlap with window(s) {windows_str}: "
                               f"record {rec_start}–{rec_end}"))
        elif any(f < threshold for _, f in fractions):
            partial = [(wid, round(f, 2)) for wid, f in fractions if f < threshold]
            flags.append(_flag("COV-PARTIAL-WINDOW",
                               f"Partial coverage in window(s) {', '.join(wid for wid, _ in partial)}: "
                               f"fractions {partial}, threshold {threshold}; "
                               f"record {rec_start}–{rec_end}"))

    # Staleness: only when end is explicitly set (not null/open-ended)
    if _d(temporal.get("end")) is not None:
        end_explicit = _d(temporal.get("end"))
        years_old = (as_of - end_explicit).days / 365.25
        if years_old > stale_years:
            flags.append(_flag("FRS-STALE",
                               f"Record ends {end_explicit} which is {years_old:.1f} years before "
                               f"as_of {as_of} (threshold {stale_years} years)"))
    return flags


def rule_grain(record: dict, candidate: dict, uc: dict, settings: dict) -> list[Flag]:
    """COV-GRAIN-MISMATCH if the record's grain is coarser than min_grain of any need the
    candidate serves (candidate["need_ids"] -> uc["needs"]). Only grains in GRAIN_ORDER are
    comparable; "event", "static" and "unknown" on either side never raise the flag."""
    rec_grain = (record.get("temporal") or {}).get("grain") or ""
    if rec_grain not in GRAIN_ORDER:
        return []
    rec_idx = GRAIN_ORDER.index(rec_grain)
    needs_by_id = {n["id"]: n for n in uc.get("needs", [])}
    for nid in candidate.get("need_ids", []):
        need = needs_by_id.get(nid)
        if not need:
            continue
        min_grain = need.get("min_grain") or ""
        if min_grain not in GRAIN_ORDER:
            continue
        if rec_idx > GRAIN_ORDER.index(min_grain):
            return [_flag("COV-GRAIN-MISMATCH",
                          f"Record grain {rec_grain!r} is coarser than need {nid} min_grain {min_grain!r}")]
    return []


def rule_metadata_contradiction(record: dict, candidate: dict, uc: dict, settings: dict) -> list[Flag]:
    """DQ-METADATA-CONTRADICTION when record["declared_metadata"]["has_missing_values"] is a
    'no' (False, "no", "false") but documentation_excerpts or quality_notes describe missing
    values (e.g. "missing values", "absence of value", "-200", "?" used as missing, "NaN").
    Careful: "Data set has no missing values" is NOT a contradiction. Strip negated phrases
    before matching."""
    declared = (record.get("declared_metadata") or {}).get("has_missing_values")
    if str(declared).strip().lower() not in {"no", "false", "0"}:
        return []

    text = " ".join(
        (record.get("documentation_excerpts") or []) + (record.get("quality_notes") or [])
    )
    # Strip negated phrases so "has no missing values" doesn't trigger the indicator search
    text = re.sub(r"\b(?:no|not any|without|has no|does?\s+not?\s+have|contains?\s+no)\s+"
                  r"(?:missing|absent)\s+\w*", " ", text, flags=re.I)

    indicators = re.search(
        r"missing[- ]?values?|absent\s+values?|tagged\s+with\s+-200"
        r"|\babsence\s+of\s+value|\bNaN\b|-200\s+value",
        text, re.I
    )
    if indicators:
        snippet = text[max(0, indicators.start() - 30): indicators.end() + 30].strip()
        return [_flag("DQ-METADATA-CONTRADICTION",
                      f"declared has_missing_values={declared!r} but text says: {snippet!r}")]
    return []


RULES = [rule_licence, rule_agreement, rule_access, rule_payload, rule_pii, rule_owner, rule_status,
         rule_temporal_coverage, rule_grain, rule_metadata_contradiction]


def evaluate(record: dict, candidate: dict, uc: dict, settings: dict) -> tuple[list[Flag], list[str]]:
    """Run every rule. Returns (flags, warnings). A rule that is not implemented yet is skipped with a warning."""
    flags: list[Flag] = []
    warnings: list[str] = []
    for rule in RULES:
        try:
            for f in rule(record, candidate, uc, settings):
                flags.append({**f, "raised_by": f"rule:{rule.__name__}"})
        except NotImplementedError as exc:
            warnings.append(f"{rule.__name__} skipped: {exc}")
    seen, unique = set(), []
    for f in flags:
        if f["code"] not in seen:
            seen.add(f["code"])
            unique.append(f)
    return unique, warnings
