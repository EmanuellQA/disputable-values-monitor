import yaml
from typing import TypedDict, Optional
from pathlib import Path

from fetch_disputables.utils import get_logger

logger = get_logger(__name__)

class DisputeAllDict(TypedDict):
    chain_id: int
    query_id: str

def _get_dispute_all_queryIds():
    dispute_all_path = Path(__file__).parents[2].resolve() / 'disputer-config.yaml'
    dispute_all_feeds_data: list[DisputeAllDict] = []
    try:
        with open(dispute_all_path, "r") as yaml_file:
            data = yaml.safe_load(yaml_file)
            if not data: raise Exception(f"Error reading data in {dispute_all_path}")
            dispute_all_feeds = data['dispute_all_feeds']
            for dispute_all_feed in dispute_all_feeds:
                chain_id = dispute_all_feed['chain_id']
                query_id = dispute_all_feed['query_id']

                dispute_all_feeds_data.append({
                    'chain_id': chain_id,
                    'query_id': query_id
                })
            return dispute_all_feeds_data
    except Exception as e:
        logger.error("Error while reading dispute-all.yaml config file")
        logger.error(e)
        return None

def is_query_id_in_dispute_all(query_id: str, chain_id: int) -> Optional[bool]:
    dispute_all_feeds_data = _get_dispute_all_queryIds()

    if dispute_all_feeds_data is None:
        logger.error("Error while reading 'disputer-config.yaml' config file")
        return None
    
    for dispute_all_feed in dispute_all_feeds_data:
        if dispute_all_feed['query_id'] == query_id and dispute_all_feed['chain_id'] == chain_id:
            logger.info(f"Dispute all query_id: {query_id} chain_id: {chain_id} found in 'disputer-config.yaml' config file")
            return True
    return False