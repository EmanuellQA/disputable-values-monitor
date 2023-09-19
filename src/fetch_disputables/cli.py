"""CLI dashboard to display recent values reported to Fetch oracles."""
import logging
import warnings
from time import sleep
from decimal import *

import os

import click
import pandas as pd
from chained_accounts import ChainedAccount
from hexbytes import HexBytes
from telliot_core.apps.telliot_config import TelliotConfig
from telliot_core.cli.utils import async_run
from web3 import Web3

from fetch_disputables import WAIT_PERIOD
from fetch_disputables.alerts import alert
from fetch_disputables.alerts import dispute_alert
from fetch_disputables.alerts import generic_alert
from fetch_disputables.alerts import get_twilio_info
from fetch_disputables.alerts import handle_notification_service
from fetch_disputables.config import AutoDisputerConfig
from fetch_disputables.data import chain_events
from fetch_disputables.data import get_events
from fetch_disputables.data import parse_new_report_event
from fetch_disputables.data import parse_new_dispute_event
from fetch_disputables.disputer import dispute
from fetch_disputables.utils import clear_console
from fetch_disputables.utils import format_values
from fetch_disputables.utils import get_logger
from fetch_disputables.utils import get_tx_explorer_url
from fetch_disputables.utils import select_account
from fetch_disputables.utils import Topics
from fetch_disputables.Ses import Ses, MockSes
from fetch_disputables.Slack import Slack, MockSlack
from fetch_disputables.utils import get_service_notification, get_reporters
from fetch_disputables.utils import get_report_intervals, get_report_time_margin
from fetch_disputables.utils import get_reporters_balances_thresholds, create_async_task

from dotenv import load_dotenv
load_dotenv()

notification_service: list[str] = get_service_notification()
reporters: list[str] = get_reporters()
reporters_time_margin: int = get_report_time_margin()

def get_reporters_report_intervals(reporters: list[str]):
    report_intervals: list[int] = get_report_intervals()

    reporters_report_intervals = dict()
    for reporter, interval in zip(reporters, report_intervals):
        reporters_report_intervals[reporter] = interval
    return reporters_report_intervals

def get_reporters_pls_balance_threshold(reporters: list[str]):
    reporters_threshold: list[int] = get_reporters_balances_thresholds()

    reporters_pls_balance_threshold = dict()
    for reporter, reporter_threshold in zip(reporters, reporters_threshold):
        reporters_pls_balance_threshold[reporter] = Decimal(reporter_threshold)
    return reporters_pls_balance_threshold

reporters_last_timestamp: dict[str, tuple[int, bool]] = dict()
reporters_report_intervals: dict[str, int] = get_reporters_report_intervals(reporters)
reporters_pls_balance: dict[str, Decimal] = dict()
reporters_pls_balance_threshold: dict[str, Decimal] = get_reporters_pls_balance_threshold(reporters)

warnings.simplefilter("ignore", UserWarning)
price_aggregator_logger = logging.getLogger("telliot_feeds.sources.price_aggregator")
price_aggregator_logger.handlers = [
    h for h in price_aggregator_logger.handlers if not isinstance(h, logging.StreamHandler)
]

logger = get_logger(__name__)
ses = None
slack = None


def print_title_info() -> None:
    """Prints the title info."""
    click.echo("Disputable Values Monitor 📒🔎📲")


@click.command()
@click.option(
    "-av", "--all-values", is_flag=True, default=False, show_default=True, help="if set, get alerts for all values"
)
@click.option("-a", "--account-name", help="the name of a ChainedAccount to dispute with", type=str)
@click.option("-w", "--wait", help="how long to wait between checks", type=int, default=WAIT_PERIOD)
@click.option("-d", "--is-disputing", help="enable auto-disputing on chain", is_flag=True)
@click.option(
    "-c",
    "--confidence-threshold",
    help="set general confidence percentage threshold for monitoring only",
    type=float,
    default=0.1,
)
@async_run
async def main(all_values: bool, wait: int, account_name: str, is_disputing: bool, confidence_threshold: float) -> None:
    """CLI dashboard to display recent values reported to Fetch oracles."""
    global ses, slack
    if "email" in notification_service:
        ses = MockSes() if os.getenv("MOCK_SES", "true") == "true" else Ses(all_values)

    if "slack" in notification_service:
        slack = MockSlack() if os.getenv("MOCK_SLACK", "true") == "true" else Slack(all_values)

    await start(
        all_values=all_values,
        wait=wait,
        account_name=account_name,
        is_disputing=is_disputing,
        confidence_threshold=confidence_threshold,
    )


async def start(
    all_values: bool, wait: int, account_name: str, is_disputing: bool, confidence_threshold: float
) -> None:
    """Start the CLI dashboard."""
    cfg = TelliotConfig()
    cfg.main.chain_id = 943
    disp_cfg = AutoDisputerConfig()
    print_title_info()

    from_number, recipients = get_twilio_info()
    if from_number is None or recipients is None:
        logger.error("Missing phone numbers. See README for required environment variables. Exiting.")
        return

    if not disp_cfg.monitored_feeds:
        logger.error("No feeds set for monitoring, please add feeds to ./disputer-config.yaml")
        return

    account: ChainedAccount = select_account(cfg, account_name)

    if account and is_disputing:
        click.echo("...Now with auto-disputing!")

    display_rows = []
    displayed_events = set()
    new_dispute_events_alerts_sent = set()

    # Build query if filter is set
    while True:

        # Fetch NewReport events
        event_lists = await get_events(
            cfg=cfg,
            contract_name="fetch360-oracle",
            topics=[Topics.NEW_REPORT],
        )
        fetch_flex_report_events = await get_events(
            cfg=cfg,
            contract_name="fetchflex-oracle",
            topics=[Topics.NEW_REPORT],
        )
        fetch360_events = await chain_events(
            cfg=cfg,
            # addresses are for token contract
            chain_addy={
                1: "0x88dF592F8eb5D7Bd38bFeF7dEb0fBc02cf3778a0",
                5: "0x51c59c6cAd28ce3693977F2feB4CfAebec30d8a2",
            },
            topics=[[Topics.NEW_ORACLE_ADDRESS], [Topics.NEW_PROPOSED_ORACLE_ADDRESS]],
        )
        governance_dispute_events = await get_events(
            cfg=cfg,
            contract_name="fetch-governance",
            topics=[Topics.NEW_DISPUTE],
        )
        event_lists += fetch360_events + fetch_flex_report_events + governance_dispute_events

        send_alerts_when_reporters_stops_reporting(reporters_last_timestamp)

        reporters_pls_balance_task = create_async_task(
            update_reporters_pls_balance,
            reporters,
            reporters_pls_balance
        )
        reporters_pls_balance_task.add_done_callback(
            lambda future_obj: send_alerts_reporters_balance_for_balance_threshold(
                reporters_pls_balance,
                reporters_pls_balance_threshold
            )
        )

        for event_list in event_lists:
            # event_list = [(80001, EXAMPLE_NEW_REPORT_EVENT)]
            if not event_list:
                continue
            for chain_id, event in event_list:

                cfg.main.chain_id = chain_id
                if (
                    HexBytes(Topics.NEW_ORACLE_ADDRESS) in event.topics
                    or HexBytes(Topics.NEW_PROPOSED_ORACLE_ADDRESS) in event.topics
                ):
                    link = get_tx_explorer_url(cfg=cfg, tx_hash=event.transactionHash.hex())
                    msg = f"\n❗NEW ORACLE ADDRESS ALERT❗\n{link}"
                    generic_alert(from_number=from_number, recipients=recipients, msg=msg)
                    continue
                    
                if HexBytes(Topics.NEW_DISPUTE) in event.topics:
                    if event.transactionHash.hex() in new_dispute_events_alerts_sent:
                        continue

                    new_dispute = await parse_new_dispute_event(
                        cfg=cfg,
                        log=event
                    )

                    if new_dispute.reporter in reporters:
                        subject = f"New Dispute Event against Reporter {new_dispute.reporter} on Chain {chain_id}"
                        msg = f"New Dispute Event:\n{new_dispute}"
                        handle_notification_service(
                            subject=subject,
                            msg=msg,
                            notification_service=notification_service,
                            sms_message_function=lambda : dispute_alert(f"{subject}\n{msg}", recipients, from_number),
                            ses=ses,
                            slack=slack,
                        )
                        logger.info(f"New Dispute Event against Reporter - alerts sent - {notification_service}")
                        new_dispute_events_alerts_sent.add(new_dispute.tx_hash)
                    continue

                try:
                    new_report = await parse_new_report_event(
                        cfg=cfg,
                        monitored_feeds=disp_cfg.monitored_feeds,
                        log=event,
                        confidence_threshold=confidence_threshold,
                    )
                except Exception as e:
                    logger.error(f"unable to parse new report event on chain_id {chain_id}: {e}")
                    continue

                # Skip duplicate & missing events
                if new_report is None or new_report.tx_hash in displayed_events:
                    continue
                displayed_events.add(new_report.tx_hash)

                if new_report.reporter in reporters:
                    update_reporter_last_timestamp(
                        reporters_last_timestamp,
                        new_report.reporter,
                        new_report.submission_timestamp
                    )
    
                # Refesh
                clear_console()
                print_title_info()

                if is_disputing:
                    click.echo("...Now with auto-disputing!")

                handle_notification_service(
                    subject=f"New Report Event on Chain {chain_id}",
                    msg=f"New Report Event on Chain {chain_id}:\n{new_report}",
                    notification_service=notification_service,
                    sms_message_function=lambda : alert(all_values, new_report, recipients, from_number),
                    ses=ses,
                    slack=slack,
                    new_report=new_report
                )

                if is_disputing and new_report.disputable:
                    success_msg = await dispute(cfg, disp_cfg, account, new_report)
                    if success_msg:
                        handle_notification_service(
                            subject=f"Dispute Successful on Chain {chain_id}",
                            msg=f"Dispute Successful on Chain {chain_id}:\n{success_msg}\nReport:\n{new_report}",
                            notification_service=notification_service,
                            sms_message_function=lambda : dispute_alert(success_msg, recipients, from_number),
                            ses=ses,
                            slack=slack,
                        )

                display_rows.append(
                    (
                        new_report.tx_hash,
                        new_report.submission_timestamp,
                        new_report.link,
                        new_report.query_type,
                        new_report.value,
                        new_report.status_str,
                        new_report.asset,
                        new_report.currency,
                        new_report.chain_id,
                    )
                )

                # Prune display
                if len(display_rows) > 10:
                    # sort by timestamp
                    display_rows = sorted(display_rows, key=lambda x: x[1])
                    displayed_events.remove(display_rows[0][0])
                    del display_rows[0]

                # Display table
                _, times, links, query_type, values, disputable_strs, assets, currencies, chain = zip(*display_rows)

                dataframe_state = dict(
                    When=times,
                    Transaction=links,
                    QueryType=query_type,
                    Asset=assets,
                    Currency=currencies,
                    # split length of characters in the Values' column that overflow when displayed in cli
                    Value=values,
                    Disputable=disputable_strs,
                    ChainId=chain,
                )
                df = pd.DataFrame.from_dict(dataframe_state)
                df = df.sort_values("When")
                df["Value"] = df["Value"].apply(format_values)
                print(df.to_markdown(index=False), end="\r")
                df.to_csv("table.csv", mode="a", header=False)
                # reset config to clear object attributes that were set during loop
                disp_cfg = AutoDisputerConfig()

        sleep(wait)


def update_reporter_last_timestamp(
    reporters_last_timestamp: dict[str, tuple[int, bool]],
    reporter: str,
    new_report_timestamp: int
):
    timestamp, alert_sent = reporters_last_timestamp.get(reporter, (0, False))
    last_timestamp = max(
        timestamp,
        new_report_timestamp
    )
    reporters_last_timestamp[reporter] = (last_timestamp, last_timestamp == timestamp and alert_sent)

def send_alerts_when_reporters_stops_reporting(reporters_last_timestamp: dict[str, tuple[int, bool]]):
    from_number, recipients = get_twilio_info()

    current_timestamp = int(pd.Timestamp.now("UTC").timestamp())

    for reporter, (last_timestamp, alert_sent) in reporters_last_timestamp.items():
        time_threshold = reporters_report_intervals[reporter] + reporters_time_margin
        
        if current_timestamp - last_timestamp <= time_threshold:
            continue
        if alert_sent:
            continue

        minutes = f"{time_threshold // 60} minutes"
        subject = f"Reporter stop reporting"
        msg = f"Reporter {reporter} has not submitted a report in over {minutes}"
        handle_notification_service(
            subject=subject,
            msg=msg,
            notification_service=notification_service,
            sms_message_function=lambda : generic_alert(f"{subject}\n{msg}", recipients, from_number),
            ses=ses,
            slack=slack,
        )
        logger.info(
            f"{msg} - alerts sent - {notification_service}"
        )
        reporters_last_timestamp[reporter] = (last_timestamp, True)

async def update_reporters_pls_balance(reporters: list[str], reporters_pls_balance: dict[str, Decimal]):
    provider_url = "https://rpc.v4.testnet.pulsechain.com"
    w3 = Web3(Web3.HTTPProvider(provider_url))
    for reporter in reporters:
        balance_wei = w3.eth.getBalance(reporter)
        balance = Decimal(w3.fromWei(balance_wei, 'ether'))
        old_balance, alert_sent = reporters_pls_balance.get(reporter, (0, False))
        reporters_pls_balance[reporter] = (balance, balance == old_balance and alert_sent)

def send_alerts_reporters_balance_for_balance_threshold(
    reporters_pls_balance: dict[str, Decimal],
    reporters_pls_balance_threshold: dict[str, Decimal]
):
    from_number, recipients = get_twilio_info()

    for reporter, (pls_balance, alert_sent) in reporters_pls_balance.items():
        if pls_balance >= reporters_pls_balance_threshold[reporter]: continue
        if alert_sent: continue

        subject = f"Reporter balance threshold met"
        msg = f"Reporter {reporter} PLS balance is less than {reporters_pls_balance_threshold[reporter]}\nCurrent PLS balance: {pls_balance}"
        handle_notification_service(
            subject=subject,
            msg=msg,
            notification_service=notification_service,
            sms_message_function=lambda : generic_alert(f"{subject}\n{msg}", recipients, from_number),
            ses=ses,
            slack=slack,
        )
        logger.info(
            f"{msg} - alerts sent - {notification_service}"
        )
        reporters_pls_balance[reporter] = (pls_balance, True)

if __name__ == "__main__":
    main()
