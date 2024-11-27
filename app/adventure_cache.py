from cachetools import TTLCache
from cachetools.func import ttl_cache
from time import sleep
from otel import CustomLogFW, CustomMetrics, CustomTracer
import logging

# This is a cheapo caching implementation that will keep track of all the adventures we've got going on
# but will let them age out and disappear after a while.
#
# This will be fine for up to hundreds of users but will not scale if the container needs to scale, because
# multiple replicas of the container won't share caches, and hence we'd need to swap in something like redis
# later if we were actually serious.
# 
# This code can easily be replaced with a redis cache lookup later though.
TIMEOUT_SECONDS = 7200 # 2 hours
MAX_SIZE = 500

logFW = CustomLogFW(service_name='adventure')
handler = logFW.setup_logging()
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.INFO)

cache = TTLCache(maxsize=MAX_SIZE, ttl=TIMEOUT_SECONDS)

# Define the cache 
def get(key: str) -> str:
    # Simulate some data fetching or processing
    logging.info(f"Fetching cache data for key: {key}")
    return cache.get(key, None)

# Access the underlying cache from the decorated function
def set(key: str, value: str):
    """Manually set an item in the cache."""
    cache[key] = value
    logging.info(f"Manually set {key} in the cache.")
    print("Set cache item " + key + " to " +str(value))
    return value
