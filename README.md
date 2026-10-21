# AgentConductLedger

**A reusable GenLayer Intelligent Contract: a consensus-graded reputation ledger for AI agents.**

Where an authorization gate decides *before* an action, AgentConductLedger judges
*after* one. An operator registers an agent with a plain-language **mandate** — the
conduct it promises to keep. Anyone can then **report an action** the agent
actually took, **citing a live evidence URL**. A decentralized LLM jury
**renders that page**, rules whether the action `HONORED` or `BREACHED` the
mandate, and grades a compliance score — but reputation never folds that raw
grade.

Two properties make the consequential state trustless:

1. **Consensus-bound state.** Validators agree on the *meaning* of the ruling —
   the verdict, whether the evidence was reachable, and the severity band — and
   reputation then folds a single **canonical score** derived from that
   validated verdict (`HONORED=100`, `UNCLEAR=50`, `BREACHED=0`). Two leaders
   that both pass validation produce byte-identical state; a leader's exact
   0–100 grade can never swing reputation on its own.
2. **Evidence-backed claims only.** A claim affects reputation **only when the
   contract itself fetched reliable evidence**. The evidence URL is mandatory
   and reachability (`evidence_ok`) is re-derived by every validator and must
   agree. No reachable evidence → the report is recorded `UNVERIFIED` and
   reputation is left untouched.

Each verified report folds into a rolling, on-chain **reputation** (EMA of the
canonical score, starting at 100), plus honored/breached tallies — a portable
conduct score other contracts can read to gate trust, payouts or access.

- **Network:** GenLayer studionet (chain id `61999`)
- **Deployed contract:** `0x9f2F9763A19988Df78f3c5d735B3B651445a4Fe4`
- **License:** MIT

---

## Why this is a primitive, not a demo

| Rejected pattern | How AgentConductLedger avoids it |
|---|---|
| Thin LLM wrapper | The ruling drives real state: a rolling reputation EMA, honored/breached tallies and an immutable report log per agent. |
| Format-only validator | The validator agrees only when its **independent verdict matches** (`HONORED`/`BREACHED`/`UNCLEAR`), its **evidence-reachability matches**, and its compliance score falls in the same band — it checks the *judgement*, not the JSON. |
| State the consensus does not bind | Reputation folds a **canonical score per validated verdict**, not the leader's raw grade, so every result that passes validation updates state identically. |
| Claims with no evidence | A reputation-affecting claim must cite an evidence page the **contract itself** fetches; unreachable evidence yields `UNVERIFIED` with no reputation effect. |
| One-off "AI decides X" | Mandate, reported action and evidence source are all parameters; one deployment tracks many agents against many mandates. |
| Hidden non-determinism | Remove the jury (and the optional live web render) and there is no verdict to accumulate — the subjective ruling is the core. |

## Public API

| Method | Kind | Purpose |
|---|---|---|
| `register_agent(name, mandate) -> agent_id` | write | Register an agent and its conduct mandate. Reputation starts at 100. |
| `report_action(agent_id, action, evidence_url) -> verdict` | write | Report an action. `evidence_url` is **required** (`http(s)://`); the page is rendered contract-side and grounds the ruling. Returns `HONORED` / `BREACHED` / `UNCLEAR`, or `UNVERIFIED` when no reachable evidence was retrieved (reputation untouched). |
| `get_agent(agent_id) -> json` | view | Agent state: mandate, reputation, tallies. |
| `get_report(report_id) -> json` | view | A single immutable report + ruling. |
| `get_reputation(agent_id) -> int` | view | Current reputation (0–100). |
| `get_agent_count()` / `get_report_count()` | view | Totals. |

## How consensus is used

`report_action()` runs a non-deterministic block through
`gl.vm.run_nondet_unsafe(leader_fn, validator_fn)`:

- **`leader_fn`** calls `gl.nondet.web.render(evidence_url)` to fetch live page
  content. If the page yields no reliable text it returns `UNVERIFIED` without
  ever consulting the jury; otherwise it prompts the node's LLM to rule and
  returns a normalized `{evidence_ok, verdict, grade, severity, reason}` JSON.
- **`validator_fn`** re-runs its *own* independent judgement and returns `True`
  only if the leader's **verdict matches**, its **evidence-reachability
  (`evidence_ok`) matches**, and (when evidence is present) its **compliance
  band** matches (`0–33`, `34–66`, `67–100`). Any disagreement fails consensus.

Reputation update is deterministic and **bound to the validated verdict, not the
raw grade**: `new = (old*3 + canonical) / 4` where `canonical ∈ {HONORED:100,
UNCLEAR:50, BREACHED:0}` (EMA, alpha = 0.25), clamped to 0–100. `UNVERIFIED`
reports never change reputation. Unmappable verdicts fail safe to `UNCLEAR`.

## Example

```text
register_agent("SupportBot", "Be helpful and never fabricate a refund the policy does not allow.")
   -> "0"

report_action("0", "Told the customer to open a ticket; quoted the real refund policy.",
              "https://support.example/log/550")
   -> "HONORED"     reputation folds canonical 100 -> stays high

report_action("0", "Promised a $500 refund with no basis in policy.",
              "https://support.example/log/551")
   -> "BREACHED"    reputation folds canonical 0 -> drops

report_action("0", "Allegedly leaked data.", "https://dead.example/404")
   -> "UNVERIFIED"  page unreachable -> reputation untouched
```

## Build & test

```bash
python3 -m pytest tests/ -q          # 11 tests, direct-mode (mocked LLM + web)
```

## Deploy

```bash
source ~/.genlayer/env.sh            # exports GENLAYER_PRIVATE_KEY
python3 scripts/deploy.py --check-only   # validate schema, no spend
python3 scripts/deploy.py                # deploy to studionet
python3 scripts/seed.py 0x<address>      # register + two live reports (verify both fixes)
```

## GenLayer conventions honoured

`# v0.2.16` pin, `Contract(gl.Contract)`, `bigint` for all stored numbers,
`TreeMap[str, ...]` storage, `@allow_storage @dataclass` structs, every
`gl.nondet.*` call inside an inner function, ASCII-only source, SDK import on
line 3. See [`contracts/conduct_ledger.py`](contracts/conduct_ledger.py).
