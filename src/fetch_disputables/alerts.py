"""Send text messages using Twilio."""
import os
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union
import re

import click
from twilio.rest import Client
from twilio.http.http_client import TwilioHttpClient
from twilio.http.response import Response
from requests import Request, Session

from fetch_disputables import ALWAYS_ALERT_QUERY_TYPES
from fetch_disputables.data import NewReport

from fetch_disputables.Ses import Ses
from fetch_disputables.Slack import Slack

from dotenv import load_dotenv

load_dotenv()

class MockClient(TwilioHttpClient):
    def __init__(self):
        self.response = None

    def request(self, method, url, params=None, data=None, headers=None, auth=None, timeout=None,
                allow_redirects=False):
        # Here you can change the URL, headers and other request parameters
        kwargs = {
            'method': method.upper(),
            'url': re.sub(r'^https:\/\/.*?\.twilio\.com', 'http://127.0.0.1:4010', url),
            'params': params,
            'data': data,
            'headers': headers,
            'auth': auth,
        }

        session = Session()
        request = Request(**kwargs)

        prepped_request = session.prepare_request(request)
        session.proxies.update({
            'http': 'http://127.0.0.1:4010',
            'https': 'http://127.0.0.1:4010'
        })
        response = session.send(
            prepped_request,
            allow_redirects=allow_redirects,
            timeout=timeout,
        )

        return Response(int(response.status_code), response.text)

def generic_alert(recipients: List[str], from_number: str, msg: str) -> None:
    """Send a text message to the given recipients."""
    send_text_msg(get_twilio_client(), recipients, from_number, msg)


def get_twilio_info() -> Tuple[Optional[str], Optional[List[str]]]:
    """Read the Twilio from number, client and phone numbers from the environment."""
    twilio_from = os.environ.get("TWILIO_FROM")
    phone_numbers = os.environ.get("ALERT_RECIPIENTS")
    return twilio_from, phone_numbers.split(",") if phone_numbers is not None else None


def dispute_alert(msg: str, recipients: List[str], from_number: str) -> None:
    """send an alert that the dispute was successful to the user"""

    twilio_client = get_twilio_client()
    send_text_msg(twilio_client, recipients, from_number, msg)

    return


def alert(all_values: bool, new_report: NewReport, recipients: List[str], from_number: str) -> None:

    twilio_client = get_twilio_client()

    if new_report.query_type in ALWAYS_ALERT_QUERY_TYPES:
        msg = generate_alert_msg(False, new_report.link)
        send_text_msg(twilio_client, recipients, from_number, msg)

        return

    # Account for unsupported queryIDs
    if new_report.disputable is not None:
        if new_report.disputable:
            msg = generate_alert_msg(True, new_report.link)

    # If user wants ALL NewReports
    if all_values:
        msg = generate_alert_msg(False, new_report.link)
        send_text_msg(twilio_client, recipients, from_number, msg)

    else:
        if new_report.disputable:
            send_text_msg(twilio_client, recipients, from_number, msg)


def generate_alert_msg(disputable: bool, link: str) -> str:
    """Generate an alert message string that
    includes a link to a relevant expolorer."""

    if disputable:
        return f"\n❗DISPUTABLE VALUE❗\n{link}"
    else:
        return f"\n❗NEW VALUE❗\n{link}"


def get_twilio_client() -> Client:
    """Get a Twilio client."""
    if os.environ.get("MOCK_TWILIO") == "true":
        print("Using Twilio MockClient on port 4010")
        return Client(
            os.environ.get("TWILIO_ACCOUNT_SID"),
            os.environ.get("TWILIO_AUTH_TOKEN"),
            http_client=MockClient()
        )
    return Client(os.environ.get("TWILIO_ACCOUNT_SID"), os.environ.get("TWILIO_AUTH_TOKEN"))


def send_text_msg(client: Client, recipients: list[str], from_number: str, msg: str) -> None:
    """Send a text message to the recipients."""
    click.echo("Alert sent!")
    for num in recipients:
        client.messages.create(
            to=num,
            from_=from_number,
            body=msg,
        )


def handle_notification_service(
    subject: str,
    msg: str,
    notification_service: Union[List[str], None],
    sms_message_function,
    ses: Union[Ses, None],
    slack: Union[Slack, None],
) -> List[str]:
    results = {"sms": None, "email": None, "slack": None}
    if "sms" in notification_service:
        results["sms"] = sms_message_function()
    if "email" in notification_service:
        results["email"] = ses.send_email(subject=subject, msg=msg)
    if "slack" in notification_service:
        results["slack"] = slack.send_message(subject=subject, msg=msg)
    return results
