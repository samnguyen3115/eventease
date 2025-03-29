from flask import Blueprint, request, jsonify, render_template
import google.generativeai as genai
import json
from app import db
from app.main.models import User, Event, Task
from eventtask import save_tasks_to_db
from app.main import main_blueprint as bp_main

model = genai.GenerativeModel(
  model_name="gemini-1.5-flash",
)

@bp_main.route('/', methods=['GET'])
@bp_main.route('/index',methods=['GET','POST'])
def index():
    return render_template('index.html')

@bp_main.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_input = data.get('message')
    event_id = data.get('event_id')

    chat_session = model.start_chat()
    response = chat_session.send_message(user_input)
    response_text = response.text

    save_tasks_to_db(response_text, event_id)
    return jsonify({"response": response_text})

@bp_main.route('/generate_tasks/<int:event_id>', methods=['POST'])
def generate_and_save_tasks(event_id):
    user_input = "I will plan an event"
    chat_session = model.start_chat()
    response = chat_session.send_message(user_input)
    response_text = response.text

    save_tasks_to_db(response_text, event_id)
    return "Tasks generated and saved!"
