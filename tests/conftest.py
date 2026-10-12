import pytest
from pathlib import Path
from gltest.direct.sdk_loader import setup_sdk_paths

CONTRACT = "contracts/conduct_ledger.py"


@pytest.fixture(autouse=True)
def init_paths():
    setup_sdk_paths(Path(CONTRACT), None)


@pytest.fixture
def contract(direct_deploy, direct_vm, accounts):
    from genlayer.py.types import Address
    direct_vm.sender = Address(accounts[0].address)
    return direct_deploy(CONTRACT)
