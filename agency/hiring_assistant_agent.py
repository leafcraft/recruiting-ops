"""hiring_assistant_agent — first-round async screen, with the weighted
rubric score and the bias-flag gate enforced as deterministic floors.

@pre_compose  load_candidate — pull the candidate record (resume + the
              resume-screen result that already passed) so the interviewer
              scores the CONVERSATION against a real person.
@chain        enforce_rubric_floors — floors the LLM can't waive:
              (a) WEIGHTED SCORE: recompute weighted_score from the
                  rubric_scores × weights (don't trust the model's
                  self-reported total), then DERIVE the recommendation
                  from the score thresholds — advance ≥0.70, borderline
                  ≥0.55, else decline.
              (b) BIAS FLAGS: any forbidden-topic flag forces
                  requires_hrbp_review=true → HRBP, overriding any positive
                  recommendation.
              (c) MALFORMED GUARD: a missing candidate_id/req_id is
                  error_skipped, never auto-declined.
              Then it records the screen onto the candidate (ATS write).

WHY PYTHON: the recommendation is a hire-influencing decision; the
threshold arithmetic and the bias override are compliance-critical and
must be deterministic, reproducible, unit-tested — not a prompt's promise.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from leafmesh import LeafMeshLogger, pre_compose, chain
from agency._shared import store

logger = LeafMeshLogger(__name__)

ADVANCE_FLOOR = 0.70
BORDERLINE_FLOOR = 0.55

_DEFAULTS: dict[str, Any] = {
    "screen_id": "", "candidate_id": "", "req_id": "", "rubric_scores": [],
    "weighted_score": 0.0, "recommendation": "", "bias_flags": [],
    "transcript_chars": 0, "duration_minutes": 0, "requires_hrbp_review": False,
    "requires_hiring_manager_review": False, "conducted_at_utc": "",
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


def load_candidate(data: Any, ctx: Any) -> dict[str, Any]:
    cid = str(_pick(data, "candidate_id") or "")
    cand = store.get_candidate(cid) if cid else {}
    return {"context": {
        "candidate_id": cid,
        "candidate": cand,
        "prior_screen_score": cand.get("prior_screen_score", 0.0),
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


def _weighted(rubric: list[Any]) -> float:
    total = 0.0
    for r in rubric:
        if not isinstance(r, dict):
            continue
        try:
            total += float(r.get("score", 0) or 0) * float(r.get("weight", 0) or 0)
        except (TypeError, ValueError):
            continue
    return round(max(0.0, min(total, 1.0)), 2)


async def enforce_rubric_floors(result: dict[str, Any], ctx: Any) -> dict[str, Any]:
    # (c) MALFORMED GUARD — a missing id never becomes an auto-decline.
    if not result.get("candidate_id") or not result.get("req_id"):
        result["recommendation"] = "error_skipped"
        result["requires_hrbp_review"] = False
        result["requires_hiring_manager_review"] = False
        result["screen_id"] = ""
        result["weighted_score"] = 0.0
        logger.warning("[screen] malformed payload — error_skipped (no auto-decline)")
        return result

    # (a) WEIGHTED SCORE — recompute, then derive the recommendation.
    score = _weighted(result.get("rubric_scores") or [])
    result["weighted_score"] = score
    if score >= ADVANCE_FLOOR:
        result["recommendation"] = "advance"
    elif score >= BORDERLINE_FLOOR:
        result["recommendation"] = "borderline"
    else:
        result["recommendation"] = "decline"

    # (b) BIAS FLAGS — any flag → HRBP, overriding the recommendation.
    has_bias = bool(result.get("bias_flags"))
    result["requires_hrbp_review"] = has_bias
    result["requires_hiring_manager_review"] = (
        result["recommendation"] in ("advance", "borderline") and not has_bias
    )

    # ATS write — persist the screen result onto the candidate.
    store.record_screen(result["candidate_id"], score, result["recommendation"])
    logger.info(
        f"[screen] {result['candidate_id']} score={score} "
        f"rec={result['recommendation']} bias={has_bias}")
    return result


@pre_compose(context_processor=load_candidate)
@chain(enforce_rubric_floors)
async def hiring_assistant_agent(llm_response: Any, input_data: Any,
                                 context: Any) -> dict[str, Any]:
    llm = _parse(llm_response)
    out = {**_DEFAULTS}
    for k in _DEFAULTS:
        if k in llm:
            out[k] = llm[k]
    out["candidate_id"] = str(out.get("candidate_id") or _pick(input_data, "candidate_id") or "")
    out["req_id"] = str(out.get("req_id") or _pick(input_data, "req_id") or "")
    if not out["conducted_at_utc"]:
        out["conducted_at_utc"] = datetime.now(timezone.utc).isoformat()
    if not out["screen_id"] and out["candidate_id"]:
        out["screen_id"] = f"screen-{out['candidate_id']}-{uuid.uuid4().hex[:10]}"
    logger.info("[screen] scored (enforce_rubric_floors derives rec + bias gate)")
    return out
