import os
from dotenv import load_dotenv
load_dotenv()

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from fetch_disputables.data import NewReport

from fetch_disputables.utils import get_logger

logger = get_logger(__name__)

class Ses:
    def __init__(self, all_values: bool) -> None:
        self.ses = boto3.client('ses', config=Config(
            region_name=os.getenv('AWS_REGION'),
        ))
        self.source = os.getenv('AWS_SOURCE_EMAIL')
        self.destination = os.getenv('AWS_DESTINATION_EMAILS', "").split(',')
        self.all_values = all_values

    def get_send_args(self, subject: str, msg: str) -> dict:
        msg = msg.replace("\n", "<br>")
        return {
            'Source': self.source,
            'Destination': {
                'ToAddresses': self.destination,
                'CcAddresses': [],
                'BccAddresses': []
            },
            'Message': {
                'Subject': {'Data': subject},
                'Body': {'Text': {'Data': msg}, 'Html': {'Data': msg}}}
        }        

    def send_email(self, subject: str, msg: str, new_report: NewReport = None) -> dict:
        if new_report and not self.all_values and not new_report.disputable:
            return
        
        send_args = self.get_send_args(subject, msg)
        try:
            response = self.ses.send_email(**send_args)
            logger.info(f"Email sent! Message ID: {response['MessageId']}")
            return response
        except ClientError:
            logger.error(
                f"Failed to send email from {self.source} to {self.destination}")

class TeamSes(Ses):
    def __init__(self) -> None:
        super().__init__(all_values=True)
        self.destination = os.getenv('AWS_TEAM_EMAILS', "").split(',')

    def send_email(self, subject: str, msg: str) -> dict:
        send_args = self.get_send_args(subject, msg)
        try:
            response = self.ses.send_email(**send_args)
            logger.info(f"Team email sent! Message ID: {response['MessageId']}")
            return response
        except ClientError:
            logger.error(
                f"Failed to send team email from {self.source} to {self.destination}")

class MockSes():
    def send_email(self, subject: str, msg: str, new_report: NewReport = None) -> dict:
        logger.info("Using mock AWS SES client.")
        return {'ResponseMetadata': {'HTTPStatusCode': 200}}