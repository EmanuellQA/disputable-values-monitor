import os
from slack_sdk.webhook import WebhookClient
from dotenv import load_dotenv
from fetch_disputables.utils import get_logger

from fetch_disputables.data import NewReport
from fetch_disputables.utils import NotificationSources, EnvironmentAlerts

load_dotenv()

logger = get_logger(__name__)

class Slack:
    def __init__(self, all_values: bool) -> None:
        self.high_webhook = WebhookClient(os.getenv('SLACK_WEBHOOK_HIGH'))
        self.mid_webhook = WebhookClient(os.getenv('SLACK_WEBHOOK_MID'))
        self.low_webhook = WebhookClient(os.getenv('SLACK_WEBHOOK_LOW'))
        self.all_values = all_values

    def _map_notification_source_to_environment_alert(self, notification_source: NotificationSources) -> str:
        notification_source_to_alert = {
            NotificationSources.NEW_DISPUTE_AGAINST_REPORTER: 'DISPUTE_AGAINST_REPORTER',
            NotificationSources.AUTO_DISPUTER_BEGAN_A_DISPUTE: 'BEGAN_DISPUTE',
            NotificationSources.REMOVE_REPORT: 'REMOVE_REPORT',
            NotificationSources.ALL_REPORTERS_STOP_REPORTING: 'ALL_REPORTERS_STOP',
            NotificationSources.NEW_REPORT: 'DISPUTABLE_REPORT',
            NotificationSources.REPORTER_STOP_REPORTING: 'REPORTER_STOP',
            NotificationSources.REPORTER_BALANCE_THRESHOLD: 'REPORTER_BALANCE',
            NotificationSources.DISPUTER_BALANCE_THRESHOLD: 'DISPUTER_BALANCE'
        }
        return notification_source_to_alert[notification_source]

    def _select_webhook(self, notification_source: NotificationSources):
        high_alerts = EnvironmentAlerts.get_high_alerts()
        mid_alerts = EnvironmentAlerts.get_mid_alerts()
        low_alerts = EnvironmentAlerts.get_low_alerts()

        alert = self._map_notification_source_to_environment_alert(notification_source)

        if alert in high_alerts: return self.high_webhook
        if alert in mid_alerts: return self.mid_webhook
        if alert in low_alerts: return self.low_webhook

        logger.error(f"""
            Invalid environment alerts configuration:
            Defaults:
            - HIGH_ALERTS: {EnvironmentAlerts.HIGH_DEFAULT}
            - MID_ALERTS: {EnvironmentAlerts.MID_DEFAULT}
            - LOW_ALERTS: {EnvironmentAlerts.LOW_DEFAULT}
            Configured:
            - HIGH_ALERTS: {high_alerts}
            - MID_ALERTS: {mid_alerts}
            - LOW_ALERTS: {low_alerts}
            Notification Source: {notification_source}
            Notification source mapped to environment alert: {alert}
            Error: '{alert}' is not in '{EnvironmentAlerts.get_all_alerts()}'
        """)
        raise Exception(f"Invalid environment alerts: {alert} not in {EnvironmentAlerts.get_all_alerts()}")

    def send_message(
        self, subject: str, msg: str, new_report: NewReport = None, notification_source: NotificationSources = None
    ):
        if new_report and not self.all_values and not new_report.disputable and not new_report.removable:
            return
        
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{subject}*"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{msg}"
                }
            }
        ]

        try:
            webhook = self._select_webhook(notification_source)

            response = webhook.send(
                text="fallback",
                blocks=blocks
            )
            if response.body != "ok":
                raise Exception(f"{response.body}")
            logger.info(f"Slack message sent! response body: {response.body}")
            return response
        except Exception as e:
            logger.error(f"Failed to send slack message: {e}")
            raise e

class MockSlack():
    def send_message(
        self, subject: str, msg: str, new_report: NewReport = None, notification_source: NotificationSources = None
    ):
        logger.info("Using mock Slack client.")
        return type('obj', (object,), {'status_code': 200})