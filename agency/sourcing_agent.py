"""sourcing_agent — the Sourcer (programmatic).

auto_discover matches `sourcing_agent`. The sourcer pulls the req's open
pipeline and loads the screening backlog that Sena's parallel copies claim
from (claim_candidate_batch).

Day 0 (no `integration` in config.yaml): the SDK calls this with
`connector_response=None`, and it reads the req's screen-stage pipeline from
the dev store (agency/_shared/store.py). The reply says `source: dev_store`.

Wired (config: `integration: "n8n"` + `connector_config: {connection:
sourcing_n8n}`): the SDK calls the n8n workflow first and passes its reply
here. A successful reply is shaped into the yields. A failed call returns 0
candidates with the error in `sourcing_note`, so the recruiter sees it — it
never falls back to seed data, which would look like a real search.

Why the n8n wiring is commented out on day 0: an integration whose vault
record is missing or has no workflow address is switched off at start
(leafmesh 2.4.490+), so this code would not be reached until it is wired.
"""
from __future__ import annotations

import json
from typing import Any

from leafmesh import LeafMeshLogger

from agency._shared import store

logger = LeafMeshLogger(__name__)


def _pick(data: Any, key: str) -> Any:
    """Read a field from the input, tolerating payload / upstream nesting."""
    if not isinstance(data, dict):
        return None
    if data.get(key) not in (None, ""):
        return data[key]
    for blob_key in ("payload", "upstream_yields"):
        blob = data.get(blob_key)
        if isinstance(blob, dict):
            if blob.get(key) not in (None, ""):
                return blob[key]
            for v in blob.values():
                if isinstance(v, dict) and v.get(key) not in (None, ""):
                    return v[key]
    return None


def _content(connector_response: dict) -> dict:
    c = connector_response.get("content")
    if isinstance(c, str):
        try:
            c = json.loads(c)
        except ValueError:
            c = {}
    return c if isinstance(c, dict) else {}


def source(req_id: str, connector_response: Any = None) -> dict[str, Any]:
    """The sourcing result for one req (pure: testable without a mesh)."""
    if isinstance(connector_response, dict) and connector_response.get("success") is True:
        c = _content(connector_response)
        ids = [str(i) for i in (c.get("candidate_ids") or []) if str(i).strip()]
        found = int(c.get("candidates_found") or len(ids))
        src, note = "sourcing_n8n", f"{found} candidate(s) from the ATS sourcing workflow."
    elif isinstance(connector_response, dict) and connector_response.get("success") is False:
        err = str(connector_response.get("error") or "the sourcing workflow failed")
        logger.warning(f"[sourcing] workflow failed for {req_id}: {err}")
        return {"candidates_found": 0, "candidate_ids": [], "req_id": req_id,
                "source": "sourcing_n8n_failed",
                "sourcing_note": f"ATS sourcing call failed: {err[:200]}"}
    else:
        rows = store.pipeline(req_id, stage="screen") if req_id else []
        ids = [r["candidate_id"] for r in rows]
        found = len(ids)
        src = "dev_store"
        note = (f"{found} unscreened candidate(s) for {req_id} from the dev store "
                f"(no ATS wired)." if req_id else "No req_id given.")
    if req_id:
        store.load_claim_queue(req_id, ids)   # a fresh backlog for the screener copies
    return {"candidates_found": found, "candidate_ids": ids, "req_id": req_id,
            "source": src, "sourcing_note": note}


async def sourcing_agent(connector_response: Any, input_data: Any, context: Any) -> dict:
    req_id = str(_pick(input_data, "req_id") or "").strip()
    out = source(req_id, connector_response)
    logger.info(f"[sourcing] req={req_id or '?'} found={out['candidates_found']} via {out['source']}")
    return out
