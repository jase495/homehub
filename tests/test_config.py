from homehub.config import DEFAULT_CONFIG, deep_merge, load_config


def test_deep_merge_preserves_nested_defaults():
    merged = deep_merge(DEFAULT_CONFIG, {"sleep": {"off": "21:30"}})
    assert merged["sleep"] == {"enabled": True, "off": "21:30", "on": "06:00"}


def test_load_config_creates_setup_token():
    config = load_config()
    assert len(config["setup_token"]) >= 20
    assert config["title"] == "HomeHub"

