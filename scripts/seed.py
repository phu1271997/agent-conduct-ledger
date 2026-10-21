#!/usr/bin/env python3
"""Seed + verify AgentConductLedger live on studionet.

Registers one agent, then files two reports against a real, reachable evidence
page - showing (a) an evidence-backed verdict that folds the canonical score and
(b) that a report with no reachable evidence is recorded UNVERIFIED and leaves
reputation untouched.

    source ~/.genlayer/env.sh
    python3 scripts/seed.py 0x<contract-address>
"""
import json
import os
import sys

import genlayer_py as g
from genlayer_py import chains
from genlayer_py.types import TransactionStatus

# A small, stable page whose rendered text is comfortably > 40 chars.
GOOD_URL = "https://example.com/"
# A URL that renders to (effectively) nothing -> UNVERIFIED, reputation untouched.
EMPTY_URL = "http://example.com/nonexistent-" + "x" * 8


def _client(key):
    return g.create_client(chain=chains.studionet, account=g.create_account(key))


def _wait(client, tx):
    return client.wait_for_transaction_receipt(
        transaction_hash=tx, status=TransactionStatus.ACCEPTED,
        interval=5000, retries=120)


def _read(client, addr, method, args):
    return client.read_contract(address=addr, function_name=method, args=args)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python3 scripts/seed.py 0x<contract>")
        return 2
    addr = sys.argv[1]
    owner_key = os.environ["GENLAYER_PRIVATE_KEY"]
    reporter_key = os.environ.get("GENLAYER_PRIVATE_KEY_2", owner_key)

    owner = _client(owner_key)
    reporter = _client(reporter_key)

    print("Registering agent ...")
    tx = owner.write_contract(address=addr, function_name="register_agent",
                              args=["DocsBot", "Only link to real, reachable public pages."])
    _wait(owner, tx)
    aid = str(int(_read(owner, addr, "get_agent_count", [])) - 1)
    print("  agent id:", aid, "reputation:", _read(owner, addr, "get_reputation", [aid]))

    print("Report #1 - evidence-backed (reachable page) ...")
    tx = reporter.write_contract(address=addr, function_name="report_action",
                                 args=[aid, "Linked customers to the official example page.", GOOD_URL])
    _wait(reporter, tx)
    print("  agent:", _read(reporter, addr, "get_agent", [aid]))
    print("  report 0:", _read(reporter, addr, "get_report", ["0"]))

    print("Report #2 - no reachable evidence (must stay UNVERIFIED) ...")
    tx = reporter.write_contract(address=addr, function_name="report_action",
                                 args=[aid, "Allegedly linked a dead page.", EMPTY_URL])
    _wait(reporter, tx)
    print("  agent:", _read(reporter, addr, "get_agent", [aid]))
    print("  report 1:", _read(reporter, addr, "get_report", ["1"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
