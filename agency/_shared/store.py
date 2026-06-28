"""Dev-mode store for recruiting-ops.

Stands in for the customer's ATS (Greenhouse / Lever / Ashby) — reqs,
the candidate pipeline (resume data, prior screens, scorecards) and the
interviewer roster — so the
  intake → screen → correspond → interview → schedule
chain runs end-to-end BEFORE any connector is wired. Replace each read
with the matching `n8n`/ATS call in prod; the function SIGNATURES are the
contract. The integration points:

  * candidate search / pipeline  → wire ${N8N_SOURCING_WEBHOOK_URL}
  * funnel / stage ledger        → wire ${N8N_ATS_FUNNEL_WEBHOOK_URL}
  * salary bands + scorecards    → read from the ATS req record

Setting those env vars alone does nothing until you wire the calls here.
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
# Salary bands are in CENTS. A 0/0 band = HRBP-unconfirmed (band gate
# fails closed). req-payments has a confirmed band so the offer-mode
# band gate has something real to enforce against.
_SEED_REQS = [
    {"req_id": "req-payments-001", "title": "Senior Backend Engineer — Payments",
     "level": "senior", "location": "Remote (US)",
     "salary_band_low_cents": 17000000, "salary_band_high_cents": 21000000,
     "received_at_utc": "2026-06-01T09:00:00+00:00",
     "required_dimensions": ["systems_design", "coding", "payments_domain", "collaboration"]},
    {"req_id": "req-frontend-002", "title": "Staff Frontend Engineer — Growth",
     "level": "staff", "location": "New York, NY",
     "salary_band_low_cents": 20000000, "salary_band_high_cents": 25000000,
     "received_at_utc": "2026-06-05T09:00:00+00:00",
     "required_dimensions": ["frontend_architecture", "coding", "product_sense", "collaboration"]},
    {"req_id": "req-ml-003", "title": "Machine Learning Engineer",
     "level": "mid", "location": "Remote (Global)",
     # Band unconfirmed — HRBP must fill it; offer-mode gate fails closed.
     "salary_band_low_cents": 0, "salary_band_high_cents": 0,
     "received_at_utc": "2026-06-10T09:00:00+00:00",
     "required_dimensions": ["ml_modelling", "coding", "experimentation", "collaboration"]},
]

# ── Seed candidate pipeline (resume data + prior screens + scorecards).
# `name_signal` / `school_prestige` are the bias-prone fields the screener
# must learn NOT to lean on — the @chain bias floor watches for them.
_SEED_CANDIDATES = [
    {"candidate_id": "cand-101", "req_id": "req-payments-001",
     "name": "Talia Wong", "stage": "screen",
     "years_experience": 8, "school_prestige": "state_school",
     "skills": ["go", "kafka", "stripe", "distributed_systems"],
     "resume_summary": "8y backend; built ledger + reconciliation at a fintech; "
                       "led Stripe migration handling $400M/yr.",
     "prior_screen_score": 0.0, "current_offer_ask_cents": 0,
     "demographics": {"gender": "female", "ethnicity": "asian"}},
    {"candidate_id": "cand-102", "req_id": "req-payments-001",
     "name": "Marcus Bell", "stage": "screen",
     "years_experience": 6, "school_prestige": "ivy_league",
     "skills": ["java", "spring", "postgres"],
     "resume_summary": "6y backend; payments adjacent; strong on relational data, "
                       "less on event streaming.",
     "prior_screen_score": 0.0, "current_offer_ask_cents": 0,
     "demographics": {"gender": "male", "ethnicity": "black"}},
    {"candidate_id": "cand-103", "req_id": "req-payments-001",
     "name": "Priya Nair", "stage": "onsite",
     "years_experience": 10, "school_prestige": "state_school",
     "skills": ["go", "rust", "kafka", "stripe", "ledgers"],
     "resume_summary": "10y; payments platform lead; designed idempotent "
                       "double-entry ledger at scale.",
     "prior_screen_score": 0.86, "current_offer_ask_cents": 23500000,
     "demographics": {"gender": "female", "ethnicity": "south_asian"}},
    {"candidate_id": "cand-201", "req_id": "req-frontend-002",
     "name": "Dana Kim", "stage": "screen",
     "years_experience": 9, "school_prestige": "bootcamp",
     "skills": ["react", "typescript", "design_systems", "a11y"],
     "resume_summary": "9y frontend; built a 200-component design system; "
                       "growth/experimentation focus.",
     "prior_screen_score": 0.0, "current_offer_ask_cents": 0,
     "demographics": {"gender": "female", "ethnicity": "asian"}},
]

# ── Seed interviewer roster (the interview coordinator's panel pool).
# Diversity-aware loop design needs ≥2 distinct levels available.
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
