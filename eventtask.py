from sqlite3 import IntegrityError
import google.generativeai as genai
from flask import json
import os
from dotenv import load_dotenv
from config import Config
from app import create_app, db
from app.main.models import User,Event,Task
import sqlalchemy as sqla
import sqlalchemy.orm as sqlo

app = create_app(Config)
load_dotenv()


@app.shell_context_processor
def make_shell_context():
    return {'sqla': sqla, 'sqlo': sqlo, 'db': db, 'User': User, 'Event': Event, 'Task': Task}  

@app.before_request
def initDB(*args, **kwargs):
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)

