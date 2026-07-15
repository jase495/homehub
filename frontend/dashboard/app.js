(() => {
  "use strict";

  const byId = id => document.getElementById(id);
  const state = {
    data: null,
    viewDate: new Date(new Date().getFullYear(), new Date().getMonth(), 1),
    eventsByDay: new Map(),
    eventByKey: new Map(),
    selectedDay: null,
    editorDate: new Date(),
    editorMinutes: 9 * 60,
    editorDuration: 60,
    editingEvent: null,
    selectedCalendarId: "",
    eventDeleteArmed: false,
    taskDate: new Date(),
    editingTask: null,
    selectedTaskListId: "",
    taskDeleteArmed: false,
    activeText: null,
    completedOpen: false,
    setupInfo: null,
    availableVersion: null,
    installArmed: false,
    systemArmed: "",
    displayStatus: null,
    wakeRequested: false,
    promptedUpdate: "",
    toastTimer: null,
    refreshing: false,
    network: null,
    selectedNetwork: null,
    networkPassword: "",
  };

  const elements = {
    brandTitle: byId("brandTitle"),
    brandSubtitle: byId("brandSubtitle"),
    syncStatus: byId("syncStatus"),
    monthTitle: byId("monthTitle"),
    milestone: byId("milestone"),
    sleepSummary: byId("sleepSummary"),
    clockTime: byId("clockTime"),
    clockDate: byId("clockDate"),
    clockYear: byId("clockYear"),
    calendarGrid: byId("calendarGrid"),
    calendarLegend: byId("calendarLegend"),
    taskList: byId("taskList"),
    completedToggle: byId("completedToggle"),
    completedList: byId("completedList"),
    dayTitle: byId("dayTitle"),
    dayEvents: byId("dayEvents"),
    eventTitle: byId("eventTitle"),
    eventEditorEyebrow: byId("eventEditorEyebrow"),
    eventEditorTitle: byId("eventEditorTitle"),
    eventDateLabel: byId("eventDateLabel"),
    eventTimeGroup: byId("eventTimeGroup"),
    eventTimeLabel: byId("eventTimeLabel"),
    eventCalendarChoices: byId("eventCalendarChoices"),
    taskTitle: byId("taskTitle"),
    taskDateLabel: byId("taskDateLabel"),
    taskListChoices: byId("taskListChoices"),
    networkButton: byId("networkButton"),
    networkLabel: byId("networkLabel"),
    networkChoices: byId("networkChoices"),
    networkPassword: byId("networkPassword"),
    setupQr: byId("setupQr"),
    setupUrl: byId("setupUrl"),
    sleepEnabled: byId("sleepEnabled"),
    sleepOff: byId("sleepOff"),
    sleepOn: byId("sleepOn"),
    displayMethod: byId("displayMethod"),
    displayStatus: byId("displayStatus"),
    powerModeBadge: byId("powerModeBadge"),
    versionText: byId("versionText"),
    updateBadge: byId("updateBadge"),
    updateMessage: byId("updateMessage"),
    checkUpdate: byId("checkUpdate"),
    installUpdate: byId("installUpdate"),
    toast: byId("toast"),
  };

  function bindTap(node, handler) {
    if (!node) return;
    const eventName = window.PointerEvent ? "pointerup" : "click";
    node.addEventListener(eventName, event => {
      if (eventName === "pointerup" && event.pointerType === "mouse" && event.button !== 0) return;
      event.preventDefault();
      handler(event);
    }, {passive: false});
  }

  function addPressFeedback(node) {
    if (!window.PointerEvent || !node) return;
    node.addEventListener("pointerdown", event => {
      const target = event.target.closest("button,.day-cell");
      if (target) target.classList.add("is-pressed");
    }, {passive: true});
    ["pointerup", "pointercancel", "pointerleave"].forEach(name => {
      node.addEventListener(name, () => {
        node.querySelectorAll(".is-pressed").forEach(item => item.classList.remove("is-pressed"));
      }, {passive: true});
    });
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      cache: "no-store",
      ...options,
      headers: {"Content-Type": "application/json", ...(options.headers || {})},
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.error || `HomeHub request failed (${response.status})`);
    }
    return payload;
  }

  function showToast(message, error = false) {
    clearTimeout(state.toastTimer);
    elements.toast.textContent = message;
    elements.toast.classList.remove("hidden");
    elements.toast.classList.toggle("error", error);
    state.toastTimer = setTimeout(() => elements.toast.classList.add("hidden"), 3600);
  }

  function openModal(id) {
    const modal = byId(id);
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
  }

  function closeModal(id) {
    const modal = byId(id);
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
  }

  function copyDate(value) {
    return new Date(value.getFullYear(), value.getMonth(), value.getDate());
  }

  function dateFromKey(key) {
    const [year, month, day] = key.split("-").map(Number);
    return new Date(year, month - 1, day);
  }

  function dateKey(value) {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, "0");
    const day = String(value.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function parseEventDate(value, allDay = false) {
    if (!value) return new Date(0);
    if (allDay && /^\d{4}-\d{2}-\d{2}$/.test(value)) return dateFromKey(value);
    return new Date(value);
  }

  function formatTime(value) {
    return value.toLocaleTimeString("en-AU", {hour: "numeric", minute: "2-digit"}).replace(" ", " ");
  }

  function compactTime(event) {
    if (event.allDay) return "";
    const start = parseEventDate(event.start);
    const minutes = start.getMinutes() ? `:${String(start.getMinutes()).padStart(2, "0")}` : "";
    const hour = start.getHours();
    const suffix = hour >= 12 ? "p" : "a";
    const twelveHour = hour % 12 || 12;
    return `${twelveHour}${minutes}${suffix}`;
  }

  function readableDate(value, long = false) {
    return value.toLocaleDateString("en-AU", long
      ? {weekday: "long", day: "numeric", month: "long", year: "numeric"}
      : {weekday: "short", day: "numeric", month: "short"});
  }

  function eventKey(event) {
    return `${event.calendarId || ""}::${event.id || ""}`;
  }

  function rebuildEventIndex() {
    state.eventsByDay = new Map();
    state.eventByKey = new Map();
    for (const event of state.data?.events || []) {
      state.eventByKey.set(eventKey(event), event);
      const start = parseEventDate(event.start, event.allDay);
      const rawEnd = parseEventDate(event.end || event.start, event.allDay);
      const end = new Date(rawEnd.getTime() - 1);
      const cursor = copyDate(start);
      const finalDay = copyDate(end < start ? start : end);
      for (let count = 0; cursor <= finalDay && count < 366; count += 1) {
        const key = dateKey(cursor);
        if (!state.eventsByDay.has(key)) state.eventsByDay.set(key, []);
        state.eventsByDay.get(key).push(event);
        cursor.setDate(cursor.getDate() + 1);
      }
    }
    for (const events of state.eventsByDay.values()) {
      events.sort((left, right) => String(left.start || "").localeCompare(String(right.start || "")));
    }
  }

  function eventLimit() {
    if (window.innerHeight >= 960) return 6;
    if (window.innerHeight >= 820) return 5;
    return 4;
  }

  function renderCalendar() {
    const year = state.viewDate.getFullYear();
    const month = state.viewDate.getMonth();
    elements.monthTitle.textContent = state.viewDate.toLocaleDateString("en-AU", {month: "long", year: "numeric"});
    const monthStart = new Date(year, month, 1);
    const mondayOffset = (monthStart.getDay() + 6) % 7;
    const firstCell = new Date(year, month, 1 - mondayOffset);
    const today = dateKey(new Date());
    const fragment = document.createDocumentFragment();
    const limit = eventLimit();

    for (let index = 0; index < 42; index += 1) {
      const day = new Date(firstCell);
      day.setDate(firstCell.getDate() + index);
      const key = dateKey(day);
      const cell = document.createElement("div");
      cell.className = "day-cell";
      if (day.getMonth() !== month) cell.classList.add("other-month");
      if (key === today) cell.classList.add("today");
      cell.dataset.date = key;
      cell.setAttribute("role", "button");
      cell.setAttribute("aria-label", readableDate(day, true));

      const number = document.createElement("span");
      number.className = "day-number";
      number.textContent = String(day.getDate());
      cell.append(number);

      const compact = document.createElement("div");
      compact.className = "day-events-compact";
      const events = state.eventsByDay.get(key) || [];
      for (const event of events.slice(0, limit)) {
        const row = document.createElement("div");
        row.className = "event-line";
        const dot = document.createElement("span");
        dot.className = "event-dot";
        dot.style.backgroundColor = event.color || "#d49a55";
        const time = document.createElement("span");
        time.className = "event-time";
        time.textContent = compactTime(event);
        const name = document.createElement("span");
        name.className = "event-name";
        name.textContent = event.title || "(No title)";
        row.append(dot, time, name);
        compact.append(row);
      }
      if (events.length > limit) {
        const more = document.createElement("span");
        more.className = "event-more";
        more.textContent = `+${events.length - limit} more`;
        compact.append(more);
      }
      cell.append(compact);
      fragment.append(cell);
    }
    elements.calendarGrid.replaceChildren(fragment);
  }

  function renderLegend() {
    const fragment = document.createDocumentFragment();
    for (const calendar of state.data?.calendars || []) {
      const item = document.createElement("span");
      item.className = "legend-item";
      const dot = document.createElement("span");
      dot.className = "event-dot";
      dot.style.backgroundColor = calendar.color || "#d49a55";
      item.append(dot, document.createTextNode(calendar.title || "Calendar"));
      fragment.append(item);
    }
    elements.calendarLegend.replaceChildren(fragment);
  }

  function taskMeta(task) {
    const parts = [];
    if (task.list) parts.push(task.list);
    if (task.due) {
      const due = new Date(task.due);
      if (!Number.isNaN(due.getTime())) parts.push(`Due ${due.toLocaleDateString("en-AU", {day: "numeric", month: "short"})}`);
    }
    return parts.join(" - ");
  }

  function taskRow(task, completed = false) {
    const row = document.createElement("div");
    row.className = "task-row";
    if (completed) row.classList.add("completed-task-row");
    if (!completed) {
      const check = document.createElement("button");
      check.className = "task-check";
      check.dataset.taskId = task.id || "";
      check.dataset.taskListId = task.taskListId || "";
      check.setAttribute("aria-label", `Complete ${task.title || "task"}`);
      if (task.readOnly) check.disabled = true;
      row.append(check);
    }
    const copy = document.createElement("button");
    copy.className = "task-copy";
    copy.dataset.taskId = task.id || "";
    copy.dataset.taskListId = task.taskListId || "";
    const title = document.createElement("strong");
    title.textContent = task.title || "Untitled task";
    const meta = document.createElement("small");
    meta.textContent = taskMeta(task);
    copy.append(title, meta);
    row.append(copy);
    if (completed) {
      const restore = document.createElement("button");
      restore.className = "task-restore";
      restore.dataset.taskId = task.id || "";
      restore.dataset.taskListId = task.taskListId || "";
      restore.textContent = "Undo";
      row.append(restore);
      const remove = document.createElement("button");
      remove.className = "task-remove";
      remove.dataset.taskId = task.id || "";
      remove.dataset.taskListId = task.taskListId || "";
      remove.textContent = "Delete";
      row.append(remove);
    }
    return row;
  }

  function renderTasks() {
    const tasks = state.data?.tasks || [];
    const completed = state.data?.completedTasks || [];
    if (!tasks.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      const title = document.createElement("strong");
      title.textContent = "Everything is done";
      const detail = document.createElement("span");
      detail.textContent = "Enjoy the quiet moment.";
      empty.append(title, detail);
      elements.taskList.replaceChildren(empty);
    } else {
      elements.taskList.replaceChildren(...tasks.map(task => taskRow(task)));
    }
    elements.completedToggle.textContent = `Completed tasks (${completed.length})`;
    elements.completedList.replaceChildren(...completed.map(task => taskRow(task, true)));
    elements.completedList.classList.toggle("hidden", !state.completedOpen);
  }

  function renderStatus() {
    const data = state.data || {};
    const status = data.status || "starting";
    let label = "Starting";
    let className = "offline";
    if (status === "online") {
      const updated = data.updatedAt ? new Date(data.updatedAt) : null;
      label = updated && !Number.isNaN(updated.getTime())
        ? `Live - synced ${formatTime(updated)}`
        : "Live";
      className = "";
    } else if (status === "stale") {
      label = "Offline cache";
      className = "stale";
    } else if (status === "setup_required") {
      label = "Google setup needed";
    }
    elements.syncStatus.className = `sync-status ${className}`.trim();
    elements.syncStatus.innerHTML = "";
    const dot = document.createElement("span");
    dot.className = "status-dot";
    elements.syncStatus.append(dot, document.createTextNode(label));
    elements.brandTitle.textContent = data.title || "HomeHub";
    elements.brandSubtitle.textContent = data.subtitle || "Calendar & Tasks";

    const sleep = data.config?.sleep || {};
    elements.sleepSummary.textContent = sleep.enabled === false
      ? "Screen always on"
      : `Screen off ${displayClockValue(sleep.off || "22:00")} - ${displayClockValue(sleep.on || "06:00")}`;
    renderMilestone();
  }

  function renderMilestone() {
    const milestone = state.data?.config?.milestone || {};
    if (!milestone.enabled || !milestone.date) {
      elements.milestone.classList.add("hidden");
      return;
    }
    const target = dateFromKey(milestone.date);
    const days = Math.ceil((copyDate(target) - copyDate(new Date())) / 86400000);
    elements.milestone.textContent = days >= 0
      ? `${milestone.label || "Milestone"} in ${days} day${days === 1 ? "" : "s"}`
      : `${milestone.label || "Milestone"}`;
    elements.milestone.classList.remove("hidden");
  }

  function applyData(data) {
    state.data = data;
    rebuildEventIndex();
    renderCalendar();
    renderLegend();
    renderTasks();
    renderStatus();
    if (!byId("dayModal").classList.contains("hidden") && state.selectedDay) renderDayAgenda();
  }

  async function refreshData(silent = false) {
    if (state.refreshing) return;
    state.refreshing = true;
    try {
      applyData(await api("/api/data"));
    } catch (error) {
      if (!silent) showToast(error.message, true);
    } finally {
      state.refreshing = false;
    }
  }

  function renderClock() {
    const now = new Date();
    elements.clockTime.textContent = now.toLocaleTimeString("en-AU", {hour: "numeric", minute: "2-digit"});
    elements.clockDate.textContent = now.toLocaleDateString("en-AU", {weekday: "long", day: "numeric", month: "long"});
    elements.clockYear.textContent = `\u00b7 ${now.toLocaleDateString("en-AU", {year: "numeric"})}`;
  }

  function eventTimeLabel(event) {
    if (event.allDay) return "All day";
    const start = parseEventDate(event.start);
    const end = parseEventDate(event.end);
    return `${formatTime(start)} - ${formatTime(end)}`;
  }

  function renderDayAgenda() {
    const events = state.eventsByDay.get(dateKey(state.selectedDay)) || [];
    elements.dayTitle.textContent = readableDate(state.selectedDay, true);
    if (!events.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      const title = document.createElement("strong");
      title.textContent = "Nothing planned";
      const detail = document.createElement("span");
      detail.textContent = "This day is clear.";
      empty.append(title, detail);
      elements.dayEvents.replaceChildren(empty);
      return;
    }

    const fragment = document.createDocumentFragment();
    for (const event of events) {
      const row = document.createElement("button");
      row.className = "day-event";
      row.dataset.eventKey = eventKey(event);
      const color = document.createElement("span");
      color.className = "day-event-color";
      color.style.backgroundColor = event.color || "#d49a55";
      const copy = document.createElement("span");
      copy.className = "day-event-copy";
      const title = document.createElement("strong");
      title.textContent = event.title || "(No title)";
      const meta = document.createElement("span");
      const details = [eventTimeLabel(event), event.calendar, event.location].filter(Boolean);
      meta.textContent = details.join(" - ");
      copy.append(title, meta);
      const action = document.createElement("span");
      action.className = "day-event-action";
      action.textContent = event.editable ? "Edit" : "View";
      row.append(color, copy, action);
      fragment.append(row);
    }
    elements.dayEvents.replaceChildren(fragment);
  }

  function openDay(day) {
    state.selectedDay = copyDate(day);
    renderDayAgenda();
    openModal("dayModal");
  }

  function setTextTarget(target, value = "") {
    state.activeText = target;
    target.textContent = value;
  }

  function createKeyboard(container, options = {}) {
    const rows = [
      ...(options.symbols ? [["@", ".", "_", "!", "#", "$", "%", "&", "+", "?"]] : []),
      ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
      ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
      ["A", "S", "D", "F", "G", "H", "J", "K", "L"],
      ["Z", "X", "C", "V", "B", "N", "M", "-", "'"],
      options.preserveCase ? ["Case", "Space", "Delete"] : ["Space", "Delete"],
    ];
    const fragment = document.createDocumentFragment();
    for (const keys of rows) {
      const row = document.createElement("div");
      row.className = "keyboard-row";
      for (const key of keys) {
        const button = document.createElement("button");
        button.className = "keyboard-key";
        if (key === "Space") button.classList.add("space");
        if (key === "Delete") button.classList.add("delete");
        if (key === "Case") button.classList.add("case");
        button.dataset.key = key;
        button.textContent = options.preserveCase && /^[A-Z]$/.test(key) ? key.toLowerCase() : key;
        row.append(button);
      }
      fragment.append(row);
    }
    container.replaceChildren(fragment);
    bindTap(container, event => {
      const key = event.target.closest("[data-key]")?.dataset.key;
      if (!key || !state.activeText) return;
      if (key === "Case") {
        options.uppercase = !options.uppercase;
        container.querySelectorAll("[data-key]").forEach(button => {
          if (/^[A-Z]$/.test(button.dataset.key)) {
            button.textContent = options.uppercase ? button.dataset.key : button.dataset.key.toLowerCase();
          }
        });
        return;
      }
      const current = state.activeText.textContent || "";
      if (key === "Delete") state.activeText.textContent = [...current].slice(0, -1).join("");
      else if (key === "Space") state.activeText.textContent = `${current} `;
      else if (options.preserveCase) {
        const character = /^[A-Z]$/.test(key) && !options.uppercase ? key.toLowerCase() : key;
        state.activeText.textContent = `${current}${character}`;
      }
      else state.activeText.textContent = `${current}${current.length ? key.toLowerCase() : key}`;
      if (state.activeText === elements.networkPassword) state.networkPassword = state.activeText.textContent || "";
    });
  }

  function renderEditorControls() {
    elements.eventDateLabel.textContent = readableDate(state.editorDate);
    elements.eventTimeLabel.textContent = minutesLabel(state.editorMinutes);
    const allDay = state.editorDuration === "allDay";
    elements.eventTimeGroup.classList.toggle("hidden", allDay);
    document.querySelectorAll("[data-duration]").forEach(button => {
      button.classList.toggle("selected", String(state.editorDuration) === button.dataset.duration);
    });
  }

  function populateEventCalendars(selectedId = "") {
    const calendars = state.data?.writableCalendars || [];
    const fragment = document.createDocumentFragment();
    for (const calendar of calendars) {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.calendarId = calendar.id;
      button.textContent = calendar.title || "Calendar";
      fragment.append(button);
    }
    state.selectedCalendarId = selectedId
      || calendars.find(calendar => calendar.primary)?.id
      || calendars[0]?.id
      || "";
    elements.eventCalendarChoices.replaceChildren(fragment);
    renderChoiceSelection(elements.eventCalendarChoices, "calendarId", state.selectedCalendarId);
  }

  function renderChoiceSelection(container, key, selected) {
    container.querySelectorAll(`[data-${key.replace(/[A-Z]/g, value => `-${value.toLowerCase()}`)}]`).forEach(button => {
      button.classList.toggle("selected", button.dataset[key] === selected);
    });
  }

  function openEventEditor(event = null, day = new Date()) {
    state.editingEvent = event;
    state.editorDate = event ? parseEventDate(event.start, event.allDay) : copyDate(day);
    state.editorMinutes = event && !event.allDay
      ? parseEventDate(event.start).getHours() * 60 + parseEventDate(event.start).getMinutes()
      : 9 * 60;
    if (event?.allDay) state.editorDuration = "allDay";
    else if (event) {
      const minutes = Math.round((parseEventDate(event.end) - parseEventDate(event.start)) / 60000);
      state.editorDuration = [30, 60, 90, 120, 180, 240].includes(minutes) ? minutes : 60;
    } else state.editorDuration = 60;
    elements.eventEditorEyebrow.textContent = event ? "Edit event" : "New event";
    elements.eventEditorTitle.textContent = event ? "Update calendar event" : "Add to calendar";
    byId("saveEvent").textContent = event ? "Save changes" : "Add event";
    byId("deleteEvent").classList.toggle("hidden", !event);
    byId("deleteEvent").textContent = "Delete";
    state.eventDeleteArmed = false;
    setTextTarget(elements.eventTitle, event?.title || "");
    populateEventCalendars(event?.calendarId || "");
    elements.eventCalendarChoices.classList.toggle("locked", Boolean(event));
    renderEditorControls();
    closeModal("dayModal");
    openModal("eventModal");
  }

  function minutesLabel(minutes) {
    const value = new Date(2000, 0, 1, Math.floor(minutes / 60), minutes % 60);
    return value.toLocaleTimeString("en-AU", {hour: "numeric", minute: "2-digit"});
  }

  function editorPayload() {
    return {
      title: elements.eventTitle.textContent.trim(),
      date: dateKey(state.editorDate),
      startMinutes: state.editorMinutes,
      durationMinutes: state.editorDuration === "allDay" ? 60 : Number(state.editorDuration),
      allDay: state.editorDuration === "allDay",
      calendarId: state.editingEvent?.calendarId || state.selectedCalendarId,
    };
  }

  function optimisticEvent(payload, original = null) {
    const calendar = (state.data?.calendars || []).find(item => item.id === payload.calendarId) || {};
    let start;
    let end;
    if (payload.allDay) {
      start = payload.date;
      const next = dateFromKey(payload.date);
      next.setDate(next.getDate() + 1);
      end = dateKey(next);
    } else {
      const day = dateFromKey(payload.date);
      day.setHours(Math.floor(payload.startMinutes / 60), payload.startMinutes % 60, 0, 0);
      start = day.toISOString();
      end = new Date(day.getTime() + payload.durationMinutes * 60000).toISOString();
    }
    return {
      id: original?.id || `pending-${Date.now()}`,
      title: payload.title,
      start,
      end,
      allDay: payload.allDay,
      location: original?.location || "",
      calendar: original?.calendar || calendar.title || "Calendar",
      calendarId: payload.calendarId,
      color: original?.color || calendar.color || "#d49a55",
      editable: true,
      pending: true,
    };
  }

  async function saveEvent() {
    const payload = editorPayload();
    if (!payload.title) return showToast("Enter an event name", true);
    if (!payload.calendarId) return showToast("No writable Google calendar is available", true);
    const original = state.editingEvent;
    const originalEvents = [...(state.data?.events || [])];
    const optimistic = optimisticEvent(payload, original);
    if (original) {
      state.data.events = originalEvents.map(event => eventKey(event) === eventKey(original) ? optimistic : event);
    } else {
      state.data.events = [...originalEvents, optimistic];
    }
    rebuildEventIndex();
    renderCalendar();
    const returnDay = copyDate(state.editorDate);
    closeModal("eventModal");
    openDay(returnDay);
    showToast(original ? "Saving changes" : "Adding event");
    try {
      const path = original ? `/api/event/${encodeURIComponent(original.id)}` : "/api/event";
      const method = original ? "PUT" : "POST";
      const response = await api(path, {method, body: JSON.stringify(payload)});
      applyData(response.data);
      showToast(original ? "Event updated" : "Event added");
    } catch (error) {
      state.data.events = originalEvents;
      rebuildEventIndex();
      renderCalendar();
      renderDayAgenda();
      showToast(error.message, true);
    }
  }

  async function deleteEvent() {
    const event = state.editingEvent;
    if (!event) return;
    const button = byId("deleteEvent");
    if (!state.eventDeleteArmed) {
      state.eventDeleteArmed = true;
      button.textContent = "Tap again to delete";
      setTimeout(() => {
        if (!state.eventDeleteArmed) return;
        state.eventDeleteArmed = false;
        button.textContent = "Delete";
      }, 6000);
      return;
    }
    state.eventDeleteArmed = false;
    button.disabled = true;
    try {
      const response = await api(`/api/event/${encodeURIComponent(event.id)}`, {
        method: "DELETE",
        body: JSON.stringify({calendarId: event.calendarId}),
      });
      applyData(response.data);
      closeModal("eventModal");
      openDay(state.selectedDay || state.editorDate);
      showToast("Event deleted");
    } catch (error) {
      button.disabled = false;
      button.textContent = "Delete";
      showToast(error.message, true);
    }
  }

  function populateTaskLists(selectedId = "") {
    const lists = state.data?.taskLists || [];
    state.selectedTaskListId = selectedId || lists[0]?.id || "";
    elements.taskListChoices.replaceChildren(...lists.map(list => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.taskListId = list.id;
      button.textContent = list.title || "Tasks";
      return button;
    }));
    renderChoiceSelection(elements.taskListChoices, "taskListId", state.selectedTaskListId);
  }

  function openTaskEditor(task = null) {
    if (task?.readOnly) return showToast("Assigned tasks are read-only in HomeHub");
    state.editingTask = task;
    const parsedDue = task?.due ? new Date(task.due) : null;
    state.taskDate = parsedDue && !Number.isNaN(parsedDue.getTime()) ? copyDate(parsedDue) : copyDate(new Date());
    setTextTarget(elements.taskTitle, task?.title || "");
    elements.taskDateLabel.textContent = readableDate(state.taskDate);
    populateTaskLists(task?.taskListId || "");
    elements.taskListChoices.classList.toggle("locked", Boolean(task));
    byId("taskEditorEyebrow").textContent = task ? "Edit task" : "New task";
    byId("taskEditorTitle").textContent = task ? "Update family job" : "Add a family job";
    byId("saveTask").textContent = task ? "Save changes" : "Add task";
    byId("deleteTask").classList.toggle("hidden", !task);
    byId("deleteTask").textContent = "Delete";
    state.taskDeleteArmed = false;
    openModal("taskModal");
  }

  async function saveTask() {
    const title = elements.taskTitle.textContent.trim();
    if (!title) return showToast("Enter a task name", true);
    const original = state.editingTask;
    const payload = {title, due: dateKey(state.taskDate), taskListId: original?.taskListId || state.selectedTaskListId};
    if (!payload.taskListId) return showToast("No Google Task list is available", true);
    const oldTasks = [...(state.data?.tasks || [])];
    const list = (state.data?.taskLists || []).find(item => item.id === payload.taskListId);
    const optimistic = {
      id: original?.id || `pending-${Date.now()}`,
      taskListId: payload.taskListId,
      title,
      due: `${payload.due}T00:00:00Z`,
      list: list?.title || "Tasks",
      pending: true,
    };
    state.data.tasks = original
      ? oldTasks.map(task => task.id === original.id && task.taskListId === original.taskListId ? optimistic : task)
      : [...oldTasks, optimistic];
    renderTasks();
    closeModal("taskModal");
    showToast(original ? "Saving task" : "Adding task");
    try {
      const path = original
        ? `/api/task/${encodeURIComponent(original.taskListId)}/${encodeURIComponent(original.id)}`
        : "/api/task";
      const response = await api(path, {method: original ? "PUT" : "POST", body: JSON.stringify(payload)});
      applyData(response.data);
      showToast(original ? "Task updated" : "Task added");
    } catch (error) {
      state.data.tasks = oldTasks;
      renderTasks();
      showToast(error.message, true);
    }
  }

  async function completeTask(button) {
    const taskId = button.dataset.taskId;
    const taskListId = button.dataset.taskListId;
    if (!taskId || !taskListId || button.classList.contains("pending")) return;
    const oldTasks = [...(state.data?.tasks || [])];
    const task = oldTasks.find(item => item.id === taskId && item.taskListId === taskListId);
    button.classList.add("pending");
    state.data.tasks = oldTasks.filter(item => !(item.id === taskId && item.taskListId === taskListId));
    if (task) state.data.completedTasks = [task, ...(state.data.completedTasks || [])];
    renderTasks();
    try {
      const response = await api("/api/task/complete", {
        method: "POST",
        body: JSON.stringify({taskId, taskListId}),
      });
      applyData(response.data);
    } catch (error) {
      state.data.tasks = oldTasks;
      if (task) state.data.completedTasks = (state.data.completedTasks || []).filter(item => item !== task);
      renderTasks();
      showToast(error.message, true);
    }
  }

  async function restoreTask(button) {
    const taskId = button.dataset.taskId;
    const taskListId = button.dataset.taskListId;
    if (!taskId || !taskListId || button.disabled) return;
    button.disabled = true;
    try {
      const response = await api("/api/task/restore", {
        method: "POST",
        body: JSON.stringify({taskId, taskListId}),
      });
      applyData(response.data);
      showToast("Task restored");
    } catch (error) {
      button.disabled = false;
      showToast(error.message, true);
    }
  }

  async function deleteTask() {
    const task = state.editingTask;
    if (!task) return;
    const button = byId("deleteTask");
    if (!state.taskDeleteArmed) {
      state.taskDeleteArmed = true;
      button.textContent = "Tap again to delete";
      setTimeout(() => {
        if (!state.taskDeleteArmed) return;
        state.taskDeleteArmed = false;
        button.textContent = "Delete";
      }, 6000);
      return;
    }
    state.taskDeleteArmed = false;
    button.disabled = true;
    try {
      const response = await api(`/api/task/${encodeURIComponent(task.taskListId)}/${encodeURIComponent(task.id)}`, {
        method: "DELETE",
        body: "{}",
      });
      applyData(response.data);
      closeModal("taskModal");
      showToast("Task deleted");
    } catch (error) {
      button.disabled = false;
      button.textContent = "Delete";
      showToast(error.message, true);
    }
  }

  async function deleteCompletedTask(button) {
    if (!button.dataset.armed) {
      button.dataset.armed = "true";
      button.textContent = "Confirm";
      setTimeout(() => { button.dataset.armed = ""; button.textContent = "Delete"; }, 6000);
      return;
    }
    try {
      const response = await api(`/api/task/${encodeURIComponent(button.dataset.taskListId)}/${encodeURIComponent(button.dataset.taskId)}`, {
        method: "DELETE",
        body: "{}",
      });
      applyData(response.data);
      showToast("Task deleted");
    } catch (error) {
      showToast(error.message, true);
    }
  }

  function displayClockValue(value) {
    const [hour, minute] = String(value || "00:00").split(":").map(Number);
    return new Date(2000, 0, 1, hour, minute).toLocaleTimeString("en-AU", {hour: "numeric", minute: "2-digit"});
  }

  function populateSleepSelect(select) {
    const fragment = document.createDocumentFragment();
    for (let minutes = 0; minutes < 1440; minutes += 30) {
      const option = document.createElement("option");
      option.value = `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
      option.textContent = displayClockValue(option.value);
      fragment.append(option);
    }
    select.replaceChildren(fragment);
  }

  async function ensureSetupInfo() {
    if (!state.setupInfo) state.setupInfo = await api("/api/setup/screen");
    elements.setupQr.src = state.setupInfo.qrSvg;
    elements.setupUrl.textContent = state.setupInfo.url;
    elements.versionText.textContent = `Installed HomeHub ${state.setupInfo.version}`;
    return state.setupInfo;
  }

  function renderNetworkStatus(network) {
    state.network = network;
    const online = network?.state === "online";
    const limited = network?.state === "limited";
    elements.networkButton.classList.toggle("online", online);
    elements.networkButton.classList.toggle("limited", limited);
    elements.networkButton.classList.toggle("offline", !online && !limited);
    elements.networkButton.classList.toggle("ethernet", network?.type === "ethernet");
    elements.networkLabel.textContent = network?.type === "ethernet"
      ? "Ethernet"
      : network?.ssid || (limited ? "Limited" : "Offline");
    byId("networkStateDot").className = `network-state-dot ${online ? "online" : limited ? "limited" : "offline"}`;
    byId("networkCurrentName").textContent = network?.type === "ethernet"
      ? `Ethernet · ${network.connection || "Connected"}`
      : network?.ssid || "Not connected";
    const detail = [
      network?.state === "online" ? "Internet connected" : network?.state === "limited" ? "Local network only" : "Offline",
      network?.signal != null ? `${network.signal}% signal` : "",
      network?.ip || "",
    ].filter(Boolean);
    byId("networkCurrentDetail").textContent = detail.join(" · ");
  }

  async function pollNetworkStatus(silent = true) {
    try {
      renderNetworkStatus(await api("/api/network/status"));
    } catch (error) {
      renderNetworkStatus({state: "offline", type: "offline"});
      if (!silent) showToast(error.message, true);
    }
  }

  function chooseNetwork(network) {
    state.selectedNetwork = network;
    state.networkPassword = "";
    setTextTarget(elements.networkPassword, "");
    byId("networkSelectedName").textContent = network.ssid;
    byId("networkPasswordSection").classList.toggle("hidden", !network.secured);
    byId("connectNetwork").disabled = false;
    elements.networkChoices.querySelectorAll("[data-ssid]").forEach(button => {
      button.classList.toggle("selected", button.dataset.ssid === network.ssid);
    });
  }

  async function scanNetworks() {
    const scanButton = byId("scanNetworks");
    scanButton.disabled = true;
    scanButton.textContent = "Scanning";
    elements.networkChoices.textContent = "Looking for Wi-Fi networks…";
    try {
      const setup = await ensureSetupInfo();
      const result = await api(`/api/setup/network/scan?token=${encodeURIComponent(setup.token)}`);
      elements.networkChoices.replaceChildren(...(result.networks || []).map(network => {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.ssid = network.ssid;
        const name = document.createElement("strong");
        name.textContent = network.ssid;
        const detail = document.createElement("span");
        detail.textContent = `${network.signal}% · ${network.secured ? network.security || "Secured" : "Open"}${network.active ? " · Connected" : ""}`;
        button.append(name, detail);
        button._network = network;
        return button;
      }));
      if (!(result.networks || []).length) elements.networkChoices.textContent = "No Wi-Fi networks found.";
    } catch (error) {
      elements.networkChoices.textContent = error.message;
      showToast(error.message, true);
    } finally {
      scanButton.disabled = false;
      scanButton.textContent = "Scan Wi-Fi";
    }
  }

  function openNetworkSettings() {
    state.selectedNetwork = null;
    byId("connectNetwork").disabled = true;
    byId("networkPasswordSection").classList.add("hidden");
    openModal("networkModal");
    pollNetworkStatus(false);
    scanNetworks();
  }

  async function connectNetwork() {
    if (!state.selectedNetwork) return;
    const password = elements.networkPassword.textContent || "";
    if (state.selectedNetwork.secured && password.length < 8) return showToast("Enter the Wi-Fi password", true);
    const button = byId("connectNetwork");
    button.disabled = true;
    button.textContent = "Connecting";
    try {
      const setup = await ensureSetupInfo();
      const result = await api(`/api/setup/network/connect?token=${encodeURIComponent(setup.token)}`, {
        method: "POST",
        body: JSON.stringify({ssid: state.selectedNetwork.ssid, password}),
      });
      elements.networkPassword.textContent = "";
      state.networkPassword = "";
      showToast(result.message || "HomeHub is switching Wi-Fi");
      setTimeout(() => pollNetworkStatus(false), 5000);
    } catch (error) {
      button.disabled = false;
      button.textContent = "Connect";
      showToast(error.message, true);
    }
  }

  function openSettings() {
    const sleep = state.data?.config?.sleep || {};
    elements.sleepEnabled.checked = sleep.enabled !== false;
    elements.sleepOff.value = sleep.off || "22:00";
    elements.sleepOn.value = sleep.on || "06:00";
    elements.displayMethod.value = sleep.method || "auto";
    elements.setupUrl.textContent = "Loading setup address";
    elements.updateMessage.textContent = "HomeHub only accepts signed releases and rolls back if an update fails.";
    elements.updateBadge.textContent = "Current";
    elements.updateBadge.classList.remove("available");
    elements.installUpdate.classList.add("hidden");
    state.installArmed = false;
    openModal("settingsModal");
    pollDisplayStatus();
    setTimeout(() => ensureSetupInfo().catch(error => {
      elements.setupUrl.textContent = error.message;
    }), 0);
  }

  async function saveSleepSettings() {
    try {
      const response = await api("/api/settings", {
        method: "POST",
        body: JSON.stringify({
          enabled: elements.sleepEnabled.checked,
          off: elements.sleepOff.value,
          on: elements.sleepOn.value,
          method: elements.displayMethod.value,
        }),
      });
      applyData(response.data);
      showToast("Screen schedule saved");
      await pollDisplayStatus();
      return true;
    } catch (error) {
      showToast(error.message, true);
      return false;
    }
  }

  async function checkForUpdate() {
    elements.checkUpdate.disabled = true;
    elements.checkUpdate.textContent = "Checking";
    elements.updateMessage.textContent = "Checking the signed HomeHub release channel.";
    try {
      const setup = await ensureSetupInfo();
      const result = await api(`/api/setup/update/check?token=${encodeURIComponent(setup.token)}`);
      state.availableVersion = result.available ? result.version : null;
      if (state.availableVersion) {
        elements.updateBadge.textContent = "Available";
        elements.updateBadge.classList.add("available");
        elements.updateMessage.textContent = `HomeHub ${state.availableVersion} is ready to install.`;
        elements.installUpdate.textContent = `Install ${state.availableVersion}`;
        elements.installUpdate.classList.remove("hidden");
      } else {
        elements.updateBadge.textContent = "Current";
        elements.updateBadge.classList.remove("available");
        elements.updateMessage.textContent = `HomeHub ${result.current} is up to date.`;
        elements.installUpdate.classList.add("hidden");
      }
    } catch (error) {
      elements.updateMessage.textContent = error.message;
      showToast(error.message, true);
    } finally {
      elements.checkUpdate.disabled = false;
      elements.checkUpdate.textContent = "Check for update";
    }
  }

  async function installUpdate(confirmed = false) {
    if (!state.availableVersion) return;
    if (!confirmed && !state.installArmed) {
      state.installArmed = true;
      elements.installUpdate.textContent = "Tap again to install";
      elements.updateMessage.textContent = "The display may restart. HomeHub will roll back automatically if the update is unhealthy.";
      setTimeout(() => {
        if (!state.installArmed) return;
        state.installArmed = false;
        elements.installUpdate.textContent = `Install ${state.availableVersion}`;
      }, 6000);
      return;
    }
    state.installArmed = false;
    elements.installUpdate.disabled = true;
    elements.installUpdate.textContent = "Starting update";
    try {
      const setup = await ensureSetupInfo();
      await api(`/api/setup/update/install?token=${encodeURIComponent(setup.token)}`, {
        method: "POST",
        body: JSON.stringify({version: state.availableVersion}),
      });
      elements.updateMessage.textContent = "Verified update started. HomeHub will restart when ready.";
      showToast("Update started");
    } catch (error) {
      elements.installUpdate.disabled = false;
      elements.installUpdate.textContent = `Install ${state.availableVersion}`;
      showToast(error.message, true);
    }
  }

  function displayModeLabel(status) {
    if (status?.mode === "away") return "Away";
    if (status?.mode === "sleep") return "Sleeping";
    return "Home";
  }

  function renderDisplayStatus(status) {
    state.displayStatus = status;
    state.wakeRequested = false;
    const mode = displayModeLabel(status);
    elements.powerModeBadge.textContent = mode;
    const method = status.activeMethod || status.configuredMethod || "automatic";
    elements.displayStatus.textContent = status.lastError
      ? `Not working: ${status.lastError}`
      : `${status.currentlyOff ? "Screen off" : "Screen on"} · ${method}`;
    elements.displayStatus.classList.toggle("error-copy", Boolean(status.lastError));
    if ((status.mode !== "home" || status.reason === "preview") && !status.currentlyOff) {
      byId("resumeEyebrow").textContent = status.mode === "away" ? "Away mode" : "HomeHub is sleeping";
      byId("resumeTitle").textContent = status.mode === "away" ? "Are you home again?" : "Welcome back";
      openModal("resumeOverlay");
    } else if (status.mode === "home") {
      closeModal("resumeOverlay");
    }
  }

  async function pollDisplayStatus() {
    try {
      renderDisplayStatus(await api("/api/display/status"));
    } catch (error) {
      elements.displayStatus.textContent = error.message;
      elements.displayStatus.classList.add("error-copy");
    }
  }

  async function displayAction(action) {
    try {
      const result = await api("/api/display/control", {
        method: "POST",
        body: JSON.stringify({action}),
      });
      renderDisplayStatus(result.display);
      if (action === "test") showToast("Screen will return in 10 seconds");
      if (action === "home") {
        closeModal("powerModal");
        closeModal("resumeOverlay");
        showToast("Home schedule resumed");
      }
      if (action === "sleep_now" || action === "away") {
        closeModal("powerModal");
        closeModal("settingsModal");
        showToast(action === "away" ? "Away mode enabled" : "Good night");
      }
      if (action === "end_peek") closeModal("resumeOverlay");
    } catch (error) {
      showToast(error.message, true);
    }
  }

  async function runSystemAction(action, button) {
    if (state.systemArmed !== action) {
      state.systemArmed = action;
      button.textContent = action === "reboot" ? "Tap again to reboot" : "Tap again to restart";
      setTimeout(() => {
        if (state.systemArmed !== action) return;
        state.systemArmed = "";
        button.textContent = action === "reboot" ? "Reboot HomeHub" : "Restart display";
      }, 6000);
      return;
    }
    state.systemArmed = "";
    button.disabled = true;
    button.textContent = action === "reboot" ? "Rebooting" : "Restarting";
    try {
      const setup = await ensureSetupInfo();
      await api(`/api/setup/${action === "reboot" ? "reboot" : "restart-display"}?token=${encodeURIComponent(setup.token)}`, {method: "POST", body: "{}"});
      showToast(action === "reboot" ? "HomeHub is rebooting" : "Display is restarting");
    } catch (error) {
      button.disabled = false;
      button.textContent = action === "reboot" ? "Reboot HomeHub" : "Restart display";
      showToast(error.message, true);
    }
  }

  async function pollUpdateStatus() {
    try {
      const result = await api("/api/update/status");
      if (!result.available || result.dismissed || state.promptedUpdate === result.version) return;
      if (document.querySelector(".modal:not(.hidden)")) return;
      state.availableVersion = result.version;
      state.promptedUpdate = result.version;
      byId("updatePromptTitle").textContent = `HomeHub ${result.version} is ready`;
      openModal("updatePrompt");
    } catch (_error) {
      // Periodic checks are deliberately quiet; manual checks show diagnostics.
    }
  }

  function moveDate(target, days) {
    target.setDate(target.getDate() + days);
  }

  function bindControls() {
    bindTap(byId("previousMonth"), () => {
      state.viewDate.setMonth(state.viewDate.getMonth() - 1);
      renderCalendar();
    });
    bindTap(byId("nextMonth"), () => {
      state.viewDate.setMonth(state.viewDate.getMonth() + 1);
      renderCalendar();
    });
    bindTap(byId("todayButton"), () => {
      const now = new Date();
      state.viewDate = new Date(now.getFullYear(), now.getMonth(), 1);
      renderCalendar();
    });
    bindTap(byId("addEventButton"), () => openEventEditor(null, new Date()));
    bindTap(byId("addTaskButton"), () => openTaskEditor(null));
    bindTap(elements.networkButton, openNetworkSettings);
    bindTap(byId("powerButton"), () => {
      openModal("powerModal");
      pollDisplayStatus();
    });
    bindTap(byId("settingsButton"), openSettings);
    bindTap(elements.calendarGrid, event => {
      const cell = event.target.closest(".day-cell");
      if (cell?.dataset.date) openDay(dateFromKey(cell.dataset.date));
    });
    bindTap(elements.dayEvents, event => {
      const row = event.target.closest("[data-event-key]");
      if (!row) return;
      const selected = state.eventByKey.get(row.dataset.eventKey);
      if (!selected) return;
      if (!selected.editable) return showToast("This calendar is read-only");
      openEventEditor(selected, state.selectedDay);
    });
    bindTap(byId("dayAddEvent"), () => openEventEditor(null, state.selectedDay || new Date()));
    bindTap(elements.taskList, event => {
      const button = event.target.closest(".task-check");
      if (button) return completeTask(button);
      const edit = event.target.closest(".task-copy");
      if (!edit) return;
      const task = (state.data?.tasks || []).find(item => item.id === edit.dataset.taskId && item.taskListId === edit.dataset.taskListId);
      if (task) openTaskEditor(task);
    });
    bindTap(elements.completedList, event => {
      const restore = event.target.closest(".task-restore");
      if (restore) return restoreTask(restore);
      const remove = event.target.closest(".task-remove");
      if (remove) return deleteCompletedTask(remove);
    });
    bindTap(elements.completedToggle, () => {
      state.completedOpen = !state.completedOpen;
      elements.completedList.classList.toggle("hidden", !state.completedOpen);
    });
    bindTap(byId("eventDateBack"), () => { moveDate(state.editorDate, -1); renderEditorControls(); });
    bindTap(byId("eventDateForward"), () => { moveDate(state.editorDate, 1); renderEditorControls(); });
    bindTap(byId("eventTimeBack"), () => { state.editorMinutes = (state.editorMinutes + 1410) % 1440; renderEditorControls(); });
    bindTap(byId("eventTimeForward"), () => { state.editorMinutes = (state.editorMinutes + 30) % 1440; renderEditorControls(); });
    bindTap(byId("durationRow"), event => {
      const value = event.target.closest("[data-duration]")?.dataset.duration;
      if (!value) return;
      state.editorDuration = value === "allDay" ? value : Number(value);
      renderEditorControls();
    });
    bindTap(elements.eventCalendarChoices, event => {
      if (state.editingEvent) return;
      const button = event.target.closest("[data-calendar-id]");
      if (!button) return;
      state.selectedCalendarId = button.dataset.calendarId;
      renderChoiceSelection(elements.eventCalendarChoices, "calendarId", state.selectedCalendarId);
    });
    bindTap(byId("saveEvent"), saveEvent);
    bindTap(byId("deleteEvent"), deleteEvent);
    bindTap(byId("taskDateBack"), () => { moveDate(state.taskDate, -1); elements.taskDateLabel.textContent = readableDate(state.taskDate); });
    bindTap(byId("taskDateForward"), () => { moveDate(state.taskDate, 1); elements.taskDateLabel.textContent = readableDate(state.taskDate); });
    bindTap(elements.taskListChoices, event => {
      if (state.editingTask) return;
      const button = event.target.closest("[data-task-list-id]");
      if (!button) return;
      state.selectedTaskListId = button.dataset.taskListId;
      renderChoiceSelection(elements.taskListChoices, "taskListId", state.selectedTaskListId);
    });
    bindTap(byId("saveTask"), saveTask);
    bindTap(byId("deleteTask"), deleteTask);
    bindTap(byId("scanNetworks"), scanNetworks);
    bindTap(elements.networkChoices, event => {
      const button = event.target.closest("[data-ssid]");
      if (button?._network) chooseNetwork(button._network);
    });
    bindTap(byId("connectNetwork"), connectNetwork);
    bindTap(byId("saveSleep"), saveSleepSettings);
    bindTap(byId("testDisplay"), async () => {
      if (await saveSleepSettings()) displayAction("test");
    });
    document.querySelectorAll("[data-display-action]").forEach(button => {
      bindTap(button, () => displayAction(button.dataset.displayAction));
    });
    bindTap(byId("resumeHome"), () => displayAction("home"));
    bindTap(byId("keepSleeping"), () => displayAction("end_peek"));
    bindTap(byId("restartDisplay"), () => runSystemAction("restart-display", byId("restartDisplay")));
    bindTap(byId("rebootHomeHub"), () => runSystemAction("reboot", byId("rebootHomeHub")));
    bindTap(elements.checkUpdate, checkForUpdate);
    bindTap(elements.installUpdate, () => installUpdate(false));
    bindTap(byId("updateLater"), async () => {
      closeModal("updatePrompt");
      try { await api("/api/update/later", {method: "POST", body: "{}"}); }
      catch (_error) { /* The prompt is still safely dismissed locally. */ }
    });
    bindTap(byId("updateNow"), () => {
      closeModal("updatePrompt");
      installUpdate(true);
    });
    document.querySelectorAll("[data-close]").forEach(button => bindTap(button, () => closeModal(button.dataset.close)));
    document.querySelectorAll(".text-entry").forEach(entry => bindTap(entry, () => { state.activeText = entry; }));
    addPressFeedback(document.body);

    document.addEventListener(window.PointerEvent ? "pointerup" : "click", event => {
      const status = state.displayStatus;
      if (!status?.currentlyOff || status.reason === "test" || state.wakeRequested) return;
      state.wakeRequested = true;
      event.preventDefault();
      event.stopImmediatePropagation();
      api("/api/display/control", {method: "POST", body: JSON.stringify({action: "peek"})})
        .then(() => setTimeout(pollDisplayStatus, 1200))
        .catch(() => { state.wakeRequested = false; });
    }, {capture: true, passive: false});
  }

  function initialise() {
    document.documentElement.style.setProperty("cursor", "none", "important");
    populateSleepSelect(elements.sleepOff);
    populateSleepSelect(elements.sleepOn);
    createKeyboard(byId("eventKeyboard"));
    createKeyboard(byId("taskKeyboard"));
    createKeyboard(byId("networkKeyboard"), {symbols: true, preserveCase: true});
    bindControls();
    renderClock();
    refreshData();
    pollDisplayStatus();
    pollNetworkStatus();
    setTimeout(pollUpdateStatus, 5000);
    setInterval(renderClock, 1000);
    setInterval(() => refreshData(true), 60000);
    setInterval(pollDisplayStatus, 5000);
    setInterval(() => pollNetworkStatus(true), 15000);
    setInterval(pollUpdateStatus, 60 * 1000);
    let resizeTimer;
    window.addEventListener("resize", () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(renderCalendar, 120);
    });
  }

  initialise();
})();
