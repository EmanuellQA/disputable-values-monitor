import asyncio
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Union

import yaml
from dotenv import load_dotenv
from web3 import Web3

from .alerts import generic_alert, get_twilio_info
from .Ses import MockSes, Ses, TeamSes
from .Slack import MockSlack, Slack
from .utils import NotificationSources, create_async_task, get_logger

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

    async def _send_notification(
        self,
        chain_id: int,
        rpc: str,
        contract_address: str,
        tx_hash: str,
        block_number: int,
    ):
        from_number, recipients = get_twilio_info()

        subject = f"Transaction {tx_hash} Reverted (ChainID: {chain_id})"
        msg = f"""
            Reverted transaction:
            Chain ID: {chain_id}
            RPC: {rpc}
            Contract address: {contract_address}
            Tx hash: {tx_hash}
            Block number: {block_number}
        """

        tx_revert_alert_task = create_async_task(
            self.handle_notification_service,
            subject=subject,
            msg=msg,
            notification_service=self.notification_service,
            sms_message_function=lambda notification_source: generic_alert(
                from_number=from_number,
                recipients=recipients,
                msg=f"{subject}\n{msg}",
                notification_source=notification_source,
            ),
            ses=self.ses,
            slack=self.slack,
            team_ses=self.team_ses,
            notification_service_results=self.notification_service_results,
            notification_source=NotificationSources.TRANSACTION_REVERTED,
        )

        tx_revert_alert_task.add_done_callback(
            lambda future_obj, msg_callback=subject: self.notification_task_callback(
                msg=msg_callback,
                notification_service_results=self.notification_service_results,
                notification_source=NotificationSources.REPORTER_BALANCE_THRESHOLD,
            )
        )

    async def process_contract(
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
                            Chain ID: {w3.eth.chain_id}
                            RPC: {w3.provider}
                            Contract address: {contract_address}
                            Tx hash: {tx_hash.hex()}
                            Block number: {block_number}
                            Sending notification...
                        """)
                        create_async_task(
                            self._send_notification,
                            chain_id=w3.eth.chain_id,
                            rpc=str(w3.provider),
                            contract_address=contract_address,
                            tx_hash=tx_hash.hex(),
                            block_number=block_number,
                        )

    async def process_contracts(self):
        rpc_url = self._map_network_id_env_to_rpc_url()
        w3 = Web3(Web3.HTTPProvider(rpc_url))

        start_block = self.start_block
        last_block = w3.eth.block_number

        logger.info(f"""
            Processing contracts:
            Contracts: {self.contract_addresses}
            Start block: {start_block}
            Last block: {last_block}
        """)

        for contract_address in self.contract_addresses:
            await self.process_contract(contract_address, w3, start_block, last_block)

        self.start_block = last_block

    async def run(self):
        try:
            self._read_contract_monitor_config()
        except Exception as e:
            logger.error(
                f"Error reading contract monitor config: {e} - aborting contract monitor"
            )
            return

        logger.info("Starting contract monitor")
        poll_interval = 30
        while True:
            await self.process_contracts()
            await asyncio.sleep(poll_interval)

    def start_thread(self):
        asyncio.run(self.run())

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

        thread = threading.Thread(
            target=self.start_thread, daemon=True, name="ContractMonitor"
        )
        thread.start()


contract_monitor = ContractMonitor()
