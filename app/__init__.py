from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from config import Config

db = SQLAlchemy()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    CORS(app)

    with app.app_context():
        # Import models to register them with SQLAlchemy
        from . import models

        # Register Blueprints
        from .routes import auth, wallet, admin, game, main
        app.register_blueprint(auth.bp)
        app.register_blueprint(wallet.bp)
        app.register_blueprint(admin.bp)
        app.register_blueprint(game.bp)
        app.register_blueprint(main.bp)

        db.create_all()

    return app
