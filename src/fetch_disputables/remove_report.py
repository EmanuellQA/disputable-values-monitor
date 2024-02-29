from chained_accounts import ChainedAccount
from telliot_core.apps.telliot_config import TelliotConfig
from web3 import Web3
from web3.exceptions import ContractLogicError

from fetch_disputables.ManagedFeeds import ManagedFeeds
from fetch_disputables.data import get_contract
from fetch_disputables.utils import get_logger
from fetch_disputables.utils import NewReport
from fetch_disputables.handle_connect_endpoint import get_endpoint
from fetch_disputables.utils import get_tx_explorer_url

from fetch_disputables.disputer import get_gas_price

logger = get_logger(__name__)

async def remove_report(
    cfg: TelliotConfig, managed_feeds: ManagedFeeds, account: ChainedAccount, new_report: NewReport, gas_multiplier: int = 1
) -> str:
    if not managed_feeds.has_managed_feeds:
        logger.info("No managed feeds. See ./managed-feeds.yaml")
        return ""
    
    if account is None:
        logger.info(f"No account provided, skipping removable report on chain_id {new_report.chain_id}")
        return ""
    
    try:
        endpoint = get_endpoint(cfg, new_report.chain_id)
        if not endpoint: raise ValueError
    except ValueError:
        logger.error(f"Unable to remove value: can't find an endpoint on chain id {new_report.chain_id}")
        return ""
    
    try:
        endpoint.connect()
    except ValueError:
        logger.error(f"Unable to remove value: can't connect to endpoint on chain id {new_report.chain_id}")
        return ""
    w3 = endpoint.web3
    fetch_flex = get_contract(cfg, name="fetchflex-oracle", account=account)

    if fetch_flex is None:
        logger.error(f"Unable to find fetchflex-oracle contract on chain_id {new_report.chain_id}")
        return ""
    
    try:
        acc_nonce = w3.eth.get_transaction_count(Web3.toChecksumAddress(account.address))
    except Exception as e:
        logger.error(f"Unable to remove value on chain_id {new_report.chain_id}: could not retrieve account nonce: {e}")
        return ""
    
    remove_value_function = fetch_flex.contract.get_function_by_name("removeValue")
    remove_value_tx = remove_value_function(
        _queryId=new_report.query_id,
        _timestamp=new_report.submission_timestamp,
    )

    try:
        msg = f"Unable to estimate gas usage for remove value on chain_id {new_report.chain_id}:"
        gas_limit: int = remove_value_tx.estimateGas({"from": Web3.toChecksumAddress(account.address)})
    except ContractLogicError as e:
        logger.error(f"{msg} {e}")
        return ""
    except Exception as e:
        logger.error(f"{msg} {e}")
        return ""
    
    tx_receipt, status = await fetch_flex.write(
        func_name="removeValue",
        _queryId=new_report.query_id,
        _timestamp=new_report.submission_timestamp,
        gas_limit=int(gas_limit * 1.2),
        legacy_gas_price=get_gas_price(w3, gas_multiplier),
        acc_nonce=acc_nonce,
    )

    if not status.ok:
        logger.error(
            f"unable to remove value on {new_report.query_id}"
            + f"at submission timestamp {new_report.submission_timestamp}:"
            + status.error
        )
        return ""
    
    new_report.status_str += ": removed!"
    explorer = endpoint.explorer
    if not explorer:
        remove_tx_link = str(tx_receipt.transactionHash.hex())
    else:
        remove_tx_link = get_tx_explorer_url(str(tx_receipt.transactionHash.hex()), cfg)

    logger.info("Remove value Tx Link: " + remove_tx_link)
    return "Remove value Tx Link: " + remove_tx_link
