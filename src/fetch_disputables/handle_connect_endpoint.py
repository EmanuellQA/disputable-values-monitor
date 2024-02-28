import logging
from collections import defaultdict
from logging.handlers import RotatingFileHandler
from typing import Optional

from telliot_core.apps.telliot_config import TelliotConfig
from telliot_core.model.endpoints import RPCEndpoint

def get_logger(name: str) -> logging.Logger:
    log_format = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    fh = RotatingFileHandler("log.txt", maxBytes=10000000)
    formatter = logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S")
    fh.setFormatter(formatter)
    logger = logging.getLogger(name)
    logger.addHandler(fh)
    logger.setLevel(logging.DEBUG)
    return logger

logger = get_logger(__name__)

connected_endpoints: dict[int, RPCEndpoint] = defaultdict(lambda: None)

def handle_connect_endpoint(endpoint: RPCEndpoint, chain_id: int) -> None:
    if chain_id in connected_endpoints and connected_endpoints[chain_id] is not None:
        connected_endpoint = connected_endpoints[chain_id]
        is_connected = connected_endpoint._web3.isConnected()

        if is_connected: return

        if not is_connected:
            logger.info(f"endpoint {connected_endpoint.url} lost connection")
            connected_endpoints[chain_id] = None

    try:
        is_connected = endpoint.connect()
        if not is_connected:
            logger.warning(f"could not connect to {endpoint.url} for chain_id {chain_id}")
            return
        logger.info(f"Chain id {chain_id} connected to: {endpoint.url}")
        connected_endpoints[chain_id] = endpoint
    except ValueError as e:
        logger.warning(f"unable to connect to endpoint for chain_id {chain_id}: {e}")
        return
    
def get_endpoint(cfg: TelliotConfig, chain_id: int) -> Optional[RPCEndpoint]:
    endpoints = cfg.endpoints.find(chain_id=chain_id)
    for endpoint in endpoints:
        chain_id = endpoint.chain_id

        handle_connect_endpoint(endpoint, chain_id)

        connected_endpoint = connected_endpoints[chain_id]

        if connected_endpoint is None: continue

        return connected_endpoint
    logger.warning(f"unable to connect to endpoint for chain_id {chain_id}")
    return None