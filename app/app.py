from dotenv import load_dotenv
load_dotenv()
from otel import CustomLogFW
from flask import Flask, render_template, request
import json
import logging
import random

from . import adventure_game
from . import adventure_cache
from . import forge

app = Flask(__name__)

logFW = CustomLogFW(service_name='app')
handler = logFW.setup_logging()
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.INFO)

# This is inefficient but it'll 
games = {}

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/adventure', methods=['POST'])
def adventure():
    body = request.json
    if body is None or body.get('user', '') == '':
        return { "error": "Invalid body" }, 400
    
    user = body['user']
    game_id = adventure_game.get_game_id(user)
    adventure = adventure_cache.cache.get(game_id)

    # New player, make sure we track their adventure by name
    if adventure is None:
        adventure = adventure_game.AdventureGame(user)
        forge.forge.initialize_forge(adventure)
        adventure_cache.cache.set(adventure)
    elif not forge.forge.is_tracking(adventure):
        # When an adventure from another thread is found here, we need to re-initialize
        # the forge to run on this thread, otherwise its state won't be maintained
        forge.forge.initialize_forge(adventure)
    
    response = adventure.command(body.get('command', ''))

    # Update cache; adventure has changed
    adventure_cache.cache.set(adventure)

    return { "id": adventure.id, "response": response, "user": user }, 200

@app.route('/api/adventurer', methods=['GET'])
def adventurer_name():
    males = ['Godrick', 'Gawain', 'Percival', 'Lancelot', 'Tristan', 'Mordred', 'Bedivere', 'Galahad', 'Merlin', 'Arthur',
             'Beavis', 'Ector', 'Gareth', 'Lucian', 'Grendel', 'Gavin', 'Loki', 'Mimir', 'Odin', 'Thor']
    females = ['Elaine', 'Isolde', 'Enid', 'Lynette', 'Guinevere', 'Morgana', 'Nimue',
              'Ingrid', 'Elanor', 'Arwen', 'Eowyn', 'Galadriel', 'Freyja',
              'Viviane', 'Ragnell']
    givens = females + males 
    role = ['son of', 'daughter of', 'house', 'clan', 'tribe', 'librarian of', 
            'scribe of', 'scribe for', 'treasurer to', 'steward to', 'chancellor to',
            'advisor to', 'squire to', 'knight of', 'page to', 'bard to', 'plumber to',
            'healer to', 'herald to', 'minstrel to', 'jester to', 'fool to', 'courtier to']
    surnames = ['the Brave', 'the Wise', 'the Fool', 'the Terrible', 'the Maladorous', 'the Unwashed', 
                'the Talented', 'the Scourge', 'the Rogue', 'the Mage', 'the Sorcerer', 'the Wizard',
                'the Chaste', 'the Pure', 'the Unyielding', 'the Unbreakable', 'the Unbowed', 'the Unbent',
                'the Pious', 'the Faithful', 'the Valiant', 'the True', 'the Flamboyant', 'the Unseen',
                'the Unworthy', 'the Unfortunate', 'the Mirthsome'] + [ 
                     # Patronynmics
                     name + "son" for name in males
                ] + [ 
                    # Matronymics
                    name + "dottir" for name in females 
                ]

    name = random.choice(givens) + " " + random.choice(surnames) + " (" + random.choice(role) + " " + random.choice(givens) + ")"
    logging.info("A hardy new adventurer approaches!  We shall call them " + name)
    return { "name": name }

@app.route('/api/forge', methods=['GET'])
def get_forge_games():
    """Warning make sure this is the method you want, this provides visibility into what
    games the local forge is monitoring; not the total list of games."""
    return list(forge.forge.games.keys()), 200

@app.route('/api/game/<string:game_id>', methods=['GET'])
def get_game_by_id(game_id):
    if ' ' in game_id:
        return { "error": "Not found " + game_id }, 404

    adventure = adventure_cache.cache.get(game_id)
    if adventure is None:
        return { "error": "Game not found" }, 404

    return adventure.get_state(), 200

@app.route('/api/cache', methods=['GET'])
def cache_status():
    """Returns the full state of the memcached cache"""
    return adventure_cache.cache.status(), 200

@app.route("/api/echo", methods=['POST'])
def echo():
    body = request.json
    context = {
        "method": request.method,
        "headers": dict(request.headers),
        "args": request.args.to_dict(),
        "form": request.form.to_dict(),
        "cookies": request.cookies.to_dict(),
        "remote_addr": request.remote_addr,
        "cookies": request.cookies,
    }
    logging.info("CONTEXT " + json.dumps(context) + " BODY " + json.dumps(body))
    return body

@app.route('/api/health', methods=['GET'])
def power():
    return { "healthy": "yes" }

def get_app():
    return app