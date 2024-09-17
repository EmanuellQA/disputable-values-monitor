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

from fetch_disputables.utils import get_logger
from fetch_disputables.utils import NotificationSources, EnvironmentAlerts

from dotenv import load_dotenv

load_dotenv()

logger = get_logger(__name__)

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

        response_text = '{"body":"string","num_segments":"string","direction":"inbound","from":"string","to":"string","date_updated":"string","price":"string","error_message":"string","uri":"string","account_sid":"stringstringstringstringstringstri","num_media":"string","status":"queued","messaging_service_sid":"stringstringstringstringstringstri","sid":"stringstringstringstringstringstri","date_sent":"string","date_created":"string","error_code":0,"price_unit":"string","api_version":"string","subresource_uris":{},"tags":"null"}'
        return Response(
            int("201"),
            response_text
        )

def _map_notification_source_to_environment_alert(notification_source: NotificationSources) -> str:
        notification_source_to_alert = {
            NotificationSources.NEW_DISPUTE_AGAINST_REPORTER: 'DISPUTE_AGAINST_REPORTER',
            NotificationSources.AUTO_DISPUTER_BEGAN_A_DISPUTE: 'BEGAN_DISPUTE',
            NotificationSources.REMOVE_REPORT: 'REMOVE_REPORT',
            NotificationSources.ALL_REPORTERS_STOP_REPORTING: 'ALL_REPORTERS_STOP',
            NotificationSources.NEW_REPORT: 'DISPUTABLE_REPORT',
            NotificationSources.REPORTER_STOP_REPORTING: 'REPORTER_STOP',
            NotificationSources.REPORTER_BALANCE_THRESHOLD: 'REPORTER_BALANCE',
            NotificationSources.DISPUTER_BALANCE_THRESHOLD: 'DISPUTER_BALANCE',
            NotificationSources.TRANSACTION_REVERTED: 'TRANSACTION_REVERTED'
        }
        return notification_source_to_alert[notification_source]


def generic_alert(recipients: List[str], from_number: str, msg: str, notification_source: NotificationSources) -> Union[None, str]:
    """Send a text message to the given recipients."""

    env_alert = _map_notification_source_to_environment_alert(notification_source)
    critical_alerts = EnvironmentAlerts.get_critical_alerts()
    if env_alert not in critical_alerts:
        return f"{env_alert} not in critical alerts"
    send_text_msg(get_twilio_client(), recipients, from_number, msg)


def get_twilio_info() -> Tuple[Optional[str], Optional[List[str]]]:
    """Read the Twilio from number, client and phone numbers from the environment."""
    twilio_from = os.environ.get("TWILIO_FROM")
    phone_numbers = os.environ.get("ALERT_RECIPIENTS")
    return twilio_from, phone_numbers.split(",") if phone_numbers is not None else None


def dispute_alert(msg: str, recipients: List[str], from_number: str, notification_source: NotificationSources) -> Union[None, str]:
    """send an alert that the dispute was successful to the user"""
    env_alert = _map_notification_source_to_environment_alert(notification_source)
    critical_alerts = EnvironmentAlerts.get_critical_alerts()
    if env_alert not in critical_alerts:
        return f"{env_alert} not in critical alerts"

    twilio_client = get_twilio_client()
    send_text_msg(twilio_client, recipients, from_number, msg)

    return


def alert(all_values: bool, new_report: NewReport, recipients: List[str], from_number: str, notification_source: NotificationSources) -> Union[None, str]:
    """Send an alert to the user based on the new report."""

    env_alert = _map_notification_source_to_environment_alert(notification_source)
    critical_alerts = EnvironmentAlerts.get_critical_alerts()
    if env_alert not in critical_alerts:
        return f"{env_alert} not in critical alerts"

    twilio_client = get_twilio_client()

    if new_report.query_type in ALWAYS_ALERT_QUERY_TYPES:
        msg = generate_alert_msg(False, new_report.link)
        send_text_msg(twilio_client, recipients, from_number, msg)

        return

    # Account for unsupported queryIDs
    if new_report.disputable is not None or new_report.removable is not None:
        if new_report.disputable or new_report.removable:
            msg = generate_alert_msg(True, new_report.link, new_report.removable)

    # If user wants ALL NewReports
    if all_values:
        msg = generate_alert_msg(False, new_report.link)
        send_text_msg(twilio_client, recipients, from_number, msg)

    else:
        if new_report.disputable or new_report.removable:
            send_text_msg(twilio_client, recipients, from_number, msg)


def generate_alert_msg(disputable: bool, link: str, removable: bool = False) -> str:
    """Generate an alert message string that
    includes a link to a relevant expolorer."""

    if disputable:
        if removable:
            return f"\n!!REMOVABLE VALUE!!\n{link}"
        return f"\n!!DISPUTABLE VALUE!!\n{link}"
    else:
        return f"\n!!NEW VALUE!!\n{link}"


def get_twilio_client() -> Client:
    """Get a Twilio client."""
    if os.environ.get("MOCK_TWILIO", "true") == "true":
        print("Using Twilio MockClient on port 4010")
        return Client(
            "AC33333333333333333333333333333333",
            "33333333333333333333333333333333",
            http_client=MockClient()
        )
    return Client(os.environ.get("TWILIO_ACCOUNT_SID"), os.environ.get("TWILIO_AUTH_TOKEN"))


def send_text_msg(client: Client, recipients: list[str], from_number: str, msg: str) -> None:
    """Send a text message to the recipients."""
    for num in recipients:
        logger.info(f"Sending SMS to {num}")
        try:
            client.messages.create(
                to=num,
                from_=from_number,
                body=msg,
            )
            logger.info(f"SMS sent to {num} successfully")
        except Exception as e:
            logger.error(f"Error sending SMS to {num}: {e}")


async def handle_notification_service(
    subject: str,
    msg: str,
    notification_service: Union[List[str], None],
    sms_message_function,
    ses: Union[Ses, None],
    slack: Union[Slack, None],
    new_report: NewReport = None,
    team_ses: Union[Ses, None] = None,
    notification_service_results: Union[dict, None] = None,
    notification_source: Union[NotificationSources, None] = None,
) -> List[str]:
    if team_ses != None and "email" in notification_service:
        logger.info(f"Sending team email - {notification_source}")
        try:
            notification_service_results[notification_source]["team_email"] = team_ses.send_email(subject=subject, msg=msg)
            notification_service_results[notification_source]["error"]["team_email"] = None
            logger.info("Team email sent")
        except Exception as e:
            notification_service_results[notification_source]["error"]["team_email"] = e
            logger.error(f"Error sending team email: {e}")

    if "sms" in notification_service:
        logger.info(f"Sending SMS message - {notification_source}")
        try:
            sms_response = sms_message_function(notification_source)
            if sms_response == None:
                sms_response = f"SMS message sent - {notification_source}"
                notification_service_results[notification_source]["error"]["sms"] = None
            elif isinstance(sms_response, str):
                sms_response = f"SMS message not sent - {sms_response}"
                notification_service_results[notification_source]["error"]["sms"] = sms_response
            notification_service_results[notification_source]["sms"] = sms_response
            logger.info(sms_response)
        except Exception as e:
            notification_service_results[notification_source]["error"]["sms"] = e
            logger.error(f"Error sending SMS message: {e}")

    if "email" in notification_service:
        logger.info(f"Sending email - {notification_source}")
        try:
            email_response = ses.send_email(subject=subject, msg=msg, new_report=new_report)
            notification_service_results[notification_source]["email"] = email_response
            notification_service_results[notification_source]["error"]["email"] = None
            if email_response != None:
                logger.info("Email sent")
        except Exception as e:
            notification_service_results[notification_source]["error"]["email"] = e
            logger.error(f"Error sending email: {e}")

    if "slack" in notification_service:
        logger.info(f"Sending slack message - {notification_source}")
        try:
            slack_response = slack.send_message(
                subject=subject, msg=msg, new_report=new_report, notification_source=notification_source
            )
            notification_service_results[notification_source]["slack"] = slack_response
            notification_service_results[notification_source]["error"]["slack"] = None
            if slack_response != None:
                logger.info("Slack message sent")
        except Exception as e:
            notification_service_results[notification_source]["error"]["slack"] = e
            logger.error(f"Error sending slack message: {e}")
