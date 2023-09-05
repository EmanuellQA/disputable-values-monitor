"""CLI dashboard to display recent values reported to Fetch oracles."""
import logging
import warnings
from time import sleep

import os

import click
import pandas as pd
from chained_accounts import ChainedAccount
from hexbytes import HexBytes
from telliot_core.apps.telliot_config import TelliotConfig
from telliot_core.cli.utils import async_run

from fetch_disputables import WAIT_PERIOD
from fetch_disputables.alerts import alert
from fetch_disputables.alerts import dispute_alert
from fetch_disputables.alerts import generic_alert
from fetch_disputables.alerts import get_twilio_info
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
from fetch_disputables.Ses import Ses
from fetch_disputables.Slack import Slack

from dotenv import load_dotenv
load_dotenv()

notification_service = os.getenv('NOTIFICATION_SERVICE').split(',')
reporters = os.getenv('REPORTERS').split(',')

warnings.simplefilter("ignore", UserWarning)
price_aggregator_logger = logging.getLogger("telliot_feeds.sources.price_aggregator")
price_aggregator_logger.handlers = [
    h for h in price_aggregator_logger.handlers if not isinstance(h, logging.StreamHandler)
]

logger = get_logger(__name__)
ses = Ses() if "email" in notification_service else None
slack = Slack() if "slack" in notification_service else None


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
                        if "sms" in notification_service:
                            dispute_alert(f"{subject}\n{msg}", recipients, from_number)
                        if "email" in notification_service:
                            ses.send_email(
                                subject=subject,
                                msg=msg,
                            )
                        if "slack" in notification_service:
                            slack.send_message(
                                subject=subject,
                                msg=msg,
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

                # Refesh
                clear_console()
                print_title_info()

                if is_disputing:
                    click.echo("...Now with auto-disputing!")

                if "sms" in notification_service:
                    alert(all_values, new_report, recipients, from_number)
                if "email" in notification_service:
                    ses.send_email(
                        subject=f"New Report Event on Chain {chain_id}",
                        msg=f"New Report Event on Chain {chain_id}:\n{new_report}",
                    )      
                if "slack" in notification_service:
                    slack.send_message(
                        subject=f"New Report Event on Chain {chain_id}",
                        msg=f"New Report Event on Chain {chain_id}:\n{new_report}",
                    )                                 

                if is_disputing and new_report.disputable:
                    success_msg = await dispute(cfg, disp_cfg, account, new_report)
                    if success_msg:
                        if "sms" in notification_service:
                            dispute_alert(success_msg, recipients, from_number)
                        if "email" in notification_service:
                            ses.send_email(
                                subject=f"Dispute Successful on Chain {chain_id}",
                                msg=f"Dispute Successful on Chain {chain_id}:\n{success_msg}",
                            )
                        if "slack" in notification_service:
                            slack.send_message(
                                subject=f"Dispute Successful on Chain {chain_id}",
                                msg=f"Dispute Successful on Chain {chain_id}:\n{success_msg}",
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


if __name__ == "__main__":
    main()
