"""tests for dispute logic of auto-disputer"""
import os
import time
from unittest import mock

import pytest
from chained_accounts import ChainedAccount
from telliot_core.apps.core import TelliotConfig
from telliot_core.model.endpoints import RPCEndpoint
from telliot_core.utils.response import ResponseStatus
from telliot_feeds.feeds.eth_usd_feed import eth_usd_median_feed

from fetch_disputables import EXAMPLE_NEW_REPORT_EVENT_TX_RECEIPT
from fetch_disputables.config import AutoDisputerConfig
from fetch_disputables.data import Metrics
from fetch_disputables.data import MonitoredFeed
from fetch_disputables.data import parse_new_report_event
from fetch_disputables.data import Threshold
from fetch_disputables.disputer import dispute
from fetch_disputables.disputer import get_dispute_fee
from fetch_disputables.utils import NewReport


@pytest.mark.skip
@pytest.mark.asyncio
async def test_not_meant_to_dispute(caplog, disputer_account):
    """test when dispute() is called but a dispute is not meant to be sent"""

    report = NewReport(
        "0xabc123",
        1679425719,  # this eth block does not have a fetch value on the eth/usd query id
        1337,
        "etherscan.io/",
        "SpotPrice",
        15.5,
        "eth",
        "usd",
        "0x83a7f3d48786ac2667503a61e8c415438ed2922eb86a2906e4ee66d9a2ce4992",  # eth/usd query id
        True,
        "status ",
    )

    cfg = TelliotConfig()
    disp_config = AutoDisputerConfig()

    report.query_id = "hi how are you"

    await dispute(cfg, disp_config, account=disputer_account, new_report=report)

    assert (
        "Found disputable new report on chain_id 1337 outside selected Monitored Feeds, skipping dispute" in caplog.text
    )


@pytest.mark.skip
@pytest.mark.asyncio
async def test_dispute_on_empty_block(setup, caplog: pytest.LogCaptureFixture, disputer_account: ChainedAccount):
    """
    test typical dispute with a timestamp that doesn't contain a value.
    it will revert on chain
    """

    cfg = setup
    disp_config = AutoDisputerConfig()

    report = NewReport(
        "0xabc123",
        1679425719,  # this eth block does not have a fetch value on the eth/usd query id
        1337,
        "etherscan.io/",
        "SpotPrice",
        15.5,
        "eth",
        "usd",
        "0x83245f6a6a2f6458558a706270fbcc35ac3a81917602c1313d3bfa998dcc2d4b",  # eth/usd query id
        True,
        "status ",
    )

    await dispute(cfg, disp_config, disputer_account, report)

    expected_success_logs = ["balance", "Dispute Fee", "no value exists at given timestamp"]

    for i in expected_success_logs:
        assert i in caplog.text

    # missing query id

    mock_approve_tx = (EXAMPLE_NEW_REPORT_EVENT_TX_RECEIPT[0], ResponseStatus(ok=True))
    mock_dispute_tx = (EXAMPLE_NEW_REPORT_EVENT_TX_RECEIPT[0], ResponseStatus(ok=True))

    report.query_id = ""

    with mock.patch("telliot_core.contract.contract.Contract.write", side_effect=[mock_approve_tx, mock_dispute_tx]):
        await dispute(cfg, disp_config, disputer_account, report)

    for i in expected_success_logs:
        assert i in caplog.text

    # query id is inactive
    report.query_id = "0x7af670d5ad732a520e49b33749a97d58de18c234d5b0834415fb19647e03a2cb"  # abc/usd

    with mock.patch("telliot_core.contract.contract.Contract.write", side_effect=[mock_approve_tx, mock_dispute_tx]):
        await dispute(cfg, disp_config, disputer_account, report)

    for i in expected_success_logs:
        assert i in caplog.text


@pytest.mark.skip
@pytest.mark.asyncio
async def test_dispute_on_disputable_block(setup, caplog: pytest.LogCaptureFixture, disputer_account: ChainedAccount):
    """
    test typical dispute with a timestamp that contains a value.
    it will submit to chain
    """

    cfg = setup
    disp_config = AutoDisputerConfig()

    report = NewReport(
        "0xabc123",
        1679497091,
        1337,
        "etherscan.io/",
        "SpotPrice",
        15.5,
        "eth",
        "usd",
        "0x83a7f3d48786ac2667503a61e8c415438ed2922eb86a2906e4ee66d9a2ce4992",  # eth/usd query id
        True,
        "status ",
    )

    await dispute(cfg, disp_config, disputer_account, report)

    expected_success_logs = [
        "Equality threshold selected",
        "balance",
        "Dispute Fee",
        "Approval Tx Hash:",
        "Dispute Tx Link:",
    ]

    for i in expected_success_logs:
        assert i in caplog.text

    # missing query id
    mock_approve_tx = (EXAMPLE_NEW_REPORT_EVENT_TX_RECEIPT[0], ResponseStatus(ok=True))
    mock_dispute_tx = (EXAMPLE_NEW_REPORT_EVENT_TX_RECEIPT[0], ResponseStatus(ok=True))

    report.query_id = ""

    with mock.patch("telliot_core.contract.contract.Contract.write", side_effect=[mock_approve_tx, mock_dispute_tx]):
        await dispute(cfg, disp_config, disputer_account, report)

    for i in expected_success_logs:
        assert i in caplog.text

    # query id is inactive
    report.query_id = "0x7af670d5ad732a520e49b33749a97d58de18c234d5b0834415fb19647e03a2cb"  # abc/usd

    with mock.patch("telliot_core.contract.contract.Contract.write", side_effect=[mock_approve_tx, mock_dispute_tx]):
        await dispute(cfg, disp_config, disputer_account, report)

    for i in expected_success_logs:
        assert i in caplog.text


@pytest.mark.skip
@pytest.mark.asyncio
async def test_dispute_using_sample_log(
    setup, caplog: pytest.LogCaptureFixture, fetch_usd_report_log, disputer_account: ChainedAccount
):
    """
    Send a dispute using a sample log fixture after parsing a new report event.
    The log is mocked to be disputable
    """

    cfg = setup
    disp_config = AutoDisputerConfig()

    threshold = Threshold(Metrics.Percentage, 0.50)
    monitored_feeds = [MonitoredFeed(eth_usd_median_feed, threshold)]

    mock_telliot_val = 1
    mock_approve_tx = (EXAMPLE_NEW_REPORT_EVENT_TX_RECEIPT[0], ResponseStatus(ok=True))
    mock_dispute_tx = (EXAMPLE_NEW_REPORT_EVENT_TX_RECEIPT[0], ResponseStatus(ok=True))

    for endpoint in cfg.endpoints.find(chain_id=1):
        cfg.endpoints.endpoints.remove(endpoint)

    endpoint = RPCEndpoint(1, "Goerli", "Infura", os.getenv("NODE_URL"), "etherscan.io")
    cfg.endpoints.endpoints.append(endpoint)

    with mock.patch(
        "fetch_disputables.data.general_fetch_new_datapoint", return_value=(mock_telliot_val, int(time.time()))
    ):
        new_report = await parse_new_report_event(
            cfg, eth_usd_report_log, monitored_feeds=monitored_feeds, confidence_threshold=0.1
        )

    assert new_report.disputable

    with mock.patch("telliot_core.contract.contract.Contract.write", side_effect=[mock_approve_tx, mock_dispute_tx]):
        await dispute(cfg, disp_config, disputer_account, new_report)

    expected_logs = ["balance", "Dispute Fee", "Approval Tx Hash", "revert no value exists at given timestamp"]

    for i in expected_logs:
        assert i in caplog.text


@pytest.mark.asyncio
async def test_get_dispute_fee():

    cfg = TelliotConfig()
    cfg.main.chain_id = 943
    endpoint = cfg.endpoints.find(chain_id=943)[0]
    endpoint.url = "https://rpc.v4.testnet.pulsechain.com"

    report = NewReport(
        "0xabc123",
        1679497091,
        1337,
        "scan.v4.testnet.pulsechain.com/",
        "SpotPrice",
        15.5,
        "fetch",
        "usd",
        "0x88e6984af423a49262b7d87ef9bc8746ef10def1a819961984e15372b6e1e4ad",  # eth/usd query id
        True,
        "status ",
    )

    dispute_fee = await get_dispute_fee(cfg, report)
    assert dispute_fee == int(1e19)
