import os
import sys
from dotenv import load_dotenv
from config import Config
from src import create_app, db
from src.database.models import User,Event,Task
import sqlalchemy as sqla
import sqlalchemy.orm as sqlo


# Load environment variables first
load_dotenv()

# Validate critical environment variables
required_env_vars = ['GEMINI_API_KEY']
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    print(f"Error: Missing required environment variables: {', '.join(missing_vars)}")
    print("Please set these variables in your .env file")
    sys.exit(1)

app = create_app(Config)

from src.api.chatbot import chatbot_router
from src.api.event import event_router
from src.api.task import task_router
app.register_blueprint(chatbot_router)
app.register_blueprint(event_router)
app.register_blueprint(task_router)
chatbot_router.template_folder = Config.TEMPLATE_FOLDER_MAIN
event_router.template_folder = Config.TEMPLATE_FOLDER_MAIN
task_router.template_folder = Config.TEMPLATE_FOLDER_MAIN

@app.shell_context_processor
def make_shell_context():
    return {'sqla': sqla, 'sqlo': sqlo, 'db': db, 'User': User, 'Event': Event, 'Task': Task}  

@app.before_request
def initDB(*args, **kwargs):
    try:
        db.create_all()
    except Exception as e:
        print(f"Database initialization error: {e}")

if __name__ == "__main__":
    # Use environment variable for debug mode, default to False for production safety
    debug_mode = os.getenv('FLASK_DEBUG', '0').lower() in ['1', 'true', 'yes']
    port = int(os.getenv('FLASK_PORT', 5000))
    
    try:
        app.run(debug=debug_mode, port=port, host='0.0.0.0')
    except Exception as e:
        print(f"Failed to start server: {e}")
        sys.exit(1)

