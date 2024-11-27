# app/__init__.py
from flask import Flask

# Very important; downstream modules require env declarations.
from dotenv import load_dotenv
load_dotenv()

from . import app

def create_app(config_class=None):
    instance = app.get_app()
    if config_class:
        instance.config.from_object(config_class)
    return instance