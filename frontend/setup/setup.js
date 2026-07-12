(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const query = new URLSearchParams(location.search);
  const token = query.get("token") || localStorage.homehubSetupToken || "";
  if (token) localStorage.homehubSetupToken = token;
  let status = {};
  let weatherMode = "local";
  let availableUpdate = null;

  async function api(path, options = {}) {
    const join = path.includes("?") ? "&" : "?";
    const response = await fetch(`${path}${join}token=${encodeURIComponent(token)}`, {
      ...options,
      headers: {"Content-Type": "application/json", ...(options.headers || {})},
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  }

  function message(text, error = false) {
    $("message").textContent = text;
    $("message").classList.toggle("error", error);
  }

  function selectTab(mode) {
    weatherMode = mode;
    $("localWeather").classList.toggle("hidden", mode !== "local");
    $("cloudWeather").classList.toggle("hidden", mode !== "cloud");
    document.querySelectorAll("[data-tab]").forEach(button => button.classList.toggle("selected", button.dataset.tab === mode));
  }

  function renderProgress() {
    const steps = [
      [true, "HomeHub online", status.hostname || "Appliance reachable"],
      [status.credentialsUploaded, "Google credentials", status.credentialsUploaded ? "Uploaded" : "Required once"],
      [status.googleConnected, "Google connected", status.googleConnected ? "Calendar & Tasks ready" : "Approval required"],
      [status.weather?.source && status.weather.source !== "disabled", "Farm weather", status.weather?.source || "Optional"],
    ];
    $("progress").replaceChildren(...steps.map(([done, title, detail]) => {
      const node = document.createElement("div");
      node.className = `progress-step ${done ? "done" : ""}`;
      node.innerHTML = `<strong>${done ? "✓" : "○"} ${title}</strong><small>${detail}</small>`;
      return node;
    }));
  }

  function renderChoices(id, items, selected, valueKey, labelKey) {
    const container = $(id);
    container.replaceChildren();
    if (!items.length) {
      container.textContent = status.googleConnected ? "No items returned yet. Wait for the first sync." : "Connect Google first.";
      return;
    }
    items.forEach(item => {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = item[valueKey];
      input.checked = !selected.length || selected.includes(item[valueKey]);
      label.append(input, document.createTextNode(item[labelKey]));
      container.append(label);
    });
  }

  async function load() {
    try {
      status = await api("/api/setup/status");
      $("connection").textContent = `${status.hostname} • ${status.ip}`;
      $("googleStatus").textContent = status.googleConnected ? "Google connected" : "Google not connected";
      $("googleStatus").style.color = status.googleConnected ? "var(--ok)" : "var(--bad)";
      $("title").value = status.title || "HomeHub";
      $("subtitle").value = status.subtitle || "";
      $("timezone").value = status.timezone || "Australia/Brisbane";
      const sleep = status.sleep || {};
      $("sleepEnabled").checked = sleep.enabled !== false;
      $("sleepOff").value = sleep.off || "22:00";
      $("sleepOn").value = sleep.on || "06:00";
      const milestone = status.milestone || {};
      $("milestoneEnabled").checked = milestone.enabled === true;
      $("milestoneLabel").value = milestone.label || "";
      $("milestoneDate").value = milestone.date || "";
      const weather = status.weather || {};
      weatherMode = weather.source === "ecowitt_cloud" ? "cloud" : "local";
      selectTab(weatherMode);
      $("gatewayUrl").value = weather.ecowitt_local?.gateway_url || "";
      $("stationMac").value = weather.ecowitt_local?.mac || "";
      $("appKey").value = weather.ecowitt_cloud?.application_key || "";
      $("apiKey").value = weather.ecowitt_cloud?.api_key || "";
      $("cloudMac").value = weather.ecowitt_cloud?.mac || "";
      $("tunnelCommand").textContent = `ssh -L 8080:127.0.0.1:8080 -L 8765:127.0.0.1:8765 YOUR_PI_USER@homehub.local\nThen open: http://localhost:8080/setup/?token=${token}`;
      renderProgress();
      renderChoices("calendarChoices", status.calendars || [], status.calendar_ids || [], "id", "title");
      renderChoices("taskChoices", status.taskLists || [], status.task_lists || [], "title", "title");
      $("versionStatus").textContent = `Installed HomeHub ${status.version}.`;
    } catch (error) {
      message(error.message, true);
    }
  }

  function selectedValues(container) {
    return [...$(container).querySelectorAll("input:checked")].map(input => input.value);
  }

  $("uploadCredentials").onclick = async () => {
    const file = $("credentials").files[0];
    if (!file) return message("Choose the downloaded Google JSON first", true);
    try {
      await api("/api/setup/credentials", {method: "POST", body: JSON.stringify({content: JSON.parse(await file.text())})});
      message("Google credentials uploaded");
      await load();
    } catch (error) { message(error.message, true); }
  };

  $("connectGoogle").onclick = async () => {
    try {
      const data = await api("/api/setup/google/start", {method: "POST", body: "{}"});
      window.open(data.authorizationUrl, "_blank");
      message("Google approval opened. Keep the two SSH tunnel ports active for this one-time step.");
    } catch (error) { message(error.message, true); }
  };

  document.querySelectorAll("[data-tab]").forEach(button => button.onclick = () => selectTab(button.dataset.tab));

  $("scanWeather").onclick = async () => {
    $("scanWeather").disabled = true;
    $("scanWeather").textContent = "Scanning…";
    $("stations").replaceChildren();
    try {
      const data = await api("/api/setup/scan-weather");
      if (!data.stations.length) $("stations").textContent = "No compatible gateway answered. Enter its IP manually or use Ecowitt cloud.";
      data.stations.forEach(station => {
        const row = document.createElement("div");
        row.className = "station";
        row.innerHTML = `<div><strong>${station.model}</strong><small>${station.ip} ${station.endpoint}</small></div>`;
        const use = document.createElement("button");
        use.textContent = "Use this";
        use.onclick = () => { $("gatewayUrl").value = station.url; selectTab("local"); };
        row.append(use);
        $("stations").append(row);
      });
    } catch (error) { message(error.message, true); }
    finally { $("scanWeather").disabled = false; $("scanWeather").textContent = "Scan this network"; }
  };

  $("save").onclick = async () => {
    const weather = weatherMode === "cloud" ? {
      enabled: true, source: "ecowitt_cloud", refresh_seconds: 300,
      ecowitt_cloud: {application_key: $("appKey").value.trim(), api_key: $("apiKey").value.trim(), mac: $("cloudMac").value.trim(), base_url: "https://api.ecowitt.net/api/v3/device/real_time"},
      ecowitt_local: {gateway_url: ""},
    } : {
      enabled: true, source: $("gatewayUrl").value.trim() ? "ecowitt_local" : "disabled", refresh_seconds: 300,
      ecowitt_local: {gateway_url: $("gatewayUrl").value.trim(), mac: $("stationMac").value.trim()},
      ecowitt_cloud: status.weather?.ecowitt_cloud || {},
    };
    const payload = {
      title: $("title").value.trim() || "HomeHub", subtitle: $("subtitle").value.trim(), timezone: $("timezone").value.trim(),
      sleep: {enabled: $("sleepEnabled").checked, off: $("sleepOff").value, on: $("sleepOn").value},
      milestone: {enabled: $("milestoneEnabled").checked, label: $("milestoneLabel").value.trim(), date: $("milestoneDate").value},
      weather, calendar_ids: selectedValues("calendarChoices"), task_lists: selectedValues("taskChoices"),
    };
    try { await api("/api/setup/save", {method: "POST", body: JSON.stringify(payload)}); message("HomeHub settings saved"); await load(); }
    catch (error) { message(error.message, true); }
  };

  $("checkUpdate").onclick = async () => {
    try {
      const data = await api("/api/setup/update/check");
      availableUpdate = data.available ? data : null;
      $("installUpdate").disabled = !availableUpdate;
      $("versionStatus").textContent = data.available ? `Verified update ${data.version} is available.` : `HomeHub ${data.current} is current.`;
    } catch (error) { message(error.message, true); }
  };
  $("installUpdate").onclick = async () => {
    if (!availableUpdate) return;
    if (!confirm(`Install HomeHub ${availableUpdate.version}?`)) return;
    try { await api("/api/setup/update/install", {method: "POST", body: JSON.stringify({version: availableUpdate.version})}); message("Verified update started. HomeHub will restart and roll back automatically if unhealthy."); }
    catch (error) { message(error.message, true); }
  };
  $("restartDisplay").onclick = async () => { try { await api("/api/setup/restart-display", {method: "POST", body: "{}"}); } catch (error) { message(error.message, true); } };
  $("reboot").onclick = async () => { if (confirm("Reboot HomeHub now?")) await api("/api/setup/reboot", {method: "POST", body: "{}"}); };

  load();
})();
