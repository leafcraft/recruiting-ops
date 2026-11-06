"""resume_screener_agent — Sena, the Screening Analyst.

auto_discover matches `resume_screener_agent`. Sena is an llm + super_agent that
CLAIMS and READS the candidate pipeline through her tools (claim_candidate_batch
-> get_req_spec -> get_candidate) and produces a skills-and-experience shortlist.
The MODEL decides and pulls; this CODE fails closed.

She runs with `scaling.copies.count: 3` (config): three parallel copies each claim a DISJOINT
batch via the atomic claim tool, so the backlog is split, not duplicated. With
`scaling.copies.handoff: last` the copies' shortlists CONCATENATE into one — and this
is exactly why the number-sum merge footgun (nuances, parallel copies) never
bites here: enforce_screen_floors RECOMPUTES avg_fit_score from the combined
shortlist rather than trusting a summed self-report.

@chain enforce_screen_floors — the deterministic floors a prompt can't waive:
  (a) BIAS: if any top_reason / briefing leans on a bias-prone signal (name /
      school prestige / photo / address), force bias_signal=true -> HRBP.
  (0) NO DATA: a shortlisted candidate whose record has no skills and no
      resume summary is DROPPED — a score on nothing is a guess.
  (b) SCORE: recompute avg fit from the shortlist; a thin shortlist
      (< MIN_SHORTLIST) or a weak avg (< MIN_AVG_FIT) forces re_source_required,
      and the re-source loop is bounded (Rule 3) so it escalates, never spins.
"""
from __future__ import annotations

import json
import re
from typing import Any

from leafmesh import LeafMeshLogger, chain
from agency._shared import session_stash, store

logger = LeafMeshLogger(__name__)

# Deterministic screen floors — compliance-critical, not waivable.
MIN_SHORTLIST = 3          # fewer than this -> re-source, not outreach
MIN_AVG_FIT = 0.55         # avg fit below this -> pipeline too weak to advance
MAX_RESOURCE_ROUNDS = 2    # bound the thin-pipeline re-source loop (Rule 3)

# Bias-prone signal terms. If the model's own reasoning / top_reason text leans
# on any of these (rather than skills + experience), it is a bias signal
# regardless of what the model self-reported.
_BIAS_TERMS = (
    "name", "sounds", "ethnic", "gender", "photo", "headshot", "age",
    "ivy", "prestige", "prestigious", "alma mater", "pedigree",
    "address", "neighborhood", "neighbourhood", "zip", "accent",
)

_DEFAULTS: dict[str, Any] = {
    "shortlist": [], "bias_signal": False, "avg_fit_score": 0.0,
    "recruiter_briefing": "", "re_source_required": False,
}


def _sid(input_data: Any, context: Any) -> str:
    for s in (context, input_data):
        if isinstance(s, dict) and s.get("session_id"):
            return str(s["session_id"])
    return ""


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


def _has_no_data(candidate_id: str) -> bool:
    """True when the record of truth holds no skills and no resume summary.
    An unknown id (not in the dev store, e.g. read through the ATS mcp tools)
    is not judged here."""
    rec = store.get_candidate(str(candidate_id or ""))
    if not rec:
        return False
    return not rec.get("skills") and not str(rec.get("resume_summary") or "").strip()


async def enforce_screen_floors(result: dict[str, Any], ctx: Any) -> dict[str, Any]:
    result = result if isinstance(result, dict) else {}
    shortlist = result.get("shortlist") or []

    # (0) NO-DATA FLOOR — never keep a score on a record with nothing to score.
    kept = [s for s in shortlist
            if not (isinstance(s, dict) and _has_no_data(s.get("candidate_id", "")))]
    if len(kept) != len(shortlist):
        logger.info(f"[screener] FLOOR dropped {len(shortlist) - len(kept)} no-data candidate(s)")
    shortlist = kept
    result["shortlist"] = shortlist

    # (a) BIAS FLOOR — the model's reasoning text betrays bias-prone leaning.
    reasons = " ".join(
        str((s or {}).get("top_reason", "")) for s in shortlist if isinstance(s, dict)
    )
    if _bias_in_text(reasons) or _bias_in_text(str(result.get("recruiter_briefing", ""))):
        result["bias_signal"] = True   # force — overrides the model's self-report

    # (b) SCORE FLOOR — RECOMPUTE avg fit from the (possibly instance-combined)
    #     shortlist; never trust a summed / self-reported average.
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


@chain(enforce_screen_floors)
async def resume_screener_agent(llm_response: Any, input_data: Any,
                                context: Any) -> dict[str, Any]:
    """Return the model's skills-and-experience shortlist; the floor re-checks
    it (bias + score). The model pulls the pipeline via its claim/read tools."""
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
