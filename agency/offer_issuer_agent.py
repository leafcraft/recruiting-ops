"""Ora — Offer Issuer (the FINISHER / actuator).

auto_discover matches `offer_issuer_agent`. Ora sits BEHIND the hiring-manager
approval step. She never approves — she re-checks that a human actually approved,
re-derives the salary band from the record, renders the real offer letter, and
records an append-only ledger entry. She is the concrete "@chain fails closed":

  a) approval RE-CHECK — reaching this agent does NOT mean approved. An
     allow-token allowlist + block-token denylist; an UNKNOWN verdict fails closed.
  b) deterministic invariants a human can't waive — a recovered offer with a
     real amount, and within_band RE-DERIVED from the band of record (an
     out-of-band offer never issues, whatever the human clicked; a 0/0
     unconfirmed band fails closed).
  c) render the real offer letter to ./out; on a tripped floor, DELETE the
     partial and record `status: blocked` with reasons — never a half-issued offer.
  d) dev-store recovery — after the HITL gate the upstream payload is dropped,
     so Ora recovers the offer from the session stash / dev store, and the
     dev-store delivery ANNOUNCES itself (it is not a real send ack).

Idempotent per offer: the same terms (req + candidate + amount) already
issued are not issued twice — a re-approval or a replayed hand-off is blocked,
not re-rendered and re-ledgered. A revised offer (a new amount) issues.
"""
from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Any

from leafmesh import LeafMeshLogger, chain

try:
    from ._shared import store
    from ._shared.session_stash import resolve_session_id, stash_get, stash_put
except ImportError:  # pragma: no cover — direct-run fallback
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _shared import store  # type: ignore
    from _shared.session_stash import resolve_session_id, stash_get, stash_put  # type: ignore

logger = LeafMeshLogger(__name__)

_OUT_DIR = Path("./out")
_APPROVE_TOKENS = frozenset({"approved", "approve", "sign", "signed", "yes", "ok"})
_BLOCK_TOKENS = frozenset({"rejected", "reject", "no", "deny", "denied",
                           "held", "held_for_review", "hold"})


def _signal(input_data: dict) -> str:
    """The human verdict, from wherever the SDK delivered it (shape-tolerant)."""
    sources = [input_data]
    up = input_data.get("upstream_yields")
    if isinstance(up, dict):
        sources.extend(v for v in up.values() if isinstance(v, dict))
        sources.append(up)
    for src in sources:
        if not isinstance(src, dict):
            continue
        for key in ("human_message", "human_decision", "decision", "message"):
            val = src.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip().lower()
    return ""


def _is_approved(input_data: dict) -> bool:
    """Fail closed: only an explicit approve token counts; unknown => not approved."""
    sig = _signal(input_data)
    if sig in _BLOCK_TOKENS:
        return False
    return sig in _APPROVE_TOKENS


def _is_blocked(input_data: dict) -> bool:
    return _signal(input_data) in _BLOCK_TOKENS


def _recover_offer(input_data: dict, context: dict) -> dict:
    """Recover the offer across the HITL boundary: upstream -> stash -> dev store."""
    up = input_data.get("upstream_yields") or {}
    candidates = [input_data]
    if isinstance(up, dict):
        candidates.append(up)
        candidates.extend(v for v in up.values() if isinstance(v, dict))
    for src in candidates:
        if isinstance(src, dict) and src.get("offer_amount_cents"):
            return {
                "req_id": str(src.get("req_id") or input_data.get("req_id") or ""),
                "candidate_id": str(src.get("candidate_id")
                                    or input_data.get("candidate_id") or ""),
                "offer_amount_cents": int(src.get("offer_amount_cents") or 0),
                "offer_body": str(src.get("offer_body") or ""),
            }
    sid = resolve_session_id(input_data, context)
    stashed = stash_get(sid)
    if stashed.get("offer_amount_cents"):
        return stashed
    req_id = str(input_data.get("req_id") or "")
    stored = store.get_offer(req_id)
    if stored:
        return stored
    return {"req_id": req_id,
            "candidate_id": str(input_data.get("candidate_id") or ""),
            "offer_amount_cents": 0, "offer_body": ""}


def _within_band(offer: dict) -> bool:
    """Re-derive within_band from the band of RECORD — a human can't waive it,
    and a 0/0 unconfirmed band fails closed."""
    low, high = store.salary_band(str(offer.get("req_id") or ""))
    amount = int(offer.get("offer_amount_cents") or 0)
    if not (low and high) or amount <= 0:
        return False
    return low <= amount <= high


def _render_offer_letter(offer: dict) -> str:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    req_id = str(offer.get("req_id") or "req")
    cid = str(offer.get("candidate_id") or "candidate")
    path = _OUT_DIR / f"{req_id}_{cid}_offer_letter.md"
    amount = int(offer.get("offer_amount_cents") or 0)
    lines = [
        f"# Offer letter — {cid} ({req_id})",
        f"Base offer: {amount / 100:,.2f} (currency per HRIS)",
        "",
        offer.get("offer_body") or "_Offer body assembled from the approved terms._",
        "",
        "_Approved by the hiring manager, within the confirmed salary band, and "
        "recorded in the offer ledger._",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def _delete_partial(result: dict) -> None:
    p = result.get("offer_letter_path")
    if p:
        Path(p).unlink(missing_ok=True)
        result["offer_letter_path"] = ""


def enforce_issuance_floor(result: Any, context: dict) -> dict:
    """The finisher floor — issue ONLY on a real approval + a within-band offer."""
    result = result if isinstance(result, dict) else {}
    result.setdefault("block_reasons", [])

    if not result.get("approved"):
        result["status"] = "blocked"
        if _is_blocked(result.get("_input", {})):
            result["block_reasons"].append("hiring manager rejected / held")
        else:
            result["block_reasons"].append("no explicit approval on record (fail closed)")
        _delete_partial(result)
        logger.info(f"[ora] issuance floor BLOCKED: {result['block_reasons']}")
        return result

    offer = result.get("_offer") or {}
    if int(offer.get("offer_amount_cents") or 0) <= 0:
        result.update(status="blocked", issued=False)
        result["block_reasons"].append("no recoverable offer amount to issue")
        _delete_partial(result)
        logger.info("[ora] issuance floor BLOCKED: no offer amount")
        return result

    # within_band is RE-DERIVED here (two-layer defense with the drafter) — a
    # human approval can't push an out-of-band or unconfirmed-band offer out.
    if not result.get("within_band"):
        result.update(status="blocked", issued=False)
        result["block_reasons"].append("offer outside the confirmed salary band (fail closed)")
        _delete_partial(result)
        logger.info("[ora] issuance floor BLOCKED: out-of-band")
        return result

    if store.offer_already_issued(str(offer.get("req_id") or ""),
                                  str(offer.get("candidate_id") or ""),
                                  int(offer.get("offer_amount_cents") or 0)):
        result.update(status="blocked", issued=False)
        result["block_reasons"].append("this offer was already issued (same req, candidate and amount)")
        _delete_partial(result)
        logger.info("[ora] issuance floor BLOCKED: duplicate issue")
        return result

    # Passed the floor — render, ledger, record delivery. The letter file is
    # real; the delivery is a DEV outbox record, not an HRIS ack. Ora sends
    # nothing itself: to post the finished offer to your HRIS, set `notify` on
    # offer_issuer_agent in config.yaml (the mesh posts the output).
    result["offer_letter_path"] = _render_offer_letter(offer)
    delivery = "dev_store"
    store.record_outbox({"req_id": offer.get("req_id"),
                         "candidate_id": offer.get("candidate_id"),
                         "action": "issue_offer", "delivery": delivery,
                         "offer_letter_path": result["offer_letter_path"]})
    store.append_ledger({"req_id": offer.get("req_id"),
                         "candidate_id": offer.get("candidate_id"),
                         "event": "offer_issued",
                         "offer_amount_cents": offer.get("offer_amount_cents"),
                         "delivery": delivery})
    result.update(issued=True, status="issued")
    logger.info(f"[ora] issued offer {offer.get('req_id')}/{offer.get('candidate_id')} "
                f"via {delivery} -> {result['offer_letter_path']}")
    return result


@chain(enforce_issuance_floor)
async def offer_issuer_agent(llm_response: Any, input_data: Any, context: Any) -> dict:
    input_data = input_data if isinstance(input_data, dict) else {}
    context = context if isinstance(context, dict) else {}
    offer = _recover_offer(input_data, context)
    sid = resolve_session_id(input_data, context)
    if offer.get("offer_amount_cents"):
        stash_put(sid, offer)   # keep it recoverable across a re-entry

    out: dict[str, Any] = {
        "approved": False, "issued": False, "within_band": False,
        "offer_letter_path": "", "status": "", "block_reasons": [],
        "_input": input_data, "_offer": offer,
    }
    out["within_band"] = _within_band(offer)
    if _is_approved(input_data):
        out["approved"] = True     # the floor issues it (if within band)
    else:
        out["status"] = "blocked"  # the floor records the block reason
    return out
