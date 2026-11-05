"""correspondence_drafter_agent — drafts ALL candidate correspondence
(outreach / offer / rejection), with the salary-band gate and the
rejection-personalisation floor enforced as deterministic floors.

@pre_compose  load_candidate_context — pull the req's CONFIRMED salary
              band + the candidate record (resume + prior screen) from the
              ATS (dev: store) so an offer is checked against the real band
              and a rejection can reference real background.
@chain        enforce_correspondence_floors — floors the LLM can't waive:
              (a) SALARY BAND: for an offer, recompute within_band from the
                  STORE's band vs the offered number — never trust the
                  model's self-report. Out-of-band OR an unconfirmed (0/0)
                  band forces requires_hrbp_review=true. Fails CLOSED when
                  the band is unknown.
              (b) REJECTION: an unpersonalisable or too-short rejection
                  forces requires_recruiter_review=true — a letter that
                  could not be personalised never goes out unreviewed.
@compose      per-downstream payloads — the HRBP needs the band math, the
              hiring manager needs the clean offer, the WORM log needs a
              compact audit record. Each peer gets exactly what it needs.

WHY PYTHON: an out-of-band offer is the single most expensive thing this
mesh can get wrong (pay-equity / budget exposure). The band check must be
deterministic code reading the band of record, not a prompt asking nicely.
"""
from __future__ import annotations

import json
import re
from typing import Any

from leafmesh import LeafMeshLogger, pre_compose, chain, compose
from agency._shared import store

logger = LeafMeshLogger(__name__)

MIN_REJECTION_CHARS = 120   # shorter than this → too generic to send unreviewed

_DEFAULTS: dict[str, Any] = {
    "correspondence_type": "", "message_body": "", "cited_signals": [],
    "offer_body": "", "within_band": False, "requires_hrbp_review": False,
    "candidate_facing_message": "", "rejection_stage": "", "reason_class": "",
    "personalisation_signal": "", "alternate_roles_suggested": [],
    "requires_recruiter_review": False, "offer_amount_cents": 0, "req_id": "",
}


def _pick(data: Any, key: str) -> Any:
    if not isinstance(data, dict):
        return None
    if data.get(key) not in (None, ""):
        return data[key]
    for blob_key in ("upstream_yields", "candidate_context", "human_data"):
        blob = data.get(blob_key)
        if isinstance(blob, dict):
            if blob.get(key) not in (None, ""):
                return blob[key]
            for v in blob.values():
                if isinstance(v, dict) and v.get(key) not in (None, ""):
                    return v[key]
    return None


def load_candidate_context(data: Any, ctx: Any) -> dict[str, Any]:
    """Pull the confirmed salary band + the candidate record."""
    rid = str(_pick(data, "req_id") or "")
    cid = str(_pick(data, "candidate_id") or "")
    low, high = store.salary_band(rid) if rid else (0, 0)
    cand = store.get_candidate_for_review(cid) if cid else {}
    return {"context": {
        "req_id": rid,
        "candidate_id": cid,
        "candidate": cand,
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


def _ctx(ctx: Any) -> dict[str, Any]:
    prepared = (ctx or {}).get("prepared_data", {}) if isinstance(ctx, dict) else {}
    c = prepared.get("context", {}) if isinstance(prepared, dict) else {}
    return c if isinstance(c, dict) else {}


async def enforce_correspondence_floors(result: dict[str, Any],
                                        ctx: Any) -> dict[str, Any]:
    c = _ctx(ctx)
    ctype = str(result.get("correspondence_type", "")).lower()

    if ctype == "offer":
        low = int(c.get("salary_band_low_cents") or 0)
        high = int(c.get("salary_band_high_cents") or 0)
        amount = int(result.get("offer_amount_cents") or 0)
        band_confirmed = bool(low and high)
        # Recompute within_band from the band of record. An unconfirmed
        # band (0/0) or a missing amount fails CLOSED → HRBP.
        if not band_confirmed or amount <= 0:
            result["within_band"] = False
        else:
            result["within_band"] = low <= amount <= high
        if not result["within_band"]:
            result["requires_hrbp_review"] = True   # force — never sent without HRBP
            logger.info(
                f"[corr] OFFER band gate → HRBP "
                f"(amount={amount} band={low}-{high} confirmed={band_confirmed})")
        # Persist the offer so the finisher (Ora) can recover it AFTER the
        # hiring-manager approval step drops the upstream payload. PROD: HRIS.
        rid = str(result.get("req_id") or c.get("req_id") or "")
        if rid:
            store.put_offer(rid, {
                "req_id": rid,
                "candidate_id": str(c.get("candidate_id") or ""),
                "offer_amount_cents": amount,
                "offer_body": str(result.get("offer_body") or ""),
                "within_band": result["within_band"],
            })

    elif ctype == "rejection":
        msg = str(result.get("candidate_facing_message", ""))
        signal = str(result.get("personalisation_signal", ""))
        stage = str(result.get("rejection_stage", "")).lower()
        if (not signal or len(msg) < MIN_REJECTION_CHARS
                or stage in ("interview", "final_round", "offer_declined")):
            result["requires_recruiter_review"] = True
            logger.info("[corr] REJECTION personalisation floor → recruiter review")

    return result


# ── @compose per-peer payloads ───────────────────────────────────────
def _to_hrbp(result: dict, ctx: Any) -> dict[str, Any]:
    c = _ctx(ctx)
    return {
        "req_id": result.get("req_id", "") or c.get("req_id", ""),
        "candidate_id": c.get("candidate_id", ""),
        "offer_amount_cents": result.get("offer_amount_cents", 0),
        "salary_band_low_cents": c.get("salary_band_low_cents", 0),
        "salary_band_high_cents": c.get("salary_band_high_cents", 0),
        "within_band": result.get("within_band", False),
        "offer_body": result.get("offer_body", ""),
    }


def _to_hiring_manager(result: dict, ctx: Any) -> dict[str, Any]:
    c = _ctx(ctx)
    return {
        "req_id": result.get("req_id", "") or c.get("req_id", ""),
        "candidate_id": c.get("candidate_id", ""),
        "offer_body": result.get("offer_body", ""),
        "offer_amount_cents": result.get("offer_amount_cents", 0),
        "within_band": result.get("within_band", False),
    }


def _to_audit(result: dict, ctx: Any) -> dict[str, Any]:
    c = _ctx(ctx)
    return {
        "session_id": (ctx or {}).get("session_id", "") if isinstance(ctx, dict) else "",
        "payload": {
            "event": "candidate_correspondence",
            "correspondence_type": result.get("correspondence_type", ""),
            "req_id": result.get("req_id", "") or c.get("req_id", ""),
            "candidate_id": c.get("candidate_id", ""),
            "within_band": result.get("within_band", False),
            "rejection_stage": result.get("rejection_stage", ""),
            "reason_class": result.get("reason_class", ""),
        },
    }


@pre_compose(context_processor=load_candidate_context)
@compose(
    hrbp_human=_to_hrbp,
    hiring_manager_human=_to_hiring_manager,
    recruiting_audit_logger_agent=_to_audit,
)
@chain(enforce_correspondence_floors)
async def correspondence_drafter_agent(llm_response: Any, input_data: Any,
                                       context: Any) -> dict[str, Any]:
    llm = _parse(llm_response)
    c = _ctx(context)
    out = {**_DEFAULTS}
    for k in _DEFAULTS:
        if k in llm:
            out[k] = llm[k]
    out["req_id"] = str(out.get("req_id") or c.get("req_id") or "")
    out["correspondence_type"] = str(out.get("correspondence_type") or "outreach")
    out["offer_amount_cents"] = int(out.get("offer_amount_cents") or 0)
    logger.info(
        f"[corr] type={out['correspondence_type']} "
        f"(enforce_correspondence_floors holds band + personalisation floors)")
    return out
