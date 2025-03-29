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

# # Configure Gemini API
# genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# # Create the model
# generation_config = {
#     "temperature": 1,
#     "top_p": 0.95,
#     "top_k": 40,
#     "max_output_tokens": 8192,
#     "response_mime_type": "text/plain",
# }

# model = genai.GenerativeModel(
#     model_name="gemini-1.5-flash",
#     generation_config=generation_config,
#     system_instruction="You are a planning expert, user will give input as a prompt and you will suggest them task to do. Generate a long checklist of what to do and what to bring in JSON format. Also add priority to each task as you think is 1:important/2:necessary/3:normal, don't add any note, just task and priority,Remember to just ask 1-2 question and then generate the json immediately based on what you got",
# )
# chat_session = model.start_chat(
#     history=[]
# )

# while True:
#     user_input = input("You: ")
#     print()

#     response = chat_session.send_message(user_input)

#     model_response = response.text

#     print(f'Bot: {model_response}')
#     print()

#     chat_session.history.append({"role": "user", "parts": [user_input]})
#     chat_session.history.append({"role": "model", "parts": [model_response]})
    

@app.shell_context_processor
def make_shell_context():
    return {'sqla': sqla, 'sqlo': sqlo, 'db': db, 'User': User, 'Event': Event, 'Task': Task}  

@app.before_request
def initDB(*args, **kwargs):
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)

