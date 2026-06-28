"""interview_coordinator_agent — designs the interview loop, with the
duration cap, the mandatory HM debrief, and the diversity floor enforced
as deterministic floors.

@pre_compose  load_roster — pull the req's required dimensions + the
              actual interviewer roster (dev: store) so the loop is built
              from REAL panelists with real levels, not invented ones.
@chain        enforce_loop_floors — floors the LLM can't waive:
              (a) DURATION CAP: drop panels from the back until the loop
                  fits within MAX_LOOP_MINUTES (5h).
              (b) HM DEBRIEF: always append the hiring-manager debrief slot.
              (c) DIVERSITY: panel_diversity_ok is true ONLY when the
                  panels span ≥2 distinct interviewer levels — recomputed,
                  not trusted.
              (d) REVIEW FLOOR: a non-diverse OR too-thin (< MIN_LOOP_MINUTES)
                  loop forces requires_recruiter_review=true.

WHY PYTHON: the duration cap and the diversity floor are candidate-fairness
controls — a loop that's too long burns the candidate, a non-diverse panel
is a bias risk. Recomputing from the actual panels is the only honest check.
"""
from __future__ import annotations

import json
import re
from typing import Any

from leafmesh import LeafMeshLogger, pre_compose, chain
from agency._shared import store

logger = LeafMeshLogger(__name__)

MAX_LOOP_MINUTES = 300     # 5h hard cap
MIN_LOOP_MINUTES = 120     # sub-2h loop is too thin to assess
HM_DEBRIEF = {
    "kind": "hm_debrief", "title": "Hiring manager debrief",
    "duration_minutes": 30, "interviewer_role": "hiring_manager",
    "interviewer_level": "", "dimension": "decision",
}

_DEFAULTS: dict[str, Any] = {
    "req_id": "", "role_level": "", "panels": [], "total_minutes": 0,
    "dimensions_covered": [], "panel_diversity_ok": False,
    "requires_recruiter_review": False, "loop_briefing": "",
}


def _pick(data: Any, key: str) -> Any:
    if not isinstance(data, dict):
        return None
    if data.get(key) not in (None, ""):
        return data[key]
    uy = data.get("upstream_yields")
    if isinstance(uy, dict):
        if uy.get(key) not in (None, ""):
            return uy[key]
        for v in uy.values():
            if isinstance(v, dict) and v.get(key) not in (None, ""):
                return v[key]
    return None


def load_roster(data: Any, ctx: Any) -> dict[str, Any]:
    rid = str(_pick(data, "req_id") or "")
    req = store.get_req(rid) if rid else {}
    dims = store.required_dimensions(rid) if rid else []
    return {"context": {
        "req_id": rid,
        "role_level": req.get("level", "mid"),
        "required_dimensions": dims,
        "interviewer_roster": store.interviewer_roster(dims),
    }}


def _parse(resp: Any) -> dict[str, Any]:
    if isinstance(resp, dict):
        return resp
    if isinstance(resp, str):
        try:
            return json.loads(resp)
        except ValueError:
            m = re.search(r"\{.*\}", resp, re.S)
            if m:
                try:
                    return json.loads(m.group(0))
                except ValueError:
                    pass
    return {}


def _minutes(p: Any) -> int:
    try:
        return int((p or {}).get("duration_minutes", 0) or 0)
    except (TypeError, ValueError):
        return 0


async def enforce_loop_floors(result: dict[str, Any], ctx: Any) -> dict[str, Any]:
    panels = [p for p in (result.get("panels") or []) if isinstance(p, dict)]
    # Strip any HM debrief the model already added — we re-append exactly one.
    panels = [p for p in panels if p.get("kind") != "hm_debrief"]

    # (a) DURATION CAP — drop interview panels from the back until they fit
    #     (reserve room for the 30-min debrief we append below).
    budget = MAX_LOOP_MINUTES - HM_DEBRIEF["duration_minutes"]
    kept: list[dict[str, Any]] = []
    running = 0
    for p in panels:
        m = _minutes(p)
        if running + m > budget:
            continue
        kept.append(p)
        running += m

    # (b) HM DEBRIEF — always present, last.
    kept.append(dict(HM_DEBRIEF))
    result["panels"] = kept
    result["total_minutes"] = sum(_minutes(p) for p in kept)

    # (c) DIVERSITY — recompute from the actual interview panels.
    levels = {str((p or {}).get("interviewer_level", "")).strip()
              for p in kept if p.get("kind") != "hm_debrief"}
    levels.discard("")
    result["panel_diversity_ok"] = len(levels) >= 2
    result["dimensions_covered"] = sorted(
        {str((p or {}).get("dimension", "")) for p in kept if p.get("dimension")})

    # (d) REVIEW FLOOR — non-diverse or too-thin loop → recruiter.
    result["requires_recruiter_review"] = (
        not result["panel_diversity_ok"] or result["total_minutes"] < MIN_LOOP_MINUTES
    )
    logger.info(
        f"[loop] panels={len(kept)} mins={result['total_minutes']} "
        f"diverse={result['panel_diversity_ok']} "
        f"review={result['requires_recruiter_review']}")
    return result


@pre_compose(context_processor=load_roster)
@chain(enforce_loop_floors)
async def interview_coordinator_agent(llm_response: Any, input_data: Any,
                                      context: Any) -> dict[str, Any]:
    llm = _parse(llm_response)
    out = {**_DEFAULTS}
    for k in _DEFAULTS:
        if k in llm:
            out[k] = llm[k]
    out["req_id"] = str(out.get("req_id") or _pick(input_data, "req_id") or "")
    out["role_level"] = str(out.get("role_level") or _pick(input_data, "level") or "mid")
    logger.info("[loop] designed (enforce_loop_floors holds cap + diversity + debrief)")
    return out
