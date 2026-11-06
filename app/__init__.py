from urllib.parse import urlsplit

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from config import Config

db = SQLAlchemy()

UNSAFE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


def _register_csrf_guard(app):
    """Reject cross-site state-changing API calls.

    Every mutating API request must be JSON (a plain HTML form cannot send
    application/json without a CORS preflight), and if the browser sends an
    Origin header it must be this site or an explicitly allowed origin.
    """

    @app.before_request
    def csrf_guard():
        if request.method not in UNSAFE_METHODS or not request.path.startswith('/api/'):
            return None

        origin = request.headers.get('Origin')
        if origin:
            allowed = set(app.config.get('CORS_ORIGINS') or [])
            same_origin = urlsplit(origin).netloc == request.host
            if not same_origin and origin not in allowed:
                return jsonify({'error': 'Cross-origin request blocked'}), 403

        if not request.is_json:
            return jsonify({'error': 'Requests must use Content-Type: application/json'}), 415
        return None


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)

    origins = app.config.get('CORS_ORIGINS') or []
    if origins:
        from flask_cors import CORS
        CORS(app, resources={r'/api/*': {'origins': origins}}, supports_credentials=True)

    _register_csrf_guard(app)

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
