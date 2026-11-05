# Recruiting Operations — Product Requirements / Build Doc

> A full recruiting department as a mesh of self-reliant agents. A
> **requisition intake specialist** normalises a freshly filed req; a
> **sourcer** pulls the candidate pipeline from the company's ATS /
> LinkedIn Recruiter; a **resume screener** scores the shortlist against
> the spec and flags bias; a **candidate-correspondence writer** drafts
> every message a candidate sees — outreach, offers, rejections; an
> **interview coordinator** designs the loop and a **scheduling
> coordinator** books the panel into the company's calendar. A
> **recruiting-ops analyst** watches the funnel; a **screening
> interviewer** runs the first async round; an **EEOC compliance auditor**
> runs the weekly 4/5ths-rule adverse-impact check. A **talent
> coordinator** (Cass) opens each case; **Ora**, the offer issuer, is the
> finisher. Four people hold the gates — **recruiter, hiring manager,
> recruiting manager, HRBP** — and nothing advances on their silence. A
> hash-chained WORM audit closes every terminal branch.
>
> Built on LeafMesh as an **operation of self-reliant agents**. The
> config IS the department. Candidate data lives in the customer's ATS and
> interviews in the customer's calendar, reached through `n8n` connectors
> once wired; until then the sourcer, booker and Ora run on the dev store.
> The four judgment agents pull their own ATS context (`@pre_compose`) and
> enforce their own compliance floors (`@chain`) the LLM cannot waive —
> bias, the screen score floor, the salary-band gate, the rubric
> thresholds, the interview-loop fairness controls. A dev store
> (`agency/_shared/store.py`) seeds realistic reqs + candidates so the
> chain runs day-0; the compliance-grade EEOC 4/5ths math is the other
> Python.

---

## 1. The operation at a glance

```
 req filed in ATS        referral        InMail reply      cron / ATS export
 (req_filed)        (referral_received) (linkedin_…reply)  (pipeline / bias)
        │                   │                  │                  │
   ┌────▼───────────────┐   │                  │         ┌────────▼─────────┐
   │ talent_coordinator │   │                  │         │ recruiting_ops / │
   │ (Cass) open case   │   │                  │         │ bias_audit       │
   └────┬───────────────┘   │                  │         └────────┬─────────┘
   ┌────▼───────────────┐   │                  │  thin → recruiting mgr │
   │ req_intake_agent   │   │                  │  adverse impact → HRBP │
   │ (LLM) normalise    │   │                  │
   │ incomplete ─► recruiter_human             │
   └────┬───────────────┘   │                  │
        │ complete          │                  │
   ┌────▼───────────────┐    │                  │
   │ sourcing_agent     │    │                  │
   │ (dev store / n8n)  │    │                  │
   │  0 found ─► recruiter_human                │
   └────┬───────────────┘    │                  │
        │ candidates>0        │                  │
   ┌────▼────────────────────▼──┐               │
   │ resume_screener_agent (LLM)│               │
   │  bias? ─► hrbp_human        │              │
   └────┬───────────────────────┘               │
        │ no bias                                │
   ┌────▼─────────────────────────────◄─────────┘  (InMail reply / rejection /
   │ correspondence_drafter_agent (LLM)             offer / ghosted close)
   │  mode = outreach | offer | rejection
   │   outreach / flagged-reject ─► recruiter_human
   │   out-of-band / flagged offer ─► hrbp_human
   │   clean offer ─► hiring_manager_human
   │   clean rejection ─► WORM audit
   └──────────────────────────────────────────────┘

   interview path (design_interview_loop):
   ┌─────────────────────────────┐   clean   ┌────────────────────┐
   │ interview_coordinator_agent │──────────►│ panel_booker_agent │
   │ (LLM) design loop           │  flagged  │ (n8n → calendar)   │
   └──────────┬──────────────────┘──► recruiter_human  │ booked>0 ─► WORM
              │                       book_panel ──────►│ 0 ─► recruiter_human
              └──────────────────────────────────────────────────┘

   async screen path (async_screen_interview):
   ┌──────────────────────────┐ bias  ─► hrbp_human
   │ hiring_assistant_agent    │ advance/borderline ─► hiring_manager_human
   │ (LLM) rubric score        │ decline ─► correspondence_drafter (rejection)
   └───────────────────────────┘

   human seats (nothing advances on silence):
   recruiter_human ─ book_panel ─► panel_booker_agent; else ─► WORM
   hiring_manager_human ─ approved ─► offer_issuer_agent (Ora) ─► WORM; else ─► WORM
   recruiting_manager_human, hrbp_human ─► WORM
```

The chain flows **forward** — each entry point kicks work off and the
originator steps out; nothing returns to a conductor hub. There are no
human→human routes: each seat decides and its answer is recorded. The one
cycle is recruiter → booker → recruiter when no calendar is wired, and each
turn of it waits for the recruiter.

---

## 2. Actor inventory

| Agent | Class | Role (job title) | One-line |
|---|---|---|---|
| `talent_coordinator_agent` | 🤖 LLM | Talent coordinator (Cass) | Opens the case on a filed req; answers status asks from the case record |
| `req_intake_agent` | 🤖 LLM + module | Requisition intake specialist | Normalises a filed req (title/level/location/band); completeness floor in `@chain` (title + level + confirmed band) |
| `sourcing_agent` | ⚙️ programmatic (Python; n8n when wired) | Sourcer | Pulls the req's pipeline (dev store day 0, ATS / LinkedIn Recruiter when wired) and loads the screening backlog |
| `resume_screener_agent` | 🤖 LLM + tools + module | Resume screener (Sena) | Claims and reads candidates through its tools (3 copies, disjoint batches); no-data, bias + score floors in `@chain` |
| `correspondence_drafter_agent` | 🤖 LLM + module | Candidate-correspondence writer | Drafts ALL candidate-facing messages; salary-band gate in `@chain`, per-peer `@compose` |
| `interview_coordinator_agent` | 🤖 LLM + module | Interview coordinator | Designs the loop (`@pre_compose` pulls the roster); 5h cap + diversity floor in `@chain` |
| `panel_booker_agent` | ⚙️ programmatic (Python; n8n when wired) | Interview scheduling coordinator | Books the approved panel into the company's calendar / ATS scheduling; day 0 records the proposed panel and books nothing |
| `offer_issuer_agent` | ⚙️ programmatic (Python) | Offer issuer (Ora) — finisher | Re-checks the approval + band of record, renders the letter, ledgers it; same terms never issued twice |
| `hiring_assistant_agent` | 🤖 LLM + module | First-round screening interviewer | Scores the async first round (`@pre_compose` pulls the candidate); rubric thresholds + bias gate in `@chain` |
| `recruiting_ops_agent` | ⚙️ programmatic (n8n) | Recruiting-operations analyst | Reads the funnel ledger from the ATS — thin-funnel sweep + stage / time-to-hire metrics |
| `bias_audit_agent` | ⚙️ programmatic (Python) | EEOC compliance auditor | Weekly 4/5ths-rule adverse-impact audit on screening decisions |
| `recruiter_human` | 👤 human | Recruiter | Reviews outreach drafts, shortlists, flagged loops; releases flagged panels to booking |
| `hiring_manager_human` | 👤 human | Hiring manager | Final approval on a clean, in-band offer |
| `recruiting_manager_human` | 👤 human | Recruiting manager | Team-level call on a thin or stalled funnel |
| `hrbp_human` | 👤 human | HR business partner | Bias / salary-band / policy authority — the highest gate; gets the Manager's error escalations |
| `recruiting_audit_logger_agent` | 🧾 external (WORM) | Compliance records keeper | Hash-chained, append-only audit of every terminal decision |

> **Why three connector agents are `programmatic`, not LLMs.** Sourcing,
> the funnel ledger, and panel booking are reads/writes against the
> customer's systems of record (ATS, LinkedIn Recruiter, calendar) — not
> judgment over text. The sourcer and booker carry a small Python module
> that serves the dev store day 0 and shapes the `n8n` workflow's reply once
> wired; their `integration` lines ship commented because an `n8n`
> integration with no record or no address is switched off at start.
> The funnel analyst is pure connector config and is inert until wired.

> **Why `bias_audit_agent` keeps its Python module.** The EEOC 4/5ths rule
> (29 CFR 1607.4(D)) is compliance-grade domain math — per-group
> selection-rate ratios with a minimum-sample floor where a wrong number is
> legal exposure. It must be deterministic, reproducible, unit-tested code;
> an LLM estimate is not audit-defensible.

---

## 3. Data artifacts

- **Req** — `{req_id, title, level, location, salary_band_low_cents, salary_band_high_cents, received_at_utc}` (the one declared `data_structure`; a band of 0/0 means the HRBP has not confirmed it, and such a req is held at intake).
- **Shortlist** — `[{candidate_id, fit_score, top_reason}]` + `avg_fit_score`, `bias_signal`, `recruiter_briefing` (from the screener).
- **Correspondence** — one shape covering all three modes: `{correspondence_type, message_body, cited_signals, offer_body, within_band, requires_hrbp_review, candidate_facing_message, rejection_stage, reason_class, personalisation_signal, alternate_roles_suggested, requires_recruiter_review}`.
- **Interview loop** — `{req_id, role_level, panels[], total_minutes, dimensions_covered, panel_diversity_ok, requires_recruiter_review, loop_briefing}`.
- **Screen** — `{screen_id, rubric_scores[], weighted_score, recommendation, bias_flags, requires_hrbp_review, requires_hiring_manager_review, …}`.
- **Funnel** (from the ATS) — `{thin_reqs, escalate, stage_counts, drop_off_rates, median_time_to_offer_days, median_time_to_hire_days, requires_recruiter_action, funnel_briefing}`.
- **Bias finding** — `{findings[], adverse_impact_count, requires_hrbp_review, …}`.
- **Audit entry** — `{audit_event_id, written_at_utc, payload, hash_chain_prev, hash_chain_current}`.

Candidates + funnel live in the customer's **ATS** (Greenhouse / Lever /
Ashby); interviews in the customer's **calendar** (Google / Outlook); the
WORM trail in `./logs/recruiting_audit.jsonl` (dev) → S3 Object Lock /
Splunk in prod.

---

## 4. Per-agent PRD

### 4.0 `req_intake_agent` — requisition intake specialist (LLM + module)
Normalises a filed req into title / level / location / salary band (cents).
**Never invents a salary band.** `@pre_compose load_req_context` pulls any
prior/duplicate req and the band of record; `@chain
enforce_completeness_floor` forces `req_complete=false` when title, a
recognised level or a confirmed band is missing. **Wires.** →
`sourcing_agent` when `req_complete == true`; → `recruiter_human` when
false (a human fixes the intake rather than sourcing blind).

### 4.1 `sourcing_agent` — sourcer (PROGRAMMATIC · Python, n8n when wired)
`agency/sourcing_agent.py`. Day 0 it reads the req's screen-stage pipeline
from the dev store; wired, it shapes the `n8n` workflow's
`{candidates_found, candidate_ids}` reply (a failed call is reported as 0
found — never replaced by seed data). Either way it loads the screening
backlog the screener copies claim from. **Wires.** →
`resume_screener_agent` when `candidates_found > 0`; → `recruiter_human`
when `candidates_found == 0` (empty top-of-funnel — widen criteria or
approve external spend).

### 4.2 `resume_screener_agent` — resume screener (LLM + tools + module)
Scores each candidate, computes `avg_fit_score`, sets `bias_signal`,
briefs the recruiter. Three copies each claim a disjoint batch with
`claim_candidate_batch`, then read the spec and each record with
`get_req_spec` / `get_candidate` (EEO self-identification is stripped from
everything they read). **Module (`agency/resume_screener_agent.py`).**
`@chain enforce_screen_floors` drops any shortlisted candidate whose record
holds no skills and no resume summary, then holds two floors the prompt
cannot waive:
(a) **bias floor** — if any `top_reason` / briefing leans on a bias-prone
signal (name / school prestige / photo / address) it FORCES
`bias_signal=true`, overriding the model's self-report; (b) **score floor**
— it recomputes `avg_fit_score` from the shortlist and FORCES
`re_source_required=true` when the shortlist is below 3 or avg fit below
0.55, bounding the re-source loop (Rule 3). **Wires.** → `hrbp_human` when
`bias_signal == true`; → `recruiter_human` when `re_source_required ==
true` (thin pipeline, widen criteria); → `correspondence_drafter_agent`
when both are false.

### 4.3 `correspondence_drafter_agent` — candidate-correspondence writer (LLM + module)
The consolidated writer for **all** candidate-facing text. Infers the mode
(`correspondence_type`): explicit field wins; offer terms → offer; decline
/ ghosted-close → rejection; else outreach. Uses the strongest model
(`claude-sonnet-4-6`) because offers are the highest-stakes correspondence. **Module
(`agency/correspondence_drafter_agent.py`).** `@pre_compose
load_candidate_context` pulls the req's **confirmed salary band** + the
candidate record from the ATS. `@chain enforce_correspondence_floors` is
the **salary-band gate**: for an offer it RECOMPUTES `within_band` from the
band of record (never trusting the model's self-report) — out-of-band **or**
an unconfirmed (0/0) band **fails closed**, forcing `requires_hrbp_review`;
for a rejection an empty `personalisation_signal`, a too-short message
(<120 chars) or an interview-stage reject forces `requires_recruiter_review`.
`@compose` then hands each downstream a tailored payload — HRBP gets the
band math, the hiring manager gets the clean offer, the WORM log gets a
compact audit record. **Wires.**
→ `recruiter_human` (outreach, or a flagged rejection);
→ `hrbp_human` (out-of-band / flagged offer);
→ `hiring_manager_human` (clean in-band offer);
→ `recruiting_audit_logger_agent` (clean rejection — loop closed, logged).

### 4.4 `interview_coordinator_agent` — interview coordinator (LLM + module)
Designs the loop: dimension coverage, a diversity-aware panel, a mandatory
HM debrief, capped at 5 hours.  **Module
(`agency/interview_coordinator_agent.py`).** `@pre_compose load_roster`
pulls the req's required dimensions + the actual interviewer roster (with
levels) from the ATS so the loop is built from real panelists. `@chain
enforce_loop_floors` holds the fairness floors deterministically: it drops
panels from the back until the loop fits the **5-hour cap**, always appends
the **HM debrief**, RECOMPUTES `panel_diversity_ok` (≥2 distinct
interviewer levels), and FORCES `requires_recruiter_review` on a
non-diverse or sub-2-hour loop. **Wires.** → `recruiter_human` when
`requires_recruiter_review == true`; → `panel_booker_agent` when clean.

### 4.5 `panel_booker_agent` — interview scheduling coordinator (PROGRAMMATIC · n8n)
Connector-only actuator: creates the calendar events / calls the ATS
scheduling API, returns `{interviews_booked, panel}`. Sits behind the
recruiter gate for flagged loops (the recruiter releases them with
`book_panel`). **Wires.** → `recruiting_audit_logger_agent` when
`interviews_booked > 0` (a booking is a fact worth a WORM entry); →
`recruiter_human` when `interviews_booked == 0` (booking failed — book
manually).

### 4.6 `hiring_assistant_agent` — first-round screening interviewer (LLM + module)
Scores the async first round on a five-dimension weighted rubric. **Module (`agency/hiring_assistant_agent.py`).**
`@pre_compose load_candidate` pulls the candidate record + their prior
resume-screen score. `@chain enforce_rubric_floors` RECOMPUTES
`weighted_score` from the rubric × weights and DERIVES the recommendation
from the thresholds (advance ≥0.70, borderline ≥0.55, else decline) — the
model cannot inflate its own score; any `bias_flags` entry FORCES
`requires_hrbp_review`, overriding the recommendation; and a malformed
payload becomes `error_skipped` so a candidate is never auto-declined for a
bad payload. It also records the screen onto the candidate (ATS write).
**Wires.**
→ `hrbp_human` when `requires_hrbp_review` (bias flag — overrides);
→ `hiring_manager_human` when advance/borderline and no bias;
→ `correspondence_drafter_agent` when `decline` (rejection mode).

### 4.7 `recruiting_ops_agent` — recruiting-operations analyst (PROGRAMMATIC · n8n)
Three modes dispatched by a `mode` input to its `n8n` workflow:
`sweep` (thin-funnel across active reqs), `ingest` (record one stage
transition), `report` (drop-off + time-to-offer/hire metrics). **Wires.**
→ `recruiting_manager_human` when `escalate == true` (thin funnel needs
management); → `recruiter_human` when `requires_recruiter_action == true
and escalate == false` (the funnel needs working, not escalating). The
daily-sweep cron is **commented out** until the connector is wired — a
cron firing at an unconfigured webhook would just error every morning.

### 4.8 `bias_audit_agent` — EEOC compliance auditor (PROGRAMMATIC · Python)
Weekly (`0 8 * * 0`) 4/5ths-rule audit on screening decisions exported
from the ATS. Deterministic per-group selection-rate ratios with a
minimum-sample floor of 5. **Wires.** → `hrbp_human` when
`requires_hrbp_review == true` (an adverse-impact finding).

### 4.9 The human seats (nothing advances on silence)
- `recruiter_human` (2h) → `panel_booker_agent` on `book_panel`; any other
  reply → WORM.
- `hiring_manager_human` (one business day, 8h) → `offer_issuer_agent` on
  `approved`; `rejected` / `hold` / anything else → WORM.
- `recruiting_manager_human` (4h) → WORM.
- `hrbp_human` (one business day, 8h) → WORM. The HRBP cannot push an
  out-of-band offer out: Ora re-derives the band and blocks it.

If nobody answers in time, the request waits no longer: the Inbox card
closes and the ticket records that no reply came. Nothing is sent, approved
or booked, and nobody is chased automatically. Every seat keeps
`fallback_on_timeout: true` + `fallback_response: held_for_review` (which
routes to WORM) as the declared intent; on leafmesh 2.4.486 a timeout on a
`dual` seat routes nothing. `operator_ids` are left unset so gates route to
the **shared inbox** (a placeholder email would make the task invisible).

### 4.9a `offer_issuer_agent` — Ora, the offer issuer (PROGRAMMATIC · finisher)
Re-checks that the hiring manager's reply is an explicit approval (unknown
fails closed), recovers the offer across the approval step, re-derives
`within_band` from the band of record, refuses terms already issued (same
req + candidate + amount), renders the letter to `./out`, and appends to the
offer ledger and dev outbox. A blocked run deletes any partial letter.

### 4.10 `recruiting_audit_logger_agent` — compliance records keeper (EXTERNAL · WORM)
`framework: custom`; registered in `main.py` via `mesh.intelligence(...)`.
Appends hash-chained JSON lines so any insertion/deletion is detectable.
Terminal (`can_call: []`).

---

## 5. Entry points

| Entry point | Target | Trigger |
|---|---|---|
| `req_filed` | `talent_coordinator_agent` | Requisition opened in the ATS — Cass opens the case |
| `candidate_status` | `talent_coordinator_agent` | "Where is this req / candidate?" |
| `referral_received` | `resume_screener_agent` | A referral candidate jumps straight to screening |
| `linkedin_inmail_reply` | `correspondence_drafter_agent` | Candidate replied to outreach |
| `scheduled_pipeline_health` | `recruiting_ops_agent` | Top-of-funnel sweep (+ funnel metrics) |
| `manual_sourcing` | `sourcing_agent` | Recruiter-initiated sourcing pull |
| `candidate_stage_update` | `recruiting_ops_agent` | Record one stage transition (ingest mode) |
| `funnel_metrics_report` | `recruiting_ops_agent` | Read funnel metrics (report mode) |
| `design_interview_loop` | `interview_coordinator_agent` | Design a loop for a req |
| `candidate_rejection` | `correspondence_drafter_agent` | Draft a personalised rejection |
| `post_onsite_reject` | `correspondence_drafter_agent` | Longer onsite-stage feedback letter |
| `ghosted_candidate_close` | `correspondence_drafter_agent` | Polite close-out after 14+ days silent |
| `async_screen_interview` | `hiring_assistant_agent` | First-round async screen |
| `weekly_bias_audit` | `bias_audit_agent` | Sunday cron — EEOC audit |
| `recruiter_reply` / `hiring_manager_reply` | the seat | A person answers a waiting card |
| `direct_call_interview_coordinator` / `direct_call_correspondence_drafter` | each | Debug / ad-hoc invocation (bypass the upstream chain) |

---

## 6. Controls / trust

- **Bias is a hard gate — enforced in `@chain`, not just the prompt.** The
  `resume_screener_agent` module FORCES `bias_signal` when the reasoning
  leans on a bias-prone field; the `hiring_assistant_agent` module FORCES
  `requires_hrbp_review` on any `bias_flags` entry. Both route to
  `hrbp_human`, overriding any positive recommendation.
- **Salary band is a hard gate — recomputed in `@chain`, fails closed.**
  The `correspondence_drafter_agent` module recomputes `within_band` from
  the band of record; an out-of-band offer **or** an unconfirmed (0/0) band
  forces `requires_hrbp_review`, and the `can_call` edges send it to the
  HRBP. The LLM cannot mark an out-of-band offer in-band.
- **Screen score floor + interview-loop fairness.** A thin/weak shortlist
  forces re-source to the recruiter (never silent outreach); the interview
  loop is capped at 5h with a recomputed diversity floor — both
  deterministic `@chain` floors.
- **Unenforced narration eliminated.** Every "route to recruiter_human"
  narration has a backing `can_call` edge (intake incomplete, sourcing
  zero-found, ops recruiter-action, booking zero-booked), each mutually
  exclusive with its sibling so exactly one fires.
- **Nothing on silence.** No seat's timeout approves, sends or books
  anything; the card closes and the ticket records it. Every seat's
  `can_call` covers every reply word its prompt offers plus the
  `held_for_review` fallback (validated by `validate_config` check #5).
- **Offer issuance is fail-closed and idempotent.** Ora issues only on an
  explicit approval, inside the band of record, and never the same terms
  twice.
- **EEO data is audit-only.** Candidate self-identification feeds the
  4/5ths audit and is stripped from what the screener, interviewer and
  letter writer read.
- **WORM terminus on every branch.** Hash-chained, append-only.
- **State in the customer's systems.** Candidates + funnel in the ATS,
  interviews in the calendar, via `n8n`; the dev store stands in until then.

---

## 7. Configuration pointer

See `README.md` §Configuration for the three-tier breakdown (boot /
host-prereqs-or-adapters / connectors) and `env` for the variables. The
connector agents are wired to their `n8n` workflows by vault connection
(`sourcing_n8n`, `panel_booking_n8n`, `ats_funnel_n8n`); the sourcer and
booker run on the dev store until then, the funnel analyst is inert. The
manager's Slack/PagerDuty escalation targets are not
shipped — add them under `manager.escalation` (a webhook target names vault
connection `escalation_webhook`, an "Add custom" record on the Infrastructure
page, service type 'Outbound webhook').

---

## 8. Reflection / decisions

- **One correspondence writer, three modes.** Outreach, offer and
  rejection letters were three thin drafters; consolidated into one
  candidate-correspondence writer (Rule 2) with mode inferred from input
  and the salary-band/personalisation guardrails enforced as HARD RULES.
- **One interview coordinator + one booker.** Loop design (judgment) is the
  LLM role; booking (a side-effect into the customer's calendar) is a thin
  connector behind the recruiter gate — the thing that *acts* stays small.
- **Connectors for systems of record.** Sourcing, funnel ledger and panel
  booking go through `n8n` workflows — the data lives in the customer's
  ATS/calendar. The sourcer and booker keep a small Python module so day 0
  runs on the dev store and the wired reply is shaped the same way.
- **Floors in Python.** The EEOC 4/5ths math, the completeness, bias,
  band and rubric floors, and Ora's issuance floor are deterministic code
  because a wrong answer there is legal or pay-equity exposure.
- **`operator_ids` left unset.** Shared-inbox routing; a placeholder email
  would silently swallow every HITL task.
