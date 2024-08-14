import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Union

import yaml
from dotenv import load_dotenv
from web3 import Web3

from .Ses import MockSes, Ses, TeamSes
from .Slack import MockSlack, Slack
from .utils import NotificationSources, get_logger
from .alerts import generic_alert, get_twilio_info

load_dotenv(".env")

logger = get_logger(__name__)


class ContractMonitor:
    def _read_contract_monitor_config(self):
        contract_monitor_path = (
            Path(__file__).resolve().parents[2] / "contract-monitor.yaml"
        )
        with open(contract_monitor_path, "r") as yaml_file:
            data = yaml.safe_load(yaml_file)
            start_block = data["start_block"]
            contract_addresses = data["contract_addresses"]

            self.start_block = start_block
            self.contract_addresses = contract_addresses

    def _map_network_id_env_to_rpc_url(self) -> str:
        network_id = os.getenv("NETWORK_ID", "369")
        rpc_urls = {
            "369": "https://rpc.pulsechain.com",
            "943": "https://rpc.v4.testnet.pulsechain.com",
        }
        return rpc_urls.get(network_id, "https://rpc.pulsechain.com")
    
    def _send_notification(self, hash: str, contract_address: str):
        from_number, recipients = get_twilio_info()

        subject = f"Transaction {hash} Reverted"
        msg = f"Transaction {hash} reverted in contract {contract_address}"

        self.handle_notification_service(
            subject=subject,
            msg=msg,
            notification_service=self.notification_service,
            sms_message_function=lambda notification_source: generic_alert(from_number=from_number, recipients=recipients, msg=f"{subject}\n{msg}", notification_source=notification_source),
            ses=self.ses,
            slack=self.slack,
            team_ses=self.team_ses,
            notification_service_results=self.notification_service_results,
            notification_source=NotificationSources.TRANSACTION_REVERTED
        )

    def process_contract(
        self, contract_address: str, w3: Web3, start_block: int, last_block: int
    ):
        for block_number in range(start_block, last_block + 1):
            block = w3.eth.get_block(block_number, full_transactions=True)
            for tx in block.transactions:
                from_address = tx["from"]
                to_address = tx["to"]

                if (
                    from_address.lower() == contract_address.lower()
                    or to_address.lower() == contract_address.lower()
                ):
                    tx_hash = tx["hash"]
                    receipt = w3.eth.get_transaction_receipt(tx_hash)

                    if receipt["status"] == 0:
                        logger.info(f"""
                            Found reverted transaction:
                            Contract address: {contract_address}
                            Tx hash: {tx_hash}
                        """)
                        
                        print("transaction reverted")
                        self._send_notification(tx_hash, contract_address)

    def process_contracts(self):
        rpc_url = self._map_network_id_env_to_rpc_url()
        w3 = Web3(Web3.HTTPProvider(rpc_url))

        start_block = self.start_block
        last_block = w3.eth.block_number

        print(f"Start block: {start_block}")
        print(f"Last block: {last_block}")

        for contract_address in self.contract_addresses:
            self.process_contract(contract_address, w3, start_block, last_block)

        self.start_block = last_block

    def run(self):
        try:
            self._read_contract_monitor_config()
        except Exception as e:
            logger.error(
                f"Error reading contract monitor config: {e} - aborting contract monitor"
            )
            return

        logger.info("Starting contract monitor")
        while True:
            self.process_contracts()
            time.sleep(30)

    def start(
        self,
        ses: Union[Ses, MockSes],
        team_ses: TeamSes,
        slack: Union[Slack, MockSlack],
        notification_service: list[str],
        notification_service_results: dict[NotificationSources, dict],
        handle_notification_service: Callable,
        notification_task_callback: Callable,
    ):
        self.ses = ses
        self.team_ses = team_ses
        self.slack = slack
        self.notification_service = notification_service
        self.notification_service_results = notification_service_results
        self.handle_notification_service = handle_notification_service
        self.notification_task_callback = notification_task_callback
        self.run()


contract_monitor = ContractMonitor()
