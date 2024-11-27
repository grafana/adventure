from cachetools import TTLCache
from cachetools.func import ttl_cache
from time import sleep, time
from otel import CustomLogFW, CustomMetrics, CustomTracer
import logging
import pickle
import redis
import os
from . import adventure_game

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

cache = None

class SimpleCache:
    def __init__(self): pass
    def get(self, key: str) -> str: pass
    def set(self, key: str, value: str): pass
    def status(self): pass

class RedisCache(SimpleCache):
    def __init__(self):
        self.client = redis.Redis(host=os.environ['REDIS_IP'], port=6379, db=0)
        self.client.ping()

    def status(self):
        # TODO
        return []

    def get(self, key: str):
        value = self.client.get(key)
        pickle_string = value.decode('utf-8') if value is not None else None

        if pickle_string is None:
            return None
        
        return adventure_game.deserialize_game(pickle.loads(pickle_string))

    def set(self, key: str, game):
        self.client.set(key, adventure_game.serialize_game(game))
        return game

class LocalCache(SimpleCache):
    def __init__(self):
        self.cache = TTLCache(maxsize=MAX_SIZE, ttl=TIMEOUT_SECONDS)

    def status(self):
        resp = []

        for key in sorted(cache.keys()):
            adventure = cache.get(key)
            resp.append({ 
                "user": key, 
                "id": adventure.id,
                "current_location": adventure.current_location,
                "game_active": adventure.game_active,
            })
        return resp

    # Define the cache 
    def get(self, key: str) -> str:
        # Simulate some data fetching or processing
        logging.info(f"Fetching cache data for key: {key}")
        pickle_string = cache.get(key, None)

        if pickle_string is None:
            return None

        return adventure_game.deserialize_game(pickle.loads(pickle_string))

    # Access the underlying cache from the decorated function
    def set(self, key: str, game):
        """Manually set an item in the cache."""
        cache[key] = adventure_game.serialize_game(game)
        logging.info(f"Manually set {key} in the cache.")
        print("Set cache item " + key + " to " +str(game))
        return game

if os.environ.get('REDIS_IP',None) is not None:
    cache = RedisCache()
else:
    cache = LocalCache()
