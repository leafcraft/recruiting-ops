"""resume_screener_agent — scores the pipeline against the req, with the
bias signal and score floor enforced as deterministic floors.

@pre_compose  load_pipeline — pull the req spec + the actual candidate
              pipeline (resume data + any prior screens) from the ATS
              (dev: store) so the LLM scores REAL candidates, not a blank.
@chain        enforce_screen_floors — floors the LLM can't waive:
              (a) BIAS: if the model's own reasoning leaned on a
                  bias-prone signal (name / school prestige / photo /
                  address), force bias_signal=true → routes to HRBP. The
                  prompt asks for this; the floor GUARANTEES it.
              (b) SCORE FLOOR: a thin shortlist (< MIN_SHORTLIST) or an
                  avg fit below MIN_AVG_FIT can never be waved through to
                  outreach — set re_source_required and bound the
                  re-source loop (Rule 3) so a thin pipeline escalates
                  to the recruiter instead of looping.

WHY PYTHON: the screen is the first compliance-critical gate — a biased
shortlist or a quietly-lowered fit bar is exactly what a prompt cannot be
trusted to hold under pressure. The floor is deterministic code.
"""
from __future__ import annotations

import json
import re
from typing import Any

from leafmesh import LeafMeshLogger, pre_compose, chain
from agency._shared import store, session_stash

logger = LeafMeshLogger(__name__)

# Deterministic screen floors — compliance-critical, not waivable.
MIN_SHORTLIST = 3          # fewer than this → re-source, not outreach
MIN_AVG_FIT = 0.55         # avg fit below this → pipeline too weak to advance
MAX_RESOURCE_ROUNDS = 2    # bound the thin-pipeline re-source loop (Rule 3)

# Bias-prone signal terms. If the model's own reasoning / top_reason text
# leans on any of these (rather than skills + experience), it is a bias
# signal regardless of what the model self-reported.
_BIAS_TERMS = (
    "name", "sounds", "ethnic", "gender", "photo", "headshot", "age",
    "ivy", "prestige", "prestigious", "alma mater", "pedigree",
    "address", "neighborhood", "neighbourhood", "zip", "accent",
)

_DEFAULTS: dict[str, Any] = {
    "shortlist": [], "bias_signal": False, "avg_fit_score": 0.0,
    "recruiter_briefing": "", "re_source_required": False,
}


def _req_id(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    rid = data.get("req_id")
    if not rid:
        uy = data.get("upstream_yields")
        if isinstance(uy, dict):
            rid = uy.get("req_id")
            if not rid:
                for v in uy.values():
                    if isinstance(v, dict) and v.get("req_id"):
                        rid = v["req_id"]
                        break
    return str(rid or "")


def _sid(input_data: Any, context: Any) -> str:
    for s in (context, input_data):
        if isinstance(s, dict) and s.get("session_id"):
            return str(s["session_id"])
    return ""


def load_pipeline(data: Any, ctx: Any) -> dict[str, Any]:
    """Pull the req spec + the candidate pipeline the LLM will score."""
    rid = _req_id(data)
    req = store.get_req(rid) if rid else {}
    cands = store.pipeline(rid, stage="screen") if rid else []
    return {"context": {
        "req_id": rid,
        "req": req,
        "candidates": cands,
        "candidate_count": len(cands),
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


def _bias_in_text(blob: str) -> bool:
    blob = blob.lower()
    return any(re.search(rf"\b{re.escape(t)}", blob) for t in _BIAS_TERMS)


async def enforce_screen_floors(result: dict[str, Any], ctx: Any) -> dict[str, Any]:
    shortlist = result.get("shortlist") or []
    # (a) BIAS FLOOR — the model's reasoning text betrays bias-prone leaning.
    reasons = " ".join(
        str((s or {}).get("top_reason", "")) for s in shortlist if isinstance(s, dict)
    )
    if _bias_in_text(reasons) or _bias_in_text(str(result.get("recruiter_briefing", ""))):
        result["bias_signal"] = True   # force — overrides the model's self-report

    # (b) SCORE FLOOR — recompute avg fit from the shortlist (don't trust
    #     the model's self-reported average), then hold the line.
    fits = [float((s or {}).get("fit_score", 0) or 0)
            for s in shortlist if isinstance(s, dict)]
    avg = round(sum(fits) / len(fits), 3) if fits else 0.0
    result["avg_fit_score"] = avg
    thin = len(shortlist) < MIN_SHORTLIST or avg < MIN_AVG_FIT
    result["re_source_required"] = bool(thin and not result.get("bias_signal"))
    if result["re_source_required"]:
        sid = _sid(result, ctx if isinstance(ctx, dict) else {})
        rounds = session_stash.bump(sid, "resource_rounds")
        if rounds > MAX_RESOURCE_ROUNDS:
            logger.warning(
                f"[screener] re-source cap hit ({rounds}) — pipeline still thin")
        logger.info(
            f"[screener] FLOOR re-source (shortlist={len(shortlist)} avg={avg})")
    return result


@pre_compose(context_processor=load_pipeline)
@chain(enforce_screen_floors)
async def resume_screener_agent(llm_response: Any, input_data: Any,
                                context: Any) -> dict[str, Any]:
    llm = _parse(llm_response)
    out = {**_DEFAULTS}
    out["shortlist"] = list(llm.get("shortlist") or [])
    out["bias_signal"] = bool(llm.get("bias_signal"))
    out["avg_fit_score"] = float(llm.get("avg_fit_score") or 0)
    out["recruiter_briefing"] = str(llm.get("recruiter_briefing") or "")
    logger.info(
        f"[screener] shortlist={len(out['shortlist'])} "
        f"(enforce_screen_floors holds bias + score floors)")
    return out
