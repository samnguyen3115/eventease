import os
import json
from flask import Flask
from dotenv import load_dotenv
from config import Config
import google.generativeai as genai
from app import db, create_app
from app.main.models import User, Task, Event
from app.main import bp_main  # Import the blueprint here
import sqlalchemy as sqla
import sqlalchemy.orm as sqlo

load_dotenv()

# Configure Gemini API
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Create the model
generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    generation_config=generation_config,
    system_instruction="You are a planning expert, user will give input as a prompt and you will suggest them task to do. Generate a long checklist of what to do and what to bring in JSON format. Also add priority to each task as you think is 1:important/2:necessary/3:normal, don't add any note, just task and priority",
)

app = create_app(Config)
app.register_blueprint(bp_main, url_prefix='/')  # Register the blueprint

@app.shell_context_processor
def make_shell_context():
    return {'sqla': sqla, 'sqlo': sqlo, 'db': db, 'Task': Task, 'Event': Event, 'User': User}

@app.before_request
def initDB():
    db.create_all()

def save_tasks_to_db(response_text, event_id):
    try:
        tasks_data = json.loads(response_text)
        
        for task_data in tasks_data.get('tasks', []):
            task = Task(
                description=task_data.get('task', 'No description provided'),
                priority=task_data.get('priority', 3),
                event_id=event_id
            )
            db.session.add(task)
        
        db.session.commit()
        print("Tasks saved to the database successfully!")
    except Exception as e:
        db.session.rollback()
        print(f"Error saving tasks to the database: {e}")

if __name__ == "__main__":
    app.run(debug=True)
