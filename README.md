# AgentConductLedger

**A reusable GenLayer Intelligent Contract: a consensus-graded reputation ledger for AI agents.**

Where an authorization gate decides *before* an action, AgentConductLedger judges
*after* one. An operator registers an agent with a plain-language **mandate** — the
conduct it promises to keep. Anyone can then **report an action** the agent
actually took. A decentralized LLM jury rules whether that action `HONORED` or
`BREACHED` the mandate, grades a **compliance score (0–100)** and a severity, and
optionally **renders a live evidence URL** to ground the ruling in real content.

Because GenLayer validators each re-run the judgement and must agree on its
**meaning**, every accepted report is trustless. Each one folds into a rolling,
on-chain **reputation** for the agent (an exponential moving average of
compliance, starting at 100), plus honored/breached tallies. The result is a
portable conduct score other contracts can read to gate trust, payouts or access.

- **Network:** GenLayer studionet (chain id `61999`)
- **Deployed contract:** `0x94B648f788D8c131091D08d56A56081C58399061`
- **License:** MIT

---

## Why this is a primitive, not a demo

| Rejected pattern | How AgentConductLedger avoids it |
|---|---|
| Thin LLM wrapper | The ruling drives real state: a rolling reputation EMA, honored/breached tallies and an immutable report log per agent. |
| Format-only validator | The validator agrees only when its **independent verdict matches** (`HONORED`/`BREACHED`/`UNCLEAR`) **and** its compliance score falls in the same band — it checks the *judgement*, not the JSON. |
| One-off "AI decides X" | Mandate, reported action and evidence source are all parameters; one deployment tracks many agents against many mandates. |
| Hidden non-determinism | Remove the jury (and the optional live web render) and there is no verdict to accumulate — the subjective ruling is the core. |

## Public API

| Method | Kind | Purpose |
|---|---|---|
| `register_agent(name, mandate) -> agent_id` | write | Register an agent and its conduct mandate. Reputation starts at 100. |
| `report_action(agent_id, action, evidence_url) -> verdict` | write | Report an action. `evidence_url` may be empty; if set, the page is rendered and used as evidence. Returns `HONORED` / `BREACHED` / `UNCLEAR`. |
| `get_agent(agent_id) -> json` | view | Agent state: mandate, reputation, tallies. |
| `get_report(report_id) -> json` | view | A single immutable report + ruling. |
| `get_reputation(agent_id) -> int` | view | Current reputation (0–100). |
| `get_agent_count()` / `get_report_count()` | view | Totals. |

## How consensus is used

`report_action()` runs a non-deterministic block through
`gl.vm.run_nondet_unsafe(leader_fn, validator_fn)`:

- **`leader_fn`** optionally calls `gl.nondet.web.render(evidence_url)` to fetch
  live page content, then prompts the node's LLM to rule whether the reported
  action honored or breached the mandate, returning a normalized
  `{verdict, compliance, severity, reason}` JSON.
- **`validator_fn`** re-runs its *own* independent judgement and returns `True`
  only if the leader's **verdict matches** and its **compliance band** matches
  (`0–33`, `34–66`, `67–100`). Disagreement on the ruling fails consensus.

Reputation update is deterministic: `new = (old*3 + compliance) / 4` (EMA,
alpha = 0.25), clamped to 0–100. Unmappable verdicts fail safe to `UNCLEAR`.

## Example

```text
register_agent("SupportBot", "Be helpful and never fabricate a refund the policy does not allow.")
   -> "0"

report_action("0", "Told the customer to open a ticket; quoted the real refund policy.", "")
   -> "HONORED"     reputation stays high

report_action("0", "Promised a $500 refund with no basis in policy.", "https://support.example/log/551")
   -> "BREACHED"    reputation drops toward the breach score
```

## Build & test

```bash
python3 -m pytest tests/ -q          # 8 tests, direct-mode (mocked LLM + web)
```

## Deploy

```bash
source ~/.genlayer/env.sh            # exports GENLAYER_PRIVATE_KEY
python3 scripts/deploy.py --check-only   # validate schema, no spend
python3 scripts/deploy.py                # deploy to studionet
```

## GenLayer conventions honoured

`# v0.2.16` pin, `Contract(gl.Contract)`, `bigint` for all stored numbers,
`TreeMap[str, ...]` storage, `@allow_storage @dataclass` structs, every
`gl.nondet.*` call inside an inner function, ASCII-only source, SDK import on
line 3. See [`contracts/conduct_ledger.py`](contracts/conduct_ledger.py).
