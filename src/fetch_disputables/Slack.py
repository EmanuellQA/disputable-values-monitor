import os
from slack_sdk.webhook import WebhookClient
from dotenv import load_dotenv
from fetch_disputables.utils import get_logger

from fetch_disputables.data import NewReport

load_dotenv()

logger = get_logger(__name__)

class Slack:
    def __init__(self, all_values: bool) -> None:
        self.webhook = WebhookClient(os.getenv('SLACK_WEBHOOK_URL'))
        self.all_values = all_values

    def send_message(self, subject: str, msg: str, new_report: NewReport = None):
        if new_report and not self.all_values and not new_report.disputable:
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
            response = self.webhook.send(
                text="fallback",
                blocks=blocks
            )
            logger.info(f"Slack message sent! response body: {response.body}")
            return response
        except Exception as e:
            logger.error(f"Failed to send slack message: {e}")

class MockSlack():
    def send_message(self, subject: str, msg: str, new_report: NewReport = None):
        logger.info("Using mock Slack client.")
        return type('obj', (object,), {'status_code': 200})