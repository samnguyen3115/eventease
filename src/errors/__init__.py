from flask import Blueprint

error_blueprint = Blueprint('errors', __name__)

from src.errors import errors