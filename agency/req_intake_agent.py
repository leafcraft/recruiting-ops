"""req_intake_agent — normalises the requisition, grounded in the ATS and
held to a deterministic completeness floor.

@pre_compose  load_req_context — pull what intake must reason over BEFORE
              it normalises: (a) any PRIOR req with the same req_id (a
              re-submission of a req already on file) and (b) any likely
              DUPLICATE open req with the same title, plus (c) the role's
              CONFIRMED salary band of record. So the LLM normalises against
              the ATS — flagging a re-source-twice duplicate and never
              inventing a band the comp record already pins.
@chain        enforce_completeness_floor — the floor the LLM can't waive:
              a req missing title, level, OR a confirmed salary band (a 0/0
              band = HRBP-unconfirmed) is FORCED incomplete (req_complete =
              false) and routed to the recruiter to fix — never passed to
              sourcing, which would query the ATS blind / source against an
              unpinned band. The prompt asks for clean extraction; this
              GUARANTEES an underspecified req can't slip downstream.

WHY PYTHON: sourcing spend and pay-equity exposure both start here. A
title-less req queries the ATS blind; a band-less req sources against a
comp number nobody confirmed. "Is this req actually complete?" is a gate,
not a vibe — it must be deterministic code reading the record of truth.
"""
from __future__ import annotations

import json
import re
from typing import Any

from leafmesh import LeafMeshLogger, pre_compose, chain
from agency._shared import store

logger = LeafMeshLogger(__name__)

# A level the org actually ladders against — anything else is "unspecified"
# and the req is not yet sourceable.
_VALID_LEVELS = {"jr", "junior", "mid", "sr", "senior", "staff", "principal"}

_DEFAULTS: dict[str, Any] = {
    "req_id": "", "title": "", "level": "", "location": "",
    "salary_band_low_cents": 0, "salary_band_high_cents": 0,
    "req_complete": False, "missing_fields": [],
    "duplicate_req_id": "", "prior_req_id": "",
}


def _pick(data: Any, key: str) -> Any:
    """Read a field from the intake payload, tolerating the upstream-yields /
    payload nesting the entry point may wrap it in."""
    if not isinstance(data, dict):
        return None
    if data.get(key) not in (None, ""):
        return data[key]
    for blob_key in ("payload", "upstream_yields", "original_webhook_data"):
        blob = data.get(blob_key)
        if isinstance(blob, dict):
            if blob.get(key) not in (None, ""):
                return blob[key]
            for v in blob.values():
                if isinstance(v, dict) and v.get(key) not in (None, ""):
                    return v[key]
    return None


def load_req_context(data: Any, ctx: Any) -> dict[str, Any]:
    """Pull the prior/duplicate req + the confirmed band of record so the
    LLM normalises against the ATS, not a blank."""
    rid = str(_pick(data, "req_id") or "")
    title = str(_pick(data, "title") or "")
    prior = store.get_req(rid) if rid else {}
    duplicate = store.find_duplicate_req(title, exclude_req_id=rid)
    low, high = store.salary_band(rid) if rid else (0, 0)
    return {"context": {
        "req_id": rid,
        "prior_req": prior,
        "prior_req_id": prior.get("req_id", ""),
        "duplicate_req": duplicate,
        "duplicate_req_id": duplicate.get("req_id", ""),
        "salary_band_low_cents": low,
        "salary_band_high_cents": high,
        "band_confirmed": bool(low and high),
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


def assess_completeness(req: dict[str, Any]) -> list[str]:
    """The deterministic completeness rule, isolated so it is trivially
    testable: a req is sourceable ONLY with a title, a recognised level,
    and a CONFIRMED band (both ends > 0; a 0/0 band is HRBP-unconfirmed).
    Returns the list of missing/invalid fields — empty means complete."""
    missing: list[str] = []
    if not str(req.get("title") or "").strip():
        missing.append("title")
    if str(req.get("level") or "").strip().lower() not in _VALID_LEVELS:
        missing.append("level")
    low = int(req.get("salary_band_low_cents") or 0)
    high = int(req.get("salary_band_high_cents") or 0)
    if not (low > 0 and high > 0):
        missing.append("salary_band")
    return missing


async def enforce_completeness_floor(result: dict[str, Any],
                                     ctx: Any) -> dict[str, Any]:
    """Force req_complete from the record, not the model's say-so. A req
    missing title / level / confirmed band can NEVER be marked complete —
    it routes to the recruiter (the config edges fire on req_complete),
    not to sourcing."""
    missing = assess_completeness(result)
    result["missing_fields"] = missing
    result["req_complete"] = not missing      # FORCED — overrides any self-report
    if missing:
        logger.info(
            f"[intake] FLOOR incomplete req={result.get('req_id','?')} "
            f"missing={missing} → recruiter (not sourcing)")
    return result


@pre_compose(context_processor=load_req_context)
@chain(enforce_completeness_floor)
async def req_intake_agent(llm_response: Any, input_data: Any,
                           context: Any) -> dict[str, Any]:
    llm = _parse(llm_response)
    out = {**_DEFAULTS}
    out["req_id"] = str(llm.get("req_id") or "")
    out["title"] = str(llm.get("title") or "").strip()
    out["level"] = str(llm.get("level") or "").strip()
    out["location"] = str(llm.get("location") or "").strip()
    out["salary_band_low_cents"] = int(llm.get("salary_band_low_cents") or 0)
    out["salary_band_high_cents"] = int(llm.get("salary_band_high_cents") or 0)
    # Carry the dedupe signal the @pre_compose surfaced (best-effort — the
    # entry point may also have echoed it through context).
    if isinstance(llm.get("duplicate_req_id"), str):
        out["duplicate_req_id"] = llm["duplicate_req_id"]
    if isinstance(llm.get("prior_req_id"), str):
        out["prior_req_id"] = llm["prior_req_id"]
    logger.info(
        f"[intake] normalised req={out['req_id'] or '?'} "
        f"(enforce_completeness_floor sets req_complete)")
    return out
