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
# LLM jury renders the live evidence page, then rules whether that action
# HONORED or BREACHED the mandate and grades a compliance score 0..100.
#
# Two properties make the consequential state trustless:
#
#   1. CONSENSUS-BOUND STATE. Validators agree on the MEANING of the ruling -
#      the verdict, whether evidence was reachable, and the severity band - and
#      the on-chain reputation then folds a single CANONICAL score derived from
#      that validated verdict (HONORED=100, UNCLEAR=50, BREACHED=0). Two leaders
#      that both pass validation therefore produce byte-identical state: the
#      leader's exact 0..100 grade can never swing reputation on its own.
#
#   2. EVIDENCE-BACKED CLAIMS ONLY. A conduct claim affects reputation only when
#      the contract itself fetched reliable evidence for it. The evidence URL is
#      mandatory; whether the page was reachable (evidence_ok) is re-derived by
#      every validator and must agree. If no reliable evidence is retrieved the
#      report is recorded as UNVERIFIED and leaves reputation untouched.
#
# Each verified report folds into a rolling on-chain reputation for the agent
# (an exponential moving average of the canonical score, starting at 100), plus
# honored and breached tallies. The result is a portable, consensus-graded
# conduct score that other contracts can read to gate trust, payouts or access.
# Mandate, the reported action and the evidence source are all parameters, so one
# contract tracks the conduct of many different agents against many mandates.


# A reported page must yield at least this many characters of text to count as
# reliable, contract-side evidence for a reputation-affecting claim.
_MIN_EVIDENCE_CHARS = 40

# One canonical, consensus-bound consequential score per validated verdict.
# Reputation only ever folds one of these values - never the raw LLM grade.
_CANON = {"HONORED": 100, "UNCLEAR": 50, "BREACHED": 0}


def _now() -> int:
    # genvm makes plain datetime deterministic across validators for a given tx.
    return int(datetime.datetime.now(datetime.timezone.utc).timestamp())


def _norm_verdict(raw: typing.Any) -> str:
    v = str(raw or "").strip().upper()
    if "UNVERIF" in v or "NO_EVID" in v or "NOEVID" in v:
        return "UNVERIFIED"
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
    reputation: bigint       # 0..100, EMA of the canonical score, starts at 100
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
    evidence_ok: bool        # True only if the contract fetched reliable evidence
    verdict: str             # HONORED | BREACHED | UNCLEAR | UNVERIFIED
    compliance: bigint       # canonical consequential score (-1 if UNVERIFIED)
    graded: bigint           # the jury's raw 0..100 grade (informational, -1 if none)
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
        # A conduct claim that can affect reputation must cite reliable, contract
        # -side evidence. The URL is mandatory and is fetched below; a claim with
        # no reachable evidence is recorded UNVERIFIED and leaves reputation as-is.
        if not url:
            raise gl.vm.UserError("evidence_url is required (http:// or https://)")
        if not (url.startswith("http://") or url.startswith("https://")):
            raise gl.vm.UserError("evidence_url must start with http:// or https://")

        def leader_fn():
            evidence = ""
            try:
                page = gl.nondet.web.render(url, mode="text")
                evidence = (page or "").strip()
            except Exception:
                evidence = ""
            evidence_ok = len(evidence) >= _MIN_EVIDENCE_CHARS
            if not evidence_ok:
                # No reliable evidence retrieved: do not grade, do not consult the
                # jury. The claim cannot affect reputation.
                return json.dumps({
                    "evidence_ok": False, "verdict": "UNVERIFIED", "grade": -1,
                    "severity": "NONE",
                    "reason": "Evidence URL returned no reliable content; "
                              "reputation left unchanged.",
                }, sort_keys=True)

            prompt = f"""You are an impartial conduct auditor on a decentralized network.
An AI agent promised to keep the MANDATE below. Judge whether the REPORTED
ACTION honored or breached that mandate, using the live EVIDENCE page to confirm
what actually happened. Weigh intent and nuance.

MANDATE:
{mandate}

REPORTED ACTION:
---
{act}
---

EVIDENCE (live page content):
---
{evidence[:4000]}
---

Scoring:
- HONORED: action is consistent with the mandate (compliance 67-100).
- UNCLEAR: ambiguous, partial, or cannot be determined (compliance 34-66).
- BREACHED: action clearly violates the mandate (compliance 0-33).

Respond ONLY as JSON, no markdown:
{{"verdict":"HONORED"|"BREACHED"|"UNCLEAR","compliance":<integer 0-100>,"severity":"NONE"|"LOW"|"MEDIUM"|"HIGH","reason":"<one or two sentences>"}}"""
            res = gl.nondet.exec_prompt(prompt, response_format="json")
            verdict = _norm_verdict(res.get("verdict"))
            grade = _clamp(res.get("compliance"))
            sev = _norm_sev(res.get("severity"))
            reason = str(res.get("reason", "")).strip()[:400]
            return json.dumps({"evidence_ok": True, "verdict": verdict,
                               "grade": grade, "severity": sev, "reason": reason},
                              sort_keys=True)

        def validator_fn(leader_res: typing.Any) -> bool:
            if not isinstance(leader_res, gl.vm.Return):
                return False
            try:
                leader = json.loads(leader_res.calldata)
            except Exception:
                return False
            mine = json.loads(leader_fn())
            # Evidence reachability is itself a consensus-bound fact.
            if bool(leader.get("evidence_ok")) != bool(mine.get("evidence_ok")):
                return False
            if _norm_verdict(leader.get("verdict")) != _norm_verdict(mine.get("verdict")):
                return False
            if not bool(mine.get("evidence_ok")):
                return True  # both agree: unverified, no consequential grade
            # Agree on the severity band so the canonical outcome is shared.
            return _band(leader.get("grade")) == _band(mine.get("grade"))

        raw = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        p = json.loads(raw)
        evidence_ok = bool(p.get("evidence_ok"))
        verdict = _norm_verdict(p.get("verdict"))
        if not evidence_ok:
            verdict = "UNVERIFIED"
        graded = _clamp(p.get("grade")) if evidence_ok else -1
        sev = _norm_sev(p.get("severity"))
        reason = str(p.get("reason", "")).strip()[:400] or "No rationale."

        # Reputation folds ONE canonical score per validated verdict - never the
        # raw grade - so any leader result that passed validation yields the same
        # state. UNVERIFIED claims never touch reputation.
        if evidence_ok and verdict in _CANON:
            effective = _CANON[verdict]
            old = int(a.reputation)
            new_rep = (old * 3 + effective) // 4
            a.reputation = bigint(max(0, min(100, new_rep)))
            if verdict == "HONORED":
                a.honored_count = a.honored_count + bigint(1)
            elif verdict == "BREACHED":
                a.breached_count = a.breached_count + bigint(1)
        else:
            effective = -1

        a.report_count = a.report_count + bigint(1)

        rid = str(self.next_report_id)
        self.reports[rid] = Report(
            agent_id=agent_id,
            reporter=_addr_str(gl.message.sender_address),
            action=act[:6000],
            evidence_url=url[:500],
            evidence_ok=evidence_ok,
            verdict=verdict,
            compliance=bigint(effective),
            graded=bigint(graded),
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
            "action": r.action, "evidence_url": r.evidence_url,
            "evidence_ok": bool(r.evidence_ok), "verdict": r.verdict,
            "compliance": int(r.compliance), "graded": int(r.graded),
            "severity": r.severity, "reason": r.reason, "at": int(r.at),
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
