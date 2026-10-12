# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *

import json
import typing
import datetime
from dataclasses import dataclass

# AgentConductLedger - a reusable GenLayer reputation primitive for AI agents.
#
# Where a gate decides BEFORE an action, this primitive judges AFTER one. An
# operator registers an agent with a plain-language "mandate" (the conduct the
# agent promises to keep). Anyone can then report an action the agent actually
# took via report_action(agent_id, action_text, evidence_url). A decentralized
# LLM jury rules whether that action HONORED or BREACHED the mandate and grades
# a compliance score 0..100 with a severity. If an evidence URL is supplied, the
# jury also renders the live page and grounds its ruling in that content.
#
# Consensus is reached on the MEANING of the ruling: a validator re-runs its own
# independent judgement and agrees only if it lands on the SAME verdict and a
# comparable compliance band - never on JSON shape.
#
# Each accepted report folds into a rolling on-chain reputation for the agent
# (an exponential moving average of compliance, starting at 100), plus honored
# and breached tallies. The result is a portable, consensus-graded conduct score
# that other contracts can read to gate trust, payouts or access. Mandate, the
# reported action and the evidence source are all parameters, so one contract
# tracks the conduct of many different agents against many different mandates.


def _now() -> int:
    # genvm makes plain datetime deterministic across validators for a given tx.
    return int(datetime.datetime.now(datetime.timezone.utc).timestamp())


def _norm_verdict(raw: typing.Any) -> str:
    v = str(raw or "").strip().upper()
    if "BREACH" in v or "VIOLAT" in v or "BROKE" in v or "FAIL" in v:
        return "BREACHED"
    if "UNCLEAR" in v or "UNSURE" in v or "PARTIAL" in v or "MIXED" in v:
        return "UNCLEAR"
    if "HONOR" in v or "HONOUR" in v or "KEPT" in v or "COMPL" in v or v == "OK":
        return "HONORED"
    return "UNCLEAR"


def _norm_sev(raw: typing.Any) -> str:
    v = str(raw or "").strip().upper()
    if "HIGH" in v or "SEVERE" in v or "CRIT" in v:
        return "HIGH"
    if "MED" in v or "MODER" in v:
        return "MEDIUM"
    if "LOW" in v or "MINOR" in v:
        return "LOW"
    return "NONE"


def _clamp(raw: typing.Any) -> int:
    try:
        c = int(raw)
    except Exception:
        c = 0
    return max(0, min(100, c))


def _band(raw: typing.Any) -> int:
    c = _clamp(raw)
    return 0 if c < 34 else (1 if c < 67 else 2)


@allow_storage
@dataclass
class Agent:
    owner: str
    name: str
    mandate: str
    reputation: bigint       # 0..100, EMA of compliance, starts at 100
    honored_count: bigint
    breached_count: bigint
    report_count: bigint


@allow_storage
@dataclass
class Report:
    agent_id: str
    reporter: str
    action: str
    evidence_url: str
    verdict: str             # HONORED | BREACHED | UNCLEAR
    compliance: bigint       # 0..100
    severity: str            # NONE | LOW | MEDIUM | HIGH
    reason: str
    at: bigint


class Contract(gl.Contract):
    agents: TreeMap[str, Agent]
    reports: TreeMap[str, Report]
    next_agent_id: bigint
    next_report_id: bigint

    def __init__(self):
        self.next_agent_id = bigint(0)
        self.next_report_id = bigint(0)

    # ------------------------------------------------------------------ writes

    @gl.public.write
    def register_agent(self, name: str, mandate: str) -> str:
        if not name or not name.strip():
            raise gl.vm.UserError("name must not be empty")
        if not mandate or not mandate.strip():
            raise gl.vm.UserError("mandate must not be empty")
        if len(mandate) > 4000:
            raise gl.vm.UserError("mandate too long (max 4000 chars)")

        aid = str(self.next_agent_id)
        self.agents[aid] = Agent(
            owner=_addr_str(gl.message.sender_address),
            name=name.strip()[:120],
            mandate=mandate.strip(),
            reputation=bigint(100),
            honored_count=bigint(0),
            breached_count=bigint(0),
            report_count=bigint(0),
        )
        self.next_agent_id = self.next_agent_id + bigint(1)
        return aid

    @gl.public.write
    def report_action(self, agent_id: str, action: str, evidence_url: str) -> str:
        if agent_id not in self.agents:
            raise gl.vm.UserError("agent not found")
        if not action or not action.strip():
            raise gl.vm.UserError("action must not be empty")
        if len(action) > 6000:
            raise gl.vm.UserError("action too long (max 6000 chars)")

        a = self.agents[agent_id]
        mandate = a.mandate
        act = action.strip()
        url = (evidence_url or "").strip()
        if url and not (url.startswith("http://") or url.startswith("https://")):
            raise gl.vm.UserError("evidence_url must start with http:// or https://")

        def leader_fn():
            evidence = ""
            if url:
                try:
                    page = gl.nondet.web.render(url, mode="text")
                    evidence = (page or "")[:4000]
                except Exception:
                    evidence = ""
            evidence_block = evidence if evidence else "(no evidence page provided or page unreachable)"
            prompt = f"""You are an impartial conduct auditor on a decentralized network.
An AI agent promised to keep the MANDATE below. Judge whether the REPORTED
ACTION honored or breached that mandate. Weigh intent and nuance. Use the
EVIDENCE only to confirm what actually happened; if it is empty, judge the
reported action on its face.

MANDATE:
{mandate}

REPORTED ACTION:
---
{act}
---

EVIDENCE (live page content, may be empty):
---
{evidence_block}
---

Scoring:
- HONORED: action is consistent with the mandate (compliance 67-100).
- UNCLEAR: ambiguous, partial, or cannot be determined (compliance 34-66).
- BREACHED: action clearly violates the mandate (compliance 0-33).

Respond ONLY as JSON, no markdown:
{{"verdict":"HONORED"|"BREACHED"|"UNCLEAR","compliance":<integer 0-100>,"severity":"NONE"|"LOW"|"MEDIUM"|"HIGH","reason":"<one or two sentences>"}}"""
            res = gl.nondet.exec_prompt(prompt, response_format="json")
            verdict = _norm_verdict(res.get("verdict"))
            comp = _clamp(res.get("compliance"))
            sev = _norm_sev(res.get("severity"))
            reason = str(res.get("reason", "")).strip()[:400]
            return json.dumps({"verdict": verdict, "compliance": comp,
                               "severity": sev, "reason": reason}, sort_keys=True)

        def validator_fn(leader_res: typing.Any) -> bool:
            if not isinstance(leader_res, gl.vm.Return):
                return False
            try:
                leader = json.loads(leader_res.calldata)
            except Exception:
                return False
            mine = json.loads(leader_fn())
            if _norm_verdict(leader.get("verdict")) != _norm_verdict(mine.get("verdict")):
                return False
            return _band(leader.get("compliance")) == _band(mine.get("compliance"))

        raw = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        p = json.loads(raw)
        verdict = _norm_verdict(p.get("verdict"))
        comp = _clamp(p.get("compliance"))
        sev = _norm_sev(p.get("severity"))
        reason = str(p.get("reason", "")).strip()[:400] or "No rationale."

        # Fold compliance into a rolling reputation (EMA, alpha = 0.25).
        old = int(a.reputation)
        new_rep = (old * 3 + comp) // 4
        a.reputation = bigint(max(0, min(100, new_rep)))
        if verdict == "HONORED":
            a.honored_count = a.honored_count + bigint(1)
        elif verdict == "BREACHED":
            a.breached_count = a.breached_count + bigint(1)
        a.report_count = a.report_count + bigint(1)

        rid = str(self.next_report_id)
        self.reports[rid] = Report(
            agent_id=agent_id,
            reporter=_addr_str(gl.message.sender_address),
            action=act[:6000],
            evidence_url=url[:500],
            verdict=verdict,
            compliance=bigint(comp),
            severity=sev,
            reason=reason,
            at=bigint(_now()),
        )
        self.next_report_id = self.next_report_id + bigint(1)
        return verdict

    # ------------------------------------------------------------------- views

    @gl.public.view
    def get_agent(self, agent_id: str) -> str:
        if agent_id not in self.agents:
            raise gl.vm.UserError("agent not found")
        a = self.agents[agent_id]
        return json.dumps({
            "id": agent_id, "owner": a.owner, "name": a.name, "mandate": a.mandate,
            "reputation": int(a.reputation), "honored_count": int(a.honored_count),
            "breached_count": int(a.breached_count), "report_count": int(a.report_count),
        })

    @gl.public.view
    def get_report(self, report_id: str) -> str:
        if report_id not in self.reports:
            raise gl.vm.UserError("report not found")
        r = self.reports[report_id]
        return json.dumps({
            "id": report_id, "agent_id": r.agent_id, "reporter": r.reporter,
            "action": r.action, "evidence_url": r.evidence_url, "verdict": r.verdict,
            "compliance": int(r.compliance), "severity": r.severity,
            "reason": r.reason, "at": int(r.at),
        })

    @gl.public.view
    def get_reputation(self, agent_id: str) -> int:
        if agent_id not in self.agents:
            raise gl.vm.UserError("agent not found")
        return int(self.agents[agent_id].reputation)

    @gl.public.view
    def get_agent_count(self) -> int:
        return int(self.next_agent_id)

    @gl.public.view
    def get_report_count(self) -> int:
        return int(self.next_report_id)


def _addr_str(a: typing.Any) -> str:
    try:
        return a.as_hex
    except Exception:
        return str(a)
