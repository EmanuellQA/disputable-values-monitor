"""Helper functions."""
import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from typing import Optional
from typing import Union

import asyncio

import click
from chained_accounts import ChainedAccount
from chained_accounts import find_accounts
from telliot_core.apps.telliot_config import TelliotConfig
from telliot_feeds.utils.cfg import setup_account

from dotenv import load_dotenv
load_dotenv()

def get_tx_explorer_url(tx_hash: str, cfg: TelliotConfig) -> str:
    """Get transaction explorer URL."""
    explorer: str = cfg.get_endpoint().explorer
    if explorer is not None and explorer[-1] != "/": explorer += "/"
    if explorer is not None:
        return explorer + "tx/" + tx_hash
    else:
        return f"Explorer not defined for chain_id {cfg.main.chain_id}"


@dataclass
class Topics:
    """Topics for Fetch events."""

    # Keccak256("NewReport(bytes32,uint256,bytes,uint256,bytes,address)")
    NEW_REPORT: str = "0x48e9e2c732ba278de6ac88a3a57a5c5ba13d3d8370e709b3b98333a57876ca95"  # oracle.NewReport
    # sha3("NewOracleAddress(address,uint256)")
    NEW_ORACLE_ADDRESS: str = (
        "0x31f30a38b53d085dbe09f68f490447e9032b29de8deb5aae4ccd3577a09ff284"  # oracle.NewOracleAddress
    )
    # sha3("NewProposedOracleAddress(address,uint256)")
    NEW_PROPOSED_ORACLE_ADDRESS: str = (
        "0x8fe6b09081e9ffdaf91e337aba6769019098771106b34b194f1781b7db1bf42b"  # oracle.NewProposedOracleAddress
    )
    # Keccak256("NewDispute(uint256,bytes32,uint256,address,address)")
    NEW_DISPUTE: str = "0xfb173db1d03c427e32a0cd1772db1992fc65a383a802057ce24c3b619e65e8bd"


@dataclass
class NewDispute:
    """NewDispute event."""

    tx_hash: str = ""
    timestamp: int = 0
    reporter: str = ""
    query_id: str = ""
    dispute_id: int = 0
    initiator: str = ""
    chain_id: int = 0
    link: str = ""


@dataclass
class NewReport:
    """NewReport event."""

    tx_hash: str = ""
    submission_timestamp: int = 0  # timestamp attached to NewReport event (NOT the time retrieved by the DVM)
    chain_id: int = 0
    link: str = ""
    query_type: str = ""
    value: Union[str, bytes, float, int] = 0
    asset: str = ""
    currency: str = ""
    query_id: str = ""
    disputable: Optional[bool] = None
    status_str: str = ""
    reporter: str = ""


def disputable_str(disputable: Optional[bool], query_id: str) -> str:
    """Return a string indicating whether the query is disputable."""
    if disputable is not None:
        return "yes ❗📲" if disputable else "no ✔️"
    return f"❗unsupported query ID: {query_id}"


def clear_console() -> None:
    """Clear the console."""
    # windows
    if os.name == "nt":
        _ = os.system("cls")
    # mac, linux (name=="posix")
    else:
        _ = os.system("clear")


def select_account(cfg: TelliotConfig, account: Optional[str]) -> Optional[ChainedAccount]:
    """Select an account for disputing, allow no account to be chosen."""

    if account is not None:
        accounts = find_accounts(name=account)
        click.echo(f"Your account name: {accounts[0].name if accounts else None}")
    else:
        run_alerts_only = click.confirm("Missing an account to send disputes. Run alerts only?")
        if not run_alerts_only:
            new_account = setup_account(cfg.main.chain_id)
            if new_account is not None:
                click.echo(f"{new_account.name} selected!")
                return new_account
            return None
        else:
            return None

    accounts[0].unlock()
    return accounts[0]


def get_logger(name: str) -> logging.Logger:
    """DVM logger

    Returns a logger that logs to file. The name arg
    should be the current file name. For example:
    _ = get_logger(name=__name__)
    """
    log_format = "%(levelname)-7s | %(name)s | %(message)s"
    fh = logging.FileHandler("log.txt")
    formatter = logging.Formatter(log_format)
    fh.setFormatter(formatter)
    logger = logging.getLogger(name)
    logger.addHandler(fh)
    logger.setLevel(logging.DEBUG)
    return logger


def are_all_attributes_none(obj: object) -> bool:
    """Check if all attributes of an object are None."""
    if not hasattr(obj, "__dict__"):
        return False
    for attr in obj.__dict__:
        if getattr(obj, attr) is not None:
            return False
    return True


def format_values(val: Any) -> Any:
    """shorten values for cli display"""
    if isinstance(val, float):
        return Decimal(f"{val:.4f}")
    elif len(str(val)) > 10:
        return f"{str(val)[:6]}...{str(val)[-5:]}"
    else:
        return val

def get_service_notification():
    return [service.lower().strip() for service in os.getenv('NOTIFICATION_SERVICE', "").split(',')]

def get_reporters():
    return [reporter.strip() for reporter in os.getenv('REPORTERS', "").split(',')]

def get_report_intervals():
    report_intervals = [int(interval) for interval in os.getenv('REPORT_INTERVALS', "").split(',') if interval != ""] 
    reporters_length = len(get_reporters())
    if len(report_intervals) != reporters_length:
        safe_default_time = 30 * 60
        log_msg = f"REPORT_INTERVALS for REPORTERS not properly configured, defaulting to {safe_default_time // 60} minutes for each reporter"
        print(log_msg)
        get_logger(__name__).warning(log_msg)
        return [30 * 60 for _ in range(reporters_length)]
    return report_intervals

def get_reporters_balances_thresholds():
    reporters_threshold = [int(interval) for interval in os.getenv('REPORTERS_BALANCE_THRESHOLD', []).split(',')]
 
    reporters_length = len(get_reporters())
    if len(reporters_threshold) != reporters_length:
        safe_default_threshold = 200
        log_msg = f"REPORTERS_BALANCE_THRESHOLD for REPORTERS not properly configured, defaulting to {safe_default_threshold} PLS for each reporter"
        print(log_msg)
        get_logger(__name__).warning(log_msg)
        return [safe_default_threshold for _ in range(reporters_length)]
    return reporters_threshold

def get_report_time_margin():
    return int(os.getenv('REPORT_TIME_MARGIN', 60 * 1))

def create_async_task(function, *args, **kwargs):
    return asyncio.create_task(function(*args, **kwargs))