"""bias_audit_agent — EEOC 4/5ths-rule adverse-impact audit.

WHY THIS STAYS PYTHON: the 4/5ths rule (EEOC Uniform Guidelines,
29 CFR 1607.4(D)) is compliance-grade DOMAIN MATH — per-group
selection-rate ratios with a minimum-sample floor, where a wrong
number is a legal exposure. It must be deterministic, reproducible
and unit-testable code; an LLM estimate is not defensible in an
audit. Everything else this module once did (SQLite findings
ledger) was glue and is gone: screening decisions arrive in the
INPUT (export from YOUR ATS, posted to the weekly_bias_audit entry
point) and findings flow to hrbp_human + the WORM audit log
through the mesh.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from leafmesh import LeafMeshLogger

logger = LeafMeshLogger(__name__)

# EEOC 4/5ths rule — adverse impact if selection rate for any
# protected group is < 80% of the rate for the highest group.
ADVERSE_IMPACT_THRESHOLD = 0.80

# Minimum sample per group before a comparison is statistically
# worth drawing (tiny groups produce noise, not findings).
MIN_GROUP_SAMPLE = 5

# Dimensions to audit if the customer's data has them; never invent.
DEMOGRAPHIC_DIMENSIONS = ("gender", "ethnicity", "age_band", "veteran",
                          "disability")

_ADVANCE_DECISIONS = frozenset({"advance", "advanced", "approve"})


def _four_fifths_check(group_rates: dict[str, float]) -> dict[str, Any]:
    """Apply the EEOC 4/5ths rule across groups."""
    if not group_rates or len(group_rates) < 2:
        return {"adverse_impact": False, "comparisons": []}
    majority_group, majority_rate = max(group_rates.items(), key=lambda kv: kv[1])
    if majority_rate == 0:
        return {"adverse_impact": False, "comparisons": []}
    comparisons = []
    adverse = False
    for group, rate in group_rates.items():
        if group == majority_group:
            continue
        ratio = rate / majority_rate if majority_rate else 0.0
        is_adverse = ratio < ADVERSE_IMPACT_THRESHOLD
        if is_adverse:
            adverse = True
        comparisons.append({
            "majority_group": majority_group,
            "minority_group": group,
            "majority_rate": round(majority_rate, 3),
            "minority_rate": round(rate, 3),
            "ratio": round(ratio, 3),
            "adverse_impact": is_adverse,
        })
    return {"adverse_impact": adverse, "comparisons": comparisons,
            "majority_group": majority_group,
            "majority_rate": round(majority_rate, 3)}


async def bias_audit_agent(llm_response, input_data, context):
    # Input: list of screening decisions in the audit window
    # [{candidate_id, req_id, decision, demographics: {gender, ...}}]
    decisions = list(input_data.get("decisions") or [])
    window_days = int(input_data.get("window_days") or 30)
    now = datetime.now(timezone.utc)
    window_start = (now - timedelta(days=window_days)).isoformat()
    window_end = now.isoformat()

    findings: list[dict[str, Any]] = []
    adverse_impact_count = 0

    for dim in DEMOGRAPHIC_DIMENSIONS:
        group_totals: dict[str, int] = defaultdict(int)
        group_advanced: dict[str, int] = defaultdict(int)
        for d in decisions:
            if not isinstance(d, dict):
                continue
            demo = d.get("demographics") or {}
            if dim not in demo or not demo[dim]:
                continue
            group = str(demo[dim]).lower()
            group_totals[group] += 1
            if str(d.get("decision", "")).lower() in _ADVANCE_DECISIONS:
                group_advanced[group] += 1

        if len(group_totals) < 2:
            continue   # Can't compare with only one group

        qualified_groups = {g: t for g, t in group_totals.items()
                            if t >= MIN_GROUP_SAMPLE}
        if len(qualified_groups) < 2:
            continue

        group_rates = {
            g: (group_advanced.get(g, 0) / qualified_groups[g])
            for g in qualified_groups
        }
        result = _four_fifths_check(group_rates)

        findings.append({
            "finding_id": f"audit-{dim}-{int(now.timestamp())}",
            "dimension": dim,
            "group_totals": dict(qualified_groups),
            "group_advance_rates": {k: round(v, 3)
                                      for k, v in group_rates.items()},
            "majority_group": result.get("majority_group"),
            "comparisons": result["comparisons"],
            "adverse_impact": result["adverse_impact"],
        })
        if result["adverse_impact"]:
            adverse_impact_count += 1

    requires_hrbp = adverse_impact_count > 0
    logger.info(
        f"[bias-audit] decisions={len(decisions)} findings={len(findings)} "
        f"adverse={adverse_impact_count}"
    )

    return {
        "action": "audit",
        "window_start_utc": window_start,
        "window_end_utc": window_end,
        "decisions_audited": len(decisions),
        "findings": findings,
        "adverse_impact_count": adverse_impact_count,
        "requires_hrbp_review": requires_hrbp,
        "generated_at_utc": now.isoformat(),
    }
