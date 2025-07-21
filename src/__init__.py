from flask import Flask
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_moment import Moment
from flask_mail import Mail
from flask_bootstrap import Bootstrap
import os
from jinja2 import ChoiceLoader, FileSystemLoader
from flask import Blueprint


db = SQLAlchemy()
migrate = Migrate()
login = LoginManager()
login.login_view = 'auth.login'
moment = Moment()
mail = Mail()
bootstrap = Bootstrap()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.static_folder = config_class.STATIC_FOLDER
    
    # Set up multiple template directories
    template_dirs = [
        config_class.TEMPLATE_FOLDER_MAIN,  
        config_class.TEMPLATE_FOLDER_AUTH,  
        os.path.join(os.path.dirname(__file__), 'templates')  # app/templates
    ]
    
    app.jinja_loader = ChoiceLoader([
        FileSystemLoader(template_dir) for template_dir in template_dirs
    ])

    db.init_app(app)
    migrate.init_app(app,db)
    login.init_app(app)
    bootstrap.init_app(app)
    moment.init_app(app)
    mail.init_app(app)

    # blueprint registration
    from src.api.routes import bp_main
    app.register_blueprint(bp_main)
    bp_main.template_folder = Config.TEMPLATE_FOLDER_MAIN

    from src.auth import auth_blueprint as auth
    auth.template_folder = Config.TEMPLATE_FOLDER_AUTH
    app.register_blueprint(auth)
    


    return app



