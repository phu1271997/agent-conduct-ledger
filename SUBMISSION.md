# Portal submission — AgentConductLedger

- **Track:** Builder
- **Contribution Type:** Intelligent Contracts
- **Contribution Date:** 2026-10-12

**Title**
AgentConductLedger - consensus-graded reputation ledger for AI agents

**Notes / Description (<= 1000 chars)**
AgentConductLedger is a reusable GenLayer primitive that scores an AI agent's conduct AFTER the fact. An operator registers an agent with a plain-language mandate; anyone reports an action the agent took via report_action(agent_id, action, evidence_url). A decentralized LLM jury rules HONORED / BREACHED / UNCLEAR, grades compliance 0-100, and - when an evidence URL is given - renders the live page to ground the ruling. Consensus is on MEANING: each validator re-runs its own judgement and agrees only if the verdict matches and compliance lands in the same band, not on JSON shape. Each accepted report folds into a rolling on-chain reputation (EMA of compliance, starting at 100) plus honored/breached tallies, giving a portable conduct score other contracts can read to gate trust, payouts or access. Mandate, action and evidence source are parameters. 8 passing gltest tests. Deployed to studionet.

**Evidence**
- Repo: https://github.com/phu1271997/agent-conduct-ledger
- Contract (studionet, chain 61999): `0x94B648f788D8c131091D08d56A56081C58399061`

**Taxonomy**
- Primary: Identity/Reputation
- Tag 1: Reputation Scoring
- Tag 2: Claim Attestation
