# Portal submission — AgentConductLedger

- **Track:** Builder
- **Contribution Type:** Intelligent Contracts
- **Contribution Date:** 2026-10-21 (resubmission)

**Title**
AgentConductLedger - consensus-bound reputation ledger for AI agents

**Notes / Description (<= 1000 chars)**
AgentConductLedger is a reusable GenLayer primitive that scores an AI agent's conduct AFTER the fact. An operator registers an agent with a plain-language mandate; anyone reports an action via report_action(agent_id, action, evidence_url). The evidence URL is required: a decentralized LLM jury renders the live page contract-side, then rules HONORED / BREACHED / UNCLEAR. Consensus is on MEANING - each validator re-runs its own judgement and agrees only if the verdict matches, evidence-reachability matches, and compliance lands in the same band. The consequential state is fully bound: reputation folds a single CANONICAL score per validated verdict (HONORED=100, UNCLEAR=50, BREACHED=0), never the raw grade, so two results that both pass validation update state identically. A claim with no reachable evidence is recorded UNVERIFIED and never touches reputation. Reputation is a rolling EMA (starts at 100) plus honored/breached tallies, readable by other contracts. 11 passing gltest tests. Deployed + seeded on studionet.

**Evidence**
- Repo: https://github.com/phu1271997/agent-conduct-ledger
- Contract (studionet, chain 61999): `0x9f2F9763A19988Df78f3c5d735B3B651445a4Fe4`

**Taxonomy**
- Primary: Identity/Reputation
- Tag 1: Reputation Scoring
- Tag 2: Claim Attestation

---

## Reviewer feedback addressed (resubmission)

> "Validators compare only the compliance band, but the exact compliance score
> changes the on-chain reputation, so materially different state updates can both
> pass validation."

Fixed: reputation no longer folds the leader's raw 0–100 grade. Each validated
verdict maps to one canonical consequential score (`HONORED=100`, `UNCLEAR=50`,
`BREACHED=0`), so every leader result that passes validation produces identical
state. Confirmed on-chain: a report graded `18` by the jury still folded the
canonical `0`, giving reputation `75 = (100*3+0)/4`.

> "The reputation can also be updated from a reported action when no evidence is
> supplied or the page cannot be reached."

Fixed: the evidence URL is now mandatory, the page is fetched contract-side, and
reachability (`evidence_ok`) is a consensus-bound fact every validator must
agree on. If no reliable evidence is retrieved the report is recorded
`UNVERIFIED` and reputation is left untouched. Confirmed on-chain: an
unreachable URL produced `UNVERIFIED` with reputation unchanged.
