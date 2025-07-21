from flask import Flask
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_moment import Moment



db = SQLAlchemy()

migrate = Migrate()

login = LoginManager()
login.login_view = 'auth.login'
moment = Moment()



def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.static_folder = config_class.STATIC_FOLDER
    app.template_folder = config_class.TEMPLATE_FOLDER_MAIN

    db.init_app(app)
    migrate.init_app(app,db)

    login.init_app(app)
    moment.init_app(app)

    # blueprint registration
    from app.main import main_blueprint as main
    app.register_blueprint(main)
    main.template_folder = Config.TEMPLATE_FOLDER_MAIN

    from app.auth import auth_blueprint as auth
    auth.template_folder = Config.TEMPLATE_FOLDER_AUTH
    app.register_blueprint(auth)

    return app