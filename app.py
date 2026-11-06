"""Property Maintenance Request Management System - Flask application.

Run:   python app.py        then open http://127.0.0.1:5000
"""

import os
import secrets
from datetime import timedelta
from pathlib import Path

from flask import Flask, g, jsonify, redirect, render_template, request, session

from constants import CATEGORIES, HOME_BY_ROLE
from database import close_db, get_db, init_db
from errors import ApiError
from ml.predictor import load_model
from routes.api import api

BASE_DIR = Path(__file__).resolve().parent
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _secret_key(instance_path: str) -> str:
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    key_file = Path(instance_path) / "secret.key"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32))
    return key_file.read_text().strip()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)
    app.config.from_mapping(
        DATABASE=os.path.join(app.instance_path, "maintenance.db"),
        SEED_DEMO=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    app.config.setdefault("SECRET_KEY", None)
    if not app.config["SECRET_KEY"]:
        app.config["SECRET_KEY"] = _secret_key(app.instance_path)

    init_db(app.config["DATABASE"])
    load_model()  # trains on first run if no saved model exists
    if app.config["SEED_DEMO"]:
        from seed import seed
        seed(app.config["DATABASE"])

    app.teardown_appcontext(close_db)
    app.register_blueprint(api)

    @app.before_request
    def load_user_and_guard():
        if request.endpoint == "static":
            return None
        g.user = None
        user_id = session.get("user_id")
        if user_id:
            row = get_db().execute(
                "SELECT * FROM users WHERE id = ? AND active = 1", (user_id,)
            ).fetchone()
            if row is None:
                session.clear()
            else:
                g.user = row
        # Cross-site forms cannot send application/json without a CORS preflight,
        # so requiring it for state-changing API calls blocks simple CSRF attacks.
        if (request.path.startswith("/api/") and request.method in UNSAFE_METHODS
                and not request.is_json):
            raise ApiError("Content-Type must be application/json", 415)
        return None

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    # ------------------------------------------------------------- pages ----
    def role_page(role, template):
        if g.user is None:
            return redirect("/")
        if g.user["role"] != role:
            return redirect(HOME_BY_ROLE[g.user["role"]])
        return render_template(template, user=g.user, categories=CATEGORIES)

    @app.get("/")
    def index():
        if g.user is not None:
            return redirect(HOME_BY_ROLE[g.user["role"]])
        return render_template("index.html", demo=app.config["SEED_DEMO"])

    @app.get("/tenant")
    def tenant_page():
        return role_page("tenant", "tenant.html")

    @app.get("/staff")
    def staff_page():
        return role_page("staff", "staff.html")

    @app.get("/manager")
    def manager_page():
        return role_page("manager", "manager.html")

    # ----------------------------------------------------------- errors ----
    @app.errorhandler(ApiError)
    def handle_api_error(err):
        return jsonify(error=err.message), err.status

    @app.errorhandler(404)
    def not_found(_err):
        if request.path.startswith("/api/"):
            return jsonify(error="Not found"), 404
        return render_template("error.html", code=404, message="Page not found"), 404

    @app.errorhandler(405)
    def bad_method(_err):
        return jsonify(error="Method not allowed"), 405

    @app.errorhandler(413)
    def too_large(_err):
        return jsonify(error="Request too large"), 413

    @app.errorhandler(500)
    def server_error(_err):
        if request.path.startswith("/api/"):
            return jsonify(error="Something went wrong on the server"), 500
        return render_template("error.html", code=500, message="Something went wrong"), 500

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
