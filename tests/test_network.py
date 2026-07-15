from homehub import network


def test_nmcli_escaped_fields_and_wifi_status(monkeypatch):
    def fake_run(arguments, **_kwargs):
        joined = " ".join(arguments)
        if "CONNECTIVITY" in joined:
            return "full\n"
        if "device status" in joined:
            return "wlan0:wifi:connected:Farm\\: House\neth0:ethernet:disconnected:\n"
        return "*:Farm\\: House:82:WPA2\n"

    monkeypatch.setattr(network, "_run", fake_run)
    monkeypatch.setattr(network, "local_ipv4", lambda: "192.168.30.124")
    value = network.network_status()
    assert value["state"] == "online"
    assert value["type"] == "wifi"
    assert value["ssid"] == "Farm: House"
    assert value["signal"] == 82


def test_scan_deduplicates_and_orders_networks(monkeypatch):
    monkeypatch.setattr(network, "_run", lambda *_args, **_kwargs: (
        ":Guest:45:--\n*:Home:70:WPA2\n:Home:20:WPA2\n"
    ))
    value = network.scan_wifi()
    assert [item["ssid"] for item in value["networks"]] == ["Home", "Guest"]
    assert value["networks"][0]["active"] is True


def test_wifi_request_validation_never_accepts_short_secret():
    assert network.validate_wifi_request({"ssid": "Home", "password": "long-enough"})["ssid"] == "Home"
    try:
        network.validate_wifi_request({"ssid": "Home", "password": "short"})
    except ValueError as error:
        assert "8 characters" in str(error)
    else:
        raise AssertionError("short Wi-Fi password accepted")
