"""
Flask application factory + entrypoint.

Run with:  python app.py
(or `flask --app app run` / gunicorn app:app in production - see README)
"""
import hmac
from flask import Flask, request, Response, session

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

    # Optional HTTP Basic Auth gate — only active when both
    # BASIC_AUTH_USERNAME and BASIC_AUTH_PASSWORD are set (see config.py /
    # README "Deployment"). Off by default so local/dev use is unaffected.
    if config.BASIC_AUTH_USERNAME and config.BASIC_AUTH_PASSWORD:
        @app.before_request
        def _require_basic_auth():
            auth = request.authorization
            valid = (
                auth is not None
                and hmac.compare_digest(auth.username or "", config.BASIC_AUTH_USERNAME)
                and hmac.compare_digest(auth.password or "", config.BASIC_AUTH_PASSWORD)
            )
            if not valid:
                return Response(
                    "Authentication required.", 401,
                    {"WWW-Authenticate": 'Basic realm="Home Setup Dashboard"'},
                )

    @app.context_processor
    def inject_nav_categories():
        import repository as repo
        try:
            return {"nav_categories": repo.list_categories()}
        except Exception:
            return {"nav_categories": []}

    @app.context_processor
    def inject_current_actor():
        return {"current_actor": session.get("actor_name", "")}

    @app.context_processor
    def inject_pending_finds_count():
        import repository as repo
        try:
            return {"pending_finds_count": repo.count_pending_candidates()}
        except Exception:
            return {"pending_finds_count": 0}

    @app.teardown_appcontext
    def close_db(exception=None):
        pass  # connections are cached per-thread in db.py, kept open for the process lifetime

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.FLASK_DEBUG)
