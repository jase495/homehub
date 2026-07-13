(() => {
  "use strict";
  const byId = id => document.getElementById(id);
  const query = new URLSearchParams(location.search);
  const token = query.get("token") || localStorage.homehubSetupToken || "";
  if (token) localStorage.homehubSetupToken = token;
  let status = {};
  let availableUpdate = null;

  async function api(path, options = {}) {
    const join = path.includes("?") ? "&" : "?";
    const response = await fetch(`${path}${join}token=${encodeURIComponent(token)}`, {
      cache: "no-store",
      ...options,
      headers: {"Content-Type": "application/json", ...(options.headers || {})},
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  }

  function message(text, error = false) {
    byId("message").textContent = text;
    byId("message").classList.toggle("error", error);
  }

  function renderProgress() {
    const choicesReady = Boolean((status.calendar_ids || []).length || (status.task_lists || []).length);
    const steps = [
      [true, "HomeHub online", status.hostname || "Appliance reachable"],
      [status.credentialsUploaded, "Google credentials", status.credentialsUploaded ? "Uploaded" : "Required once"],
      [status.googleConnected, "Google connected", status.googleConnected ? "Calendar and Tasks ready" : "Approval required"],
      [choicesReady, "Content selected", choicesReady ? "Ready for the kitchen" : "Choose calendars and lists"],
    ];
    byId("progress").replaceChildren(...steps.map(([done, title, detail]) => {
      const node = document.createElement("div");
      node.className = `progress-step ${done ? "done" : ""}`;
      const heading = document.createElement("strong");
      heading.textContent = `${done ? "Done" : "Next"}: ${title}`;
      const small = document.createElement("small");
      small.textContent = detail;
      node.append(heading, small);
      return node;
    }));
  }

  function renderChoices(id, items, selected, valueKey, labelKey) {
    const container = byId(id);
    container.replaceChildren();
    if (!items.length) {
      container.textContent = status.googleConnected ? "Waiting for the first sync." : "Connect Google first.";
      return;
    }
    for (const item of items) {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = item[valueKey];
      input.checked = !selected.length || selected.includes(item[valueKey]);
      label.append(input, document.createTextNode(item[labelKey]));
      container.append(label);
    }
  }

  function renderSelect(id, items, valueKey, labelKey, selected) {
    const select = byId(id);
    select.replaceChildren(...items.map(item => {
      const option = document.createElement("option");
      option.value = item[valueKey];
      option.textContent = item[labelKey];
      option.selected = item[valueKey] === selected || (!selected && item.primary);
      return option;
    }));
  }

  async function load() {
    try {
      status = await api("/api/setup/status");
      byId("connection").textContent = `${status.hostname} - ${status.ip}`;
      byId("googleStatus").textContent = status.googleConnected ? "Google connected" : "Google not connected";
      byId("googleStatus").style.color = status.googleConnected ? "var(--ok)" : "var(--bad)";
      byId("title").value = status.title || "HomeHub";
      byId("subtitle").value = status.subtitle || "";
      byId("timezone").value = status.timezone || "Australia/Brisbane";
      const sleep = status.sleep || {};
      byId("sleepEnabled").checked = sleep.enabled !== false;
      byId("sleepOff").value = sleep.off || "22:00";
      byId("sleepOn").value = sleep.on || "06:00";
      const milestone = status.milestone || {};
      byId("milestoneEnabled").checked = milestone.enabled === true;
      byId("milestoneLabel").value = milestone.label || "";
      byId("milestoneDate").value = milestone.date || "";
      byId("tunnelCommand").textContent = `ssh -L 8080:127.0.0.1:8080 -L 8765:127.0.0.1:8765 YOUR_PI_USER@homehub.local\nThen open: http://localhost:8080/setup/?token=${token}`;
      renderProgress();
      renderChoices("calendarChoices", status.calendars || [], status.calendar_ids || [], "id", "title");
      renderChoices("taskChoices", status.taskLists || [], status.task_lists || [], "title", "title");
      renderSelect("defaultCalendar", status.writableCalendars || [], "id", "title", status.event_calendar_id);
      renderSelect("defaultTaskList", status.taskLists || [], "title", "title", status.default_task_list);
      byId("versionStatus").textContent = `Installed HomeHub ${status.version}.`;
    } catch (error) {
      message(error.message, true);
    }
  }

  function selectedValues(container) {
    return [...byId(container).querySelectorAll("input:checked")].map(input => input.value);
  }

  byId("uploadCredentials").onclick = async () => {
    const file = byId("credentials").files[0];
    if (!file) return message("Choose the downloaded Google JSON first", true);
    try {
      await api("/api/setup/credentials", {method: "POST", body: JSON.stringify({content: JSON.parse(await file.text())})});
      message("Google credentials uploaded");
      await load();
    } catch (error) { message(error.message, true); }
  };

  byId("connectGoogle").onclick = async () => {
    try {
      const data = await api("/api/setup/google/start", {method: "POST", body: "{}"});
      window.open(data.authorizationUrl, "_blank");
      message("Google approval opened. Keep the two tunnel ports active for this one-time step.");
    } catch (error) { message(error.message, true); }
  };

  byId("save").onclick = async () => {
    const payload = {
      title: byId("title").value.trim() || "HomeHub",
      subtitle: byId("subtitle").value.trim(),
      timezone: byId("timezone").value.trim(),
      sleep: {enabled: byId("sleepEnabled").checked, off: byId("sleepOff").value, on: byId("sleepOn").value},
      milestone: {enabled: byId("milestoneEnabled").checked, label: byId("milestoneLabel").value.trim(), date: byId("milestoneDate").value},
      calendar_ids: selectedValues("calendarChoices"),
      event_calendar_id: byId("defaultCalendar").value,
      task_lists: selectedValues("taskChoices"),
      default_task_list: byId("defaultTaskList").value,
    };
    try {
      await api("/api/setup/save", {method: "POST", body: JSON.stringify(payload)});
      message("HomeHub settings saved");
      await load();
    } catch (error) { message(error.message, true); }
  };

  byId("checkUpdate").onclick = async () => {
    try {
      const data = await api("/api/setup/update/check");
      availableUpdate = data.available ? data : null;
      byId("installUpdate").disabled = !availableUpdate;
      byId("versionStatus").textContent = data.available ? `Verified update ${data.version} is available.` : `HomeHub ${data.current} is current.`;
    } catch (error) { message(error.message, true); }
  };

  byId("installUpdate").onclick = async () => {
    if (!availableUpdate || !confirm(`Install HomeHub ${availableUpdate.version}?`)) return;
    try {
      await api("/api/setup/update/install", {method: "POST", body: JSON.stringify({version: availableUpdate.version})});
      message("Verified update started. HomeHub will restart and roll back automatically if unhealthy.");
    } catch (error) { message(error.message, true); }
  };

  byId("restartDisplay").onclick = async () => {
    try { await api("/api/setup/restart-display", {method: "POST", body: "{}"}); }
    catch (error) { message(error.message, true); }
  };
  byId("reboot").onclick = async () => {
    if (confirm("Reboot HomeHub now?")) await api("/api/setup/reboot", {method: "POST", body: "{}"});
  };

  load();
})();
