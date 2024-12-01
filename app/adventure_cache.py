from time import time
from otel import CustomLogFW
import logging
import time
import json
from pymemcache.client.base import PooledClient
import os
from . import adventure_game

cache = None

class MemcachedCache:
    """A simple cache for storing AdventureGame objects in memcached"""
    GAME_INDEX_KEY = "game_index"

    logFW = CustomLogFW(service_name='adventure_cache')
    handler = logFW.setup_logging()
    logging.getLogger('adventure_cache').addHandler(handler)
    logging.getLogger('adventure_cache').setLevel(logging.INFO)

    def __init__(self):
        tuple = (
            os.environ.get('MEMCACHED_HOST', 'localhost'),
            int(os.environ.get('MEMCACHED_PORT', 11211))
        )
        self.client = PooledClient(tuple, max_pool_size=4)
        self.log = logging.getLogger('adventure_cache')

    def status(self):
        index = self.get_index()
        result = {}
        print(index)

        game_ids = []
        table = []
        for key in index.keys():
            game = self.get(key)

            if game is None:
                result[key] = 'Game not found'
            else:
                table.append({"game_id": game.id, "user": game.adventurer_name})
                result[key] = game.get_state()
                game_ids.append(key)
        
        result['game_ids'] = game_ids
        result['games'] = len(game_ids)
        result['table'] = table
        result[MemcachedCache.GAME_INDEX_KEY] = index
        return result

    def evict_old_games(self, index):
        now = int(time.time() * 1000)
        
        evicted = 0
        for key in list(index.keys()):
            entered = index[key]
            # print("Checking " + key + " entered " + str(entered) + " for evictability at " + (str(entered + adventure_game.AdventureGame.MAX_GAME_AGE_MS)) + " now: " + str(now))
            if now > entered + adventure_game.AdventureGame.MAX_GAME_AGE_MS:
                print("Evicting " + key)
                self.log.info("Evicting game", extra={"game_id": key, "now": now, "entered": entered})
                self.client.delete(key)
                del index[key]
                evicted += 1
        
        if evicted > 0:
            self.log.info(f"Evicted {evicted} games", extra={"evicted": evicted})
            self.client.set(self.make_key(MemcachedCache.GAME_INDEX_KEY), json.dumps(index))

    def get_index(self):
        val = self.client.get(self.make_key(MemcachedCache.GAME_INDEX_KEY))
        
        if val is None:
            return {}
        
        return json.loads(val)

    def update_index(self, game):
        """Updates the total list of games that we are tracking"""
        index = self.get_index()

        # Do not modify the entered timestamp unless it's the first time into the index
        # This lets us evict old games later.  Note that sometimes the index may not have changed
        if game.id not in index:
            index[game.id] = int(time.time() * 1000)
            self.client.set(self.make_key(MemcachedCache.GAME_INDEX_KEY), json.dumps(index))

        self.evict_old_games(index)
        return game

    def make_key(self, base_key):
        # Allow the env to set a key prefix so we can have multiple copies/deployments in the same
        # memcachd instance
        KEY_PREFIX = os.environ.get('CACHE_KEY_PREFIX', 'main')
        return KEY_PREFIX + "_" + base_key

    def get(self, key: str):
        """Get a game by a given ID.  Can return None if it doesn't exist"""
        try:
            json_string = self.client.get(self.make_key(key))
        except KeyError as e:
            return None

        if json_string is None:
            return None
        
        return adventure_game.from_json(json_string)

    def set(self, game):
        """Set a game in the cache; returns the game"""

        if game is None or game.id is None:
            raise ValueError("Game must be valid and have an ID")

        # Always update last modified time ms so readers can tell if the game is stale
        game.last_state_update = int(time.time()*1000)
        self.client.set(self.make_key(game.id), adventure_game.to_json(game))
        return self.update_index(game)

cache = MemcachedCache()
