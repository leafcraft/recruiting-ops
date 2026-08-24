"""Global tools for the recruiting-ops pod.

These are Sena's day-0 tool surface — the tools she calls, in the turn, to CLAIM
and READ the candidate pipeline. Each reads the dev store (seed pipeline) so the
pod runs with no ATS connector wired, and **each announces itself**: when there
is no real source and no seed, it returns `available: false` and says why —
never a synthetic success that looks like a real read. To go live, wire the ATS
`mcp` block in config.yaml (each named action becomes its own tool); these dev
tools are the fallback contract.

`claim_candidate_batch` is the ATOMIC CLAIM that makes Sena's parallel
`instances` fan out cleanly: each copy claims a DISJOINT batch, so N copies
split the backlog instead of each screening the whole pipeline.
"""
import os

from leafmesh import global_tool, LeafMeshLogger

try:
    from ._shared import store
except ImportError:  # pragma: no cover — direct-run fallback
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _shared import store  # type: ignore

logger = LeafMeshLogger(__name__)


def _connector_wired() -> bool:
    """True if a real ATS connector is configured (sourcing webhook set)."""
    return bool(os.getenv("N8N_SOURCING_WEBHOOK_URL") or os.getenv("ATS_MCP_URL"))


@global_tool(category="screening")
def claim_candidate_batch(req_id: str, count: int = 4) -> dict:
    """Atomically claim a disjoint batch of unscreened candidates for a req.

    Parallel copies of the screener each call this so no two copies score the
    same candidate. Returns `available: false` when the backlog is drained —
    never a synthetic empty success.

    Args:
        req_id: The requisition to claim candidates for (e.g. "req-payments-001").
        count: Max candidates to claim in this batch (default 4).
    """
    result = store.claim_candidate_batch(str(req_id).strip(), int(count or 4))
    if not result.get("available") and _connector_wired():
        return {"available": False,
                "reason": "connector wired but returned no unclaimed candidates for this req"}
    logger.info(f"claim_candidate_batch req={req_id} available={result.get('available')} "
                f"claimed={len(result.get('candidates') or [])}")
    return result


@global_tool(category="screening")
def get_req_spec(req_id: str) -> dict:
    """Read a requisition's spec (title, level, required dimensions, salary band)
    so the screen scores against the real bar, not an invented one.

    Args:
        req_id: The requisition to read.
    """
    req = store.get_req(str(req_id).strip())
    if not req:
        return {"available": False,
                "reason": f"no seed req for {req_id!r}; wire the ATS mcp block"}
    return {"available": True, "req": req}


@global_tool(category="screening")
def get_candidate(candidate_id: str) -> dict:
    """Read one candidate record (resume summary, skills, prior screen score).

    Args:
        candidate_id: The candidate to read (e.g. "cand-101").
    """
    cand = store.get_candidate(str(candidate_id).strip())
    if not cand:
        return {"available": False,
                "reason": f"no candidate {candidate_id!r} in the pipeline store"}
    return {"available": True, "candidate": cand}
