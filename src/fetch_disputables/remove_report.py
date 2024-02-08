from typing import Optional

from chained_accounts import ChainedAccount
from telliot_core.apps.telliot_config import TelliotConfig
from web3 import Web3
from web3.exceptions import ContractLogicError

from fetch_disputables.config import AutoDisputerConfig
from fetch_disputables.data import get_contract
from fetch_disputables.utils import get_logger
from fetch_disputables.utils import NewReport

from fetch_disputables.disputer import get_gas_price

logger = get_logger(__name__)

LLPLS_USD_SPOT_QUERYID = "0x1f984b2c7cbcb7f024e5bdd873d8ca5d64e8696ff219ebede2374bf3217c9b75"

async def remove_report(
    cfg: TelliotConfig, disp_cfg: AutoDisputerConfig, account: ChainedAccount, new_report: NewReport, gas_multiplier: int = 1
) -> str:
    if not disp_cfg.monitored_feeds:
        logger.info("Currently not auto-dispuing on any feeds. See ./disputer-config.yaml")
        return ""
    
    disputable_query_ids = []
    for monitored_feed in disp_cfg.monitored_feeds:
        try:
            disputable_query_id = monitored_feed.feed.query.query_id.hex()
        except Exception:
            pass
        disputable_query_ids.append(disputable_query_id)

    meant_to_dispute = new_report.query_id[2:] in disputable_query_ids

    if not meant_to_dispute:
        logger.info(
            f"Found disputable new report on chain_id {new_report.chain_id}"
            " outside selected Monitored Feeds, skipping dispute"
        )
        return ""

    if account is None:
        logger.info(f"No account provided, skipping eligible dispute on chain_id {new_report.chain_id}")
        return ""
    
    cfg.main.chain_id = new_report.chain_id

    try:
        endpoint = cfg.get_endpoint()
    except ValueError:
        logger.error(f"Unable to dispute: can't find an endpoint on chain id {new_report.chain_id}")
        return ""
    
    try:
        endpoint.connect()
    except ValueError:
        logger.error(f"Unable to dispute: can't connect to endpoint on chain id {new_report.chain_id}")
        return ""
    w3 = endpoint.web3
    fetch_flex = get_contract(cfg, name="fetchflex-oracle", account=account)

    if fetch_flex is None:
        logger.error(f"Unable to find fetchflex-oracle contract on chain_id {new_report.chain_id}")
        return ""
    
    try:
        acc_nonce = w3.eth.get_transaction_count(Web3.toChecksumAddress(account.address))
    except Exception as e:
        logger.error(f"Unable to dispute on chain_id {new_report.chain_id}: could not retrieve account nonce: {e}")
        return ""
    
    remove_value_function = fetch_flex.contract.get_function_by_name("removeValue")
    remove_value_tx = remove_value_function(
        _queryId=new_report.query_id,
        _timestamp=new_report.submission_timestamp,
    )

    try:
        msg = f"Unable to estimate gas usage for dispute on chain_id {new_report.chain_id}:"
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
            f"unable to begin dispute on {new_report.query_id}"
            + f"at submission timestamp {new_report.submission_timestamp}:"
            + status.error
        )
        return ""
    
    new_report.status_str += ": removed!"
    explorer = endpoint.explorer
    if not explorer:
        dispute_tx_link = str(tx_receipt.transactionHash.hex())
    else:
        dispute_tx_link = explorer + "tx/" + str(tx_receipt.transactionHash.hex())

    logger.info("Remove Tx Link: " + dispute_tx_link)
    return "Remove Tx Link: " + dispute_tx_link
