"""panel_booker_agent — the Interview Scheduling Coordinator (programmatic).

auto_discover matches `panel_booker_agent`.

Day 0 (no `integration` in config.yaml) there is no calendar, so nothing is
booked: the proposed panel is recorded in the dev store and the reply says
`interviews_booked: 0`, which routes to the recruiter to book it by hand. It
never reports a booking that did not happen.

Wired (config: `integration: "n8n"` + `connector_config: {connection:
panel_booking_n8n}`): the SDK calls the n8n workflow first and passes its reply
here; a successful reply is shaped into the yields, a failed one is 0 booked
with the error in `booking_note`.
"""
from __future__ import annotations

import json
from typing import Any

from leafmesh import LeafMeshLogger

from agency._shared import store

logger = LeafMeshLogger(__name__)


def _pick(data: Any, key: str) -> Any:
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


def book(req_id: str, panels: list, connector_response: Any = None) -> dict[str, Any]:
    """The booking result (pure: testable without a mesh)."""
    panels = [p for p in (panels or []) if isinstance(p, dict)]
    if isinstance(connector_response, dict) and connector_response.get("success") is True:
        c = connector_response.get("content")
        if isinstance(c, str):
            try:
                c = json.loads(c)
            except ValueError:
                c = {}
        c = c if isinstance(c, dict) else {}
        booked = int(c.get("interviews_booked") or 0)
        return {"interviews_booked": booked, "panel": list(c.get("panel") or panels),
                "booking_note": f"{booked} interview(s) booked by the calendar workflow."}
    if isinstance(connector_response, dict) and connector_response.get("success") is False:
        err = str(connector_response.get("error") or "the booking workflow failed")
        return {"interviews_booked": 0, "panel": panels,
                "booking_note": f"Calendar booking failed: {err[:200]} — book this panel by hand."}
    store.record_proposed_panel(req_id, panels)
    return {"interviews_booked": 0, "panel": panels,
            "booking_note": (f"No calendar is connected, so nothing was booked. "
                             f"{len(panels)} slot(s) proposed for {req_id or 'this req'} "
                             f"— book them by hand.")}


async def panel_booker_agent(connector_response: Any, input_data: Any, context: Any) -> dict:
    req_id = str(_pick(input_data, "req_id") or "").strip()
    panels = _pick(input_data, "panels") or []
    out = book(req_id, panels if isinstance(panels, list) else [], connector_response)
    logger.info(f"[booker] req={req_id or '?'} booked={out['interviews_booked']}")
    return out
