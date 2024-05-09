"""Tests for generating alert messages."""
import os
import time
from unittest import mock

from twilio.rest import Client

from fetch_disputables.alerts import alert
from fetch_disputables.alerts import generate_alert_msg
from fetch_disputables.alerts import get_twilio_client
from fetch_disputables.alerts import get_twilio_info
from fetch_disputables.data import NewReport
from fetch_disputables.utils import NotificationSources


def test_notify_typical_disputable(capsys):
    """Test a typical disputable value on ETH/USD feed"""

    def first_alert():
        print("alert sent")

    with (mock.patch("fetch_disputables.alerts.send_text_msg", side_effect=[first_alert()])):
        r = NewReport(
            "0xabc123",
            time.time(),
            1,
            "etherscan.io/abc",
            "query type",
            15.5,
            "eth",
            "usd",
            "query id",
            True,
            "status ",
        )

        alert(False, r, "", "", NotificationSources.NEW_REPORT)

        assert "alert sent" in capsys.readouterr().out


def test_generate_alert_msg():
    link = "example transaction link"
    msg = generate_alert_msg(True, link)

    assert isinstance(msg, str)
    assert "example transaction link" in msg
    assert "DISPUTABLE VALUE" in msg


def test_get_phone_numbers():
    os.environ["ALERT_RECIPIENTS"] = "+17897894567,+17897894567,+17897894567"
    os.environ["TWILIO_FROM"] = "+19035029327"
    from_num, recipients = get_twilio_info()

    assert from_num is not None
    assert isinstance(from_num, str)
    assert from_num == "+19035029327"
    assert isinstance(recipients, list)
    assert recipients == ["+17897894567", "+17897894567", "+17897894567"]


def test_get_twilio_client(check_twilio_configured):
    client = get_twilio_client()

    assert isinstance(client, Client)


def test_notify_non_disputable(capsys):
    """test sending an alert on any new value event if all_values flag is True"""

    def first_alert():
        print("alert sent")

    def second_alert():
        print("second alert sent")

    with (mock.patch("fetch_disputables.alerts.send_text_msg", side_effect=[first_alert(), second_alert()])):
        r = NewReport(
            "0xabc123",
            time.time(),
            1,
            "etherscan.io/abc",
            "query type",
            15.5,
            "fetch",
            "usd",
            "query id",
            None,
            "status ",
        )
        alert(True, r, "", "", NotificationSources.NEW_REPORT)

        assert "alert sent" in capsys.readouterr().out

        alert(False, r, "", "", NotificationSources.NEW_REPORT)

        assert "second alert sent" not in capsys.readouterr().out


def test_notify_always_alertable_value(capsys):
    """test sending an alert for a NewReport event
    if the query type is always alertable"""

    def first_alert():
        print("alert sent")

    def second_alert():
        print("second alert sent")

    with (mock.patch("fetch_disputables.alerts.send_text_msg", side_effect=[first_alert(), second_alert()])):
        r = NewReport(
            "0xabc123",
            time.time(),
            1,
            "etherscan.io/abc",
            "FetchOracleAddress",
            "0xabcNewFetchAddress",
            None,
            None,
            "query id",
            None,
            "status ",
        )
        alert(True, r, "", "", NotificationSources.NEW_REPORT)

        assert "alert sent" in capsys.readouterr().out

        alert(False, r, "", "", NotificationSources.NEW_REPORT)

        assert "second alert sent" not in capsys.readouterr().out
