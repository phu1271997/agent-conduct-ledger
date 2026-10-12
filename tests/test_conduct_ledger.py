import json
import pytest
from unittest.mock import patch


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
        contract.report_action("999", "did something", "")


def test_report_rejects_bad_evidence_url(contract):
    aid = contract.register_agent("Bot", "Stay on policy.")
    with pytest.raises(Exception):
        contract.report_action(aid, "an action", "ftp://not-http")


# ------------------------------------------------------------------- nondet jury

@patch("genlayer.gl.nondet.web.render")
@patch("genlayer.gl.nondet.exec_prompt")
def test_report_honored_keeps_reputation(mock_prompt, mock_render, contract):
    mock_prompt.return_value = {
        "verdict": "HONORED", "compliance": 95, "severity": "NONE",
        "reason": "Answer was accurate and on-policy.",
    }
    aid = contract.register_agent("SupportBot", "Never fabricate refunds.")
    verdict = contract.report_action(aid, "Told the user to open a ticket for a refund.", "")
    assert verdict == "HONORED"
    a = json.loads(contract.get_agent(aid))
    assert a["honored_count"] == 1
    assert a["breached_count"] == 0
    # EMA of 100 and 95 -> stays high.
    assert a["reputation"] >= 95


@patch("genlayer.gl.nondet.web.render")
@patch("genlayer.gl.nondet.exec_prompt")
def test_report_breach_drops_reputation(mock_prompt, mock_render, contract):
    mock_prompt.return_value = {
        "verdict": "BREACHED", "compliance": 10, "severity": "HIGH",
        "reason": "Agent invented a refund it was not allowed to issue.",
    }
    aid = contract.register_agent("SupportBot", "Never fabricate refunds.")
    verdict = contract.report_action(aid, "Promised the user a $500 refund with no basis.", "")
    assert verdict == "BREACHED"
    a = json.loads(contract.get_agent(aid))
    assert a["breached_count"] == 1
    # EMA (100*3 + 10)/4 = 77.
    assert a["reputation"] == 77


@patch("genlayer.gl.nondet.web.render")
@patch("genlayer.gl.nondet.exec_prompt")
def test_report_with_evidence_url_renders_page(mock_prompt, mock_render, contract):
    mock_render.return_value = "Public post: step-by-step guide to staking. No ads."
    mock_prompt.return_value = {
        "verdict": "HONORED", "compliance": 88, "severity": "NONE", "reason": "Matches evidence.",
    }
    aid = contract.register_agent("Writer", "Only publish ad-free educational posts.")
    verdict = contract.report_action(aid, "Published a staking guide.", "https://example.com/post")
    assert verdict == "HONORED"
    mock_render.assert_called_once()
    r = json.loads(contract.get_report("0"))
    assert r["evidence_url"] == "https://example.com/post"


@patch("genlayer.gl.nondet.web.render")
@patch("genlayer.gl.nondet.exec_prompt")
def test_reputation_is_a_rolling_average(mock_prompt, mock_render, contract):
    aid = contract.register_agent("Bot", "Stay on policy.")
    mock_prompt.return_value = {"verdict": "BREACHED", "compliance": 0, "severity": "HIGH", "reason": "x"}
    contract.report_action(aid, "bad 1", "")   # (100*3+0)/4 = 75
    contract.report_action(aid, "bad 2", "")   # (75*3+0)/4  = 56
    a = json.loads(contract.get_agent(aid))
    assert a["reputation"] == 56
    assert a["report_count"] == 2
    assert a["breached_count"] == 2
