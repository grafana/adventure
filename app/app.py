from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request
import os
import json
import logging
import time
import random

from . import adventure_game
from . import adventure_cache

app = Flask(__name__)
logger = logging.getLogger("app")

# This is inefficient but it'll 
games = {}

@app.route('/')
def home():
    return render_template('index.html')

games = []

main_adv = adventure_game.AdventureGame("main")
adventure_cache.cache.set("main", main_adv)

@app.route('/api/adventure', methods=['POST'])
def adventure():
    body = request.json
    if body is None or body.get('user', '') == '':
        return { "error": "Invalid body" }, 400
    
    user = body['user']
    adventure = adventure_cache.cache.get(user)

    # New player, make sure we track their adventure by name
    if adventure is None:
        print("Creating new adventure for " + user)
        adventure = adventure_game.AdventureGame(user)
        adventure_cache.cache.set(user, adventure)
    
    print("Adventure " + adventure.id + " " + body.get('command', ''))
    # response = adventure.command(body.get('command', ''))
    response = main_adv.command(body.get('command', ''))

    # Update cache; adventure has changed
    adventure_cache.cache.set(user, adventure)

    if not adventure in games:
        games.append(adventure)

    return { "response": response }, 200

@app.route('/api/adventurer', methods=['GET'])
def adventurer_name():
    givens = ['Godrick', 'Gawain', 'Percival', 'Lancelot', 'Tristan', 'Mordred', 'Bedivere', 'Galahad', 'Merlin', 'Arthur',
            'Elaine', 'Isolde', 'Enid', 'Lynette', 'Guinevere', 'Morgana', 'Nimue', 'Viviane', 'Ragnell']
    familial = ['son of', 'daughter of', 'house', 'clan', 'tribe', 'advisor to', 'squire to', 'knight of', 'page to', 'bard to']
    surnames = ['the Brave', 'the Wise', 'the Fool', 'the Terrible', 'the Maladorous', 'the Unwashed', 
                'the Chaste', 'the Pure', 'the Unyielding', 'the Unbreakable', 'the Unbowed', 'the Unbent',
                'the Pious', 'the Faithful', 'the Valiant', 'the True',
                'the Unworthy', 'the Unfortunate', 'the Mirthsome']

    return {
        "name": random.choice(givens) + " " + random.choice(surnames) + " (" + random.choice(familial) + " " + random.choice(givens) + ")"
    }


@app.route('/api/cache', methods=['GET'])
def cache_status():
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
    logger.info("CONTEXT " + json.dumps(context) + " BODY " + json.dumps(body))
    return body

@app.route('/api/health', methods=['GET'])
def power():
    return { "healthy": "yes" }

def get_app():
    return app