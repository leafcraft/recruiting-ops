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
> runs the weekly 4/5ths-rule adverse-impact check. Above them sits a HITL
> chain — **recruiter → hiring manager → recruiting manager → HRBP** —
> with default-deny timeouts, and a hash-chained WORM audit on every
> terminal branch.
>
> Built on LeafMesh as an **operation of self-reliant agents**. The
> config IS the department. Candidate data lives in the customer's ATS and
> interviews in the customer's calendar, reached through `n8n` connectors.
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
   │ req_intake_agent   │   │                  │         │ recruiting_ops / │
   │ (LLM) normalise    │   │                  │         │ bias_audit       │
   │  title? ─ no ─► recruiter_human           │         └────────┬─────────┘
   └────┬───────────────┘   │                  │            escalate│ thin/bias
        │ title present      │                  │           ┌────────▼─────────┐
   ┌────▼───────────────┐    │                  │           │ HITL chain       │
   │ sourcing_agent     │    │                  │           └──────────────────┘
   │ (n8n → ATS)        │    │                  │
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

   HITL chain (default-deny on timeout):
   recruiter_human ─► recruiting_manager_human ─► hrbp_human
   hiring_manager_human ─► hrbp_human
   every human terminal ─► recruiting_audit_logger_agent (WORM)
```

The chain flows **forward** — each entry point kicks work off and the
originator steps out; nothing returns to a conductor hub. The only cycles
are the human-gated escalation edges, which are bounded by the chain
(`recruiter → manager → HRBP`, each a distinct role, no loop back down).

---

## 2. Actor inventory

| Agent | Class | Role (job title) | One-line |
|---|---|---|---|
| `req_intake_agent` | 🤖 LLM | Requisition intake specialist | Normalises a filed req (title/level/location/band); blanks salary band rather than inventing it |
| `sourcing_agent` | ⚙️ programmatic (n8n) | Sourcer | Pulls the candidate pipeline from the company's ATS / LinkedIn Recruiter |
| `resume_screener_agent` | 🤖 LLM + module | Resume screener | Scores candidates (`@pre_compose` pulls the pipeline); bias + score floors in `@chain` |
| `correspondence_drafter_agent` | 🤖 LLM + module | Candidate-correspondence writer | Drafts ALL candidate-facing messages; salary-band gate in `@chain`, per-peer `@compose` |
| `interview_coordinator_agent` | 🤖 LLM + module | Interview coordinator | Designs the loop (`@pre_compose` pulls the roster); 5h cap + diversity floor in `@chain` |
| `panel_booker_agent` | ⚙️ programmatic (n8n) | Interview scheduling coordinator | Books the approved panel into the company's calendar / ATS scheduling |
| `hiring_assistant_agent` | 🤖 LLM + module | First-round screening interviewer | Scores the async first round (`@pre_compose` pulls the candidate); rubric thresholds + bias gate in `@chain` |
| `recruiting_ops_agent` | ⚙️ programmatic (n8n) | Recruiting-operations analyst | Reads the funnel ledger from the ATS — thin-funnel sweep + stage / time-to-hire metrics |
| `bias_audit_agent` | ⚙️ programmatic (Python) | EEOC compliance auditor | Weekly 4/5ths-rule adverse-impact audit on screening decisions |
| `recruiter_human` | 👤 human | Recruiter | Reviews outreach drafts, shortlists, flagged loops; releases flagged panels to booking |
| `hiring_manager_human` | 👤 human | Hiring manager | Final approval on a clean, in-band offer |
| `recruiting_manager_human` | 👤 human | Recruiting manager | Team-level escalation when the recruiter can't resolve |
| `hrbp_human` | 👤 human | HR business partner | Bias / salary-band / policy authority — the highest gate |
| `recruiting_audit_logger_agent` | 🧾 external (WORM) | Compliance records keeper | Hash-chained, append-only audit of every terminal decision |

> **Why three connector agents are `programmatic`/`n8n`, not LLMs.** Sourcing,
> the funnel ledger, and panel booking are reads/writes against the
> customer's systems of record (ATS, LinkedIn Recruiter, calendar) — not
> judgment over text. They are pure connector config pointing at `n8n`
> workflows; their returned fields count as yields, so the outbound
> conditions evaluate normally. State lives in the customer's systems, not
> in template storage.

> **Why `bias_audit_agent` keeps its Python module.** The EEOC 4/5ths rule
> (29 CFR 1607.4(D)) is compliance-grade domain math — per-group
> selection-rate ratios with a minimum-sample floor where a wrong number is
> legal exposure. It must be deterministic, reproducible, unit-tested code;
> an LLM estimate is not audit-defensible.

---

## 3. Data artifacts

- **Req** — `{req_id, title, level, location, salary_band_low_cents, salary_band_high_cents, received_at_utc}` (the one declared `data_structure`; salary band stays 0 until the HRBP fills it).
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

### 4.0 `req_intake_agent` — requisition intake specialist (LLM)
Normalises a filed req into title / level / location / salary band (cents).
**Never invents a salary band** — sets both fields to 0 for the HRBP to
fill. **Wires.** → `sourcing_agent` when `title != ''`; →
`recruiter_human` when `title == ''` (malformed req — a human fixes the
intake rather than sourcing blind).

### 4.1 `sourcing_agent` — sourcer (PROGRAMMATIC · n8n)
Connector-only: the webhook hits an `n8n` workflow that queries the ATS
candidate search / LinkedIn Recruiter and returns `{candidates_found,
candidate_ids}`. **Wires.** → `resume_screener_agent` when
`candidates_found > 0`; → `recruiter_human` when `candidates_found == 0`
(empty top-of-funnel — widen criteria or approve external spend).

### 4.2 `resume_screener_agent` — resume screener (LLM + module)
Scores each candidate, computes `avg_fit_score`, sets `bias_signal`,
briefs the recruiter. Grounded by the `screening_rubric` knowledge group.
**Module (`agency/resume_screener_agent.py`).** `@pre_compose load_pipeline`
pulls the req spec + the real candidate pipeline (resume data + prior
screens) from the ATS (dev: store) so the LLM scores real candidates.
`@chain enforce_screen_floors` holds two floors the prompt cannot waive:
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
(`claude-sonnet-4-6`) because offers are the highest-stakes correspondence;
grounded by `offer_templates`. **Module
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
HM debrief, capped at 5 hours. Grounded by `interviewer_roster`. **Module
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
Scores the async first round on a five-dimension weighted rubric
(`interview_rubrics`). **Module (`agency/hiring_assistant_agent.py`).**
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

### 4.9 The HITL chain (HUMANS · default-deny)
- `recruiter_human` → `recruiting_manager_human` (escalate), →
  `panel_booker_agent` (release a flagged panel: `book_panel`), → WORM
  (anything resolved). Timeout → escalate to manager.
- `hiring_manager_human` → `hrbp_human` (escalate) / → WORM. Timeout →
  HRBP.
- `recruiting_manager_human` → `hrbp_human` / → WORM. Timeout → HRBP.
- `hrbp_human` → WORM (terminal authority). Timeout → `halt_for_review`
  (held, never silently approved).
All four have `fallback_on_timeout: true`; `operator_ids` are left unset
so gates route to the **shared inbox** (a placeholder email would make the
task invisible).

### 4.10 `recruiting_audit_logger_agent` — compliance records keeper (EXTERNAL · WORM)
`framework: custom`; registered in `main.py` via `mesh.intelligence(...)`.
Appends hash-chained JSON lines so any insertion/deletion is detectable.
Terminal (`can_call: []`).

---

## 5. Entry points

| Entry point | Target | Trigger |
|---|---|---|
| `req_filed` | `req_intake_agent` | Requisition opened in the ATS |
| `referral_received` | `resume_screener_agent` | A referral candidate jumps straight to screening |
| `linkedin_inmail_reply` | `correspondence_drafter_agent` | Candidate replied to outreach |
| `scheduled_pipeline_health` | `recruiting_ops_agent` | Top-of-funnel sweep (+ funnel metrics) |
| `manual_action` | `sourcing_agent` | Recruiter-initiated sourcing pull |
| `candidate_stage_update` | `recruiting_ops_agent` | Record one stage transition (ingest mode) |
| `funnel_metrics_report` | `recruiting_ops_agent` | Read funnel metrics (report mode) |
| `design_interview_loop` | `interview_coordinator_agent` | Design a loop for a req |
| `candidate_rejection` | `correspondence_drafter_agent` | Draft a personalised rejection |
| `post_onsite_reject` | `correspondence_drafter_agent` | Longer onsite-stage feedback letter |
| `ghosted_candidate_close` | `correspondence_drafter_agent` | Polite close-out after 14+ days silent |
| `async_screen_interview` | `hiring_assistant_agent` | First-round async screen |
| `weekly_bias_audit` | `bias_audit_agent` | Sunday cron — EEOC audit |
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
  narration now has a backing `can_call` edge (intake title-less, sourcing
  zero-found, ops recruiter-action, booking zero-booked), each mutually
  exclusive with its sibling so exactly one fires.
- **Default-deny HITL.** Every human gate has `fallback_on_timeout: true`
  and a fallback that routes (validated by `validate_config` check #5);
  the HRBP's timeout is `halt_for_review`, never an implicit approve.
- **WORM terminus on every branch.** Hash-chained, append-only.
- **State in the customer's systems.** No template database; candidates +
  funnel in the ATS, interviews in the calendar, via `n8n`.

---

## 7. Configuration pointer

See `README.md` §Configuration for the three-tier breakdown (boot /
host-prereqs-or-adapters / connectors) and `env` for the variables. The
connector agents (`sourcing_agent`, `recruiting_ops_agent`,
`panel_booker_agent`) ship inert — blank webhook URLs — until their `n8n`
workflows are wired; the manager's Slack/PagerDuty escalation targets are
likewise inert until their env vars are set.

---

## 8. Reflection / decisions

- **One correspondence writer, three modes.** Outreach, offer and
  rejection letters were three thin drafters; consolidated into one
  candidate-correspondence writer (Rule 2) with mode inferred from input
  and the salary-band/personalisation guardrails enforced as HARD RULES.
- **One interview coordinator + one booker.** Loop design (judgment) is the
  LLM role; booking (a side-effect into the customer's calendar) is a thin
  connector behind the recruiter gate — the thing that *acts* stays small.
- **Connector-only for systems of record.** Sourcing, funnel ledger and
  panel booking are `n8n` connectors, not Python — the data always lived
  in the customer's ATS/calendar, so the template carries no database.
- **Only the EEOC math stays Python.** Everything an LLM can reliably do is
  YAML; the compliance-grade 4/5ths math is the lone module because a wrong
  number there is legal exposure.
- **`operator_ids` left unset.** Shared-inbox routing; a placeholder email
  would silently swallow every HITL task.
