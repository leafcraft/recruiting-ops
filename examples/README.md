# recruiting-ops — example scenarios

Four realistic scenarios that exercise the major paths through this mesh.

## How to run

```bash
python examples/run_examples.py                 # all scenarios
python examples/run_examples.py 01_             # one scenario (substring match)
```

## Scenario map

- **01_new_req_filed** — `req_filed` — Hiring manager files a senior engineer req. req_intake normalises; sourcing_agent then pulls the candidate pipeline from your ATS connector (wire `N8N_SOURCING_WEBHOOK_URL` first); screener filters.
- **02_candidate_rejection_letter** — `candidate_rejection` — Phone-screen reject — correspondence_drafter (rejection mode) generates a personalised note with one specific feedback point.
- **03_offer_drafting** — `direct_call_correspondence_drafter` — Candidate cleared all loops — correspondence_drafter (offer mode) produces the offer letter, within_band check confirms compensation policy.
- **04_ghosted_candidate_close** — `ghosted_candidate_close` — Candidate went silent 14 days after onsite — drafts a polite close-out letter.

> Sourcing, funnel metrics and panel booking run through n8n
> connectors into your ATS / calendar — scenarios that reach those
> agents need the `N8N_*` env vars in `.env` pointed at real
> workflows.

## Audit trail

Every scenario appends one hash-chained entry to the template's
`logs/<audit>.jsonl` file. Tail it during a run to see the
ledger build up across scenarios.
