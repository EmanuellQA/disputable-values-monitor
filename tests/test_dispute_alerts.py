"""Tests for generating dispute alert messages."""
import logging
import os
import pytest
from hexbytes import HexBytes

from fetch_disputables.alerts import get_twilio_client
from fetch_disputables.alerts import handle_notification_service
from fetch_disputables.utils import NewDispute, get_reporters, get_service_notification
from fetch_disputables.data import parse_new_dispute_event
from telliot_core.apps.telliot_config import TelliotConfig
from fetch_disputables.utils import NotificationSources

from fetch_disputables.Ses import Ses, MockSes
from fetch_disputables.Slack import Slack, MockSlack

from web3.datastructures import AttributeDict

logger = logging.getLogger(__name__)


def local_dispute_alert(msg, recipients, from_number):
    if os.getenv("MOCK_TWILIO", "true") == "true":
        logger.info("Using mock twilio client.")
    twilio_client = get_twilio_client()
    return local_send_text_msg(twilio_client, recipients, from_number, msg)


def local_send_text_msg(client, recipients, from_number, msg):
    """Send a text message to the recipients."""
    for num in recipients:
        return client.messages.create(
            to=num,
            from_=from_number,
            body=msg,
        )

@pytest.mark.asyncio
async def test_notification_services_new_dispute_against_reporter():
    new_dispute = NewDispute(
        tx_hash='0x9999999999999999999999999999999999999999999999999999999999999999',
        timestamp=16904008000,
        reporter='0x1111111111111111111111111111111111111111',
        query_id='0x83245f6a6a2f6458558a706270fbcc35ac3a81917602c1313d3bfa998dcc2d4b',
        dispute_id=100,
        initiator='0x3333333333333333333333333333333333333333',
        chain_id=943, link='https://scan.v4.testnet.pulsechain.com/tx/0x3c189dbc4ad556d5f195813f32b4f61b5787e096f04a543897474c5466ca8e2e'
    )

    reporters = [
        "0x1111111111111111111111111111111111111111",
        "0x2222222222222222222222222222222222222222"
    ]

    notification_service = get_service_notification()

    if os.getenv("MOCK_TWILIO", "true") == "true":
        notification_service.append("sms")
        from_number = "+19035029327"
        recipients = ["+17897894567"]
    else:
        from_number = os.getenv("TWILIO_FROM")
        recipients =  os.getenv("ALERT_RECIPIENTS", "").split(',')

    if os.getenv("MOCK_SES", "true") == "true":
        notification_service.append("email")

    if os.getenv("MOCK_SLACK", "true") == "true":
        notification_service.append("slack")

    notification_source = NotificationSources.NEW_DISPUTE_AGAINST_REPORTER
    notification_service_results: dict = {
        notification_source: {
            "sms": None,
            "email": None,
            "slack": None,
            "team_email": None,
            "error": {
                "sms": None,
                "email": None,
                "slack": None,
                "team_email": None,
            }
        }
    }

    if new_dispute.reporter in reporters:
        subject = f"New Dispute Event against Reporter {new_dispute.reporter} on Chain {new_dispute.chain_id}"
        msg = f"New Dispute Event:\n{new_dispute}"

        await handle_notification_service(
            subject=subject,
            msg=msg,
            notification_service=notification_service,
            sms_message_function=lambda: local_dispute_alert(
                from_number=from_number,
                recipients=recipients,
                msg=msg
            ),
            ses=MockSes() if os.getenv("MOCK_SES", "true") == "true" else Ses(all_values=False),
            slack=MockSlack() if os.getenv("MOCK_SLACK", "true") == "true" else Slack(all_values=False),
            notification_service_results=notification_service_results,
            notification_source=notification_source
        )

        for service in notification_service:
            if service == "sms":
                if os.getenv("MOCK_TWILIO", "true") == "true":
                    assert notification_service_results[notification_source]["sms"].error_code == 0 \
                    and notification_service_results[notification_source]["sms"].direction == 'inbound'
                else:
                    assert notification_service_results[notification_source]["sms"].error_code is None \
                    and notification_service_results[notification_source]["sms"].direction == 'outbound-api'
            elif service == "email":
                assert notification_service_results[notification_source]["email"]['ResponseMetadata']['HTTPStatusCode'] == 200
            elif service == "slack":
                assert notification_service_results[notification_source]["slack"].status_code == 200


def test_notification_services_new_dispute_against_non_reporter():
    new_dispute = NewDispute(
        tx_hash='0x9999999999999999999999999999999999999999999999999999999999999999',
        timestamp=16904008000,
        reporter='0x1111111111111111111111111111111111111111',
        query_id='0x83245f6a6a2f6458558a706270fbcc35ac3a81917602c1313d3bfa998dcc2d4b',
        dispute_id=100,
        initiator='0x3333333333333333333333333333333333333333',
        chain_id=943, link='https://scan.v4.testnet.pulsechain.com/tx/0x3c189dbc4ad556d5f195813f32b4f61b5787e096f04a543897474c5466ca8e2e'
    )

    reporters = ["0x2222222222222222222222222222222222222222"]

    assert new_dispute.reporter not in reporters


@pytest.mark.asyncio
async def test_parse_new_dispute_event():
    cfg = TelliotConfig()
    cfg.main.chain_id = 943

    event = AttributeDict({
        'address': '0x9Bf22Fa8C49ef7F9B9a343A39baE002C2f800802',
        'topics': [HexBytes('0xfbfeca72a80efb0d1aabf7f937aaec719fa5c81548a4ade65b40ecdec0afca4e')],
        'data': '0x000000000000000000000000000000000000000000000000000000000000000183245f6a6a2f6458558a706270fbcc35ac3a81917602c1313d3bfa998dcc2d4b00000000000000000000000000000000000000000000000000000000655792200000000000000000000000005c790a34bd1d00c2355b85001fd036dbb96dc24f0000000000000000000000005c790a34bd1d00c2355b85001fd036dbb96dc24f000000000000000000000000000000000000000000000000000000006557922a00000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000c685fa11e01ec6f0000000000000000000000000000000000000000000000000000000000000000000001',
        'blockNumber': 17437647,
        'transactionHash': HexBytes('0x3c189dbc4ad556d5f195813f32b4f61b5787e096f04a543897474c5466ca8e2e'),
        'transactionIndex': 0,
        'blockHash': HexBytes('0xe14df2cabb0bb6352581b7be7e9ce1672e81bdad51bd17a661f0c16ce9d14c33'),
        'logIndex': 7,
        'removed': False
    })

    new_dispute = await parse_new_dispute_event(cfg=cfg, log=event)

    pls_usd_spot_queryId = "0x83245f6a6a2f6458558a706270fbcc35ac3a81917602c1313d3bfa998dcc2d4b"

    assert isinstance(new_dispute, NewDispute)
    assert new_dispute.chain_id == cfg.main.chain_id
    assert new_dispute.link == f"https://scan.v4.testnet.pulsechain.com/tx/{event.transactionHash.hex()}"
    assert new_dispute.query_id == pls_usd_spot_queryId


def test_get_reporters_list():
    os.environ["REPORTERS"] = "0x1111111111111111111111111111111111111111,0x2222222222222222222222222222222222222222"
    reporters = get_reporters()

    assert reporters is not None
    assert isinstance(reporters, list)
    assert reporters == [
        "0x1111111111111111111111111111111111111111",
        "0x2222222222222222222222222222222222222222"
    ]
