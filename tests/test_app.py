import base64

from homehub.app import create_app


def test_health_and_inline_svg_qr():
    client = create_app().test_client()
    assert client.get("/api/health").status_code == 200
    assert client.get("/").status_code == 200
    assert client.get("/setup/").status_code == 200
    assert client.get("/setup/setup.css").status_code == 200
    assert client.get("/setup/setup.js").status_code == 200
    payload = client.get("/api/setup/screen").get_json()
    assert payload["ok"] is True
    assert payload["qrSvg"].startswith("data:image/svg+xml;base64,")
    svg = base64.b64decode(payload["qrSvg"].split(",", 1)[1])
    assert b"<svg" in svg


def test_setup_api_rejects_missing_token():
    client = create_app().test_client()
    assert client.get("/api/setup/status").status_code == 403


def test_weather_discovery_endpoint_has_been_removed():
    client = create_app().test_client()
    assert client.get("/api/setup/scan-weather").status_code == 404


def test_event_update_route(monkeypatch):
    monkeypatch.setattr(
        "homehub.app.engine.update_event",
        lambda event_id, payload: {"events": [{"id": event_id, "title": payload["title"]}]},
    )
    response = create_app().test_client().put("/api/event/event-1", json={"title": "Changed"})
    assert response.status_code == 200
    assert response.get_json()["data"]["events"][0] == {"id": "event-1", "title": "Changed"}
