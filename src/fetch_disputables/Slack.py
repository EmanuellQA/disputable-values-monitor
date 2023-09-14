import os
from slack_sdk.webhook import WebhookClient
from dotenv import load_dotenv
from fetch_disputables.utils import get_logger

load_dotenv()

logger = get_logger(__name__)

class Slack:
    def __init__(self) -> None:
        self.webhook = WebhookClient(os.getenv('SLACK_WEBHOOK_URL'))

    def send_message(self, subject: str, msg: str):
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
    def send_message(self, subject: str, msg: str):
        logger.info("Using mock Slack client.")
        return type('obj', (object,), {'status_code': 200})