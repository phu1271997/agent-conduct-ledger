import json
import pytest
from unittest.mock import patch

# A page long enough to count as reliable, contract-side evidence.
EVIDENCE = "Public post: step-by-step staking guide. No ads, no fabricated claims."
URL = "https://example.com/post"


# ----------------------------------------------------------------- deterministic

def test_register_agent_starts_at_full_reputation(contract):
    aid = contract.register_agent("SupportBot", "Be helpful; never fabricate refunds.")
    assert aid == "0"
    assert int(contract.get_agent_count()) == 1
    a = json.loads(contract.get_agent(aid))
    assert a["name"] == "SupportBot"
    assert a["reputation"] == 100
    assert a["report_count"] == 0
    assert int(contract.get_reputation(aid)) == 100


def test_register_rejects_empty_mandate(contract):
    with pytest.raises(Exception):
        contract.register_agent("Bot", "   ")


def test_report_unknown_agent(contract):
    with pytest.raises(Exception):
        contract.report_action("999", "did something", URL)


def test_report_rejects_bad_evidence_url(contract):
    aid = contract.register_agent("Bot", "Stay on policy.")
    with pytest.raises(Exception):
        contract.report_action(aid, "an action", "ftp://not-http")


def test_report_requires_evidence_url(contract):
    # A reputation-affecting claim must cite reliable evidence - empty is rejected.
    aid = contract.register_agent("Bot", "Stay on policy.")
    with pytest.raises(Exception):
        contract.report_action(aid, "an action", "")


# ------------------------------------------------------------------- nondet jury

@patch("genlayer.gl.nondet.web.render")
@patch("genlayer.gl.nondet.exec_prompt")
def test_report_honored_folds_canonical_score(mock_prompt, mock_render, contract):
    mock_render.return_value = EVIDENCE
    # Raw grade is 70, but reputation must fold the CANONICAL HONORED score (100),
    # not the raw grade - so a high reputation cannot be dragged down by a leader
    # picking a low-but-still-honored number.
    mock_prompt.return_value = {
        "verdict": "HONORED", "compliance": 70, "severity": "NONE",
        "reason": "Answer was accurate and on-policy.",
    }
    aid = contract.register_agent("SupportBot", "Never fabricate refunds.")
    verdict = contract.report_action(aid, "Told the user to open a ticket.", URL)
    assert verdict == "HONORED"
    a = json.loads(contract.get_agent(aid))
    assert a["honored_count"] == 1
    assert a["breached_count"] == 0
    # EMA (100*3 + canonical 100)/4 == 100, regardless of the raw grade 70.
    assert a["reputation"] == 100
    r = json.loads(contract.get_report("0"))
    assert r["compliance"] == 100   # canonical, consensus-bound
    assert r["graded"] == 70        # raw grade kept only for transparency
    assert r["evidence_ok"] is True


@patch("genlayer.gl.nondet.web.render")
@patch("genlayer.gl.nondet.exec_prompt")
def test_report_breach_drops_reputation_by_canonical(mock_prompt, mock_render, contract):
    mock_render.return_value = EVIDENCE
    # Raw grade 30 (band 0) but canonical BREACHED score is 0.
    mock_prompt.return_value = {
        "verdict": "BREACHED", "compliance": 30, "severity": "HIGH",
        "reason": "Agent invented a refund it was not allowed to issue.",
    }
    aid = contract.register_agent("SupportBot", "Never fabricate refunds.")
    verdict = contract.report_action(aid, "Promised a $500 refund with no basis.", URL)
    assert verdict == "BREACHED"
    a = json.loads(contract.get_agent(aid))
    assert a["breached_count"] == 1
    # EMA (100*3 + canonical 0)/4 == 75, independent of the raw grade 30.
    assert a["reputation"] == 75


@patch("genlayer.gl.nondet.web.render")
@patch("genlayer.gl.nondet.exec_prompt")
def test_canonical_score_is_grade_independent(mock_prompt, mock_render, contract):
    # Two breaches with DIFFERENT raw grades in the same band produce the SAME
    # reputation path - materially different leader scores cannot both pass and
    # yet move state differently.
    mock_render.return_value = EVIDENCE
    a1 = contract.register_agent("Bot1", "Stay on policy.")
    a2 = contract.register_agent("Bot2", "Stay on policy.")
    mock_prompt.return_value = {"verdict": "BREACHED", "compliance": 5, "severity": "HIGH", "reason": "x"}
    contract.report_action(a1, "bad", URL)
    mock_prompt.return_value = {"verdict": "BREACHED", "compliance": 32, "severity": "LOW", "reason": "y"}
    contract.report_action(a2, "bad", URL)
    assert json.loads(contract.get_agent(a1))["reputation"] == 75
    assert json.loads(contract.get_agent(a2))["reputation"] == 75


@patch("genlayer.gl.nondet.web.render")
@patch("genlayer.gl.nondet.exec_prompt")
def test_unreachable_evidence_leaves_reputation_untouched(mock_prompt, mock_render, contract):
    # Page returns nothing usable: the claim is UNVERIFIED and the jury is never
    # consulted. Reputation must not move.
    mock_render.return_value = ""
    aid = contract.register_agent("Bot", "Stay on policy.")
    verdict = contract.report_action(aid, "allegedly did something bad", URL)
    assert verdict == "UNVERIFIED"
    a = json.loads(contract.get_agent(aid))
    assert a["reputation"] == 100
    assert a["honored_count"] == 0
    assert a["breached_count"] == 0
    assert a["report_count"] == 1
    mock_prompt.assert_not_called()
    r = json.loads(contract.get_report("0"))
    assert r["evidence_ok"] is False
    assert r["compliance"] == -1


@patch("genlayer.gl.nondet.web.render")
@patch("genlayer.gl.nondet.exec_prompt")
def test_report_renders_the_evidence_page(mock_prompt, mock_render, contract):
    mock_render.return_value = EVIDENCE
    mock_prompt.return_value = {
        "verdict": "HONORED", "compliance": 88, "severity": "NONE", "reason": "Matches evidence.",
    }
    aid = contract.register_agent("Writer", "Only publish ad-free educational posts.")
    verdict = contract.report_action(aid, "Published a staking guide.", URL)
    assert verdict == "HONORED"
    mock_render.assert_called_once()
    r = json.loads(contract.get_report("0"))
    assert r["evidence_url"] == URL


@patch("genlayer.gl.nondet.web.render")
@patch("genlayer.gl.nondet.exec_prompt")
def test_reputation_is_a_rolling_average(mock_prompt, mock_render, contract):
    mock_render.return_value = EVIDENCE
    aid = contract.register_agent("Bot", "Stay on policy.")
    mock_prompt.return_value = {"verdict": "BREACHED", "compliance": 0, "severity": "HIGH", "reason": "x"}
    contract.report_action(aid, "bad 1", URL)   # (100*3+0)/4 = 75
    contract.report_action(aid, "bad 2", URL)   # (75*3+0)/4  = 56
    a = json.loads(contract.get_agent(aid))
    assert a["reputation"] == 56
    assert a["report_count"] == 2
    assert a["breached_count"] == 2
