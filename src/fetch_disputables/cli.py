"""CLI dashboard to display recent values reported to Fetch oracles."""
import logging
import warnings
from time import sleep
from decimal import *
from datetime import datetime

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
from fetch_disputables.Ses import Ses, MockSes, TeamSes
from fetch_disputables.Slack import Slack, MockSlack
from fetch_disputables.utils import get_service_notification, get_reporters
from fetch_disputables.utils import get_report_intervals, get_report_time_margin
from fetch_disputables.utils import get_env_reporters_balance_threshold
from fetch_disputables.utils import create_async_task
from fetch_disputables.utils import (
    format_new_report_message, format_new_dispute_message
)
from fetch_disputables.data import get_fetch_balance, get_pls_balance
from fetch_disputables.utils import NotificationSources
from fetch_disputables.remove_report import remove_report
from fetch_disputables.ManagedFeeds import ManagedFeeds

from dotenv import load_dotenv
load_dotenv('.env')

notification_service: list[str] = get_service_notification()
notification_service_results: dict = {
    NotificationSources.NEW_DISPUTE_AGAINST_REPORTER: {
        "sms": None,
        "email": None,
        "slack": None,
        "team_email": None,
        "error": {
            "sms": None,
            "email": None,
            "slack": None,
            "team_email": None,
        }
    },
    NotificationSources.NEW_REPORT: {
        "sms": None,
        "email": None,
        "slack": None,
        "team_email": None,
        "error": {
            "sms": None,
            "email": None,
            "slack": None,
            "team_email": None,
        }
    },
    NotificationSources.AUTO_DISPUTER_BEGAN_A_DISPUTE: {
        "sms": None,
        "email": None,
        "slack": None,
        "team_email": None,
        "error": {
            "sms": None,
            "email": None,
            "slack": None,
            "team_email": None,
        }
    },
    NotificationSources.REPORTER_STOP_REPORTING: {
        "sms": None,
        "email": None,
        "slack": None,
        "team_email": None,
        "error": {
            "sms": None,
            "email": None,
            "slack": None,
            "team_email": None,
        }
    },
    NotificationSources.ALL_REPORTERS_STOP_REPORTING: {
        "sms": None,
        "email": None,
        "slack": None,
        "team_email": None,
        "error": {
            "sms": None,
            "email": None,
            "slack": None,
            "team_email": None,
        }
    },
    NotificationSources.REPORTER_BALANCE_THRESHOLD: {
        "sms": None,
        "email": None,
        "slack": None,
        "team_email": None,
        "error": {
            "sms": None,
            "email": None,
            "slack": None,
            "team_email": None,
        }
    },
    NotificationSources.DISPUTER_BALANCE_THRESHOLD: {
        "sms": None,
        "email": None,
        "slack": None,
        "team_email": None,
        "error": {
            "sms": None,
            "email": None,
            "slack": None,
            "team_email": None,
        }
    },
    NotificationSources.REMOVE_REPORT: {
        "sms": None,
        "email": None,
        "slack": None,
        "team_email": None,
        "error": {
            "sms": None,
            "email": None,
            "slack": None,
            "team_email": None,
        }
    }
} 
reporters: list[str] = get_reporters()
reporters_time_margin: int = get_report_time_margin()

def get_reporters_report_intervals(reporters: list[str]):
    report_intervals: list[int] = get_report_intervals()
    return {reporter: interval for reporter, interval in zip(reporters, report_intervals)}

def get_reporters_balance_threshold(reporters: list[str], env_variable_name: str):
    reporters_threshold: list[int] = get_env_reporters_balance_threshold(env_variable_name=env_variable_name)
    return {reporter: Decimal(reporter_threshold) for reporter, reporter_threshold in zip(reporters, reporters_threshold)}

reporters_last_timestamp: dict[str, tuple[int, bool]] = dict()
reporters_report_intervals: dict[str, int] = get_reporters_report_intervals(reporters)

ReportersBalance = dict[str, tuple[Decimal, bool]]
ReportersBalanceThreshold = dict[str, Decimal]

reporters_pls_balance: ReportersBalance = dict()
reporters_pls_balance_threshold: ReportersBalanceThreshold = get_reporters_balance_threshold(
    reporters=reporters,
    env_variable_name="REPORTERS_PLS_BALANCE_THRESHOLD"
)

reporters_fetch_balance: ReportersBalance = dict()
reporters_fetch_balance_threshold: ReportersBalanceThreshold = get_reporters_balance_threshold(
    reporters=reporters,
    env_variable_name="REPORTERS_FETCH_BALANCE_THRESHOLD"
)

disputer_balances: dict[str, tuple[Decimal, bool]] = dict()

latest_report = {
    'price': 0.0,
    'query_id': '0x0',
    'timestamp': 0,
    'initialized': False
}

warnings.simplefilter("ignore", UserWarning)
price_aggregator_logger = logging.getLogger("telliot_feeds.sources.price_aggregator")
price_aggregator_logger.handlers = [
    h for h in price_aggregator_logger.handlers if not isinstance(h, logging.StreamHandler)
]

logger = get_logger(__name__)
ses = None
team_ses = None
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
@click.option(
    "--gas-multiplier",
    "-gm",
    "gas_multiplier",
    help="increase gas price by this percentage (default 1%) ie 5 = 5%",
    nargs=1,
    type=int,
    default=1
)
@click.option(
    "--skip-processed-reports",
    "-spr",
    "skip_processed_reports",
    help="Skip reports already processed to avoid repetitive workload",
    nargs=1,
    type=bool,
    default=False,
    is_flag=True
)
@async_run
async def main(all_values: bool, wait: int, account_name: str, is_disputing: bool, confidence_threshold: float, gas_multiplier: int, skip_processed_reports: bool) -> None:
    """CLI dashboard to display recent values reported to Fetch oracles."""
    global ses, slack, team_ses
    team_ses = TeamSes()
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
        gas_multiplier=gas_multiplier,
        skip_processed_reports=skip_processed_reports
    )


async def start(
    all_values: bool, wait: int, account_name: str, is_disputing: bool, confidence_threshold: float, gas_multiplier: int, skip_processed_reports: bool
) -> None:
    """Start the CLI dashboard."""
    cfg = TelliotConfig()
    cfg.main.chain_id = int(os.getenv("NETWORK_ID", "943"))
    disp_cfg = AutoDisputerConfig()
    managed_feeds = ManagedFeeds()
    print_title_info()

    from_number, recipients = get_twilio_info()
    if from_number is None or recipients is None:
        if "sms" in notification_service:
            msg = "Missing phone numbers. See README for TWILIO required environment variables. Exiting."
            logger.error(msg)
            print(f"Error - {msg}")
            return
        logger.warning("TWILIO environment variables not configured")

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

        create_async_task(
            send_alerts_when_all_reporters_stops_reporting,
            reporters_last_timestamp,
            managed_feeds
        )

        reporters_pls_balance_task = create_async_task(
            update_reporters_pls_balance,
            cfg,
            reporters,
            reporters_pls_balance
        )
        reporters_pls_balance_task.add_done_callback(
            lambda future_obj: alert_reporters_balance_threshold(
                reporters_balance=reporters_pls_balance,
                reporters_balance_threshold=reporters_pls_balance_threshold,
                asset="PLS"
            )
        )

        reporters_fetch_balance_task = create_async_task(
            update_reporters_fetch_balance,
            cfg,
            reporters,
            reporters_fetch_balance
        )
        reporters_fetch_balance_task.add_done_callback(
            lambda future_obj: alert_reporters_balance_threshold(
                reporters_balance=reporters_fetch_balance,
                reporters_balance_threshold=reporters_fetch_balance_threshold,
                asset="FETCH"
            )
        )

        disputer_balances_task = create_async_task(
            update_disputer_balances,
            telliot_config=cfg,
            disputer_account=account,
            disputer_balances=disputer_balances
        )
        disputer_balances_task.add_done_callback(
            lambda future_obj: alert_on_disputer_balances_threshold(
                disputer_account=account,
                disputer_balances=disputer_balances
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
                        subject = f"DVM ALERT ({os.getenv('ENV_NAME', 'default')}) - New Dispute against Reporter {new_dispute.reporter}"
                        msg = format_new_dispute_message(new_dispute)
                        new_dispute_against_reporter_notification_task = create_async_task(
                            handle_notification_service,
                            subject=subject,
                            msg=msg,
                            notification_service=notification_service,
                            sms_message_function=lambda notification_source: dispute_alert(f"{subject}\n{msg}", recipients, from_number, notification_source),
                            ses=ses,
                            slack=slack,
                            notification_service_results=notification_service_results,
                            notification_source=NotificationSources.NEW_DISPUTE_AGAINST_REPORTER
                        )
                        new_dispute_against_reporter_notification_task.add_done_callback(
                            lambda future_obj: notification_task_callback(
                                msg=f"New Dispute Event against Reporter",
                                notification_service_results=notification_service_results,
                                notification_source=NotificationSources.NEW_DISPUTE_AGAINST_REPORTER
                            )
                        )
                        new_dispute_events_alerts_sent.add(new_dispute.tx_hash)
                    continue

                try:
                    new_report = await parse_new_report_event(
                        cfg=cfg,
                        monitored_feeds=disp_cfg.monitored_feeds,
                        managed_feeds=managed_feeds,
                        log=event,
                        confidence_threshold=confidence_threshold,
                        displayed_events=displayed_events,
                        skip_processed_reports=skip_processed_reports
                    )
                except Exception as e:
                    logger.error(f"unable to parse new report event on chain_id {chain_id}: {e}")
                    continue

                # Skip duplicate & missing events
                if new_report is None or new_report.tx_hash in displayed_events:
                    continue
                displayed_events.add(new_report.tx_hash)

                logger.debug(f"Found report, hash: {new_report.tx_hash}")

                if new_report.reporter in reporters:
                    update_reporter_last_timestamp(
                        reporters_last_timestamp,
                        new_report.reporter,
                        new_report.submission_timestamp
                    )

                if new_report.is_managed_feed:
                    latest_report["price"] = new_report.value
                    latest_report["query_id"] = new_report.query_id
                    latest_report["timestamp"] = new_report.submission_timestamp
                    latest_report["initialized"] = True
    
                # Refesh
                clear_console()
                print_title_info()

                if is_disputing:
                    click.echo("...Now with auto-disputing!")

                new_report_notification_task = create_async_task(
                    handle_notification_service,
                    subject=f"DVM ALERT ({os.getenv('ENV_NAME', 'default')}) - New Report",
                    msg=format_new_report_message(new_report),
                    notification_service=notification_service,
                    sms_message_function=lambda notification_source: alert(all_values, new_report, recipients, from_number, notification_source),
                    ses=ses,
                    slack=slack,
                    new_report=new_report,
                    notification_service_results=notification_service_results,
                    notification_source=NotificationSources.NEW_REPORT
                )
                new_report_notification_task.add_done_callback(
                    lambda future_obj: notification_task_callback(
                        msg=f"New Report",
                        notification_service_results=notification_service_results,
                        notification_source=NotificationSources.NEW_REPORT
                    )
                )

                if is_disputing and new_report.disputable:
                    new_dispute = await dispute(cfg, disp_cfg, account, new_report, gas_multiplier)
                    if new_dispute:
                        success_msg = format_new_dispute_message(new_dispute)
                        new_dispute_notification_task = create_async_task(
                            handle_notification_service,
                            subject=f"DVM ALERT ({os.getenv('ENV_NAME', 'default')}) - Auto-Disputer began a dispute",
                            msg=(
                                f"{success_msg}"
                                "\nAuto-Disputed Report:\n"
                                f"{format_new_report_message(new_report)}"
                            ),
                            notification_service=notification_service,
                            sms_message_function=lambda notification_source: dispute_alert(success_msg, recipients, from_number, notification_source),
                            ses=ses,
                            slack=slack,
                            team_ses=team_ses,
                            notification_service_results=notification_service_results,
                            notification_source=NotificationSources.AUTO_DISPUTER_BEGAN_A_DISPUTE
                        )
                        new_dispute_notification_task.add_done_callback(
                            lambda future_obj: notification_task_callback(
                                msg=f"Auto-Disputer began a dispute",
                                notification_service_results=notification_service_results,
                                notification_source=NotificationSources.AUTO_DISPUTER_BEGAN_A_DISPUTE
                            )
                        )

                if is_disputing and new_report.removable:
                    success_msg = await remove_report(cfg, managed_feeds, account, new_report, gas_multiplier)
                    if success_msg:
                        removable_notification_task = create_async_task(
                            handle_notification_service,
                            subject=f"DVM ALERT ({os.getenv('ENV_NAME', 'default')}) - Report Removed",
                            msg=(
                                f"Report Removed:\n"
                                f"{format_new_report_message(new_report)}"
                            ),
                            notification_service=notification_service,
                            sms_message_function=lambda notification_source: alert(all_values, new_report, recipients, from_number, notification_source),
                            ses=ses,
                            slack=slack,
                            notification_service_results=notification_service_results,
                            notification_source=NotificationSources.REMOVE_REPORT
                        )
                        removable_notification_task.add_done_callback(
                            lambda future_obj: notification_task_callback(
                                msg=f"Report Removed",
                                notification_service_results=notification_service_results,
                                notification_source=NotificationSources.REMOVE_REPORT
                            )
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

async def is_threshold_reached(managed_feeds: ManagedFeeds):
    if latest_report['initialized'] is False:
        return False
    price, query_id = latest_report["price"], latest_report["query_id"]
    current_price = await managed_feeds.fetch_new_datapoint(query_id)
    if current_price is None:
        logger.error("Failed to fetch current price from managed feeds")
        return False
    percentage_change = float(abs(current_price - price)) / price
    percentage_change_threshold = float(os.getenv('PERCENTAGE_CHANGE_THRESHOLD', 0.005))
    return percentage_change >= percentage_change_threshold

def is_time_limit_reached():
    if latest_report['initialized'] is False:
        return False
    timestamp = latest_report["timestamp"]
    current_timestamp = int(pd.Timestamp.now("UTC").timestamp())
    report_time_limit = int(os.getenv("REPORT_TIME_LIMIT", 3600))
    return current_timestamp - timestamp >= report_time_limit

is_all_reporters_alert_sent = False
report_trigger = {
    'timestamp': 0,
    'is_triggered': False
}
async def send_alerts_when_all_reporters_stops_reporting(
    reporters_last_timestamp: dict[str, tuple[int, bool]],
    managed_feeds: ManagedFeeds
):
    global is_all_reporters_alert_sent
    try:
        threshold_reached = await is_threshold_reached(managed_feeds)
        time_limit_reached = is_time_limit_reached()

        if not threshold_reached and not time_limit_reached:
            return
        
        trigger = "percentage_threshold" if threshold_reached else "time_limit"
        logger.info(f"Trigger detected - {trigger}")

        if not report_trigger["is_triggered"]:
            report_trigger["timestamp"] = int(pd.Timestamp.now("UTC").timestamp())
            report_trigger["is_triggered"] = True

        current_timestamp = int(pd.Timestamp.now("UTC").timestamp())

        ALL_REPORTERS_INTERVAL = int(os.getenv("ALL_REPORTERS_INTERVAL", None))
        if ALL_REPORTERS_INTERVAL is None: return

        from_number, recipients = get_twilio_info()

        if current_timestamp - report_trigger["timestamp"] <= ALL_REPORTERS_INTERVAL:
            return

        greater_than_all_reporters_interval = []
        for reporter, (last_timestamp, alert_sent) in reporters_last_timestamp.items():
            if last_timestamp >= report_trigger["timestamp"]:
                greater_than_all_reporters_interval.append(False)
                is_all_reporters_alert_sent = False
                report_trigger["is_triggered"] = False
            else:
                greater_than_all_reporters_interval.append(True)

        if is_all_reporters_alert_sent:
            return

        if len(greater_than_all_reporters_interval) and all(greater_than_all_reporters_interval):
            subject = f"DVM ALERT ({os.getenv('ENV_NAME', 'default')}) - All Reporters stop reporting"

            reporters_utc_timestamps = [
                f"{reporter}: {datetime.utcfromtimestamp(last_timestamp).strftime('%Y-%m-%d %H:%M:%S')} ({last_timestamp})"
                for reporter, (last_timestamp, _) in reporters_last_timestamp.items()
            ]

            msg = f"""
                All Reporters have not submitted a report in over {ALL_REPORTERS_INTERVAL // 60} minutes\n
                Alert timestamp: {datetime.utcfromtimestamp(current_timestamp).strftime('%Y-%m-%d %H:%M:%S')} ({current_timestamp})\n
                Alert timestamp - event trigger timestamp: {(current_timestamp - report_trigger["timestamp"]) // 60} minutes ({current_timestamp - report_trigger["timestamp"]} seconds)\n
                Trigger event: {trigger}\n
                Trigger timestamp: {datetime.utcfromtimestamp(report_trigger["timestamp"]).strftime('%Y-%m-%d %H:%M:%S')} ({report_trigger["timestamp"]})\n
                Reporters last timestamp UTC: {reporters_utc_timestamps}
            """
            all_reporters_stop_reporting_notification_task = create_async_task(
                handle_notification_service,
                subject=subject,
                msg=msg,
                notification_service=notification_service,
                sms_message_function=lambda notification_source: generic_alert(from_number=from_number, recipients=recipients, msg=f"{subject}\n{msg}", notification_source=notification_source),
                ses=ses,
                slack=slack,
                notification_service_results=notification_service_results,
                notification_source=NotificationSources.ALL_REPORTERS_STOP_REPORTING
            )
            all_reporters_stop_reporting_notification_task.add_done_callback(
                lambda future_obj: notification_task_callback(
                    msg=f"All Reporters stop reporting",
                    notification_service_results=notification_service_results,
                    notification_source=NotificationSources.ALL_REPORTERS_STOP_REPORTING
                )
            )
            is_all_reporters_alert_sent = True
    except Exception as e:
        logger.error(f"Error in send_alerts_when_all_reporters_stops_reporting: {e}")

def send_alerts_when_reporters_stops_reporting(reporters_last_timestamp: dict[str, tuple[int, bool]]):
    from_number, recipients = get_twilio_info()

    current_timestamp = int(pd.Timestamp.now("UTC").timestamp())

    for reporter, (last_timestamp, alert_sent) in reporters_last_timestamp.items():
        time_threshold = reporters_report_intervals[reporter] + reporters_time_margin
        
        logger.debug("In send_alerts_when_reporters_stops_reporting")
        logger.debug(f"reporter: {reporter}" )
        logger.debug(f"current_timestamp: {current_timestamp}")
        logger.debug(f"last_timestamp: {last_timestamp}")
        logger.debug(f"alert_sent: {alert_sent}")
        logger.debug(f"time_threshold: {time_threshold}")
        logger.debug(f"current_timestamp - last_timestamp: {current_timestamp - last_timestamp}")
        logger.debug(f"current_timestamp - last_timestamp <= time_threshold: {current_timestamp - last_timestamp <= time_threshold}")
        if current_timestamp - last_timestamp <= time_threshold:
            continue
        if alert_sent:
            continue

        minutes = f"{time_threshold // 60} minutes"
        subject = f"DVM ALERT ({os.getenv('ENV_NAME', 'default')}) - Reporter stop reporting"
        msg = f"Reporter {reporter} has not submitted a report in over {minutes}"
        reporter_stop_reporting_notification_task = create_async_task(
            handle_notification_service,
            subject=subject,
            msg=msg,
            notification_service=notification_service,
            sms_message_function=lambda notification_source: generic_alert(from_number=from_number, recipients=recipients, msg=f"{subject}\n{msg}", notification_source=notification_source),
            ses=ses,
            slack=slack,
            notification_service_results=notification_service_results,
            notification_source=NotificationSources.REPORTER_STOP_REPORTING
        )
        reporter_stop_reporting_notification_task.add_done_callback(
            lambda future_obj: notification_task_callback(
                msg=f"Reporter stop reporting",
                notification_service_results=notification_service_results,
                notification_source=NotificationSources.REPORTER_STOP_REPORTING
            )
        )
        reporters_last_timestamp[reporter] = (last_timestamp, True)

async def update_reporters_pls_balance(
    telliot_config: TelliotConfig,
    reporters: list[str],
    reporters_pls_balance: dict[str, tuple[Decimal, bool]],
):
    for reporter in reporters:
        balance = await get_pls_balance(telliot_config, reporter)
        old_balance, alert_sent = reporters_pls_balance.get(reporter, (0, False))
        reporters_pls_balance[reporter] = (balance, balance == old_balance and alert_sent)

async def update_reporters_fetch_balance(
    cfg: TelliotConfig,
    reporters: list[str],
    reporters_fetch_balance: dict[str, tuple[Decimal, bool]],
):
    for reporter in reporters:
        old_fetch_balance, alert_sent = reporters_fetch_balance.get(reporter, (0, False))
        reporter_fetch_balance = await get_fetch_balance(cfg, reporter)
        reporters_fetch_balance[reporter] = (reporter_fetch_balance, reporter_fetch_balance == old_fetch_balance and alert_sent)

def alert_reporters_balance_threshold(
    reporters_balance: ReportersBalance,
    reporters_balance_threshold: ReportersBalanceThreshold,
    asset: str
):
    from_number, recipients = get_twilio_info()

    for reporter, (balance, alert_sent) in reporters_balance.items():
        if balance >= reporters_balance_threshold[reporter]: continue
        if alert_sent: continue

        subject = f"DVM ALERT ({os.getenv('ENV_NAME', 'default')}) - Reporter {asset} balance threshold met"
        msg = (
            f"Reporter {reporter} {asset} balance is less than {reporters_balance_threshold[reporter]}\n"
            f"Current {asset} balance: {balance} in network ID {os.getenv('NETWORK_ID', '943')}"
        )
        reporter_balance_threshold_notification_task = create_async_task(
            handle_notification_service,
            subject=subject,
            msg=msg,
            notification_service=notification_service,
            sms_message_function=lambda : generic_alert(from_number=from_number, recipients=recipients, msg=f"{subject}\n{msg}"),
            ses=ses,
            slack=slack,
            notification_service_results=notification_service_results,
            notification_source=NotificationSources.REPORTER_BALANCE_THRESHOLD
        )
        reporter_balance_threshold_notification_task.add_done_callback(
            lambda future_obj: notification_task_callback(
                msg=f"Reporter {asset} balance threshold met",
                notification_service_results=notification_service_results,
                notification_source=NotificationSources.REPORTER_BALANCE_THRESHOLD
            )
        )
        reporters_balance[reporter] = (balance, True)

async def update_disputer_balances(
    telliot_config: TelliotConfig,
    disputer_account: ChainedAccount,
    disputer_balances: dict[str, tuple[Decimal, bool]]
):
    if disputer_account is None:
        logger.warning("Disputer address not set")
        return
    try:
        disputer_address = Web3.toChecksumAddress(disputer_account.address)
        old_balance_pls, alert_sent_pls = disputer_balances.get('PLS', (0, False))
        disputer_pls_balance = await get_pls_balance(telliot_config, disputer_address)
        disputer_balances['PLS'] = (disputer_pls_balance, disputer_pls_balance == old_balance_pls and alert_sent_pls)

        old_balance_fetch, alert_sent_fetch = disputer_balances.get('FETCH', (0, False))
        disputer_fetch_balance = await get_fetch_balance(telliot_config, disputer_address)
        disputer_balances['FETCH'] = (disputer_fetch_balance, disputer_fetch_balance == old_balance_fetch and alert_sent_fetch)
    except Exception as e:
        logger.error("Error updating disputer balances")
        logger.error(e)

def alert_on_disputer_balances_threshold(
    disputer_account: ChainedAccount,
    disputer_balances: dict[str, tuple[Decimal, bool]]
):
    if disputer_account is None:
        logger.warning("Disputer address not set")
        return

    disputer_pls_balance_threshold = os.getenv("DISPUTER_PLS_BALANCE_THRESHOLD")
    disputer_fetch_balance_threshold = os.getenv("DISPUTER_FETCH_BALANCE_THRESHOLD")

    disputer_balance_thresholds = {
        'PLS': Decimal(disputer_pls_balance_threshold) if disputer_pls_balance_threshold is not None else None,
        'FETCH': Decimal(disputer_fetch_balance_threshold) if disputer_fetch_balance_threshold is not None else None
    }

    if disputer_balance_thresholds['PLS'] is None:
        logger.warning("DISPUTER_PLS_BALANCE_THRESHOLD environment variable not set")
    
    if disputer_balance_thresholds['FETCH'] is None:
        logger.warning("DISPUTER_FETCH_BALANCE_THRESHOLD environment variable not set")

    from_number, recipients = get_twilio_info()

    for asset, (balance, alert_sent) in disputer_balances.items():
        if disputer_balance_thresholds[asset] is None: continue
        if balance >= disputer_balance_thresholds[asset]: continue
        if alert_sent: continue

        subject = f"DVM ALERT ({os.getenv('ENV_NAME', 'default')}) - Disputer {asset} balance threshold met"
        msg = (
            f"Disputer {asset} balance is less than {disputer_balance_thresholds[asset]}\n"
            f"Current {asset} balance: {balance} in network ID {os.getenv('NETWORK_ID', '943')}\n"
            f"Disputer address: {disputer_account.address}"
        )
        disputer_balance_threshold_notification_task = create_async_task(
            handle_notification_service,
            subject=subject,
            msg=msg,
            notification_service=notification_service,
            sms_message_function=lambda : generic_alert(from_number=from_number, recipients=recipients, msg=f"{subject}\n{msg}"),
            ses=ses,
            slack=slack,
            notification_service_results=notification_service_results,
            notification_source=NotificationSources.DISPUTER_BALANCE_THRESHOLD
        )
        disputer_balance_threshold_notification_task.add_done_callback(
            lambda future_obj: notification_task_callback(
                msg=f"Disputer {asset} balance threshold met",
                notification_service_results=notification_service_results,
                notification_source=NotificationSources.DISPUTER_BALANCE_THRESHOLD
            )
        )
        disputer_balances[asset] = (balance, True)

def notification_task_callback(
    msg: str,
    notification_service_results: dict,
    notification_source: str
):
    services_notified = []
    notification_result = notification_service_results[notification_source]
    for key in notification_result:
        if key == "error": continue
        if key == "team_email" and notification_source != NotificationSources.AUTO_DISPUTER_BEGAN_A_DISPUTE: continue
        if notification_result[key] == None or notification_result["error"][key] != None: continue
        services_notified.append(key)

    logger.info(
        f"{msg} - alerts sent - {services_notified}"
    )

if __name__ == "__main__":
    main()
