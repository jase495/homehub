from __future__ import annotations

import base64
import io
import json
import os
import secrets
import socket
import subprocess
import threading
import time
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import qrcode
import qrcode.image.svg
from flask import Flask, Response, jsonify, redirect, request, send_from_directory
from google_auth_oauthlib.flow import Flow

from . import VERSION
from . import engine
from .config import CREDENTIALS_PATH, PACKAGE_ROOT, STATE_DIR, TOKEN_PATH, load_config, save_config
from .discovery import local_ipv4, scan_weather_lan
from .updater import check_release

SCOPES = engine.SCOPES
DASHBOARD = PACKAGE_ROOT / "frontend" / "dashboard"
SETUP = PACKAGE_ROOT / "frontend" / "setup"
OAUTH_LOCK = threading.Lock()
OAUTH_FLOW: Flow | None = None
OAUTH_SERVER: HTTPServer | None = None


def setup_url() -> str:
    return f"http://{local_ipv4()}:8080/setup/?token={load_config()['setup_token']}"


@lru_cache(maxsize=4)
def _qr_for_url(url: str) -> str:
    image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage)
    buffer = io.BytesIO()
    image.save(buffer)
    return "data:image/svg+xml;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def setup_qr_svg_data() -> str:
    return _qr_for_url(setup_url())


def token_authorized() -> bool:
    supplied = request.args.get("token") or request.headers.get("X-HomeHub-Setup-Token", "")
    return secrets.compare_digest(str(supplied), str(load_config()["setup_token"]))


def require_setup(function):
    def wrapped(*args, **kwargs):
        if not token_authorized():
            return jsonify(ok=False, error="Invalid or missing setup token"), 403
        return function(*args, **kwargs)
    wrapped.__name__ = function.__name__
    return wrapped


class OAuthCallback(BaseHTTPRequestHandler):
    def log_message(self, *_args: Any) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        global OAUTH_FLOW
        try:
            with OAUTH_LOCK:
                if OAUTH_FLOW is None:
                    raise RuntimeError("No Google authorization is pending")
                # Desktop OAuth loopback callbacks are explicitly HTTP. Restrict
                # the oauthlib exception to this callback instead of enabling it
                # for the whole application.
                os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
                OAUTH_FLOW.fetch_token(authorization_response=f"http://localhost:8765{self.path}")
                STATE_DIR.mkdir(parents=True, exist_ok=True)
                TOKEN_PATH.write_text(OAUTH_FLOW.credentials.to_json(), encoding="utf-8")
                os.chmod(TOKEN_PATH, 0o600)
                OAUTH_FLOW = None
            body = b"<h1>HomeHub connected</h1><p>You can close this tab and return to setup.</p>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            threading.Thread(target=engine.sync_data, daemon=True).start()
        except Exception as exc:
            body = f"<h1>Connection failed</h1><pre>{exc}</pre>".encode()
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


def start_google_oauth() -> str:
    global OAUTH_FLOW, OAUTH_SERVER
    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError("Upload the Google OAuth credentials JSON first")
    with OAUTH_LOCK:
        OAUTH_FLOW = Flow.from_client_secrets_file(
            str(CREDENTIALS_PATH), scopes=SCOPES, redirect_uri="http://localhost:8765/oauth2callback"
        )
        url, _ = OAUTH_FLOW.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
        if OAUTH_SERVER is None:
            OAUTH_SERVER = HTTPServer(("127.0.0.1", 8765), OAuthCallback)
            threading.Thread(target=OAUTH_SERVER.serve_forever, daemon=True, name="homehub-oauth").start()
        return url


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 1_000_000

    @app.after_request
    def no_cache(response: Response) -> Response:
        if request.path == "/" or request.path.endswith((".js", ".css", ".html")):
            response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    @app.get("/")
    def dashboard():
        return send_from_directory(DASHBOARD, "index.html")

    @app.get("/<path:name>")
    def dashboard_asset(name: str):
        return send_from_directory(DASHBOARD, name)

    @app.get("/setup/")
    def setup_page():
        return send_from_directory(SETUP, "index.html")

    @app.get("/setup/<path:name>")
    def setup_asset(name: str):
        return send_from_directory(SETUP, name)

    @app.get("/api/health")
    def health():
        return jsonify(ok=True, version=VERSION)

    @app.get("/api/data")
    def data():
        return jsonify(engine.current_data())

    @app.get("/api/setup/screen")
    def setup_screen():
        return jsonify(ok=True, url=setup_url(), qrSvg=setup_qr_svg_data(), ip=local_ipv4())

    @app.get("/api/setup/status")
    @require_setup
    def setup_status():
        cfg = load_config()
        live = engine.current_data()
        public = engine.public_config(cfg)
        public.update({
            "ok": True,
            "version": VERSION,
            "hostname": socket.gethostname(),
            "ip": local_ipv4(),
            "googleConnected": TOKEN_PATH.exists(),
            "credentialsUploaded": CREDENTIALS_PATH.exists(),
            "setupUrl": setup_url(),
            "weather": cfg.get("weather", {}),
            "calendar_ids": cfg.get("calendar_ids", []),
            "task_lists": cfg.get("task_lists", []),
            "calendars": live.get("calendars", []),
            "taskLists": live.get("taskLists", []),
            "updateConfig": cfg.get("updates", {}),
        })
        return jsonify(public)

    @app.post("/api/setup/credentials")
    @require_setup
    def credentials():
        content = (request.get_json(silent=True) or {}).get("content")
        if not isinstance(content, dict) or not any(key in content for key in ("installed", "web")):
            return jsonify(ok=False, error="That is not a Google OAuth client JSON file"), 400
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        CREDENTIALS_PATH.write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")
        os.chmod(CREDENTIALS_PATH, 0o600)
        return jsonify(ok=True)

    @app.post("/api/setup/google/start")
    @require_setup
    def google_start():
        try:
            return jsonify(ok=True, authorizationUrl=start_google_oauth(), callbackPort=8765)
        except Exception as exc:
            return jsonify(ok=False, error=str(exc)), 400

    @app.get("/api/setup/scan-weather")
    @require_setup
    def scan_weather():
        return jsonify(ok=True, stations=scan_weather_lan(), beta=True)

    @app.post("/api/setup/save")
    @require_setup
    def setup_save():
        payload = request.get_json(silent=True) or {}
        allowed = {key: payload[key] for key in ("title", "subtitle", "timezone", "sleep", "milestone", "weather", "calendar_ids", "event_calendar_id", "task_lists", "default_task_list") if key in payload}
        cfg = save_config(allowed)
        return jsonify(ok=True, config=engine.public_config(cfg))

    @app.post("/api/setup/restart-display")
    @require_setup
    def restart_display():
        subprocess.Popen(["sudo", "systemctl", "restart", "homehub-kiosk.service"])
        return jsonify(ok=True)

    @app.get("/api/setup/update/check")
    @require_setup
    def update_check():
        try:
            release = check_release()
            return jsonify(ok=True, current=VERSION, available=bool(release), version=release.version if release else None)
        except Exception as exc:
            return jsonify(ok=False, error=str(exc)), 400

    @app.post("/api/setup/update/install")
    @require_setup
    def update_install():
        version = str((request.get_json(silent=True) or {}).get("version", ""))
        if not version:
            return jsonify(ok=False, error="Choose a verified release first"), 400
        unit = f"homehub-update-{int(time.time())}"
        subprocess.Popen(["sudo", "/usr/local/sbin/homehub-queue-update", version])
        return jsonify(ok=True, started=True, version=version), 202

    @app.post("/api/setup/reboot")
    @require_setup
    def reboot():
        subprocess.Popen(["sudo", "reboot"])
        return jsonify(ok=True)

    @app.post("/api/task/complete")
    def task_complete():
        payload = request.get_json(silent=True) or {}
        return _engine_result(engine.complete_task, payload.get("taskListId", ""), payload.get("taskId", ""))

    @app.post("/api/task")
    def task_create():
        return _engine_result(engine.create_task, request.get_json(silent=True) or {}, created=True)

    @app.post("/api/event")
    def event_create():
        return _engine_result(engine.create_event, request.get_json(silent=True) or {}, created=True)

    @app.post("/api/settings")
    def settings():
        return _engine_result(engine.update_settings, request.get_json(silent=True) or {})

    return app


def _engine_result(function, *args, created: bool = False):
    try:
        data = function(*args)
        return jsonify(ok=True, data=data), 201 if created else 200
    except Exception as exc:
        return jsonify(ok=False, error=str(exc)), 400


def sync_loop() -> None:
    while True:
        try:
            engine.sync_data()
        except Exception as exc:
            engine.write_failure(str(exc))
        time.sleep(max(30, int(load_config().get("sync_seconds", 60))))


def main() -> None:
    load_config()
    threading.Thread(target=sync_loop, daemon=True, name="homehub-sync").start()
    create_app().run(host="0.0.0.0", port=8080, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
