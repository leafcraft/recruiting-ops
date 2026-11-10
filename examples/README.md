# recruiting-ops — example scenarios

Four realistic scenarios that exercise the major paths through this mesh.

## How to run

```bash
create-leafmesh --load .   # once: loads the team into the Redis in .env (or use create-leafmesh --start .)
python examples/run_examples.py                 # all scenarios
python examples/run_examples.py 01_             # one scenario (substring match)
```

## Scenario map

- **01_new_req_filed** — `req_filed` — The payments req is filed. Cass opens the case, intake normalises it, sourcing loads the seeded pipeline (no connector needed), the screener's copies split it, and clean outreach lands with the recruiter.
- **02_candidate_rejection_letter** — `candidate_rejection` — Phone-screen reject — correspondence_drafter (rejection mode) generates a personalised note with one specific feedback point.
- **03_offer_drafting** — `direct_call_correspondence_drafter` — Priya Nair cleared the onsite; a $205,000 offer inside the $170,000–$210,000 band goes to the hiring manager. Set `proposed_base_cents` to her $235,000 ask to see the band gate send it to the HRBP.
- **04_ghosted_candidate_close** — `ghosted_candidate_close` — Candidate went silent 14 days after onsite — drafts a polite close-out letter.

> Sourcing and panel booking run on the dev store day 0 (the booker books
> nothing and hands the panel to the recruiter). Funnel metrics
> (`recruiting_ops_agent`) need the `ats_funnel_n8n` vault connection
> (Infrastructure → Integrations → n8n) picked on the agent — in Studio's raw YAML editor (see *Changing the configuration* in the main README).

## Audit trail

Every scenario appends one hash-chained entry to the template's
`logs/<audit>.jsonl` file. Tail it during a run to see the
ledger build up across scenarios.
