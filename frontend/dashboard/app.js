(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const el = Object.fromEntries([
    "appTitle","appSubtitle","prevMonth","todayButton","nextMonth","monthTitle","addEvent","settings","clockTime","clockDate","milestone","calendarGrid","calendarLegend","weatherCard","weatherStatus","weatherItems","addTask","tasksList","completedToggle","completedLabel","completedChevron","completedList","statusDot","statusText","updatedText","sleepText","detailsModal","detailsColor","detailsTitle","detailsTime","detailsCalendar","detailsLocation","eventModal","eventTitle","dateMinus","datePlus","eventDateLabel","timeField","timeMinus","timePlus","eventTimeLabel","durations","calendarSelect","eventKeyboard","saveEvent","taskModal","taskTitle","taskListSelect","taskDueChoices","taskKeyboard","saveTask","settingsModal","sleepEnabled","sleepOff","sleepOn","saveSettings","setupQr","setupUrl","toast"
  ].map(id => [id, $(id)]));

  const state = {
    data: {events:[],tasks:[],completedTasks:[],calendars:[],writableCalendars:[],taskLists:[],weather:{items:[]}},
    anchor: firstOfMonth(new Date()), eventDate: new Date(), eventStartMinutes: 540,
    eventDuration: 60, eventAllDay: false, eventShift: false, taskShift: false,
    taskDue: "", completedOpen: false, navResetTimer: null, toastTimer: null
  };

  function firstOfMonth(d){ return new Date(d.getFullYear(), d.getMonth(), 1); }
  function dateKey(d){ return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`; }
  function parseEventDate(value, allDay){ if(!value)return null; if(allDay&&/^\d{4}-\d{2}-\d{2}$/.test(value)){const [y,m,d]=value.split("-").map(Number);return new Date(y,m-1,d);} return new Date(value); }
  function gridStart(anchor){ const d=firstOfMonth(anchor), offset=(d.getDay()+6)%7; d.setDate(d.getDate()-offset); d.setHours(0,0,0,0); return d; }
  function escapeMinutes(m){ return (m+1440)%1440; }
  function timeLabel(m){ const d=new Date(2000,0,1,Math.floor(m/60),m%60); return d.toLocaleTimeString("en-AU",{hour:"numeric",minute:"2-digit"}); }
  function nextHalfHour(){ const d=new Date(); return escapeMinutes((d.getHours()*60+d.getMinutes()+29)-((d.getHours()*60+d.getMinutes()+29)%30)); }
  function sameDay(a,b){ return dateKey(a)===dateKey(b); }

  function eventsForDay(day){
    const start=new Date(day); start.setHours(0,0,0,0); const end=new Date(start); end.setDate(end.getDate()+1);
    return (state.data.events||[]).filter(event=>{const s=parseEventDate(event.start,event.allDay);let e=parseEventDate(event.end,event.allDay);if(!s)return false;if(!e||e<=s){e=new Date(s);e.setMinutes(e.getMinutes()+1);}return s<end&&e>start;});
  }

  function renderCalendar(){
    const currentMonth=state.anchor.getMonth(), today=new Date(), start=gridStart(state.anchor);
    el.monthTitle.textContent=state.anchor.toLocaleDateString("en-AU",{month:"long",year:"numeric"});
    el.calendarGrid.replaceChildren();
    for(let i=0;i<42;i++){
      const day=new Date(start); day.setDate(start.getDate()+i);
      const cell=document.createElement("div"); cell.className="day-cell";
      if(day.getMonth()!==currentMonth)cell.classList.add("outside"); if(sameDay(day,today))cell.classList.add("today");
      cell.addEventListener("click",e=>{if(!e.target.closest(".event-row"))openCreateEvent(day);});
      const num=document.createElement("div");num.className="day-number";num.textContent=day.getDate();cell.appendChild(num);
      const wrap=document.createElement("div");wrap.className="day-events";const events=eventsForDay(day);const limit=4;
      events.slice(0,limit).forEach(event=>{
        const button=document.createElement("button");button.className="event-row";
        const dot=document.createElement("span");dot.className="event-dot";dot.style.backgroundColor=event.color||"#4198ff";
        const text=document.createElement("span");text.className="event-text";
        const startDate=parseEventDate(event.start,event.allDay);const prefix=event.allDay?"":`${startDate?.toLocaleTimeString("en-AU",{hour:"numeric",minute:"2-digit"})||""} `;
        text.textContent=`${prefix}${event.title||"(No title)"}`;button.append(dot,text);button.addEventListener("click",e=>{e.stopPropagation();openDetails(event);});wrap.appendChild(button);
      });
      if(events.length>limit){const more=document.createElement("div");more.className="more-events";more.textContent=`+${events.length-limit} more`;wrap.appendChild(more);}
      cell.appendChild(wrap);el.calendarGrid.appendChild(cell);
    }
  }

  function renderLegend(){
    el.calendarLegend.replaceChildren();(state.data.calendars||[]).slice(0,6).forEach(c=>{const item=document.createElement("div");item.className="legend-item";const dot=document.createElement("span");dot.className="legend-dot";dot.style.backgroundColor=c.color||"#4198ff";const name=document.createElement("span");name.textContent=c.title||"Calendar";item.append(dot,name);el.calendarLegend.appendChild(item);});
  }

  function dueInfo(task){
    if(!task.due)return {text:"",cls:""}; const due=new Date(task.due); if(Number.isNaN(due.getTime()))return {text:"",cls:""};
    const d=new Date(due.getUTCFullYear(),due.getUTCMonth(),due.getUTCDate()), today=new Date();today.setHours(0,0,0,0);const delta=Math.round((d-today)/86400000);
    if(delta<0)return{text:"Overdue",cls:"overdue"};if(delta===0)return{text:"Today",cls:"today"};if(delta===1)return{text:"Tomorrow",cls:"tomorrow"};return{text:d.toLocaleDateString("en-AU",{weekday:"short",day:"numeric",month:"short"}),cls:""};
  }

  function renderTasks(){
    const tasks=state.data.tasks||[];el.tasksList.replaceChildren();
    if(!tasks.length){const empty=document.createElement("div");empty.className="empty-state";empty.textContent=state.data.status==="setup_required"?"Connect Google once and your family jobs will appear here.":"Nothing waiting. Nice work.";el.tasksList.appendChild(empty);}
    tasks.forEach(task=>{
      const row=document.createElement("div");row.className="task-row";const check=document.createElement("button");check.className="task-check";check.disabled=task.readOnly;check.addEventListener("click",()=>completeTask(task,check));
      const main=document.createElement("div");main.className="task-main";const title=document.createElement("div");title.className="task-title";title.textContent=task.title||"(Untitled task)";const list=document.createElement("div");list.className="task-list-name";list.textContent=task.list||"Tasks";main.append(title,list);
      const due=dueInfo(task);const dueEl=document.createElement("div");dueEl.className=`task-due ${due.cls}`;dueEl.textContent=due.text;row.append(check,main,dueEl);el.tasksList.appendChild(row);
    });
    const completed=state.data.completedTasks||[];el.completedLabel.textContent=`Completed tasks (${completed.length})`;el.completedList.replaceChildren();completed.forEach(task=>{const row=document.createElement("div");row.className="completed-row";const check=document.createElement("div");check.className="completed-check";check.textContent="✓";const main=document.createElement("div");main.className="task-main";const title=document.createElement("div");title.className="task-title";title.textContent=task.title||"Task";main.appendChild(title);const arrow=document.createElement("div");arrow.textContent="›";row.append(check,main,arrow);el.completedList.appendChild(row);});
    el.completedList.classList.toggle("hidden",!state.completedOpen);el.completedChevron.textContent=state.completedOpen?"⌃":"⌄";
  }

  async function completeTask(task,button){button.disabled=true;try{const result=await postJson("/api/task/complete",{taskListId:task.taskListId,taskId:task.id});applyData(result.data);showToast(`Done: ${task.title}`);}catch(err){button.disabled=false;showToast(err.message,true);}}



  function renderWeather(){
    const weather=state.data.weather||{}; const items=Array.isArray(weather.items)?weather.items:[];
    el.weatherItems.replaceChildren();
    const status=weather.status||"not_configured";
    el.weatherCard.className=`weather-card ${status}`;
    el.weatherStatus.textContent=({online:"Live",stale:"Stale",error:"Error",empty:"Empty",not_configured:"Not set",disabled:"Off"})[status]||"Weather";
    if(!items.length){
      const empty=document.createElement("div"); empty.className="weather-empty";
      empty.textContent=weather.error?`Weather: ${weather.error}`:(weather.summary||"Weather not configured yet");
      el.weatherItems.appendChild(empty); return;
    }
    items.slice(0,4).forEach(item=>{
      const tile=document.createElement("div"); tile.className=`weather-tile ${item.kind||""}`;
      const value=document.createElement("strong"); value.textContent=item.value||"--";
      const unit=document.createElement("span"); unit.className="weather-unit"; unit.textContent=item.unit||"";
      const label=document.createElement("small"); label.textContent=item.label||"Weather";
      const valueWrap=document.createElement("div"); valueWrap.append(value,unit);
      tile.append(valueWrap,label); el.weatherItems.appendChild(tile);
    });
  }

  function renderStatus(){
    const status=state.data.status||"stale";el.statusDot.className=`status-dot ${status}`;el.statusText.textContent=({online:"Live",stale:"Offline cache",setup_required:"Setup needed",starting:"Starting"})[status]||"Starting";
    el.updatedText.textContent=state.data.updatedAt?`Synced ${new Date(state.data.updatedAt).toLocaleTimeString("en-AU",{hour:"numeric",minute:"2-digit"})}`:(status==="setup_required"?"Google not connected":"Waiting for first sync");
    const sleep=state.data.config?.sleep||{enabled:true,off:"22:00",on:"06:00"};el.sleepText.textContent=sleep.enabled?`${clockLabel(sleep.off)} – ${clockLabel(sleep.on)}`:"Disabled";
  }
  function clockLabel(v){const [h,m]=String(v).split(":").map(Number);return new Date(2000,0,1,h,m).toLocaleTimeString("en-AU",{hour:"numeric",minute:"2-digit"});}

  function renderMilestone(){
    const m=state.data.config?.milestone;if(!m?.enabled||!m.date){el.milestone.classList.add("hidden");return;}const target=new Date(`${m.date}T00:00:00`),today=new Date();today.setHours(0,0,0,0);const days=Math.ceil((target-today)/86400000);if(days<0){el.milestone.classList.add("hidden");return;}el.milestone.textContent=days===0?`${m.label||"Milestone"} today`:`${m.label||"Milestone"} in ${days} days`;el.milestone.classList.remove("hidden");
  }

  function openDetails(event){
    el.detailsColor.style.backgroundColor=event.color||"#e4ad5f";el.detailsTitle.textContent=event.title||"(No title)";const s=parseEventDate(event.start,event.allDay),e=parseEventDate(event.end,event.allDay);
    if(event.allDay)el.detailsTime.textContent=s?s.toLocaleDateString("en-AU",{weekday:"long",day:"numeric",month:"long",year:"numeric"}):"All day";else el.detailsTime.textContent=`${s?.toLocaleDateString("en-AU",{weekday:"long",day:"numeric",month:"long"})||""} • ${s?.toLocaleTimeString("en-AU",{hour:"numeric",minute:"2-digit"})||""}${e?` – ${e.toLocaleTimeString("en-AU",{hour:"numeric",minute:"2-digit"})}`:""}`;
    el.detailsCalendar.textContent=event.calendar?`Calendar: ${event.calendar}`:"";el.detailsLocation.textContent=event.location?`Location: ${event.location}`:"";el.detailsModal.classList.remove("hidden");
  }

  function populateCalendars(){el.calendarSelect.replaceChildren();const list=state.data.writableCalendars||[];(list.length?list:[{id:"primary",title:"Primary calendar",primary:true}]).forEach(c=>{const o=document.createElement("option");o.value=c.id;o.textContent=c.title||"Calendar";if(c.primary)o.selected=true;el.calendarSelect.appendChild(o);});}
  function openCreateEvent(date=new Date()){if(state.data.status==="setup_required"){showToast("Connect Google first",true);return;}state.eventDate=new Date(date);state.eventDate.setHours(0,0,0,0);state.eventStartMinutes=nextHalfHour();state.eventDuration=60;state.eventAllDay=false;state.eventShift=false;el.eventTitle.value="";populateCalendars();renderEventForm();renderKeyboard(el.eventKeyboard,"event");el.eventModal.classList.remove("hidden");}
  function renderEventForm(){el.eventDateLabel.textContent=state.eventDate.toLocaleDateString("en-AU",{weekday:"short",day:"numeric",month:"short"});el.eventTimeLabel.textContent=timeLabel(state.eventStartMinutes);el.timeField.style.opacity=state.eventAllDay?".35":"1";el.timeMinus.disabled=state.eventAllDay;el.timePlus.disabled=state.eventAllDay;el.durations.querySelectorAll("button").forEach(b=>b.classList.toggle("selected",state.eventAllDay?b.dataset.duration==="allDay":Number(b.dataset.duration)===state.eventDuration));}

  function openCreateTask(){if(state.data.status==="setup_required"){showToast("Connect Google first",true);return;}el.taskTitle.value="";state.taskShift=false;state.taskDue="";el.taskListSelect.replaceChildren();const lists=state.data.taskLists||[];(lists.length?lists:[{id:"",title:"Tasks"}]).forEach(t=>{const o=document.createElement("option");o.value=t.id;o.textContent=t.title||"Tasks";el.taskListSelect.appendChild(o);});renderTaskDue();renderKeyboard(el.taskKeyboard,"task");el.taskModal.classList.remove("hidden");}
  function renderTaskDue(){el.taskDueChoices.querySelectorAll("button").forEach(b=>b.classList.toggle("selected",b.dataset.due===state.taskDue));}

  function renderKeyboard(container,type){
    const shift=type==="event"?state.eventShift:state.taskShift, rows=[["1","2","3","4","5","6","7","8","9","0"],["q","w","e","r","t","y","u","i","o","p"],["a","s","d","f","g","h","j","k","l"],["SHIFT","z","x","c","v","b","n","m","⌫"],["SPACE","-","'","CLEAR"]];container.replaceChildren();
    rows.forEach(keys=>{const row=document.createElement("div");row.className="keyboard-row";keys.forEach(key=>{const b=document.createElement("button");b.className="key";if(["SHIFT","⌫","CLEAR"].includes(key))b.classList.add("wide");if(key==="SPACE")b.classList.add("space");b.textContent=key==="SPACE"?"space":(shift&&/^[a-z]$/.test(key)?key.toUpperCase():key);b.addEventListener("click",()=>pressKey(type,key));row.appendChild(b);});container.appendChild(row);});
  }
  function pressKey(type,key){const input=type==="event"?el.eventTitle:el.taskTitle;const shiftKey=type==="event"?"eventShift":"taskShift";if(key==="SHIFT"){state[shiftKey]=!state[shiftKey];renderKeyboard(type==="event"?el.eventKeyboard:el.taskKeyboard,type);return;}if(key==="⌫"){input.value=input.value.slice(0,-1);return;}if(key==="CLEAR"){input.value="";return;}const char=key==="SPACE"?" ":(state[shiftKey]&&/^[a-z]$/.test(key)?key.toUpperCase():key);if(input.value.length<100)input.value+=char;if(state[shiftKey]&&/^[a-z]$/.test(key)){state[shiftKey]=false;renderKeyboard(type==="event"?el.eventKeyboard:el.taskKeyboard,type);}}

  async function saveEvent(){const title=el.eventTitle.value.trim();if(!title){showToast("Give the event a name",true);return;}setBusy(el.saveEvent,true,"Adding…");try{const result=await postJson("/api/event",{title,date:dateKey(state.eventDate),allDay:state.eventAllDay,startMinutes:state.eventStartMinutes,durationMinutes:state.eventDuration,calendarId:el.calendarSelect.value||"primary"});applyData(result.data);closeModal("eventModal");showToast(`Added: ${title}`);}catch(err){showToast(err.message,true);}finally{setBusy(el.saveEvent,false,"Add event");}}
  async function saveTask(){const title=el.taskTitle.value.trim();if(!title){showToast("Give the task a name",true);return;}let due="";const d=new Date();if(state.taskDue==="tomorrow")d.setDate(d.getDate()+1);if(state.taskDue)due=dateKey(d);setBusy(el.saveTask,true,"Adding…");try{const result=await postJson("/api/task",{title,taskListId:el.taskListSelect.value,due});applyData(result.data);closeModal("taskModal");showToast(`Added: ${title}`);}catch(err){showToast(err.message,true);}finally{setBusy(el.saveTask,false,"Add task");}}
  function setBusy(button,busy,label){button.disabled=busy;button.textContent=label;}

  function populateTimeSelect(select){select.replaceChildren();for(let m=0;m<1440;m+=30){const o=document.createElement("option");o.value=`${String(Math.floor(m/60)).padStart(2,"0")}:${String(m%60).padStart(2,"0")}`;o.textContent=timeLabel(m);select.appendChild(o);}}
  async function openSettings(){const s=state.data.config?.sleep||{enabled:true,off:"22:00",on:"06:00"};const off=s.off||"22:00",on=s.on||"06:00";el.sleepEnabled.checked=Boolean(s.enabled);el.sleepOff.value=off;el.sleepOn.value=on;[...el.sleepOff.options].forEach((o,i)=>{if(o.value===off)el.sleepOff.selectedIndex=i;});[...el.sleepOn.options].forEach((o,i)=>{if(o.value===on)el.sleepOn.selectedIndex=i;});el.settingsModal.classList.remove("hidden");requestAnimationFrame(()=>el.settingsModal.classList.add("ready"));try{const r=await fetch("/api/setup/screen",{cache:"force-cache"});const d=await r.json();el.setupQr.src=d.qrSvg;el.setupUrl.textContent=d.url;}catch(err){el.setupUrl.textContent="Open http://homehub.local:8080/setup/";}}
  async function saveSettings(){setBusy(el.saveSettings,true,"Saving…");try{const result=await postJson("/api/settings",{enabled:el.sleepEnabled.checked,off:el.sleepOff.value,on:el.sleepOn.value});applyData(result.data);closeModal("settingsModal");showToast("Screen schedule saved");}catch(err){showToast(err.message,true);}finally{setBusy(el.saveSettings,false,"Save settings");}}

  function updateClock(){const now=new Date();el.clockTime.textContent=now.toLocaleTimeString("en-AU",{hour:"numeric",minute:"2-digit"});el.clockDate.textContent=now.toLocaleDateString("en-AU",{weekday:"short",day:"numeric",month:"short",year:"numeric"});}
  function closeModal(id){$(id)?.classList.add("hidden");}
  function scheduleReturn(){clearTimeout(state.navResetTimer);state.navResetTimer=setTimeout(()=>{state.anchor=firstOfMonth(new Date());renderCalendar();},180000);}
  function applyData(data){state.data=data;el.appTitle.textContent=data.title||"HomeHub";el.appSubtitle.textContent=data.subtitle||"";el.appSubtitle.style.display=data.subtitle?"block":"none";renderCalendar();renderLegend();renderTasks();renderWeather();renderStatus();renderMilestone();}
  async function loadData(){try{const r=await fetch(`/api/data?t=${Date.now()}`,{cache:"no-store"});if(!r.ok)throw new Error(`HTTP ${r.status}`);applyData(await r.json());}catch(err){state.data.status="stale";renderStatus();console.error(err);}}
  async function postJson(url,payload){const r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});const data=await r.json().catch(()=>({}));if(!r.ok||data.ok===false)throw new Error(data.error||`Request failed (${r.status})`);return data;}
  function showToast(message,error=false){clearTimeout(state.toastTimer);el.toast.textContent=message;el.toast.className=`toast${error?" error":""}`;state.toastTimer=setTimeout(()=>el.toast.classList.add("hidden"),3500);}

  el.prevMonth.addEventListener("click",()=>{state.anchor=new Date(state.anchor.getFullYear(),state.anchor.getMonth()-1,1);renderCalendar();scheduleReturn();});
  el.nextMonth.addEventListener("click",()=>{state.anchor=new Date(state.anchor.getFullYear(),state.anchor.getMonth()+1,1);renderCalendar();scheduleReturn();});
  el.todayButton.addEventListener("click",()=>{state.anchor=firstOfMonth(new Date());renderCalendar();});el.addEvent.addEventListener("click",()=>openCreateEvent(new Date()));el.addTask.addEventListener("click",openCreateTask);el.settings.addEventListener("click",openSettings);
  el.completedToggle.addEventListener("click",()=>{state.completedOpen=!state.completedOpen;renderTasks();});document.querySelectorAll("[data-close]").forEach(b=>b.addEventListener("click",()=>closeModal(b.dataset.close)));
  [el.detailsModal,el.eventModal,el.taskModal,el.settingsModal].forEach(m=>m.addEventListener("click",e=>{if(e.target===m)m.classList.add("hidden");}));
  el.dateMinus.addEventListener("click",()=>{state.eventDate.setDate(state.eventDate.getDate()-1);renderEventForm();});el.datePlus.addEventListener("click",()=>{state.eventDate.setDate(state.eventDate.getDate()+1);renderEventForm();});el.timeMinus.addEventListener("click",()=>{state.eventStartMinutes=escapeMinutes(state.eventStartMinutes-30);renderEventForm();});el.timePlus.addEventListener("click",()=>{state.eventStartMinutes=escapeMinutes(state.eventStartMinutes+30);renderEventForm();});
  el.durations.addEventListener("click",e=>{const b=e.target.closest("button[data-duration]");if(!b)return;if(b.dataset.duration==="allDay")state.eventAllDay=true;else{state.eventAllDay=false;state.eventDuration=Number(b.dataset.duration);}renderEventForm();});el.taskDueChoices.addEventListener("click",e=>{const b=e.target.closest("button[data-due]");if(!b)return;state.taskDue=b.dataset.due;renderTaskDue();});
  el.saveEvent.addEventListener("click",saveEvent);el.saveTask.addEventListener("click",saveTask);el.saveSettings.addEventListener("click",saveSettings);
  populateTimeSelect(el.sleepOff);populateTimeSelect(el.sleepOn);updateClock();setInterval(updateClock,30000);loadData();setInterval(loadData,60000);
})();
