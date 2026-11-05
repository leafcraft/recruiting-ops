"""Dev-mode store for recruiting-ops.

Stands in for the customer's ATS (Greenhouse / Lever / Ashby) — reqs,
the candidate pipeline (resume data, prior screens, scorecards) and the
interviewer roster — so the
  intake → screen → correspond → interview → schedule
chain runs end-to-end BEFORE any connector is wired. Replace each read
with the matching `n8n`/ATS call in prod; the function SIGNATURES are the
contract. The integration points:

  * candidate search / pipeline  → sourcing_agent's n8n workflow (vault connection
                                   sourcing_n8n) — see agency/sourcing_agent.py
  * screener reads               → the ATS mcp block on resume_screener_agent
                                   (vault connection ats_mcp)
  * funnel / stage ledger        → recruiting_ops_agent's n8n workflow (ats_funnel_n8n)
  * salary bands + scorecards    → read from the ATS req record

The other reads here (bands, roster, offers) stay on this store until you
replace them with your ATS / HRIS calls.
A salary band of 0/0 means "HRBP has not confirmed it" — agents must
never invent one (the band gate fails closed when the band is unknown).
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_DIR = Path("./data")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(k: str) -> Path:
    _DIR.mkdir(parents=True, exist_ok=True)
    return _DIR / f"{k}.json"


def _load(k: str) -> dict[str, Any]:
    p = _path(k)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (ValueError, OSError):
        return {}


def _save(k: str, d: dict[str, Any]) -> None:
    p = _path(k)
    t = p.with_suffix(".json.tmp")
    t.write_text(json.dumps(d, indent=2, default=str))
    t.replace(p)


# ── Seed reqs (the ATS req records) ──────────────────────────────────
# Salary bands are annual base in USD CENTS. A 0/0 band = HRBP-unconfirmed
# (the band gate fails closed). Larkspur Pay (fictional) is a ~400-person
# fintech; bands follow its 2026 engineering ladder.
#   req-payments-001  confirmed band, deep pipeline   -> the happy path
#   req-frontend-002  confirmed band, onsite + ghosted candidates
#   req-ml-003        band NOT confirmed              -> offers fail closed to HRBP
_SEED_REQS = [
    {"req_id": "req-payments-001", "title": "Senior Backend Engineer — Payments",
     "level": "senior", "location": "Remote (US)", "department": "Payments Platform",
     "hiring_manager": "Renee Castillo (Engineering Manager, Payments)",
     "salary_band_low_cents": 17000000, "salary_band_high_cents": 21000000,
     "received_at_utc": "2026-06-01T09:00:00+00:00",
     "required_dimensions": ["systems_design", "coding", "payments_domain", "collaboration"]},
    {"req_id": "req-frontend-002", "title": "Staff Frontend Engineer — Growth",
     "level": "staff", "location": "New York, NY", "department": "Growth",
     "hiring_manager": "Victor Huang (Director of Engineering, Growth)",
     "salary_band_low_cents": 20000000, "salary_band_high_cents": 25000000,
     "received_at_utc": "2026-06-05T09:00:00+00:00",
     "required_dimensions": ["frontend_architecture", "coding", "product_sense", "collaboration"]},
    {"req_id": "req-ml-003", "title": "Machine Learning Engineer",
     "level": "mid", "location": "Remote (Global)", "department": "Risk & Fraud",
     "hiring_manager": "Imogen Clarke (ML Lead, Risk)",
     # Band unconfirmed — HRBP must fill it; offer-mode gate fails closed.
     "salary_band_low_cents": 0, "salary_band_high_cents": 0,
     "received_at_utc": "2026-06-10T09:00:00+00:00",
     "required_dimensions": ["ml_modelling", "coding", "experimentation", "collaboration"]},
]

# ── Seed candidate pipeline (resume data + prior screens + scorecards).
# Fictional people. `school_prestige` is a bias-prone field the screener must
# NOT lean on (the @chain bias floor watches its reasoning). `demographics` is
# EEO self-identification: kept for the 4/5ths audit only and stripped from
# everything the screener reads (agency/tools.py).
# Cases: cand-107 has no skills/resume data (screener must leave it off the
# shortlist, not guess); cand-103's ask is over band (offer -> HRBP);
# cand-204 went silent after the onsite (ghosted close-out).
_SEED_CANDIDATES = [
    {"candidate_id": "cand-101", "req_id": "req-payments-001",
     "name": "Talia Wong", "stage": "screen", "source": "referral",
     "years_experience": 8, "school_prestige": "state_school",
     "skills": ["go", "kafka", "stripe", "distributed_systems"],
     "resume_summary": "8y backend; built ledger + reconciliation at a fintech; "
                       "led a Stripe migration handling $400M/yr.",
     "prior_screen_score": 0.0, "current_offer_ask_cents": 0,
     "demographics": {"gender": "female", "ethnicity": "asian"}},
    {"candidate_id": "cand-102", "req_id": "req-payments-001",
     "name": "Marcus Bell", "stage": "screen", "source": "inbound",
     "years_experience": 6, "school_prestige": "ivy_league",
     "skills": ["java", "spring", "postgres"],
     "resume_summary": "6y backend; payments adjacent; strong on relational data, "
                       "less on event streaming.",
     "prior_screen_score": 0.0, "current_offer_ask_cents": 0,
     "demographics": {"gender": "male", "ethnicity": "black"}},
    {"candidate_id": "cand-103", "req_id": "req-payments-001",
     "name": "Priya Nair", "stage": "onsite", "source": "linkedin_recruiter",
     "years_experience": 10, "school_prestige": "state_school",
     "skills": ["go", "rust", "kafka", "stripe", "ledgers"],
     "resume_summary": "10y; payments platform lead; designed an idempotent "
                       "double-entry ledger at scale.",
     "prior_screen_score": 0.86, "current_offer_ask_cents": 23500000,
     "demographics": {"gender": "female", "ethnicity": "south_asian"}},
    {"candidate_id": "cand-104", "req_id": "req-payments-001",
     "name": "Owen Fletcher", "stage": "screen", "source": "linkedin_recruiter",
     "years_experience": 7, "school_prestige": "state_school",
     "skills": ["go", "postgres", "kafka", "idempotency"],
     "resume_summary": "7y backend; owns payout scheduling at a marketplace; "
                       "cut duplicate payouts to zero with idempotency keys.",
     "prior_screen_score": 0.0, "current_offer_ask_cents": 0,
     "demographics": {"gender": "male", "ethnicity": "white"}},
    {"candidate_id": "cand-105", "req_id": "req-payments-001",
     "name": "Sofia Marquez", "stage": "screen", "source": "inbound",
     "years_experience": 5, "school_prestige": "community_college",
     "skills": ["python", "stripe", "fraud_rules", "postgres"],
     "resume_summary": "5y; payments risk engineer; built chargeback and "
                       "dispute automation on Stripe.",
     "prior_screen_score": 0.0, "current_offer_ask_cents": 0,
     "demographics": {"gender": "female", "ethnicity": "hispanic"}},
    {"candidate_id": "cand-106", "req_id": "req-payments-001",
     "name": "Kwame Mensah", "stage": "screen", "source": "referral",
     "years_experience": 9, "school_prestige": "international",
     "skills": ["java", "kafka", "ledgers", "pci_dss"],
     "resume_summary": "9y; card-issuing processor; led PCI DSS scope reduction "
                       "and the move to an event-sourced ledger.",
     "prior_screen_score": 0.0, "current_offer_ask_cents": 0,
     "demographics": {"gender": "male", "ethnicity": "black"}},
    {"candidate_id": "cand-107", "req_id": "req-payments-001",
     "name": "Elena Petrova", "stage": "screen", "source": "job_board",
     "years_experience": 0, "school_prestige": "",
     "skills": [],
     "resume_summary": "",   # parse failed — no skills data; never guessed
     "prior_screen_score": 0.0, "current_offer_ask_cents": 0,
     "demographics": {}},
    {"candidate_id": "cand-201", "req_id": "req-frontend-002",
     "name": "Dana Kim", "stage": "screen", "source": "linkedin_recruiter",
     "years_experience": 9, "school_prestige": "bootcamp",
     "skills": ["react", "typescript", "design_systems", "a11y"],
     "resume_summary": "9y frontend; built a 200-component design system; "
                       "growth/experimentation focus.",
     "prior_screen_score": 0.0, "current_offer_ask_cents": 0,
     "demographics": {"gender": "female", "ethnicity": "asian"}},
    {"candidate_id": "cand-202", "req_id": "req-frontend-002",
     "name": "Noah Brennan", "stage": "screen", "source": "inbound",
     "years_experience": 11, "school_prestige": "state_school",
     "skills": ["react", "next_js", "web_performance", "graphql"],
     "resume_summary": "11y frontend; led a checkout rebuild that cut p75 LCP "
                       "from 4.1s to 1.9s.",
     "prior_screen_score": 0.0, "current_offer_ask_cents": 0,
     "demographics": {"gender": "male", "ethnicity": "white"}},
    {"candidate_id": "cand-203", "req_id": "req-frontend-002",
     "name": "Hana Sato", "stage": "screen", "source": "referral",
     "years_experience": 8, "school_prestige": "ivy_league",
     "skills": ["typescript", "react", "experimentation", "analytics"],
     "resume_summary": "8y; growth engineer; ran 60+ A/B tests a year on "
                       "onboarding and pricing pages.",
     "prior_screen_score": 0.0, "current_offer_ask_cents": 0,
     "demographics": {"gender": "female", "ethnicity": "asian"}},
    {"candidate_id": "cand-204", "req_id": "req-frontend-002",
     "name": "Asa Idahosa", "stage": "onsite", "source": "linkedin_recruiter",
     "years_experience": 10, "school_prestige": "international",
     "skills": ["react", "typescript", "design_systems", "mentoring"],
     "resume_summary": "10y frontend; staff engineer on a design-system team "
                       "serving 40 product squads.",
     "prior_screen_score": 0.81, "current_offer_ask_cents": 0,
     "last_contact_utc": "2026-05-21T15:00:00+00:00", "outreach_attempts": 3,
     "demographics": {"gender": "male", "ethnicity": "black"}},
    {"candidate_id": "cand-301", "req_id": "req-ml-003",
     "name": "Arjun Mehta", "stage": "screen", "source": "inbound",
     "years_experience": 4, "school_prestige": "state_school",
     "skills": ["python", "pytorch", "gradient_boosting", "feature_stores"],
     "resume_summary": "4y; built a transaction-fraud model that cut false "
                       "declines 18% at a card issuer.",
     "prior_screen_score": 0.0, "current_offer_ask_cents": 0,
     "demographics": {"gender": "male", "ethnicity": "south_asian"}},
]

# ── Seed interviewer roster (the interview coordinator's panel pool).
# Every req's dimensions are covered by at least two interviewer levels, so a
# diverse loop is possible for each.
_SEED_INTERVIEWERS = [
    {"interviewer_id": "int-1", "name": "Sam Ortega", "role": "engineer",
     "level": "senior", "dimensions": ["coding", "systems_design"]},
    {"interviewer_id": "int-2", "name": "Lin Zhao", "role": "engineer",
     "level": "staff", "dimensions": ["systems_design", "payments_domain"]},
    {"interviewer_id": "int-3", "name": "Ravi Patel", "role": "engineer",
     "level": "mid", "dimensions": ["coding", "collaboration"]},
    {"interviewer_id": "int-4", "name": "Jordan Webb", "role": "engineer",
     "level": "principal", "dimensions": ["frontend_architecture", "product_sense"]},
    {"interviewer_id": "int-5", "name": "Aisha Khan", "role": "engineer",
     "level": "senior", "dimensions": ["ml_modelling", "experimentation"]},
    {"interviewer_id": "int-6", "name": "Hollis Grant", "role": "product_manager",
     "level": "senior", "dimensions": ["product_sense", "collaboration"]},
    {"interviewer_id": "int-7", "name": "Tomás Rivera", "role": "engineer",
     "level": "mid", "dimensions": ["frontend_architecture", "coding"]},
    {"interviewer_id": "int-8", "name": "Mei Chen", "role": "engineer",
     "level": "principal", "dimensions": ["ml_modelling", "coding"]},
]


def _reqs() -> dict[str, Any]:
    s = _load("reqs")
    if not s:
        s = {r["req_id"]: r for r in _SEED_REQS}
        _save("reqs", s)
    return s


def _candidates() -> dict[str, Any]:
    s = _load("candidates")
    if not s:
        s = {c["candidate_id"]: c for c in _SEED_CANDIDATES}
        _save("candidates", s)
    return s


def _interviewers() -> list[dict[str, Any]]:
    s = _load("interviewers")
    if not s:
        s = {"roster": _SEED_INTERVIEWERS}
        _save("interviewers", s)
    return list(s.get("roster") or [])


# ── Reads (PROD: ATS req / candidate search) ─────────────────────────
def get_req(req_id: str) -> dict[str, Any]:
    """One req record. PROD: ATS get-job."""
    return _reqs().get(req_id, {})


def salary_band(req_id: str) -> tuple[int, int]:
    """(low_cents, high_cents) for a req. (0, 0) = HRBP-unconfirmed →
    the offer-mode band gate fails closed. PROD: ATS comp record."""
    r = _reqs().get(req_id, {})
    return int(r.get("salary_band_low_cents") or 0), int(r.get("salary_band_high_cents") or 0)


def find_duplicate_req(title: str, exclude_req_id: str = "") -> dict[str, Any]:
    """The first OPEN req with the same (normalised) title — a likely
    duplicate the recruiter should reconcile before sourcing twice.
    Empty dict if none. PROD: ATS open-req search by title."""
    want = (title or "").strip().lower()
    if not want:
        return {}
    for r in _reqs().values():
        if r.get("req_id") == exclude_req_id:
            continue
        if str(r.get("title") or "").strip().lower() == want:
            return r
    return {}


def required_dimensions(req_id: str) -> list[str]:
    """Interview dimensions this req must cover. PROD: ATS scorecard template."""
    return list(_reqs().get(req_id, {}).get("required_dimensions") or [])


def pipeline(req_id: str, stage: str = "") -> list[dict[str, Any]]:
    """The candidate pipeline for a req (optionally one stage).
    PROD: ATS candidate search."""
    rows = [c for c in _candidates().values() if c.get("req_id") == req_id]
    if stage:
        rows = [c for c in rows if c.get("stage") == stage]
    rows.sort(key=lambda c: -float(c.get("prior_screen_score") or 0))
    return rows


def get_candidate(candidate_id: str) -> dict[str, Any]:
    """One candidate record (resume + prior screen + scorecard).
    PROD: ATS get-candidate."""
    return _candidates().get(candidate_id, {})


# EEO self-identification is for the 4/5ths audit only — never shown to a
# screener, interviewer or letter writer.
_EEO_FIELDS = ("demographics",)


def get_candidate_for_review(candidate_id: str) -> dict[str, Any]:
    """One candidate record WITHOUT the EEO self-identification fields — what
    every agent that judges or writes to a candidate reads."""
    c = get_candidate(candidate_id)
    return {k: v for k, v in c.items() if k not in _EEO_FIELDS}


def interviewer_roster(dimensions: list[str] | None = None) -> list[dict[str, Any]]:
    """The interviewer pool, optionally narrowed to those who cover any of
    the given dimensions. PROD: ATS / calendar interviewer directory."""
    roster = _interviewers()
    if dimensions:
        wanted = set(dimensions)
        roster = [i for i in roster
                  if wanted & set(i.get("dimensions") or [])]
    return roster


# ── Writes (PROD: ATS stage/scorecard write) ─────────────────────────
def record_screen(candidate_id: str, score: float, recommendation: str) -> None:
    """Persist a screen result onto the candidate. PROD: ATS scorecard."""
    with _LOCK:
        s = _candidates()
        c = s.get(candidate_id)
        if c:
            c["prior_screen_score"] = round(float(score), 3)
            c["last_recommendation"] = recommendation
            c["screen_recorded_at"] = _now()
            _save("candidates", s)


def set_stage(candidate_id: str, stage: str) -> None:
    """Move a candidate to a new pipeline stage. PROD: ATS stage transition."""
    with _LOCK:
        s = _candidates()
        c = s.get(candidate_id)
        if c:
            c["stage"] = stage
            c["stage_updated_at"] = _now()
            _save("candidates", s)


# ── Atomic claim queue — backlog fan-out for Sena's parallel copies.
# Each copy calls claim_candidate_batch(req_id, count); the LPOP-style atomic
# pop under a lock guarantees copies pull DISJOINT candidates (no duplicate
# work). PROD: `UPDATE ... SKIP LOCKED RETURNING` on the ATS candidate table,
# or Redis LPOP. The in-memory queue below is the dev stand-in.
# ─────────────────────────────────────────────────────────────────────────
_CLAIM_QUEUES: dict[str, list[str]] = {}


def load_claim_queue(req_id: str, candidate_ids: list[str]) -> int:
    """Replace a req's screening backlog with a fresh sourcing pull.
    The sourcer calls this, so every sourcing run hands the screener copies a
    full, disjoint-claimable backlog (not one drained by an earlier run)."""
    req_id = str(req_id or "").strip()
    if not req_id:
        return 0
    with _LOCK:
        _CLAIM_QUEUES[req_id] = [str(c) for c in candidate_ids if str(c).strip()]
        return len(_CLAIM_QUEUES[req_id])


def _ensure_queue(req_id: str) -> list[str]:
    """Lazily seed the claim queue for a req from its screen-stage pipeline."""
    if req_id not in _CLAIM_QUEUES:
        _CLAIM_QUEUES[req_id] = [c["candidate_id"]
                                 for c in pipeline(req_id, stage="screen")]
    return _CLAIM_QUEUES[req_id]


def claim_candidate_batch(req_id: str, count: int = 4) -> dict[str, Any]:
    """Atomically claim up to `count` unscreened candidates for a req.

    Returns {available: bool, req_id, candidates: [...], remaining: int}. When
    the queue is drained it announces available:false — never a synthetic empty
    success. PROD: atomic pop from the ATS / Redis backlog.
    """
    req_id = str(req_id or "").strip()
    if not req_id:
        return {"available": False, "reason": "no req_id to claim against"}
    try:
        n = max(1, int(count))
    except (TypeError, ValueError):
        n = 4
    with _LOCK:
        q = _ensure_queue(req_id)
        if not q:
            return {"available": False, "req_id": req_id, "candidates": [],
                    "remaining": 0,
                    "reason": f"no unclaimed candidates for req {req_id!r} — the "
                              f"backlog is drained, or sourcing has not run for it yet"}
        claimed_ids = [q.pop(0) for _ in range(min(n, len(q)))]
        cands = _candidates()
        return {"available": True, "req_id": req_id,
                "candidates": [cands.get(cid, {"candidate_id": cid})
                               for cid in claimed_ids],
                "remaining": len(q)}


# ── Offers (dev mirror of the HRIS offer record) + append-only ledger +
#    outbox — the finisher (Ora) writes here day-0 with no connector wired. ──
def put_offer(req_id: str, offer: dict[str, Any]) -> None:
    """Persist a drafted offer so the finisher can recover it across the HITL
    approval step (the upstream payload is dropped after the human gate).
    PROD: the HRIS / ATS offer record."""
    key = str(req_id or "").strip()
    if not key:
        return
    with _LOCK:
        offers = _load("offers")
        offers[key] = {"stored_at": _now(), **offer}
        _save("offers", offers)


def get_offer(req_id: str) -> dict[str, Any]:
    """Recover a drafted offer by req_id. PROD: HRIS / ATS offer record."""
    return _load("offers").get(str(req_id or "").strip(), {})


def record_proposed_panel(req_id: str, panels: list[dict[str, Any]]) -> dict[str, Any]:
    """Day-0 stand-in for the calendar: the proposed panel, NOT a booking.
    The recruiter books it by hand. PROD: the calendar / ATS scheduling API."""
    with _LOCK:
        rows = _load_list("proposed_panels")
        rec = {"recorded_at": _now(), "req_id": req_id, "status": "proposed_not_booked",
               "panels": panels}
        rows.append(rec)
        _save_list("proposed_panels", rows)
    return rec


def record_outbox(entry: dict[str, Any]) -> dict[str, Any]:
    """The finisher's send record (dev stand-in for the real delivery). This is
    a DEV record, not a real ack — the finisher marks delivery accordingly."""
    with _LOCK:
        outbox = _load_list("outbox")
        rec = {"recorded_at": _now(), **entry}
        outbox.append(rec)
        _save_list("outbox", outbox)
    return rec


def append_ledger(entry: dict[str, Any]) -> dict[str, Any]:
    """Append-only offer ledger (dev mirror of the WORM sink for local demo)."""
    with _LOCK:
        ledger = _load_list("offer_ledger")
        rec = {"recorded_at": _now(), **entry}
        ledger.append(rec)
        _save_list("offer_ledger", ledger)
    return rec


def offer_already_issued(req_id: str, candidate_id: str, amount_cents: int) -> bool:
    """True when the ledger already holds an issued offer with these terms."""
    for e in _load_list("offer_ledger"):
        if (e.get("event") == "offer_issued" and str(e.get("req_id")) == str(req_id)
                and str(e.get("candidate_id")) == str(candidate_id)
                and int(e.get("offer_amount_cents") or 0) == int(amount_cents)):
            return True
    return False


def _load_list(k: str) -> list[dict[str, Any]]:
    p = _path(k)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
        return data if isinstance(data, list) else []
    except (ValueError, OSError):
        return []


def _save_list(k: str, d: list[dict[str, Any]]) -> None:
    p = _path(k)
    t = p.with_suffix(".json.tmp")
    t.write_text(json.dumps(d, indent=2, default=str))
    t.replace(p)
