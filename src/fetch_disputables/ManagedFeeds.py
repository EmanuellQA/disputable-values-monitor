import yaml
from typing import TypedDict

from telliot_core.apps.telliot_config import TelliotConfig
from telliot_feeds.feeds import CATALOG_FEEDS
from telliot_feeds.datafeed import DataFeed

from fetch_disputables.data import Threshold, Metrics, MonitoredFeed
from fetch_disputables.utils import get_logger

logger = get_logger(__name__)

class FeedConfig(TypedDict):
    threshold: Threshold
    datafeed_query_tag: str

class ManagedFeeds:
    def __init__(self):
        query_id = str
        self.has_managed_feeds = False
        self.managed_feeds: dict[query_id, FeedConfig] = self._get_managed_feeds_from_yaml()

    async def is_report_removable(self, monitored_feed: MonitoredFeed, query_id: str, cfg: TelliotConfig, value: float):
        try:
            monitored_feed.feed = self._map_queryId_to_datafeed(query_id)
            monitored_feed.threshold = self._map_queryId_to_threshold(query_id)
            return await monitored_feed.is_disputable(cfg, value)
        except Exception as e:
            logger.error("Error while checking if report is removable")
            logger.error(e)
            return False

    def _map_queryId_to_datafeed(self, query_id: str) -> DataFeed:
        datafeed_query_tag = self.managed_feeds[query_id]['datafeed_query_tag']
        datafeed = CATALOG_FEEDS.get(datafeed_query_tag)
        if not datafeed:
            raise Exception(f"Datafeed not found for query_id: {query_id} - datafeed_query_tag: {datafeed_query_tag}")
        return datafeed
        
    def _map_queryId_to_threshold(self, query_id: str) -> Threshold:
        return self.managed_feeds[query_id]['threshold']
    
    def _map_type_to_metrics(self, type: str):
        type_lower = type.lower()
        if type_lower == 'percentage':return Metrics.Percentage
        if type_lower == 'equality': return Metrics.Equality
        if type_lower == 'range': return Metrics.Range
        raise Exception(f"Invalid threshold type: {type}")

    def _get_managed_feeds_from_yaml(self):
        managed_feeds_dict = {}
        try:
            with open("managed-feeds.yaml", "r") as yaml_file:
                data = yaml.safe_load(yaml_file)
                if not data: raise Exception("Error reading data in managed-feeds.yaml")
                managed_feeds = data['managed_feeds']
                for managed_feed in managed_feeds:
                    query_id = managed_feed['query_id']
                    datafeed_query_tag = managed_feed['datafeed_query_tag']
                    threshold_data = managed_feed['threshold']
                    
                    threshold = Threshold(
                        metric=self._map_type_to_metrics(threshold_data['type']),
                        amount=threshold_data['amount']
                    )
                    managed_feeds_dict[query_id] = {
                        'threshold': threshold,
                        'datafeed_query_tag': datafeed_query_tag
                    }
                self.has_managed_feeds = True
                logger.info('Managed feeds loaded from managed-feeds.yaml')
        except Exception as e:
            logger.error("Error while reading managed-feeds.yaml config file")
            logger.error(e)
        finally:
            return managed_feeds_dict

    def is_managed_feed(self, queryId: str):
        return queryId in self.managed_feeds
