# recruiting-ops — Recruiting Operations

A full recruiting department as a mesh of self-reliant agents:
**source → screen → correspond → interview → schedule → offer**, with a
recruiter → hiring-manager → recruiting-manager → HRBP human chain, a
weekly EEOC bias audit, and a hash-chained WORM trail. The config IS the
department — candidates live in YOUR ATS and interviews in YOUR calendar,
reached through `n8n` connectors once you wire them. Until then the pod runs
on a seeded dev store.

**Self-reliant agents, not prompt theatre.** The four judgment agents each
**pull their own context** (`@pre_compose`) from the ATS and **enforce
their own compliance floors** (`@chain`) the LLM cannot waive:

| Agent | `@pre_compose` pulls | `@chain` floor (deterministic) |
|---|---|---|
| `resume_screener_agent` | (its tools `claim_candidate_batch` / `get_req_spec` / `get_candidate` read the req spec + the pipeline, EEO fields removed) | **bias floor** (forces `bias_signal` when reasoning leans on name/school/photo/address) + **screen score floor** (thin/weak shortlist → re-source, never outreach) |
| `correspondence_drafter_agent` | the req's confirmed salary band + the candidate record | **salary-band gate** — recomputes `within_band` from the band of record; out-of-band **or** an unconfirmed (0/0) band **fails closed** to HRBP. `@compose` hands HRBP / hiring-manager / WORM each its own payload |
| `hiring_assistant_agent` | the candidate + their prior screen | **rubric thresholds** (recommendation derived from the recomputed weighted score) + **bias-flag override** to HRBP + malformed-payload guard |
| `interview_coordinator_agent` | the req's dimensions + the interviewer roster | **5h cap** + mandatory **HM-debrief** + **diversity floor** (≥2 distinct interviewer levels) |

A dev store (`agency/_shared/store.py`) seeds three reqs at a fictional
~400-person fintech (Larkspur Pay), twelve candidates and an eight-person
interviewer roster, so the whole chain runs **before any connector is
wired**. The seeds cover the happy path (req-payments-001: a confirmed band
and five screenable candidates), an over-band ask (cand-103), a record with no
skills data (cand-107, left off the shortlist rather than guessed), a ghosted
onsite (cand-204) and an unconfirmed band (req-ml-003, offers fail closed to
the HRBP). Candidate EEO self-identification is kept for the 4/5ths audit only
and is stripped from everything a screener, interviewer or letter writer
reads. The other Python is the compliance-grade EEOC 4/5ths math, the sourcer
and booker (dev store day 0), and Ora, the offer issuer.

---

## Story

A hiring manager files a **Senior Backend Engineer — Payments** req in
Greenhouse (`req_filed`). **Cass**, the talent coordinator
(`talent_coordinator_agent`), opens the case and hands it to the
**requisition intake specialist** (`req_intake_agent`), which normalises it —
title, level `senior`, location, and the $170,000–$210,000 band it reads from
the comp record (it never invents one: a req without a confirmed band goes
back to the recruiter, not to sourcing). The **sourcer** (`sourcing_agent`)
pulls the req's open pipeline — from the dev store on day 0, from the ATS
candidate search and LinkedIn Recruiter once its `n8n` workflow is wired — and
loads the screening backlog. Three copies of **Sena**, the resume screener
(`resume_screener_agent`), each claim a different batch, score on skills and
experience only, and shortlist four; finding no lean on name, school or
address, she sets `bias_signal: false`, so it routes to the
**candidate-correspondence writer** (`correspondence_drafter_agent`), which
drafts outreach citing each candidate's payments work. The drafts go to the
**recruiter** (`recruiter_human`), who sends them from the ATS.

One candidate, Priya Nair, clears the loop the **interview coordinator**
(`interview_coordinator_agent`) designed — a diverse panel under five hours
that the **scheduling coordinator** (`panel_booker_agent`) books into the
team's calendar (day 0, with no calendar wired, it books nothing and hands
the proposed panel to the recruiter to book by hand). Her offer is drafted at
$205,000: in-band and clean, so it routes to the **hiring manager**
(`hiring_manager_human`) for approval, and **Ora**, the offer issuer
(`offer_issuer_agent`), re-checks the approval and the band before she
renders the letter. Had it been drafted at her $235,000 ask, the band gate
would have sent it to the **HR business partner** (`hrbp_human`) instead, and
Ora would refuse to issue it whatever anyone clicked. Every terminal step —
the sent rejection letters, the booked panel, the issued offer — lands in the
hash-chained WORM log. On Sunday, the **EEOC compliance auditor** runs the
4/5ths-rule check over the week's screening decisions; a clean run is logged,
an adverse-impact finding goes to the HRBP's Inbox.

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
python-dotenv, PyYAML) and `python main.py` boots the mesh. The agents run
day-0 against the seeded **dev store** (`agency/_shared/store.py`): the
sourcer reads its pipeline, the booker records proposed panels (it books
nothing), and Ora records issued offers in a dev outbox. Only the funnel
analyst (`recruiting_ops_agent`) is inert until Tier 3. No knowledge groups
ship with the pod. The screener and the correspondence writer name the skills
`bias` and `tone` from a skill source called `recruiting_playbooks`; no skill
files ship either — add that source and the two skills in Studio before you
rely on them. Until then those agents work from their prompts and playbooks.

### Tier 2 — Host prerequisites & escalation adapters (optional)
| Var | Why | Status |
|---|---|---|
| *(vault connection `escalation_webhook`)* | PagerDuty Events v2 — manager escalation | optional; no webhook target ships — create the connection, then add a `type: webhook` target with `connection: escalation_webhook` under `manager.escalation` |
| *(Slack, via the vault)* | Slack escalation channel | optional; none ships. Connect Slack on Infrastructure → Messaging → Slack (bot token + signing secret live there, never in `.env`), give a human seat `channels: {slack: {connection: <name>}}`, then add a `type: channel`, `provider: slack`, `channel_id: <C…>` target under `manager.escalation` |
| `LEAFMESH_ENV_TOKEN` | environment marker (`development`) | as needed |

### Tier 3 — Connectors (required for the full lifecycle)
Point the connector agents at `n8n` workflows against YOUR systems. A
workflow's address and token are entered only in the vault: create the vault
connection on Infrastructure → Integrations → n8n (base URL = the workflow's
webhook URL, token = its auth token), then wire the agent in
`configs/config.yaml` before the first start, or in Studio's YAML editor after
it (applies live, no restart; see *Changing the configuration after the first start*).

| Vault connection | Powers | How to wire | Returns |
|---|---|---|---|
| `sourcing_n8n` | `sourcing_agent` → ATS candidate search / LinkedIn Recruiter | uncomment its `integration` + `connector_config` lines | `{candidates_found, candidate_ids}` |
| `panel_booking_n8n` | `panel_booker_agent` → calendar (Google/Outlook) or ATS scheduling | uncomment its `integration` + `connector_config` lines | `{interviews_booked, panel}` |
| `ats_funnel_n8n` | `recruiting_ops_agent` → ATS funnel / stage / time-to-hire ledger | already named on the agent: create the record and it switches on (until then it is switched off, with a notice) | funnel metrics (mode-dispatched) |
| `ats_mcp` | `resume_screener_agent` → ATS reads as tools (Infrastructure → Integrations → MCP) | uncomment its `mcp:` block | one tool per action |

The sourcer and booker keep their `integration` lines commented on day 0 on
purpose: an `n8n` integration with no workflow address fails every call, and
after five failures in a row the mesh quarantines the agent, so its day-0
Python would never run again. With the lines uncommented, the same Python
shapes the workflow's reply; a failed call is reported (0 found / 0 booked)
and goes to the recruiter — it never falls back to seed data.

The screener's claim tool checks the vault for a `sourcing_n8n` or `ats_mcp`
record to know whether a real ATS is wired; nothing in `.env` switches it.

To post each issued offer to your HRIS, uncomment `notify` on
`offer_issuer_agent`: create an Outbound webhook record on Infrastructure
("Add custom", service type 'Outbound webhook'), add a webhook named
`hris_offer_issued` on Tools → Webhooks that picks it. The mesh posts Ora's
finished output; it posts blocked runs too, so the receiving side must act
only on `status == "issued"`.

The `recruiting_ops_agent` weekday-sweep cron (`wake_up: "0 9 * * 1-5"`) is
**commented out** in the config — enable it after creating the
`ats_funnel_n8n` record; until then the agent is switched off and a cron would
only fire into a switched-off agent every morning. The `bias_audit_agent` Sunday cron is always on (it audits data
you POST to the `weekly_bias_audit` entry point — no connector needed).

---

## Agent table

| Agent | Role | Responsibilities | Can perform |
|---|---|---|---|
| `talent_coordinator_agent` | Talent coordinator (Cass) | Open the case on a filed req; answer "where is this req?" from the case record | LLM (`gpt-4o-mini`); → intake on `open_req`, → recruiter on `escalate` |
| `req_intake_agent` | Requisition intake specialist | Normalise a filed req (title/level/location/band); never invent a salary band | LLM (`gpt-4o-mini`) + module (`@pre_compose` pulls prior/duplicate req + band of record, `@chain` completeness floor); → sourcer if complete (title + level + confirmed band), else → recruiter |
| `sourcing_agent` | Sourcer | Pull the req's pipeline and load the screening backlog | `programmatic` Python (dev store day 0; `n8n` via vault connection `sourcing_n8n` when wired); → screener if candidates>0, else → recruiter |
| `resume_screener_agent` | Resume screener (Sena) | Score candidates against the spec, flag bias, brief the recruiter | LLM (`claude-sonnet-4-6`, super-agent, 3 copies) + claim/read tools + module (`@chain` enforces bias + score floors); → HRBP if bias, recruiter if thin, else → correspondence writer |
| `correspondence_drafter_agent` | Candidate-correspondence writer | Draft ALL candidate messages — outreach, offers (band-enforced), rejections (bridge-preserving) | LLM (`claude-sonnet-4-6`) + module (`@pre_compose` pulls the band, `@chain` salary-band gate, `@compose` per-peer); → recruiter / HRBP / hiring manager / WORM by mode |
| `interview_coordinator_agent` | Interview coordinator | Design the loop — dimension coverage, diversity-aware panel, 5h cap | LLM (`gpt-4o-mini`) + module (`@pre_compose` pulls the roster, `@chain` enforces cap + diversity + debrief); → recruiter if flagged, else → booker |
| `panel_booker_agent` | Interview scheduling coordinator | Book the approved panel into the calendar / ATS scheduling | `programmatic` Python (day 0 records the proposed panel, books nothing; `n8n` via vault connection `panel_booking_n8n` when wired); → WORM if booked, else → recruiter to book by hand |
| `offer_issuer_agent` | Offer issuer (Ora) — finisher | Re-check the approval and the band of record, render the letter, ledger it; never issues the same terms twice | `programmatic` Python (`@chain` issuance floor); → WORM |
| `hiring_assistant_agent` | First-round screening interviewer | Score the async first round on a 5-dimension rubric; advance/borderline/decline | LLM (`claude-sonnet-4-6`) + module (`@pre_compose` pulls the candidate, `@chain` derives recommendation + bias gate); → HRBP / hiring manager / rejection draft |
| `recruiting_ops_agent` | Recruiting-operations analyst | Read the ATS funnel — thin-funnel sweep, stage + time-to-hire metrics | `programmatic` · `n8n` (vault connection `ats_funnel_n8n`); → recruiting manager if thin, else → recruiter |
| `bias_audit_agent` | EEOC compliance auditor | Weekly 4/5ths-rule adverse-impact audit on screening decisions | `programmatic` Python (`agency/bias_audit_agent.py`), cron `0 8 * * 0`; → HRBP on finding |
| `recruiter_human` | Recruiter | Review outreach/shortlists/flagged loops; book panels; release flagged panels to booking | `human` (2h); `book_panel` → booker, any other reply → WORM |
| `hiring_manager_human` | Hiring manager | Final approval on a clean, in-band offer | `human` (one business day, 8h); `approved` → Ora, any other reply → WORM |
| `recruiting_manager_human` | Recruiting manager | Team-level call on a thin or stalled funnel (from the funnel analyst) | `human` (4h); → WORM |
| `hrbp_human` | HR business partner | Bias / salary-band / policy authority — the highest gate; also gets the Manager's error escalations | `human` (one business day, 8h); → WORM |
| `recruiting_audit_logger_agent` | Compliance records keeper | Hash-chained, append-only audit of every terminal decision | `external` `custom` WORM (registered in `main.py`); terminal |

### When nobody answers

Nothing is sent, approved or booked on silence. If nobody answers a seat within
its time (recruiter 2h, recruiting manager 4h, hiring manager and HRBP one
business day), the request waits no longer: its Inbox card closes and the
ticket records that no reply came. Nobody is chased automatically — the
recruiter or hiring manager picks it up from the ticket. Each seat keeps
`fallback_on_timeout` / `fallback_response: held_for_review` in config as the
declared intent; on leafmesh 2.4.486 a timeout on these seats routes nothing.

The Manager escalates to the HRBP only on errors: a non-retryable error (sign-in,
bad request, bad config) the first time it happens, five failed agents in one
session, or restarts used up. A bias signal or an out-of-band offer reaches the
HRBP through the agents' own routes, not through the Manager.

`resume_screener_agent` runs as three copies (`scaling.copies.count: 3`) that split
the candidate backlog with its own atomic claim tool (`claim_candidate_batch`).
leafmesh 2.4.484's `scaling.copies.mode: auto` with `claim_tool:` could replace
this manual split (the mesh would claim each item and start a copy only when there
is one); that switch is the owner's decision and is not made in this template.

---

## Run it

```bash
cp env .env            # then fill in LICENSE + model keys (Tier 1)
pip install -r requirements.txt
python validate_config.py   # pre-flight: targets, conditions, yields↔prompt
python main.py             # API at http://127.0.0.1:18820/docs
```

Day-0 (no connectors), file the seeded payments req and watch the chain run
against the dev store (Cass → intake → sourcer → three screener copies →
outreach draft → recruiter's Inbox):

```bash
curl -X POST http://127.0.0.1:18820/api/mesh/call \
  -H "Content-Type: application/json" \
  -d '{"entry_point":"req_filed",
       "input_data":{"payload":{"req_id":"req-payments-001"}}}'
```

Intake normalises it → the sourcer loads the five screen-stage candidates →
the screener copies claim them (their `@chain` holds the bias + score floors)
and shortlist → correspondence drafts outreach → the recruiter reviews. Run a
screen or an offer the same way (`async_screen_interview` with
`candidate_id`, `direct_call_correspondence_drafter` with
`examples/03_offer_drafting.json`) to exercise the rubric and salary-band
floors.

`python validate_config.py` checks the graph (targets exist, conditions
reference real yields, every LLM prompt carries its OUTPUT CONTRACT, HITL
fallbacks route, cron shape, dead-module reconciliation) before you boot.
`python -m pytest tests/ -q` runs the floor unit tests (bias, salary band,
rubric thresholds, loop cap). See `PRD.md` for the full architecture.

## Changing the configuration after the first start

`configs/config.yaml` is only the first-start seed. On the first start (an empty store) the agency imports it as version 1 and from then on keeps its configuration in the store. After that the file is not read again: an edit to it is **not** applied, even after a restart (the boot log says "that edit was NOT applied").

To change a running agency:

- **Studio** — its settings pages, or the raw YAML editor.
- **API** — `PUT /api/yaml/raw` with an `X-API-Key` header and the body `{"yaml_content": "<the whole YAML>", "save_to_disk": true}`, or `PATCH /api/yaml/config` with `{"updates": {...}, "save_to_disk": true}`.

Each save is a new version and applies live on every pod — no restart. (A few settings, such as brokers, make the agency reload itself in place within seconds.) So wherever this README or a comment says "uncomment X in `configs/config.yaml`", do it in the file before the first start, or in Studio's YAML editor after it.

## Where the data store is set

From leafmesh 2.4.482 the store (Redis or Postgres) is set **only in `.env`** — never in `configs/config.yaml`. A `persistence:` block in the YAML is ignored with a warning on leafmesh 2.4.482–2.4.485; from 2.4.486 the agency refuses to start if that block differs from `.env`, and names each `.env` line to add. The project's `.env` sets the store explicitly (`LEAFMESH_STORE`, `LEAFMESH_AGENCY_NAME`, `REDIS_*`).

- Redis (default): `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_DB`; optional `REDIS_DEFAULT_TTL`, `REDIS_SESSION_TTL`, `REDIS_SSL*`, `REDIS_CLUSTER_NODES`.
- Postgres instead: `LEAFMESH_STORE=postgres` plus `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` (optional `POSTGRES_SSLMODE`).
- Or the whole server in one value: `REDIS_URL=redis://user:pw@host:6379/0` (`rediss://` turns TLS on) or `DATABASE_URL=postgresql://user:pw@host:5432/db`. The single names fill in what the URL leaves out.
- With Docker Compose the app reaches Redis as `redis` (the service name); compose sets that for you.
- Check it in Studio → **Infrastructure → Datastores**: it shows whether the store is reachable (never the address or password).

## Your vault key — back it up

`create-leafmesh` put a `LEAFMESH_VAULT_KEY` in your `.env` when it made this project. It is the master key that encrypts every connection and credential you store in the vault (in Redis / Postgres).

- **Back it up like a master password.** Lose it and every stored connection has to be entered again.
- **Never change or regenerate it** for an existing project — a new key locks the existing vault. To change it, use `leafmesh vault rotate-key`.
- Every copy of the app (every replica) must get the **same** value. Docker Compose passes it in from `.env` as an environment variable.
- Never commit `.env` (it is already in `.gitignore`).
