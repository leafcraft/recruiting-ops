# recruiting-ops — Recruiting Operations

A full recruiting department as a mesh of self-reliant agents:
**source → screen → correspond → interview → schedule → offer**, with a
recruiter → hiring-manager → recruiting-manager → HRBP human chain, a
weekly EEOC bias audit, and a hash-chained WORM trail. The config IS the
department — candidates live in YOUR ATS and interviews in YOUR calendar,
reached through `n8n` connectors.

**Self-reliant agents, not prompt theatre.** The four judgment agents each
**pull their own context** (`@pre_compose`) from the ATS and **enforce
their own compliance floors** (`@chain`) the LLM cannot waive:

| Agent | `@pre_compose` pulls | `@chain` floor (deterministic) |
|---|---|---|
| `resume_screener_agent` | the req spec + the real candidate pipeline | **bias floor** (forces `bias_signal` when reasoning leans on name/school/photo/address) + **screen score floor** (thin/weak shortlist → re-source, never outreach) |
| `correspondence_drafter_agent` | the req's confirmed salary band + the candidate record | **salary-band gate** — recomputes `within_band` from the band of record; out-of-band **or** an unconfirmed (0/0) band **fails closed** to HRBP. `@compose` hands HRBP / hiring-manager / WORM each its own payload |
| `hiring_assistant_agent` | the candidate + their prior screen | **rubric thresholds** (recommendation derived from the recomputed weighted score) + **bias-flag override** to HRBP + malformed-payload guard |
| `interview_coordinator_agent` | the req's dimensions + the interviewer roster | **5h cap** + mandatory **HM-debrief** + **diversity floor** (≥2 distinct interviewer levels) |

A dev store (`agency/_shared/store.py`) seeds realistic reqs + candidates +
an interviewer roster so the whole chain runs **before any connector is
wired**. The other Python is the compliance-grade EEOC 4/5ths math.

---

## Story

A hiring manager files a **Senior Backend Engineer — Payments** req in
Greenhouse (`req_filed`). The **requisition intake specialist**
(`req_intake_agent`) normalises it — title, level `senior`, location, and
a salary band it refuses to invent (left at 0 for HR to confirm). Because
the req has a title, it hands off to the **sourcer** (`sourcing_agent`),
whose `n8n` workflow queries the ATS candidate search and LinkedIn
Recruiter and comes back with 23 candidates. The **resume screener**
(`resume_screener_agent`) scores them against the spec, shortlists six,
and — finding it leaned only on skills and experience — sets
`bias_signal: false`, so it routes to the **candidate-correspondence
writer** (`correspondence_drafter_agent`), which drafts personalised
outreach citing each candidate's payments work. The drafts go to the
**recruiter** (`recruiter_human`) for a final human read before sending.

One candidate, Talia Wong, replies and clears the loop the **interview
coordinator** (`interview_coordinator_agent`) designed — a diverse,
five-hour panel the **scheduling coordinator** (`panel_booker_agent`)
booked straight into the team's calendar. When the offer is drafted, the
writer checks it against the band: in-band and clean, so it routes to the
**hiring manager** (`hiring_manager_human`) for final approval — had it
been a dollar over band, it would have been forced to the **HR business
partner** (`hrbp_human`) instead, no exceptions. Every terminal step —
the sent rejection letters, the booked panel, the approved offer — lands
in the hash-chained WORM log. On Sunday, the **EEOC compliance auditor**
runs the 4/5ths-rule check over the week's screening decisions; a clean
run is logged, an adverse-impact finding pages the HRBP.

## Why it works in an organization

Recruiting is high-volume, high-judgment, and high-liability all at once —
exactly where an agency pays off. The mesh **automates the mechanical
funnel** (intake normalisation, sourcing pulls, resume scoring, drafting
every candidate message, designing and booking loops, reading funnel
metrics) so recruiters spend their hours on the judgment calls, not the
copy-paste. It **closes the candidate-experience gap** that costs Glassdoor
reputation: every rejection is personalised and specific, and nobody gets
ghosted, because the close-out is a first-class flow. And it **builds
compliance in by construction** rather than bolting it on: bias signals
and out-of-band offers are *hard* gates to the HRBP that no prompt can
wave through, the weekly EEOC 4/5ths audit is deterministic math, and the
hash-chained WORM log makes every decision defensible after the fact. The
ROI is faster time-to-hire, a better candidate brand, and audit-ready
bias/compensation controls — without adding headcount.

---

## Configuration

Three tiers — start at the top; each lower tier unlocks more of the mesh.

### Tier 1 — Boot (required to start the mesh)
| Var | Why |
|---|---|
| `LEAFMESH_LICENSE_KEY` | SDK license |
| `OPENAI_API_KEY` | the `gpt-4o-mini` agents (intake, screener, coordinator) + the manager |
| `ANTHROPIC_API_KEY` | the `claude-sonnet-4-6` agents (correspondence writer, screening interviewer) |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` | session + state store (defaults `localhost:6379`) |

`pip install -r requirements.txt` (LeafMesh ≥ 2.4, APScheduler for the cron,
python-dotenv, PyYAML) and `python main.py` boots the mesh. The LLM agents
run day-0 against the seeded **dev store** (`agency/_shared/store.py`); the
connector agents are inert until Tier 3. **Knowledge groups**
(`recruiting_runbook`, `screening_rubric`, `offer_templates`,
`interviewer_roster`, `interview_rubrics`) ground the LLM agents via the
`mongo_main` RAG service — optional but recommended for real screening /
offer / interview-design quality.

### Tier 2 — Host prerequisites & escalation adapters (optional)
| Var | Why | Status |
|---|---|---|
| `PAGER_WEBHOOK` | PagerDuty Events v2 — manager escalation | optional; defaults to the PD enqueue URL |
| `SLACK_BOT_TOKEN` + `SLACK_SIGNING_SECRET` | consumed by the SDK's `provider: slack` escalation channel | optional — set all three Slack vars or leave blank to disable |
| `SLACK_RECRUITING_CHANNEL` | the Slack channel_id escalations post to | optional |
| `LEAFMESH_ENV_TOKEN` | environment marker (`development`) | as needed |

### Tier 3 — Connectors (required for the full lifecycle)
The three connector agents ship with **blank** webhook URLs and stay inert
until you point them at `n8n` workflows against YOUR systems:

| Var | Powers | Returns |
|---|---|---|
| `N8N_SOURCING_WEBHOOK_URL` | `sourcing_agent` → ATS candidate search / LinkedIn Recruiter | `{candidates_found, candidate_ids}` |
| `N8N_ATS_FUNNEL_WEBHOOK_URL` | `recruiting_ops_agent` → ATS funnel / stage / time-to-hire ledger | funnel metrics (mode-dispatched) |
| `N8N_PANEL_BOOKING_WEBHOOK_URL` | `panel_booker_agent` → calendar (Google/Outlook) or ATS scheduling | `{interviews_booked, panel}` |
| `N8N_AUTH_TOKEN` | shared bearer token for the three `n8n` workflows | — |

The `recruiting_ops_agent` daily-sweep cron (`wake_up: "0 9 * * *"`) is
**commented out** in the config — enable it after wiring
`N8N_ATS_FUNNEL_WEBHOOK_URL`, or it would error against a blank URL every
morning. The `bias_audit_agent` Sunday cron is always on (it audits data
you POST to the `weekly_bias_audit` entry point — no connector needed).

---

## Agent table

| Agent | Role | Responsibilities | Can perform |
|---|---|---|---|
| `req_intake_agent` | Requisition intake specialist | Normalise a filed req (title/level/location/band); never invent a salary band | LLM (`gpt-4o-mini`), `recruiting_runbook` knowledge (via manager); → sourcer if titled, else → recruiter |
| `sourcing_agent` | Sourcer | Pull the candidate pipeline from the ATS / LinkedIn Recruiter | `programmatic` · `n8n` (`N8N_SOURCING_WEBHOOK_URL`); → screener if candidates>0, else → recruiter |
| `resume_screener_agent` | Resume screener | Score candidates against the spec, flag bias, brief the recruiter | LLM (`gpt-4o-mini`) + module (`@pre_compose` pulls the pipeline, `@chain` enforces bias + score floors); → HRBP if bias, recruiter if thin, else → correspondence writer |
| `correspondence_drafter_agent` | Candidate-correspondence writer | Draft ALL candidate messages — outreach, offers (band-enforced), rejections (bridge-preserving) | LLM (`claude-sonnet-4-6`) + module (`@pre_compose` pulls the band, `@chain` salary-band gate, `@compose` per-peer); → recruiter / HRBP / hiring manager / WORM by mode |
| `interview_coordinator_agent` | Interview coordinator | Design the loop — dimension coverage, diversity-aware panel, 5h cap | LLM (`gpt-4o-mini`) + module (`@pre_compose` pulls the roster, `@chain` enforces cap + diversity + debrief); → recruiter if flagged, else → booker |
| `panel_booker_agent` | Interview scheduling coordinator | Book the approved panel into the calendar / ATS scheduling | `programmatic` · `n8n` (`N8N_PANEL_BOOKING_WEBHOOK_URL`); → WORM if booked, else → recruiter |
| `hiring_assistant_agent` | First-round screening interviewer | Score the async first round on a 5-dimension rubric; advance/borderline/decline | LLM (`claude-sonnet-4-6`) + module (`@pre_compose` pulls the candidate, `@chain` derives recommendation + bias gate); → HRBP / hiring manager / rejection draft |
| `recruiting_ops_agent` | Recruiting-operations analyst | Read the ATS funnel — thin-funnel sweep, stage + time-to-hire metrics | `programmatic` · `n8n` (`N8N_ATS_FUNNEL_WEBHOOK_URL`); → recruiting manager if thin, else → recruiter |
| `bias_audit_agent` | EEOC compliance auditor | Weekly 4/5ths-rule adverse-impact audit on screening decisions | `programmatic` Python (`agency/bias_audit_agent.py`), cron `0 8 * * 0`; → HRBP on finding |
| `recruiter_human` | Recruiter | Review outreach/shortlists/flagged loops; release flagged panels to booking | `human` (7200s timeout, default-deny); → recruiting manager / booker / WORM |
| `hiring_manager_human` | Hiring manager | Final approval on a clean, in-band offer | `human` (14400s timeout, → HRBP on timeout); → HRBP / WORM |
| `recruiting_manager_human` | Recruiting manager | Team-level escalation when the recruiter can't resolve | `human` (14400s timeout, → HRBP on timeout); → HRBP / WORM |
| `hrbp_human` | HR business partner | Bias / salary-band / policy authority — the highest gate | `human` (21600s timeout, `halt_for_review`); → WORM |
| `recruiting_audit_logger_agent` | Compliance records keeper | Hash-chained, append-only audit of every terminal decision | `external` `custom` WORM (registered in `main.py`); terminal |

---

## Run it

```bash
cp env .env            # then fill in LICENSE + model keys (Tier 1)
pip install -r requirements.txt
python validate_config.py   # pre-flight: targets, conditions, yields↔prompt
python main.py             # API at http://127.0.0.1:18820/docs
```

Day-0 (no connectors), file the seeded payments req and watch the chain run
against the dev store:

```bash
curl -X POST http://127.0.0.1:18820/api/mesh/call \
  -H "Content-Type: application/json" \
  -d '{"entry_point":"req_filed",
       "input_data":{"payload":{"req_id":"req-payments-001"}}}'
```

Intake normalises it → the screener (its `@pre_compose` pulls the seeded
pipeline; its `@chain` holds the bias + score floors) shortlists →
correspondence drafts outreach → the recruiter reviews. Run a screen or an
offer the same way (`async_screen_interview` with `candidate_id`,
`linkedin_inmail_reply` with `req_id` + an offer ask) to exercise the
rubric and salary-band floors.

`python validate_config.py` checks the graph (targets exist, conditions
reference real yields, every LLM prompt carries its OUTPUT CONTRACT, HITL
fallbacks route, cron shape, dead-module reconciliation) before you boot.
`python -m pytest tests/ -q` runs the floor unit tests (bias, salary band,
rubric thresholds, loop cap). See `PRD.md` for the full architecture.
