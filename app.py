"""
Flask application factory + entrypoint.

Run with:  python app.py
(or `flask --app app run` / gunicorn app:app in production - see README)
"""
from flask import Flask

import config
import db


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["JSON_SORT_KEYS"] = False

    with app.app_context():
        db.init_db()

    from routes.pages import pages_bp
    from routes.api import api_bp
    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    @app.context_processor
    def inject_nav_categories():
        import repository as repo
        try:
            return {"nav_categories": repo.list_categories()}
        except Exception:
            return {"nav_categories": []}

    @app.teardown_appcontext
    def close_db(exception=None):
        pass  # connections are cached per-thread in db.py, kept open for the process lifetime

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.FLASK_DEBUG)
