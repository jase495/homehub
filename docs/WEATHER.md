# Ecowitt weather

HomeHub displays only the farm-useful essentials: current outdoor temperature,
today's observed high and low, rain today and rain this month. It can also show
inside temperature when the gateway supplies it.

Local mode probes the configured gateway's `get_livedata_info` endpoint. Cloud
mode uses Ecowitt API v3 `device/real_time` with application key, API key and
device MAC. Today's high/low come from an API-reported extrema when present;
otherwise HomeHub tracks the highest and lowest sample it observes each local
day in `/var/lib/homehub/weather-extrema.json`.

LAN discovery is beta because gateway generations and firmware expose different
protocols. The setup wizard scans common HTTP endpoints, but manual IP and cloud
fallback are the supported recovery paths. A gateway returning HTTP 404 should
be configured with its base URL; HomeHub appends the known live-data path.

