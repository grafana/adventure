# This object is intended to encapsulate all game async state updates
# For example, while games are running, in various states the forge fires
# can be burning. This object keeps track of multi-game forge fires and other
# state while the main AdventureGame instance isn't being interacted with
#
# Additionally, it encapsulates the telemetry recording of game instances

from cachetools import TTLCache
from otel import CustomLogFW, CustomMetrics, CustomTracer
from opentelemetry import metrics
import time
import threading
import logging
import uuid
import hashlib
import time
from . import adventure_cache
import asyncio

MAX_SIZE = 5000

# TODO: better eviction policy when games end
class Forge:
    logFW = CustomLogFW(service_name='forge')
    handler = logFW.setup_logging()
    logging.getLogger('forge').addHandler(handler)
    logging.getLogger('forge').setLevel(logging.INFO)

    forge_metrics = CustomMetrics(service_name='forge')
    forge_meter = forge_metrics.get_meter()

    # Game specific metrics
    adventure_metrics = CustomMetrics(service_name='adventure')
    adventure_meter = adventure_metrics.get_meter()

    ct = CustomTracer()

    """This class encapsulates all game async state updates and telemetry recording for the game.
    It's called the Forge because tracking forge heat is why it was first needed"""
    def __init__(self):
        # Short ID based on time of generation, good enough for now
        self.id = hashlib.md5(bytes(f"{time.time()}","utf-8")).hexdigest()
        self.context = { "id": self.id }
        self.log = logging.getLogger('forge')
        # Create caches that evicts items older than 3 hours
        # Keys are assigned/entered *once* to prevent resetting ttl
        self.games = TTLCache(maxsize=MAX_SIZE, ttl=60*60*3)
        self.initialize_game_o11y()
        self.start_forge_thread()

    def initialize_game_o11y(self):
        # Metrics about the forge itself
        self.update_counter = Forge.forge_meter.create_up_down_counter(
            name="updates",
            unit="1",
            description="The number of game forges updated",
        )
        self.game_counter = Forge.forge_meter.create_up_down_counter(
            name="games",
            unit="1",
            description="The number of games being tracked",
        )

        self.trace = Forge.ct.get_trace()
        self.tracer = self.trace.get_tracer("AdventureGame")
        
        # Create an observable gauge for the forge heat level.
        self.forge_heat_gauge = Forge.adventure_meter.create_observable_gauge(
            name="forge_heat",
            description="The current heat level of the forge",
            callbacks=[self.observe_forge_heat]
        )

        # Create an observable gauge for how many swords have been forged.
        self.swords_gauge = Forge.adventure_meter.create_observable_gauge(
            name="swords",
            description="The number of swords forged",
            callbacks=[self.observe_swords]
        )

        self.holy_sword_gauge = Forge.adventure_meter.create_observable_gauge(
            name="holy_sword",
            description="The number of holy swords",
            callbacks=[self.observe_holy_swords]
        )

        self.evil_sword_gauge = Forge.adventure_meter.create_observable_gauge(
            name="evil_sword",
            description="The number of evil swords",
            callbacks=[self.observe_evil_swords]
        )

    def for_all_games_observe(self, action):
        observations = []
        deleted = []

        for key in self.games.keys():
            print("Getting latest game for ",key)
            game = adventure_cache.cache.get(key)
            if game is None:
                print("MISS for ",key)
                deleted.append(key)
                continue
            observations.extend(action(game))

        # If a game was deleted from the underlying store; remove it from what
        # we're tracking.
        if len(deleted) > 0:
            print("Deleted games", deleted)
            self.games = {key: value for key, value in self.games.items() if key not in deleted}
            self.game_counter.add(len(deleted) * -1)

        return observations

    def observe_forge_heat(self, observer):
        def observe(game):
            return [metrics.Observation(value=game.heat, attributes={"location": "blacksmith"} | game.context)]
        return self.for_all_games_observe(observe)
    
    def observe_swords(self, observer):
        def observe(game):
            sword_count = 0
            if game.has_sword:
                sword_count = 1
            elif game.has_evil_sword or game.has_holy_sword:
                sword_count = 0
            return [metrics.Observation(value=sword_count, attributes=game.context)]
        return self.for_all_games_observe(observe)
    
    def observe_holy_swords(self, observer):
        def observe(game):
            sword_count = 0
            if game.has_holy_sword:
                sword_count = 1
            elif game.has_evil_sword or game.has_sword: 
                sword_count = 0
            return [metrics.Observation(value=sword_count, attributes=game.context)]
        return self.for_all_games_observe(observe)
    
    def observe_evil_swords(self, observer):
        def observe(game):
            sword_count = 0
            if game.has_evil_sword:
                sword_count = 1
            elif game.has_holy_sword or game.has_sword:
                sword_count = 0
            return [metrics.Observation(value=sword_count, attributes=game.context)]
        return self.for_all_games_observe(observe)

    def is_tracking(self, game):
        return game.id in self.games.keys()

    def initialize_forge(self, game):
        """Given a game, this creates the async state management in the background"""
        # Key is associated with its time of entry so that we can later evict old/inactive
        # games. TODO
        self.games[game.id] = int(time.time()*1000)
        self.log.info(f"Initializing forge for game", extra=self.context | { "game_id": game.id })
        self.game_counter.add(1)

    # TODO: figure out how to monkeypatch TTLCache to support eventing on eviction
    # def evict_game(self, key, value):
    #     self.log.info(f"Cache eviction", extra={"game_id":key} | self.context)
    #    self.game_counter.add(-1)

    def increase_heat_periodically(self):
        updated = 0
        total = 0
        now = int(time.time()*1000)
        for key in self.games.keys():
            total += 1
            game = adventure_cache.cache.get(key)
            if game is None:
                continue

            # Tricky concurrency, consider that multiple forges can be tracking a game on 
            # different threads in different containers. We don't want them all ganging up and
            # accelerating forge heat
            ms_since_last_update = now - game.last_state_update
            if ms_since_last_update < 1000:
                continue

            if game.is_heating_forge:
                updated += 1
                game.heat += 1
                if game.heat >= 50:
                    self.log.info("Blacksmith burned down", extra=self.context | { "game_id": game.id })
                    game.blacksmith_burned_down = True
                    game.heat = 0
                    game.is_heating_forge = False

                adventure_cache.cache.set(game)
        
        if updated > 0:
            self.update_counter.add(updated)
            self.log.info(f"Increased heat {updated} of {total} games", extra=self.context)

    def get_thread(self): return self.thread

    def start_forge_thread(self):
        def main_loop():
            while True:
                time.sleep(1)
                self.increase_heat_periodically()
        
        self.thread = threading.Thread(target=main_loop)
        self.thread.daemon = True
        self.thread.start()

    def forge_heat_callback(self, game_id):
        """Higher order function that returns an observer function per game"""
        # Important: get game by ID always, because they're changing in the background
        game = adventure_cache.cache.get(game_id)
        return lambda observer: [ metrics.Observation(value=game.heat, attributes={"location":"blacksmith"} | game.context) ]

forge = Forge()