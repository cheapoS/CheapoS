/* The conversation owns its execution details, streams, and approval controls. */
'use strict';
const CheapOSChatView = (() => {
  const inspectionTools=new Set(['read file','outline file','list files','search','get diff']);
  function operatorEvents(events) {
    return events.filter(e=>!['model','checkpoint','permission'].includes(e.kind)&&!(e.kind==='routing'&&!e.detail?.error));
  }
  function detailEvent(event,thinkingOpen=false) {
    const d=event.detail||{};
    if(event.kind==='generation') return thinkingMarkup(d,false,thinkingOpen);
    if(event.kind==='assistant') return `<div class="workflow-note">${messageText(typeof d==='string'?d:'')}</div>`;
    if(event.kind==='checks') return commandMarkup(d,{key:d.run_id||event.id,open:!d.passed});
    if(event.kind==='tool_error') return `<section class="workflow-failure"><strong>${esc(event.title||'Action could not finish')}</strong><p>${esc(d.error||'The action did not finish. See Technical logs for the retained diagnostic.')}</p></section>`;
    const action=CheapOSGuide.activityItem(event);
    const title=action?.title||event.title||'Action';
    const important=['review','review_coaching'].includes(event.kind)||Boolean(d.error||d.result?.error||d.result?.syntax_warning);
    return `<details class="workflow-event ${important?'needs-reading':''}" data-event="work-event-${esc(event.id)}" ${important?'open':''}><summary>${icon('chevron')}<span>${esc(title)}</span>${event.time?`<time>${new Date(event.time).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'})}</time>`:''}</summary>${d.result?.syntax_warning?`<p class="error">${esc(d.result.syntax_warning)}</p>`:''}${d.result?.error?`<p class="error">${esc(d.result.error)}</p>`:eventDetail(event)}</details>`;
  }
  function eventsMarkup(events) {
    const latestThinking=events.findLast(e=>e.kind==='generation'&&e.detail?.thinking);
    const blocks=[];let inspections=[];
    function flush() {
      if(!inspections.length)return;
      const names=[...new Set(inspections.map(e=>e.detail?.arguments?.path||e.detail?.arguments?.query).filter(Boolean))];
      blocks.push(`<details class="workflow-exploration" data-event="explore-${esc(inspections[0].id)}"><summary>${icon('search')}<span>Explored the project · ${inspections.length} action${inspections.length===1?'':'s'}${names.length?`<small>${esc(names.slice(-2).join(' · '))}</small>`:''}</span>${icon('chevron')}</summary>${inspections.map(e=>detailEvent(e)).join('')}</details>`);
      inspections=[];
    }
    for(const event of events) {
      if(event.kind==='tool'&&inspectionTools.has(event.title)&&!event.detail?.result?.error&&!event.detail?.result?.syntax_warning)inspections.push(event);
      else {flush();blocks.push(detailEvent(event,event===latestThinking));}
    }
    flush();return blocks.join('');
  }
  function stepMarkup(step,task,stream) {
    const live=step.live;
    const symbol=step.outcome==='live'?'<span class="spinner"></span>':icon(['failed','revision','pending'].includes(step.outcome)?'clock':'check');
    const role={worker:'Worker',reviewer:'Reviewer',coordinator:step.phase==='coordinator'?'Coordinator':'Chat model',planner:'Planner',controller:'cheapoS'}[step.role]||'cheapoS';
    const events=operatorEvents(step.events);
    const liveOutput=live&&task.check_stream?commandMarkup(task.check_stream,{live:true}):live&&stream?`<section class="workflow-stream" aria-label="Live ${role.toLowerCase()} output"><div class="stream-label"><span class="task-dot pulsing"></span>${stream.phase==='thinking'?'Thinking':stream.phase==='answer'?'Writing':'Waiting for output'}<span>Live</span></div><pre data-thinking="workflow-stream-${esc(stream.request_id||step.id)}">${esc(stream.thinking||stream.content||'Waiting for the next chunk…')}</pre>${stream.thinking&&stream.content?`<div class="workflow-note">${messageText(stream.content)}</div>`:''}</section>`:'';
    const liveText=live?String(task.check_stream?.output||stream?.content||stream?.thinking||'').trim():'';
    const preview=liveText?`<span class="workflow-preview">${esc((liveText.length>240?'…':'')+liveText.slice(-240))}</span>`:'';
    return `<details class="workflow-step ${live?'is-live':''} outcome-${step.outcome}" data-event="workflow-${esc(step.id)}" data-step="${esc(step.id)}" ${live||['failed','revision'].includes(step.outcome)?'open':''}><summary><span class="workflow-symbol">${symbol}</span><span class="workflow-heading"><strong>${esc(step.title)}</strong><span class="workflow-status" ${live?'data-live-status':''}>${esc(step.detail)}</span>${preview}${live&&step.activity?`<small class="workflow-last-action">Latest: ${esc(step.activity)}</small>`:''}</span>${live?`<span class="workflow-elapsed" data-work-elapsed>${step.elapsed}</span>`:''}<span class="workflow-toggle">Details ${icon('chevron')}</span></summary><div class="workflow-details"><div class="workflow-model"><span>${role}</span><strong>${esc(step.model||(task.demo?'Scripted local model':live?'Model selection pending':'Model identity unavailable'))}</strong></div>${liveOutput}${events.length>80?'<p class="small muted">Showing the latest 80 progress events. Earlier events remain in Technical logs.</p>':''}<div class="workflow-events">${eventsMarkup(events.slice(-80))||(!liveOutput?`<p class="small muted">${live?'Waiting for the first action…':'No additional actions were recorded.'}</p>`:'')}</div><button type="button" class="text-link workflow-log-link" data-workflow-logs>Routing &amp; request details in Technical logs ${icon('chevron')}</button></div></details>`;
  }
  function routingDetails(task) {
    const trace=CheapOSGuide.routingTraceView(task);
    if(!trace.rows.length&&!trace.historyNotice)return '';
    return `<details class="routing-trace" data-event="routing-log" id="routing-diagnostics"><summary>Routing &amp; request diagnostics · ${trace.rows.length} selection${trace.rows.length===1?'':'s'}</summary><p class="small muted">Newest selection and request first. These are task-wide diagnostics.</p>${trace.historyNotice?`<p class="small muted">${esc(trace.historyNotice)}</p>`:''}${[...trace.rows].reverse().map(r=>`<details data-event="route-${esc(r.id)}"><summary><strong>${esc(r.role)} · ${esc(r.selected||'No route selected')}</strong></summary><p>Requested: ${esc(r.requested)} · Selected: ${esc(r.selected||'none')}</p>${r.notice?`<p class="small muted">${esc(r.notice)}</p>`:''}<details data-event="route-candidates-${esc(r.id)}"><summary>Candidate checks (${r.candidates.length})</summary><ol>${r.candidates.map(c=>`<li>${esc(c)}</li>`).join('')}</ol></details><details data-event="route-requests-${esc(r.id)}"><summary>Requests (${r.attempts.length})</summary><ol>${[...r.attempts].reverse().map(a=>`<li>${esc(a)}</li>`).join('')}</ol></details><p>${esc(r.gateway)}</p></details>`).join('')}</details>`;
  }
  function message(entry,task,decision='') {
    if(entry.kind==='user') return `<article class="chat-message from-user ${entry.steer?'steer-bubble':''}" data-message="${entry.id}"><div class="chat-author"><strong>You</strong>${entry.steer?'<span>Follow-up while working</span>':''}</div><div class="chat-message-body">${messageText(entry.text)}</div></article>`;
    const steps=entry.steps, older=steps.length>4?steps.slice(0,-3):[], visible=older.length?steps.slice(-3):steps;
    if(!steps.length&&!entry.reply&&!decision&&!entry.live&&!entry.owner)return '';
    const history=older.length?`<details class="workflow-history" data-event="history-${entry.id}"><summary>${icon('clock')}Earlier steps${entry.itemTitle?' · '+esc(entry.itemTitle):''} <span>${older.length}</span>${icon('chevron')}</summary>${older.map(s=>stepMarkup(s,task,null)).join('')}</details>`:'';
    return `<article class="chat-message from-agent cheapos-response" data-message="${entry.id}"><div class="chat-author"><span class="cheapos-avatar"><img class="brand-icon" src="./brand-icon.svg" alt="" /></span><strong>cheapoS</strong>${entry.live?`<span class="response-live">${task.pending_approval?'Needs you':task.status==='stopping'?'Pausing':task.status==='waiting_retry'?'Waiting':entry.label||'Working'}</span>`:''}</div><div class="chat-message-body">${entry.itemTitle?`<h3 class="operation-item-title">${esc(entry.itemTitle)}</h3>`:''}${entry.intro?`<p class="orchestration-intro">${esc(entry.intro)}</p>`:''}${steps.length?`<div class="workflow" aria-label="cheapoS work for this message">${history}${visible.map(s=>stepMarkup(s,task,entry.stream)).join('')}</div>`:''}${entry.reply?`<div class="cheapos-answer">${messageText(entry.reply)}</div>`:''}${decision}${entry.owner?'<section data-operation-actions aria-label="Run actions"></section>':''}</div></article>`;
  }
  return {message,routingDetails};
})();

'use strict';
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => `<svg aria-hidden="true" focusable="false" tabindex="-1"><use href="#i-${name}"/></svg>`;
const taskBusy=task=>CheapOSBranchUI.isBusy(task);
const activeStatuses = new Set(['running', 'reviewing', 'waiting_approval', 'waiting_retry', 'stopping']);
const labels = {awaiting_reply:'Ready for your message',ready:'Ready to start',running:'cheapoS is working',reviewing:'Checking your changes',waiting_approval:'Command approval needed',waiting_retry:'Waiting for a free route',paused:'Paused',budget_paused:'Paused at a limit',interrupted:'Interrupted',error:'Needs attention',takeover_requested:'Takeover requested',approved:'Reviewer approved',completed:'Ready for your review'};
const state = {startup:{},token:'',config:{},projects:[],project:null,preferences:{limits:{dollars:0,reviewer_tokens:50000,iterations:5,worker_turns:40,output_tokens:2048}},sending:false,pendingSends:new Set(),startErrors:new Map(),admission:null,pausingTask:null,stoppingStartup:false,drafts:new Map(),gateway:{},gatewayModels:[],catalogRevision:-1,gatewayListener:null,tasks:[],task:null,selection:0,view:'chat',file:0,diff:'unified',run:-1,online:false,loading:false};
const money = value => '$' + Number(value || 0).toFixed(Number(value || 0) > 0 && value < .01 ? 4 : 2);
const date = value => new Date(value).toLocaleString([], {month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});
const basename = value => String(value).split('/').filter(Boolean).pop() || 'Repository';
let toastTimer;
function toast(message) { clearTimeout(toastTimer); $('#toast').textContent=message; $('#toast').classList.add('visible'); toastTimer=setTimeout(()=>$('#toast').classList.remove('visible'),5000); }
async function api(path, body) {
  const response = await fetch('/api' + path, body === undefined ? {cache:'no-store'} : {method:'POST',headers:{'Content-Type':'application/json','X-CheapOS-Token':state.token},body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw Object.assign(new Error(data.error || 'The local server could not complete this action'),{status:response.status,code:data.code,files:data.files});
  return data;
}
function dialog(html, cls='') {
  sidebarMenu?.close(false);
  const previous=document.activeElement, d=document.createElement('dialog'); d.className='modal '+cls; d.innerHTML=html; $('#overlay-root').append(d);
  d.addEventListener('close',()=>{d.remove();if(previous?.isConnected)previous.focus();else if(previous?.dataset.taskMenu)$$('[data-task-menu]').find(b=>b.dataset.taskMenu===previous.dataset.taskMenu)?.focus();else $('#rename-task')?.focus()});
  d.addEventListener('click',e=>{if(e.target===d){const r=d.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)d.close()}});
  $$('[data-close]',d).forEach(b=>b.onclick=()=>d.close()); d.showModal(); return d;
}
const modalHeader = (eyebrow,title) => `<div class="modal-header"><div><span class="eyebrow">${eyebrow}</span><h2>${title}</h2></div><button type="button" class="icon-btn" data-close aria-label="Close dialog">${icon('x')}</button></div>`;
async function formAction(form, operation) {
  const buttons=$$('button[type="submit"]',form); buttons.forEach(b=>b.disabled=true);
  const error=$('.form-error',form); if(error) error.textContent='';
  try { await operation(); } catch(e) { if(error)error.textContent=e.message;else toast(e.message); }
  finally {buttons.forEach(b=>b.disabled=false)}
}
const sidebarPrefs=(()=>{try{return JSON.parse(localStorage.getItem('cheapos-sidebar-groups'))||{}}catch{return {}}})();
function saveSidebarPrefs(){try{localStorage.setItem('cheapos-sidebar-groups',JSON.stringify(sidebarPrefs))}catch{}}
function renderSidebar() {
  $('#task-total').textContent=state.projects.length;
  const connection=CheapOSGuide.connectionNotice(state.readiness,state.gateway,state.preferences.execution,state.config);
  $('#connection-indicator').textContent=connection.tone==='attention'?'Needs attention':connection.tone==='checking'?'Checking…':'Configured';
  const groups=state.projects.map(project=>({project,tasks:state.tasks.filter(t=>!t.demo&&t.source===project.path)}));
  const demos=state.tasks.filter(t=>t.demo);if(demos.length)groups.push({project:{path:'demo',name:'Local demo'},tasks:demos});
  const filter=$('#history-menu');
  const view=state.historyView||'active';
  filter.innerHTML=icon(view==='trash'?'x':view==='archived'?'folder':'chat')+`<span>${{active:'Chats',archived:'Archived chats',trash:'Trash'}[view]}</span>`;
  filter.setAttribute('aria-label','Show chats: '+{active:'Active',archived:'Archived',trash:'Trash'}[view]);
  filter.onclick=()=>historyMenu(filter);
  const html=groups.map(({project,tasks})=>{
    const pref=sidebarPrefs[project.path]||{}, sorted=CheapOSGuide.sidebarOrder(tasks), shown=pref.more?sorted:sorted.slice(0,12);
    return `<div class="project-group"><div class="project-group-heading"><button class="icon-btn" data-collapse="${esc(project.path)}" aria-label="${pref.collapsed?'Expand':'Collapse'} ${esc(project.name||project.path)}" aria-expanded="${!pref.collapsed}">${icon('chevron')}</button><button class="project-label ${state.project?.path===project.path?'selected':''}" data-project="${esc(project.path)}" title="${esc(project.path)}">${icon('folder')}<span>${esc(CheapOSGuide.projectName({source:project.path,demo:project.path==='demo'}))}</span></button>${project.path!=='demo'?`<button class="task-menu-button" data-project-menu="${esc(project.path)}" aria-label="Project options for ${esc(project.name)}" aria-haspopup="menu" aria-expanded="false">⋯</button>`:''}</div>${pref.collapsed?'':shown.map(t=>`<div class="task-row"><button class="task ${state.task?.id===t.id?'active':''}" data-task="${t.id}" title="${esc(t.title)}"><span class="task-dot ${['approved','awaiting_reply'].includes(t.status)?'done':''} ${taskBusy(t)?'pulsing':''}"></span><span class="task-list-title">${t.pinned?'★ ':''}${esc(t.title)}${t.trashed_at?`<small>Deleted ${esc(date(t.trashed_at))} · ${t.saved_change_count||0} saved changes${t.trash_archived_at?' · from Archived':''}</small>`:''}</span>${['error','budget_paused','waiting_approval'].includes(t.status)?'<span class="task-attention" aria-label="Needs attention">•</span>':''}</button><button class="task-menu-button" data-task-menu="${t.id}" aria-label="Options for ${esc(t.title)}" aria-haspopup="menu" aria-expanded="false">⋯</button></div>`).join('')+(!sorted.length?`<p class="project-empty">${view==='trash'?'No trashed chats':view==='archived'?'No archived chats':'No chats yet'}</p>`:'')+(sorted.length>12?`<button class="text-link show-more" data-more="${esc(project.path)}">${pref.more?'Show fewer':`Show more (${sorted.length-12})`}</button>`:'')}</div>`;
  }).join('');
  const list=$('#task-list');
  // Keep the existing DOM (and keyboard focus) when only live usage changed.
  if(list.dataset.rendered===html)return;
  const focused=document.activeElement, focusKey=focused?.getAttribute('data-task-menu')||focused?.getAttribute('data-task');
  const wasMenu=focused?.hasAttribute('data-task-menu');
  list.innerHTML=html;list.dataset.rendered=html;
  $$('[data-project-menu]').forEach(b=>b.onclick=()=>projectMenu(b.dataset.projectMenu,b));
  $$('[data-task]').forEach(b=>b.onclick=()=>selectTask(b.dataset.task));
  $$('[data-task-menu]').forEach(b=>b.onclick=()=>taskMenu(state.tasks.find(t=>t.id===b.dataset.taskMenu),b));
  $$('[data-project]').forEach(b=>b.onclick=()=>b.dataset.project==='demo'?selectTask(demos[0].id):chooseProject(state.projects.find(p=>p.path===b.dataset.project),true));
  for(const [attr,key] of [['collapse','collapsed'],['more','more']])$$('[data-'+attr+']').forEach(b=>b.onclick=()=>{const path=b.dataset[attr];sidebarPrefs[path]||={};sidebarPrefs[path][key]=!sidebarPrefs[path][key];saveSidebarPrefs();renderSidebar();$$("[data-"+attr+"]").find(el=>el.dataset[attr]===path)?.focus()});
  if(sidebarMenu){const anchor=findMenuAnchor(sidebarMenu.key);if(anchor)anchor.setAttribute('aria-expanded','true');else sidebarMenu.close(false)}
  if(focusKey)$$(wasMenu?'[data-task-menu]':'[data-task]').find(el=>(wasMenu?el.dataset.taskMenu:el.dataset.task)===focusKey)?.focus({preventScroll:true});
}
async function pauseForLifecycle(task) {
  if(taskBusy(task)){
    await api('/tasks/'+task.id+'/stop',{});
    const deadline=Date.now()+190000;
    while(Date.now()<deadline){
      const latest=await api('/tasks/'+task.id);
      if(!taskBusy(latest))break;
      await new Promise(resolve=>setTimeout(resolve,300));
    }
  }
 }
async function archiveTask(task, archived) {
  if(archived)await pauseForLifecycle(task);
  await api('/tasks/'+task.id+'/metadata',{archived});
  if(!archived)state.historyView='active';
  if(archived&&state.task?.id===task.id)home();
  await loadTasks();await refresh();
}
let sidebarMenu=null;
const menuAnchorKey=button=>button?.id|| (button?.dataset.taskMenu?'task:'+button.dataset.taskMenu:button?.dataset.projectMenu?'project:'+button.dataset.projectMenu:'');
const findMenuAnchor=key=>$$('[data-task-menu],[data-project-menu],#history-menu').find(button=>menuAnchorKey(button)===key);
function compactMenu(anchor,label,actions) {
  const key=menuAnchorKey(anchor);
  if(sidebarMenu?.key===key){sidebarMenu.close();return;}
  sidebarMenu?.close(false);
  const menu=document.createElement('div');menu.className='sidebar-menu';menu.setAttribute('role','menu');menu.setAttribute('aria-label',label);
  menu.innerHTML=actions.map((a,i)=>`<button role="${a.checked===undefined?'menuitem':'menuitemradio'}" ${a.checked===undefined?'':`aria-checked="${a.checked}"`} data-option="${i}" class="${a.danger?'danger':''}">${a.checked===undefined?'':`<span class="menu-check">${a.checked?'✓':''}</span>`}${esc(a.label)}</button>`).join('');
  $('#overlay-root').append(menu);anchor.setAttribute('aria-expanded','true');
  const rect=anchor.getBoundingClientRect(),box=menu.getBoundingClientRect();
  menu.style.left=Math.max(8,Math.min(rect.right-box.width,innerWidth-box.width-8))+'px';
  menu.style.top=Math.max(8,Math.min(rect.bottom+4,innerHeight-box.height-8))+'px';
  const close=(restore=true)=>{const current=findMenuAnchor(key)||anchor;menu.remove();current.setAttribute('aria-expanded','false');document.removeEventListener('pointerdown',outside,true);window.removeEventListener('resize',dismiss);document.removeEventListener('scroll',scroll,true);if(sidebarMenu?.menu===menu)sidebarMenu=null;if(restore&&current.isConnected)current.focus({preventScroll:true});};
  const outside=e=>{if(!menu.contains(e.target)&&!(findMenuAnchor(key)||anchor).contains(e.target))close(false)};
  const dismiss=()=>close(false),scroll=e=>{if(!menu.contains(e.target))close(false)};
  document.addEventListener('pointerdown',outside,true);window.addEventListener('resize',dismiss);document.addEventListener('scroll',scroll,true);
  menu.onkeydown=e=>{const buttons=$$('button',menu),i=buttons.indexOf(document.activeElement);if(e.key==='Escape'){e.preventDefault();close()}else if(e.key==='Tab'){close()}else if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();buttons[e.key==='Home'?0:e.key==='End'?buttons.length-1:(i+(e.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length].focus()}};
  $$('button',menu).forEach((button,i)=>button.onclick=async()=>{close();try{await actions[i].run()}catch(error){toast(error.message)}});
  sidebarMenu={key,menu,close};$('button',menu)?.focus();
}
function historyMenu(anchor) {
  compactMenu(anchor,'Show chats',[['active','Active chats'],['archived','Archived chats'],['trash','Trash']].map(([view,label])=>({label,checked:(state.historyView||'active')===view,run:async()=>{const previous=state.historyView;state.historyView=view;try{await loadTasks();renderSidebar()}catch(error){state.historyView=previous;renderSidebar();throw error}}})));
}
function taskMenu(task,anchor) {
  if(!task)return;
  const actions=task.trashed_at?[
    {label:'Inspect saved chat',run:()=>selectTask(task.id)},
    {label:'Restore chat',run:()=>restoreTrash(task)}
  ]:[
    {label:'Rename…',run:()=>renameTask(task)},
    {label:task.pinned?'Unpin':'Pin',run:async()=>{await api('/tasks/'+task.id+'/metadata',{pinned:!task.pinned});await refresh()}},
    {label:task.archived_at?'Restore to active chats':taskBusy(task)?'Pause & archive':'Archive',run:()=>archiveTask(task,!task.archived_at)},
    {label:taskBusy(task)?'Pause & move to trash':'Move to trash',danger:true,run:()=>moveToTrash(task)}
  ];
  compactMenu(anchor,'Chat options',actions);
}
async function moveToTrash(task) {
  if(taskBusy(task))toast('Pausing before moving to Trash…');
  await pauseForLifecycle(task);await api('/tasks/'+task.id+'/trash',{});
  if(state.task?.id===task.id)home();await loadTasks();
  toast('Moved to Trash.');clearTimeout(toastTimer);
  const undo=document.createElement('button');undo.className='text-link';undo.textContent='Undo';
  undo.onclick=async()=>{undo.disabled=true;try{await restoreTrash(task)}catch(error){toast(error.message)}};
  $('#toast').append(' ',undo);toastTimer=setTimeout(()=>$('#toast').classList.remove('visible'),15000);
}
async function restoreTrash(task) {
  const restored=await api('/tasks/'+task.id+'/restore',{});
  state.historyView=restored.archived_at?'archived':'active';
  await refresh();toast(restored.archived_at?'Restored to Archived.':'Restored to active history.');
}
const draftKey=()=>state.task?.id||state.project?.path||'new';
function saveDraft(){state.drafts.set(draftKey(),$('#chat-input').value)}
function restoreDraft(){$('#chat-input').value=state.drafts.get(draftKey())||'';branchUI?.restoreDraft();renderComposer()}
function home() {
  sidebarMenu?.close(false);
  saveDraft();state.selection++;state.loading=false;state.task=null;state.view='chat';
  try{localStorage.removeItem('cheapos-selected')}catch{}
  renderHome();restoreDraft();renderSidebar();panelLayout.closeMobileSidebar();$('#view-container').scrollTop=0;
}
function chooseProject(project,toggle=false) {
  const collapsed=toggle&&state.project?.path===project.path&&!sidebarPrefs[project.path]?.collapsed;
  sidebarPrefs[project.path]={...sidebarPrefs[project.path],collapsed,more:true};saveSidebarPrefs();
  saveDraft();home();state.project=project;renderHome();restoreDraft();renderSidebar();
  try{localStorage.setItem('cheapos-project',project.path)}catch{}
  $('#chat-input').focus();
}
function startupMarkup() {
  const startup=state.startup||{},ready=startup.status==='ready',busy=startup.busy;
  const title=ready?'Let’s work on it.':busy?'Getting your model ready…':['unavailable','stopped'].includes(startup.status)?'Let’s get you connected.':state.project?'What would you like to work on?':'Your project. Let’s work on it.';
  const model=startup.model;
  const modelText=model?`${model.id} · ${model.transport}${model.local?(model.transport==='Local Ollama'?'':' · Local model'):' · Free route'}`:'';
  const actions=busy?`<button class="subtle-button" data-startup="stop">Stop connecting</button>`:!ready?`<button class="primary-button" data-startup="setup">Set up connection</button><button class="text-link" data-startup="models">Advanced connections</button>`:'';
  return `<div class="welcome-mark">${busy?'<span class="spinner"></span>':'<img class="brand-icon" src="./brand-icon.svg" alt="" />'}</div><h1>${title}</h1>${model?`<div class="startup-model ${ready?'ready':''}"><span class="task-dot ${ready?'done':'pulsing'}"></span>${esc(modelText)}</div>`:''}<p class="welcome-greeting">${esc(ready?startup.content:startup.content||startup.message||'Open a local project, then talk to cheapoS.')}</p>${startup.thinking?thinkingMarkup({thinking:startup.thinking,request_id:'startup',model:model?.id||''},true):''}${ready?'<span class="startup-verified">Greeting received · no API cost reported</span>':''}<div class="startup-actions">${actions}</div>${startup.attempts?.some(a=>a.status==='failed')?`<details class="startup-attempts"><summary>Connection details</summary>${startup.attempts.filter(a=>a.status==='failed').map(a=>`<p><strong>${esc(a.model)}</strong><br>${esc(a.error)}</p>`).join('')}</details>`:''}`;
}
function bindStartupActions(root=document) {
  $$('[data-startup]',root).forEach(button=>button.onclick=async()=>{
    const action=button.dataset.startup;
    if(action==='setup'){openSetup();return}
    if(action==='models'){openConnections();return}
    if(action==='preferences'){startupPreferences();return}
    button.disabled=true;
    try{
      if(action==='cloud')await api('/startup/config',{allow_cloud:true,enabled:true});
      await api('/startup/'+(action==='stop'?'stop':'start'),{});await loadStartup();
    }catch(e){toast(e.message);button.disabled=false}
  });
}
function gatewayKeyStatus(gateway={}) {
  const storage=gateway.key_storage||{};
  if(storage.error)return storage.error;
  if(storage.source==='environment')return 'Using CHEAPOS_GATEWAY_API_KEY from the launch environment. It overrides a remembered key on startup.';
  if(storage.source==='saved')return `Saved in ${storage.backend||'this computer’s credential store'} · restored after restart.`;
  if(gateway.key_configured||gateway.client_key_configured)return 'Session-only key · will need to be entered again after restart.';
  return 'No client key configured. Provider credentials and your dashboard password stay in OmniRoute.';
}
function gatewayRememberField(gateway={},name,checked) {
  const storage=gateway.key_storage||{},canRemember=Boolean(storage.available);
  const remember=checked??(storage.saved||(canRemember&&storage.source!=='environment'&&!gateway.key_configured&&!gateway.client_key_configured));
  return `<label class="checkbox-field"><input name="${name}" type="checkbox" ${remember?'checked':''} ${canRemember||storage.saved?'':'disabled'}><span>Remember this key on this computer<small>${canRemember?`Uses ${esc(storage.backend)}. Uncheck and save to keep the key for this session only.`:'Secure storage is unavailable. Use a session-only key or a launch environment variable.'}</small></span></label>`;
}
function openSetup() {
  const d=dialog(`${modalHeader('GET CONNECTED','Choose a connection')}<p class="modal-description">Connect, open a project, then send your request.</p><div class="button-row"><button class="primary-button" data-setup="omni">OmniRoute · recommended</button><button class="outline-button" data-setup="local">Models on this computer</button></div><section id="setup-status" aria-live="polite"></section><p class="form-error" role="alert"></p><div class="modal-footer"><button class="text-link" data-setup="advanced">Advanced connections</button><button class="subtle-button" data-setup="history">Return to saved work</button></div>`,'project-modal setup-modal');
  let timer=null,busy=false,last='',readiness={},selected='';
  const stop=()=>{clearTimeout(timer);timer=null};
  d.addEventListener('close',stop);
  const perform=async operation=>{if(busy)return;busy=true;$('.form-error',d).textContent='';try{await operation()}catch(e){$('.form-error',d).textContent=e.message}finally{busy=false}};
  const render=()=>{
    const guide=CheapOSGuide.setupGuide(readiness), key=$('[name="setup_key"]',d)?.value||'', remember=$('[name="setup_remember"]',d)?.checked;
    const signature=JSON.stringify([readiness.status,readiness.gateway,readiness.prerequisites]);if(signature===last)return;
    if(document.activeElement?.name==='setup_key')return;last=signature;
    const node=readiness.prerequisites?.node, cli=readiness.prerequisites?.omniroute;
    $('#setup-status',d).innerHTML=`<h3>${esc(guide.title)}</h3><p>${esc(guide.detail)}</p>${guide.install?`${!node?.installed?'<p><a href="https://nodejs.org/en/download" target="_blank" rel="noopener noreferrer">Install Node.js LTS and npm</a>, then restart cheapoS so it can find them.</p>':''}<p>Run this in your terminal. It installs the version used for the cheapoS integration.</p><code class="approval-command">npm install -g omniroute@3.8.49</code><button class="subtle-button" data-setup="copy">Copy install command</button>`:''}${cli?.installed?`<p class="small muted">Installed OmniRoute: ${esc(cli.version||'version unknown')}${cli.compatibility==='unverified'?' · compatibility unverified':''}</p>`:''}${guide.dashboard?`<p><a href="${esc(readiness.gateway.dashboard_url)}" target="_blank" rel="noopener noreferrer">Open OmniRoute dashboard ↗</a></p><p class="small muted">Sign in there if requested, then use Providers for provider credentials. Dashboard login and provider credentials are separate from a client API key.</p>`:''}${guide.key?`<form id="setup-key-form"><label>Gateway client API key<input name="setup_key" type="password" autocomplete="new-password" required></label>${gatewayRememberField(readiness.gateway,"setup_remember",remember)}<p class="small muted">${esc(gatewayKeyStatus(readiness.gateway))}</p><button class="outline-button" type="submit">Save client key and retry</button></form>`:''}<div class="button-row">${guide.start?'<button class="primary-button" data-setup="start">Connect / start</button>':''}<button class="outline-button" data-setup="recheck">Re-check / I’m back</button>${guide.ready?'<button class="primary-button" data-setup="continue">Use this connection</button>':''}</div>${guide.ready?'<p class="small muted">Uses current eligible free routes. Automatic coding selects and checks a different reviewer. A saved explicit model pair is preserved. No project work starts until you send a request.</p>':''}`;
    if($('#setup-key-form',d)){ $('[name="setup_key"]',d).value=key;$('#setup-key-form',d).onsubmit=e=>{e.preventDefault();perform(async()=>{await api('/gateway/config',{api_key:$('[name="setup_key"]',d).value,remember_key:$('[name="setup_remember"]',d).checked});$('[name="setup_key"]',d).value='';await api('/gateway/refresh',{});last='';await check()})}; }
  };
  const check=async()=>{stop();if(!d.open||selected!=='omni')return;try{readiness=await api('/readiness?refresh=1');if(d.open)render()}catch(e){if(d.open)$('.form-error',d).textContent=e.message}finally{if(d.open&&selected==='omni')timer=setTimeout(check,4000)}};
  d.addEventListener('click',e=>{const action=e.target.closest('[data-setup]')?.dataset.setup;if(!action)return;
    if(action==='local'){stop();d.close();openLocalSetup();return}
    if(action==='advanced'){d.close();openConnections();return}
    if(action==='history'){d.close();return}
    if(action==='omni'){selected='omni';try{localStorage.setItem('cheapos-setup-path','omni')}catch{}check();return}
    if(action==='recheck'){check();return}
    if(action==='copy'){perform(async()=>{await navigator.clipboard.writeText('npm install -g omniroute@3.8.49');toast('Install command copied')});return}
    if(action==='start'){perform(async()=>{await api('/gateway/start',{});last='';await check()});return}
    if(action==='continue')perform(async()=>{
      const explicitPair=state.preferences.execution?.mode==='manual'&&state.config.worker&&state.config.reviewer;
      if(!explicitPair)state.preferences=await api('/preferences',{execution:{...state.preferences.execution,mode:'remote'}});
      await api('/startup/config',{allow_cloud:true});
      d.close();renderComposer();if(state.project)$('#chat-input').focus();else openProject();
    });
  });
  try{if(localStorage.getItem('cheapos-setup-path')==='omni'){selected='omni';check()}}catch{}
}
async function openLocalSetup() {
  const d=dialog(`${modalHeader('LOCAL MODELS','Work on this computer')}<p>Installed Ollama models must advertise completion and tool support. Cloud-forwarding aliases are excluded. Speed depends on your hardware and model.</p><div id="local-choices">Checking installed models…</div><p class="form-error" role="alert"></p><div class="modal-footer"><button class="outline-button" data-local="recheck">Re-check models</button><button class="subtle-button" data-local="sample">Try a sample task</button></div>`,'project-modal setup-modal');
  let timer,closed=false;
  d.addEventListener('close',()=>{closed=true;clearTimeout(timer)});
  const check=async(fresh=true)=>{
    clearTimeout(timer);try{const readiness=await api('/readiness'+(fresh?'?refresh=1':''));if(closed)return;const models=readiness.paths?.local?.models;
      if(readiness.checking)timer=setTimeout(()=>check(false),4000);
      if(!models){$('#local-choices',d).textContent='Checking installed models…';if(!readiness.checking)$('#local-choices',d).textContent='Could not inspect local models. Re-check or use the scripted demonstration.';return}
      $('#local-choices',d).innerHTML=models.length?`<form id="local-choice-form"><label class="full-field">Installed local model<select name="model">${models.map(name=>`<option ${state.preferences.execution?.local_model===name?'selected':''}>${esc(name)}</option>`).join('')}</select></label><p class="small muted">Advertised: completion and tools. ${readiness.levels?.greeting&&state.startup.model?.local?'A local greeting has succeeded; coding and review are still unverified.':'No completed coding loop has been verified by this setup check.'}</p><p>All local keeps both work and review here. If one model is selected, its review is a separate request to the same model.</p><button class="primary-button" type="submit">Use all local</button></form>`:`<p>No eligible installed model found. Start <a href="https://ollama.com/download" target="_blank" rel="noopener noreferrer">Ollama</a> and choose a tool-capable model from its library that fits your hardware. Model downloads are manual; check the listed size before downloading.</p><p>You can try the scripted demonstration without a model.</p>`;
      const form=$('#local-choice-form',d);if(form)form.onsubmit=e=>{e.preventDefault();formAction(d,async()=>{const model=new FormData(form).get('model');await api('/startup/config',{allow_cloud:false});state.preferences=await api('/preferences',{execution:{mode:'local',local_model:model,local_reviewer:model}});d.close();renderComposer();if(state.project)$('#chat-input').focus();else openProject()})};
    }catch(e){if(!closed)$('.form-error',d).textContent=e.message}
  };
  $('[data-local="recheck"]',d).onclick=check;$('[data-local="sample"]',d).onclick=()=>{d.close();sampleDialog()};check();
}
function startupPreferences() {
  const settings=state.startup.settings||{enabled:true,allow_cloud:false};
  const d=dialog(`<form>${modalHeader('STARTUP','Ready when you open cheapoS')}<p class="modal-description">Start with an installed local model, or a configured free route through OmniRoute. A small greeting checks that it responds.</p><label class="checkbox-field"><input name="enabled" type="checkbox" ${settings.enabled?'checked':''}><span>Connect to a free model on launch</span></label><label class="checkbox-field"><input name="allow_cloud" type="checkbox" ${settings.allow_cloud?'checked':''}><span>Allow free cloud models through OmniRoute<small>Uses providers you have already set up. Project contents are sent only when you start a chat with that model.</small></span></label><p class="small muted">At most three free models are tried per connection check, with a 512-token output cap each. No paid fallback, model downloads, or provider enrollment. A saved model choice takes priority. Saving preferences makes no inference request.</p><p class="form-error" role="alert"></p><div class="modal-footer"><span>Reviewers remain under Models.</span><button type="submit" class="primary-button">Save preferences</button></div></form>`,'project-modal');
  const form=$('form',d);form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{const values=new FormData(form);await api('/startup/config',{enabled:values.has('enabled'),allow_cloud:values.has('allow_cloud')});d.close();await loadStartup()})};
}
function renderHome() {
  $('#task-title').textContent='New chat';$('#task-title').title='';$('#rename-task').hidden=true;document.title='cheapoS';
  $('.task-heading').hidden=true;$('.tabs').hidden=true;$('#compact-session').hidden=true;$('#toggle-inspector').hidden=true;$('#inspector').classList.add('home-hidden');
  $('.main-pane').classList.add('new-conversation');
  $('#project-name').textContent=state.project?CheapOSGuide.projectName({source:state.project.path}):'Your workspace';
  $$('.view').forEach(v=>v.classList.toggle('hidden',v.id!=='chat-view'));
  if(branchUI?.renderStart()){renderComposer();return;}
  const opened=new Map($$('#chat-view details[data-event]').map(d=>[d.dataset.event,d.open]));
  $('#chat-view').innerHTML=`<div class="chat-welcome startup-welcome">${startupMarkup()}${state.project?`<div class="chat-suggestions"><button data-suggestion="Explain how this project works. Start by reading its README and main entry points.">Explain this project ${icon('chevron')}</button><button data-suggestion="Look through this project and suggest one small improvement. Explain it before making changes.">Find a small improvement ${icon('chevron')}</button></div>`:`<button class="primary-button" id="welcome-open">${icon('folder')}Open project</button>`}<button class="text-link startup-preferences" data-startup="preferences">Startup preferences</button></div>`+pendingMessageMarkup();
  for(const d of $$('#chat-view details[data-event]'))if(opened.has(d.dataset.event))d.open=opened.get(d.dataset.event);
  if($('#welcome-open'))$('#welcome-open').onclick=()=>openProject();
  $$('[data-suggestion]').forEach(b=>b.onclick=()=>{$('#chat-input').value=b.dataset.suggestion;saveDraft();renderComposer();$('#chat-input').focus()});
  bindStartupActions();renderComposer();
}
async function loadStartup() {
  const data=await api('/startup'),config=data.config;delete data.config;
  const changed=JSON.stringify(data)!==JSON.stringify(state.startup)||JSON.stringify(config)!==JSON.stringify(state.config);
  state.startup=data;state.config=config;
  if(changed){renderSidebar();renderComposer();if(!state.task)renderHome()}
}
function submissionAvailability(task=state.task,mode=branchUI?.getMode()||'interactive') {
  if(task&&taskBusy(task))return {allowed:true};
  if(state.startup.busy)return {allowed:false,reason:'Checking your free model. This draft has not been sent.'};
  if(!state.admission)return {allowed:false,reason:'Checking task capacity. This draft has not been sent.'};
  if(state.admission.legacy){const other=state.tasks.find(t=>t.id!==task?.id&&taskBusy(t));return {allowed:!other,task_id:other?.id,reason:other?'Another task is running: '+other.title+'. This draft has not been sent. Concurrent tasks become available after a later app restart.':''};}
  const kind=task?.branch_run?'unattended':mode,decision=state.admission[kind]||{allowed:false,reason:'Task capacity is unavailable.'};
  const active=state.admission.active?.find(t=>t.mode===kind),other=state.tasks.find(t=>t.id===active?.task_id);
  return {...decision,task_id:active?.task_id,reason:decision.allowed?'':`${decision.reason||'Task capacity is full.'}${other?' Running: '+other.title+'.':''} This draft has not been sent.`};
}
function sendingHere(){return state.pendingSends.has(draftKey());}
async function loadAdmission({render=true}={}){try{state.admission=await api('/admission');}catch(e){state.admission=e.status===404?{legacy:true}:null;}if(render)renderComposer();}
function clearOwnedDraft(key,message){if(state.drafts.get(key)===message)state.drafts.delete(key);if(draftKey()===key&&$('#chat-input').value.trim()===message)$('#chat-input').value='';}
function pendingMessageMarkup(){
  const pending=state.pendingMessages?.get(draftKey());if(!pending)return '';
  // A poll can observe server acceptance before the POST response arrives.
  if(state.task&&(state.task.requests||[]).length>pending.requests)return '';
  return `<article class="chat-message from-user pending-message" aria-label="Message being sent"><div class="chat-author"><strong>You</strong><span role="status">Sending…</span></div><div class="chat-message-body">${messageText(pending.text)}</div><p class="small muted">Waiting for cheapoS to accept this message. Your draft is saved.</p></article>`;
}
function beginMessageSend(key,message){
  state.pendingMessages ||= new Map();state.sendErrors ||= new Map();
  state.pendingMessages.set(key,{text:message,requests:(state.task?.requests||[]).length});
  state.sendErrors.delete(key);state.pendingSends.add(key);saveDraft();
  if(state.task)renderChat();else renderHome();renderComposer();
  $('#view-container').scrollTop=$('#view-container').scrollHeight;
}
function renderComposer() {
  branchUI?.sync();
  const task=state.task, busy=task&&taskBusy(task);
  const assistance=CheapOSGuide.coordinatorStatus(task||{execution:state.preferences.execution});
  $('#execution-choice').textContent=`Coordinator ${assistance.label} · Work setup`;
  $('#execution-choice').title=`Coordinator assistance: ${assistance.label} ${task?'for this chat':'for new chats'}. Open execution settings.`;
  renderConnectionNotice();
  $('#composer-permissions').hidden=!(task&&state.taskPermissions?.id===task.id&&(state.taskPermissions.commands.length||state.taskPermissions.project_grants?.length));
  $('#composer-permissions').textContent=state.taskPermissions?.project_grants?.length?'Tests allowed this session':'Commands allowed this session';
  $('#composer-permissions').title=state.taskPermissions?.project_grants?.length?'This project · until cheapoS restarts':'This chat · until cheapoS restarts';
  const chosenLimits=task?.limits||state.preferences.limits,preset=CheapOSGuide.workPreset(chosenLimits);
  $('#chat-budget').textContent=`${chosenLimits.dollars===0?'Free only':money(chosenLimits.dollars)+' cap'} · ${preset==='custom'?'Custom':preset==='extended'?'Extended':'Standard'} ${chosenLimits.run_minutes??15} min`;
  $('#chat-budget').title=task?'Limits for this chat':'Defaults for new chats';
  const pausing=Boolean(task&&(task.status==='stopping'||state.pausingTask===task.id));
  $('#composer-area').hidden=Boolean(task?.demo||task?.archived_at||task?.trashed_at)||state.view!=='chat';
  $('#composer-project span').textContent=task?CheapOSGuide.projectName(task):state.project?CheapOSGuide.projectName({source:state.project.path}):'Open project';
  $('#composer-project').disabled=Boolean(task);
  $('#chat-input').disabled=sendingHere();
  $('#chat-input').placeholder=state.project?'Ask about your project or describe a change…':'Open a project to get started…';
  const availability=submissionAvailability(task);
  if(busy){
    $('#chat-send').hidden=true;
    if($('#chat-steer')){
      $('#chat-steer').hidden=false;
      $('#chat-steer').disabled=pausing||sendingHere()||!$('#chat-input').value.trim();
    }
    $('#chat-input').placeholder='Add a detail or change direction…';
    $('#composer-note').textContent=pausing?'Pausing the current step. Your work and draft stay saved.':'Keep talking to cheapoS. Your message will guide the next step.';
  }else{
    const next=CheapOSConversation.readyForNext(task);
    $('#chat-send').hidden=false;
    if($('#chat-steer'))$('#chat-steer').hidden=true;
    $('#chat-send').disabled=sendingHere()||branchUI?.isSubmitting()||!availability.allowed||(!$('#chat-input').value.trim()&&!branchUI?.hasDocument());
    $('#chat-input').placeholder=next?'What should we work on next?':state.project?'Ask about your project or describe a change…':'Open a project to get started…';
    $('#composer-note').textContent=state.startup.busy?'Checking your free model. You can draft a message while it connects.':!availability.allowed?availability.reason:next?'Ready when you are. We’ll continue from the committed changes.':task?(task.changes.length?'Continue in the same task copy. See saved edits in Changes.':'Follow up here. This chat keeps its project context.'):'Edits stay in a separate copy. You review the result.';
  }
  if(task?.branch_run){$('#chat-input').placeholder='Add guidance within the accepted scope…';$('#composer-note').textContent='Guidance stays within this run’s accepted plan. Use Request changes for a reviewed revision.';}
  if(task?.branch_run&&!task.branch_run.authorization_ref&&!CheapOSBranchUI.isPlanning(task)){$('#chat-input').disabled=true;$('#chat-input').placeholder='Inspect the proposal to edit or start this run.';$('#chat-send').disabled=true;if($('#chat-steer'))$('#chat-steer').hidden=true;$('#composer-note').textContent='This is an Unattended proposal. Inspect its captured plan before editing or starting work.';}
  if(CheapOSBranchUI.isPlanning(task)){$('#chat-input').placeholder=busy?'Add details for the proposal…':'Reply or describe changes to the proposal…';$('#composer-note').textContent=busy?'Planning continues here. Your reply will guide the proposal.':'Questions and issues stay in this chat. Reply to continue planning, or inspect the ready proposal.';}
  if(!busy&&!availability.allowed){$('#composer-note').textContent=availability.reason;if(availability.task_id){const link=document.createElement('button');link.className='text-link';link.textContent='Open running task';link.onclick=()=>selectTask(availability.task_id);$('#composer-note').append(' ',link);}}
  if(['merged','left_on_branch'].includes(task?.branch_run?.status)){$('#chat-input').disabled=true;$('#chat-input').placeholder='Start a new chat to continue';$('#chat-send').disabled=true;if($('#chat-steer'))$('#chat-steer').hidden=true;$('#composer-note').textContent=task.branch_run.status==='merged'?'This run is merged. Start a new chat for the next job; its scope and approvals will be separate.':'Work is saved on its feature branch. Start a new chat for another job, or inspect the saved review above.';}
  if(task&&!task.demo)$('#composer-note').textContent+=` · Est. ${money(task.usage.cost)} used.`;
  const sending=sendingHere(),send=$('#chat-send');
  send.setAttribute('aria-label',sending?'Sending message':'Send message');
  send.innerHTML=sending?'<span class="spinner" aria-hidden="true"></span>':icon('up');
  if(sending)$('#composer-note').textContent='Sending your message… Waiting for cheapoS to accept it. Your draft is saved.';
  else if(state.sendErrors?.has(draftKey()))$('#composer-note').textContent=state.sendErrors.get(draftKey())+' Your draft remains saved.';
  const stop=$('#chat-stop');
  stop.hidden=!busy&&!state.startup.busy;
  stop.disabled=pausing||state.stoppingStartup;
  $('span',stop).textContent=busy?(pausing?'Pausing…':'Pause'):(state.stoppingStartup?'Stopping…':'Stop connecting');
  stop.title=busy?'Pause this task. Your work stays saved.':'Stop checking model availability';
  // Keep a fallback in views where the composer is not visible.
  const headerPause=busy&&$('#composer-area').hidden;
  $('#task-actions').innerHTML=headerPause?`<button class="subtle-button" id="pause-task" ${pausing?'disabled':''}>${icon('pause')}${pausing?'Pausing…':'Pause'}</button>`:'<button class="subtle-button" id="task-overview">Details</button>';
  if($('#pause-task'))$('#pause-task').onclick=stopTask;
  if($('#task-overview'))$('#task-overview').onclick=toggleInspector;
}
function projectMenu(path,anchor) {
  compactMenu(anchor,'Project options',[
    {label:'New chat',run:()=>chooseProject(state.projects.find(p=>p.path===path))},
    {label:'Project settings…',run:()=>editProject(path)}
  ]);
}
function editProject(path) {
  const d=dialog(`<form>${modalHeader('PROJECT','Project settings')}<p>Removing this project hides its sidebar shortcut. Repository files and chats are kept; you can reopen it from Hidden projects.</p><p class="small">${esc(path)}</p><p class="form-error" role="alert"></p><div class="modal-footer"><button type="button" data-close>Cancel</button><button type="submit">Remove from sidebar</button></div></form>`);
  const form=$('form',d);form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{
    await api('/projects/hide',{repository:path});
    if(state.project?.path===path){home();state.project=null;try{localStorage.removeItem('cheapos-project')}catch{}renderHome();restoreDraft()}
    await loadTasks();d.close();
  })};
}
function reopenHiddenProject(path, taskId) {
  const d=dialog(`<form>${modalHeader('HIDDEN PROJECT','Reopen this project?')}<p>Reopening restores its sidebar reference and existing chats.</p><p>${esc(path)}</p><p class="form-error" role="alert"></p><button type="submit" class="primary-button">Reopen project</button></form>`);
  const form=$('form',d);form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{const project=await api('/projects',{repository:path});await loadTasks();d.close();if(taskId)await selectTask(taskId);else chooseProject(project)})};
}
function openProject(afterOpen) {
  const d=dialog(`<form>${modalHeader('LOCAL PROJECT','Open a project')}<p class="modal-description">Choose your project once, then chat. cheapoS will work in a separate copy when you send your first message.</p><label class="full-field">Project folder<input name="repository" placeholder="/Users/you/projects/my-project" required autocomplete="off" autofocus><small>Use the root folder of a local Git repository.</small></label><div class="hidden-project-list"></div><p class="form-error" role="alert"></p><div class="modal-footer"><span>Opening a project makes no model request.</span><button type="submit" class="primary-button">Open project ${icon('chevron')}</button></div></form>`,'project-modal');
  api('/projects/hidden').then(projects=>{if(!d.isConnected)return;$('.hidden-project-list',d).innerHTML=projects.length?`<details><summary>Hidden projects (${projects.length})</summary>${projects.map(p=>`<button type="button" data-hidden-project="${esc(p.path)}" aria-label="Reopen ${esc(p.name)} at ${esc(p.path)}">${esc(p.name)} · ${esc(p.path)}</button>`).join('')}</details>`:'';$$('[data-hidden-project]',d).forEach(b=>b.onclick=()=>{d.close();reopenHiddenProject(b.dataset.hiddenProject)})}).catch(e=>{$('.form-error',d).textContent=e.message});
  const form=$('form',d);form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{const project=await api('/projects',{repository:new FormData(form).get('repository')});state.projects=await api('/projects');d.close();chooseProject(project);if(afterOpen)afterOpen()})};
}
async function selectTask(id) {
  saveDraft();rememberView();const request=++state.selection;state.loading=true;
  try {const task=await api('/tasks/'+id);if(request!==state.selection)return;if(!task.demo&&(state.hiddenProjects||[]).some(p=>p.path===task.source)){reopenHiddenProject(task.source,task.id);return;}state.task=task;state.project={path:task.source,name:basename(task.source)};state.file=0;state.run=-1;state.view='chat';try{localStorage.setItem('cheapos-selected',id)}catch{}renderTask({resetScroll:true});restoreDraft();renderSidebar();panelLayout.closeMobileSidebar();}
  catch(e){toast(e.message)}finally{if(request===state.selection)state.loading=false}
}
const viewMemory=new Map();
function rememberView(){if(!state.task)return;viewMemory.set(state.task.id+':'+state.view,{scroll:$('#view-container').scrollTop,details:new Map($$('details[data-event]').map(d=>[d.dataset.event,d.open]))});}
function setView(view) {
  rememberView();
  state.view=view;renderView();renderComposer();
  const scroller=$('#view-container');
  const saved=viewMemory.get(state.task?.id+':'+view);for(const d of $$('details[data-event]'))if(saved?.details.has(d.dataset.event))d.open=saved.details.get(d.dataset.event);scroller.scrollTo({top:view==='chat'?scroller.scrollHeight:saved?.scroll||0,behavior:'instant'});
  for(const output of $$('[data-command-output]'))output.scrollTop=output.scrollHeight;
}
function renderTask({resetScroll=false}={}) {
  const task=state.task;if(!task)return;$('.main-pane').classList.remove('new-conversation');
  loadTaskPermissions(task);
  $('.task-heading').hidden=false;$('.tabs').hidden=false;$('#compact-session').hidden=false;$('#toggle-inspector').hidden=false;$('#inspector').classList.remove('home-hidden');
  const scroller=$('#view-container'), oldScroll=scroller.scrollTop, logAnchor=state.view==='logs'&&oldScroll>60?$$('#logs-view details[data-event]').find(d=>d.getBoundingClientRect().bottom>scroller.getBoundingClientRect().top):null, logPosition=logAnchor?.getBoundingClientRect().top, logKey=logAnchor?.dataset.event, bottom=scroller.scrollHeight-scroller.clientHeight-oldScroll<60;
  const focusedDetail=['plan','logs'].includes(state.view)?document.activeElement?.closest('details[data-event]')?.dataset.event:null;
  const expanded=new Map((resetScroll?[]:$$('details[data-event]')).map(d=>[d.dataset.event,d.open]));
  const outputScroll=new Map((resetScroll?[]:$$('[data-thinking], [data-command-output]')).map(el=>[el.dataset.thinking||el.dataset.commandOutput,{top:el.scrollTop,bottom:el.scrollHeight-el.clientHeight-el.scrollTop<30}]));
  $('#task-title').textContent=task.title;$('#task-title').title=task.title;$('#rename-task').hidden=Boolean(task.trashed_at);document.title=task.title+' — cheapoS';
  $('#project-name').textContent=CheapOSGuide.projectName(task);
  $('#task-status').textContent=task.branch_run?CheapOSBranchUI.projectRun(task).label:labels[task.status]||task.status;
  $('#task-date').textContent=date(task.created_at);
  $('#task-eyebrow').classList.toggle('running',taskBusy(task));
  $('#task-subtitle').textContent=task.branch_run?'Unattended work on '+task.branch_run.feature_ref.replace(/^refs\/heads\//,'')+'. Final integration stays your decision.':task.demo?'Scripted models. Real edits, checks, and checkpoint reviews.':task.status==='approved'?'Ready for your decision. Approve and commit, or keep chatting.':'Working in a separate copy of your repository.';
  $('#change-count').textContent=task.changes.length;$('#check-count').textContent=task.checks.length;
  const sums=patchTotals(task.patch);$('#diff-tally').innerHTML=`<span>+${sums.add}</span><span>−${sums.remove}</span>`;
  $('#compact-cost').textContent=money(task.usage.cost);
  const totalTokens=(task.usage?.worker?.tokens||0)+(task.usage?.reviewer?.tokens||0)+(task.usage?.coordinator?.tokens||0)+(task.usage?.planner?.tokens||0);
  const actualCost=task.usage?.cost;
  const usagePill=$('#compute-savings-pill');
  if(usagePill){
    usagePill.hidden=totalTokens===0;
    usagePill.textContent=`${totalTokens.toLocaleString()} accounted tokens · ${actualCost==null?'cost unknown':money(actualCost)} · ${CheapOSGuide.costProvenance(task)}`;
    usagePill.title=`Cost provenance: ${task.metrics?.cost?.provenance||'unknown'}. Includes retained uncertain reservations when present. Configured accounting is not a billing receipt.`;
  }
  renderView();renderInspector();renderComposer();bindTerminalCopy();
  for(const d of $$('details[data-event]'))if(expanded.has(d.dataset.event))d.open=expanded.get(d.dataset.event);
  if(focusedDetail&&!resetScroll)$$('details[data-event]').find(d=>d.dataset.event===focusedDetail)?.querySelector('summary')?.focus({preventScroll:true});
  for(const el of $$('[data-thinking], [data-command-output]')){const saved=outputScroll.get(el.dataset.thinking||el.dataset.commandOutput);el.scrollTop=!saved||saved.bottom?el.scrollHeight:saved.top}
  scroller.scrollTop=resetScroll?scroller.scrollHeight:state.view==='chat'&&bottom?scroller.scrollHeight:oldScroll;
  if(state.view==='logs'&&logKey){const anchor=$$('#logs-view details[data-event]').find(d=>d.dataset.event===logKey);if(anchor)scroller.scrollTop+=anchor.getBoundingClientRect().top-logPosition;const latest=document.createElement('button');latest.className='logs-latest outline-button';latest.textContent='Return to latest events';latest.onclick=()=>{latest.remove();scroller.scrollTo({top:0,behavior:'instant'});};$('#logs-view').prepend(latest);if(anchor)scroller.scrollTop+=anchor.getBoundingClientRect().top-logPosition;}

}
function renderView() {
  $('#compact-session').hidden=true;
  const hasPlan=Boolean(CheapOSBranchUI.savedPlan(state.task));$('[data-view=plan]').hidden=!hasPlan;if(state.view==='plan'&&!hasPlan)state.view='chat';
  $$('.tab').forEach(b=>{const selected=b.dataset.view===state.view;b.classList.toggle('active',selected);b.setAttribute('aria-selected',String(selected));b.tabIndex=selected?0:-1;b.id='tab-'+b.dataset.view;b.setAttribute('aria-controls',b.dataset.view+'-view')});
  $$('.view').forEach(v=>{v.classList.toggle('hidden',v.id!==state.view+'-view');v.setAttribute('aria-labelledby','tab-'+v.id.replace(/-view$/,''));if(v.id!==state.view+'-view'&&(v.id!=='plan-view'||v.dataset.task!==state.task?.id)){v.innerHTML='';delete v.dataset.task;}});
  if(!state.task){renderHome();return}
  if(state.view==='logs')renderTechnicalLogs();else if(state.view==='plan')branchUI.renderPlan(state.task);else if(state.view==='chat')renderChat();else if(state.view==='activity')renderActivity();else if(state.view==='changes')renderChanges();else renderTests();
  bindTerminalCopy();
  $('#plan-view .view-history-notice')?.remove();
  if(state.task.archived_at||state.task.trashed_at){
    const view=$('#'+state.view+'-view');
    for(const el of $$('button,input,textarea',view))if(!el.matches('[data-raw-check],[data-copy-terminal]'))el.disabled=true;
    const banner=document.createElement('section');banner.className='chat-decision view-history-notice';banner.innerHTML=`<p>${state.task.trashed_at?'Trash · saved files retained':'Archived conversation'} · restore before continuing.</p><button class="primary-button">Restore</button>`;
    $('button',banner).onclick=async()=>{try{if(state.task.trashed_at)await restoreTrash(state.task);else await archiveTask(state.task,false)}catch(e){toast(e.message)}};view.prepend(banner);
  }
}
function eventDetail(event) {
  const detail=event.detail??{};
  if(event.kind==='tool'){
    const result=detail?.result,args=detail?.arguments||{};
    if(event.title==='read url')return `<p>${sourceLink(result.source_url,'Open source page')} · Read ${esc(result.fetched_at)}</p><pre class="output">${esc(result.content)}</pre><p class="muted">${result.has_more?'More lines are available. ':''}${result.truncated||result.excerpt_truncated?'Document preview was shortened. ':''}External source text.</p>`;
    if(event.title==='read file')return `<pre class="output">${esc(result?.content||'No content returned.')}</pre>`;
    if(['write file','replace text','replace lines'].includes(event.title))return `<p>Saved ${esc(args.path)} in the task copy.</p>`;
    if(Array.isArray(result))return `<pre class="output">${esc(result.map(r=>typeof r==='string'?r:JSON.stringify(r)).join('\n'))}</pre>`;
    if(typeof result==='string')return `<pre class="output">${esc(result)}</pre>`;
  }
  if(['handoff','routing','guard','web'].includes(event.kind))return `<p>${esc(typeof detail==='string'?detail:detail?.summary||detail?.error||detail?.model||detail?.url||'')}</p>`;
  if(event.kind==='generation')return '<p>Model output is available in Chat.</p>';

  if(event.kind==='review')return `<p>${esc(detail.feedback)}</p><span class="decision ${detail.decision==='APPROVE'?'approve':detail.decision==='REQUEST_CHANGES'?'revise':'pending'}">${esc(String(detail?.decision||'Review event').replaceAll('_',' '))}</span>`;
  if(event.kind==='checkpoint'&&!Number.isInteger(detail?.number))return `<p>${esc(event.title)}</p>${detail?.item_id?`<p class="muted">Task ${esc(detail.item_id)}</p>`:''}`;
  if(event.kind==='checkpoint')return `<p>${esc(detail.worker_summary)}</p><p class="muted">${esc(detail.uncertainties)}</p><button class="checkpoint-button" data-checkpoint="${detail.number}">Inspect checkpoint #${detail.number}</button>`;
  if(event.kind==='checks')return `<pre class="output">${esc(detail.output)}</pre>${detail.reason?`<p>${esc(detail.reason)}</p>`:''}`;
  if(typeof detail==='string')return `<p class="preserve">${esc(detail)}</p>`;
  return detail?`<pre class="output">${esc(JSON.stringify(detail,null,2))}</pre>`:'';
}
function sourceLink(url,label) {
  try{if(new URL(url).protocol==='https:')return `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`}catch{}
  return esc(label);
}
function messageText(value) {
  const inline=text=>text.split(/(\[[^\]\n]+\]\(https:\/\/[^\s)]+\))/g).map(part=>{
    const link=part.match(/^\[([^\]\n]+)\]\((https:\/\/[^\s)]+)\)$/);
    return link?sourceLink(link[2],link[1]):esc(part).replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>').replace(/`([^`\n]+)`/g,'<code>$1</code>');
  }).join('');
  return String(value||'').split(/```[^\n]*\n([\s\S]*?)```/g).map((part,i)=>i%2?`<pre class="chat-code"><code>${esc(part)}</code></pre>`:`<p>${inline(part)}</p>`).join('');
}
function progressMarkup(task) {
  const p=CheapOSGuide.progress(task);if(!p)return '';
  return `<section class="request-progress ${task.stream&&task.stream.phase!=='waiting'?'is-streaming':''}" aria-label="Current activity"><div class="request-progress-heading"><span class="spinner"></span><strong id="request-stage">${esc(p.title)}</strong><span id="request-elapsed" aria-label="Time in current step">${p.elapsed}</span></div><div class="request-model" id="request-detail">${esc(p.detail)}</div><p class="request-hint" id="request-hint">${esc(p.hint)}</p><div class="request-evidence"><span>${icon('code')}${esc(p.action)}</span><span>${icon('file')}${esc(p.evidence)}</span></div><div class="request-actions"><button class="text-link" data-chat-action="activity">${state.view==='activity'?'View live chat':'View activity'}</button><button class="subtle-button" data-chat-action="stop" ${p.stage==='stopping'?'disabled':''}>${p.stage==='stopping'?'Stopping…':'Pause'}</button>${p.stage==='waiting_retry'?'<button class="text-link" data-chat-action="connections">Inspect Models</button>':''}</div></section>`;
}
function updateProgressClock() {
  for(const el of $$('[data-start-time]'))el.textContent=CheapOSGuide.progress({status:'running',updated_at:el.dataset.startTime})?.elapsed||'0s';
  if(!state.task)return;
  const currentProgress=CheapOSGuide.progress(state.task),elapsed=currentProgress?.elapsed;
  if(state.task.status==='waiting_retry')for(const el of $$('[data-live-status]'))el.textContent=currentProgress.detail;
  for(const el of $$('[data-work-elapsed]'))if(elapsed)el.textContent=elapsed;
  if($('#request-elapsed')){
    const p=CheapOSGuide.progress(state.task);
    if(p){
      if($('#request-stage'))$('#request-stage').textContent=p.title;
      if($('#request-detail'))$('#request-detail').textContent=p.detail;
      $('#request-elapsed').textContent=p.elapsed;
      if($('#request-hint'))$('#request-hint').textContent=p.hint;
    }
  }
}
async function stopTask() {
  const task=state.task;
  if(!task||task.status==='stopping'||state.pausingTask===task.id)return;
  state.pausingTask=task.id;renderComposer();
  try{await api('/tasks/'+task.id+'/stop',{});await refresh()}
  catch(e){toast(e.message)}
  finally{state.pausingTask=null;renderComposer()}
}
async function stopFromComposer() {
  if(state.task&&taskBusy(state.task)){await stopTask();return}
  if(!state.startup.busy||state.stoppingStartup)return;
  state.stoppingStartup=true;renderComposer();
  try{await api('/startup/stop',{});await loadStartup()}
  catch(e){toast(e.message)}
  finally{state.stoppingStartup=false;renderComposer()}
}
function thinkingMarkup(detail,live=false,open=live) {
  if(!detail.thinking)return '';
  const key='generation-'+detail.request_id;
  return `<details class="thinking-panel ${live?'is-live':''}" data-event="${key}" ${open?'open':''}><summary>${icon('spark')}<strong>${detail.interrupted?'Thinking · interrupted':'Thinking'}</strong><span>${live?'Live':esc(detail.model)}</span>${icon('chevron')}</summary><div class="thinking-output" data-thinking="${key}">${esc(detail.thinking)}</div>${detail.truncated?'<p class="thinking-note">Showing the first 16,000 characters.</p>':''}</details>`;
}
function rawCheckLink(check) {
  if(!check.raw_output?.bytes||!state.task)return '';
  return `<p class="command-note"><button class="text-link" data-raw-check="${esc(check.run_id)}">Open original check output</button> · ${check.raw_output.bytes.toLocaleString()} bytes${check.raw_output.truncated?' · truncated at 2 MB':''}. Latest 8 runs retained.</p>`;
}
function commandMarkup(check,{live=false,open=false,key=check.run_id}={}) {
  const status=live?'Running check':({passed:'Check passed',test_failure:'Test process failed',process_timeout:'Test process timed out',task_deadline:'Task deadline reached',output_limit:'Output limit reached',user_paused:'Check paused',inputs_changed:'Verification inputs changed'}[check.outcome]||(check.passed?'Check passed':check.reason==='cancelled'?'Check stopped':'Check failed'));
  const rawOutput=check.output||(live?'Waiting for command output…':'');
  const formatted=CheapOSGuide.formatTerminalOutput(rawOutput);
  const exitPill=live?'<span class="term-status-pill live"><span class="pulse-dot"></span>Live</span>':check.passed?`<span class="term-status-pill pass">Exit 0 · ${Number(check.duration||0).toFixed(1)}s</span>`:`<span class="term-status-pill fail">Exit ${check.exit_code??'1'} · ${Number(check.duration||0).toFixed(1)}s</span>`;
  return `<details class="command-panel ${live?'is-live':check.passed?'passed':'failed'}" data-event="command-${esc(key)}" ${live||open?'open':''}><summary>${live?'<span class="spinner"></span>':icon(check.passed?'check':'x')}<strong>${status}</strong><span>${live?'Live output':`Exit ${check.exit_code??'—'} · ${Number(check.duration||0).toFixed(1)}s`}</span>${icon('chevron')}</summary><code class="command-line">${esc(check.command.join(' '))}</code>${(check.allowed_seconds||check.timeout_seconds)?`<p class="command-note">Allowed: ${Number(check.allowed_seconds||check.timeout_seconds).toFixed(1)} seconds</p>`:''}<div class="command-body"><div class="terminal-window ${live?'is-live':check.passed?'passed':'failed'}"><div class="terminal-header"><div class="traffic-dots"><span class="dot-red"></span><span class="dot-yellow"></span><span class="dot-green"></span></div><span class="terminal-title"><code>${esc(check.command.join(' '))}</code></span><div class="terminal-actions">${exitPill}<button type="button" class="terminal-copy-btn" data-copy-terminal="command-${esc(key)}" title="Copy output">${icon('file')} Copy</button></div></div><div class="terminal-viewport"><pre class="command-output terminal-body" tabindex="0" data-command-output="command-${esc(key)}" aria-label="${live?'Live command output':'Command output'}">${formatted}</pre></div>${check.truncated?'<p class="command-note">Showing the first 32 KB of output.</p>':''}${rawCheckLink(check)}${check.reason?`<p class="command-note error">${esc(check.reason)}. ${esc(check.next_action||'')}</p>`:''}</div></div></details>`;
}
function permissionMarkup(task) {
  const pending=task.pending_approval, choice=CheapOSGuide.permissionChoice(pending), profile=pending.profile;
  const explanation=profile?`<p>Allow supported unittest variants in this project until cheapoS restarts or you revoke permission. Tests execute project code, including later test edits.</p><details><summary>Test permission scope</summary><p>Project: ${esc(profile.project)}</p><p>Runner: unittest · ${esc(profile.executable)}</p><p>Test roots: ${profile.roots.map(root=>esc(root==='.'?'Project root (.)':root)).join(', ')}. Supported selectors, discovery patterns, and verbosity flags.</p></details>`:'<p>This exact command in this chat’s task copy · until cheapoS restarts. Different commands ask again.</p>';
  const reason=pending.scope_reason&&!pending.scope_reason.startsWith('No project-session')?`<p>${esc(pending.scope_reason)}</p>`:'';
  return `<section class="chat-decision"><strong>Can I run this check?</strong><code class="approval-command">${esc(pending.command.join(' '))}</code>${explanation}${reason}<div class="button-row"><button class="primary-button" data-permission="${choice.scope}">${choice.label}</button><button class="outline-button" data-permission="once">Run once</button><button class="subtle-button" data-permission="decline">Decline</button></div></section>`;
}
function bindPermissions(task) {
  $$('[data-permission]').forEach(button=>button.onclick=async()=>{
    const scope=button.dataset.permission, approval=task.pending_approval.id;
    $$('[data-permission]').forEach(b=>b.disabled=true);
    try{await api('/tasks/'+task.id+'/approval',{approved:scope!=='decline',scope:scope==='decline'?'once':scope,approval_id:approval});await loadTaskPermissions(task,true);await refresh()}
    catch(error){toast(error.message);await refresh();$$('[data-permission]').forEach(b=>b.disabled=false)}
  });
}
function renderChat() {
  const task=state.task;if(!task)return;
  const guide=CheapOSGuide.taskGuide(task),failure=task.status==='error'?CheapOSGuide.failure(task):null;
  const conversation=CheapOSConversation.build(task);
  state.chatDetails ||= new Map();
  const detailKey=key=>task.id+':'+key;
  for(const d of $$('#chat-view details[data-event]'))state.chatDetails.set(detailKey(d.dataset.event),d.open);
  const focused=document.activeElement?.tagName==='SUMMARY'?document.activeElement.closest('#chat-view details')?.dataset.event:null;
  let decision='';
  const button=(action,label,primary=false)=>`<button class="${primary?'primary-button':'subtle-button'}" data-chat-action="${action}">${label}</button>`;
  const routeFailures=task.error_code==='routing_unavailable'?(task.route?.failures||[]):[];
  const errorDetails=routeFailures.length?`<details class="chat-error"><summary>Model check results (${routeFailures.length})</summary>${routeFailures.map(f=>`<p><strong>${esc(f.model)}</strong><br>${esc(f.error)}</p>`).join('')}</details>`:task.error&&task.error!==(failure?.description||guide.description)?`<details class="chat-error"><summary>Details</summary><p>${esc(task.error)}</p></details>`:'';
  if(task.status==='waiting_retry')decision=progressMarkup(task);
  else if(task.environment_setup&&task.status==='paused'){
    const setup=task.environment_setup;
    decision=`<section class="chat-decision"><strong>${setup.status==='missing'?'Set up this task’s verification environment':'Task environment is ready to recheck'}</strong><p>${esc(setup.evidence)}</p><p>Task copy: <code>${esc(setup.workspace)}</code></p><p>${esc(setup.next_step)}</p><p>Dependency folders may be omitted from snapshots. Prepare this task copy; your source checkout is separate. Test permissions do not authorize installation.</p><div class="button-row"><button class="outline-button" data-environment="path">Copy task-copy path</button>${(setup.setup_commands||[]).map((command,index)=>`<button class="outline-button" data-environment="${index}">Copy setup command ${index+1}</button>`).join('')}<button class="outline-button" data-environment="recheck">Re-check task environment</button>${setup.status==='ready'?button('resume','Resume saved verification',true):''}</div>${(setup.setup_commands||[]).map((command,index)=>`<p><code>${esc(command)}</code><br><small>From ${esc(setup.sources[index]?.path)}:${esc(setup.sources[index]?.line)} · run manually inside the task copy.</small></p>`).join('')}</section>`;
  }
  else if(task.pending_approval)decision=permissionMarkup(task);
  else if(CheapOSBranchUI.pausePresentation(task))decision='';
  else if(task.status==='ready')decision=(`<div class="chat-decision"><p><strong>Saved, not started.</strong> ${esc(task.start_error||state.startErrors.get(task.id)||submissionAvailability(task,'interactive').reason||'Send when you are ready.')}</p>${button('start','Retry start',true)}</div>`);
  else if(CheapOSGuide.canCommit(task))decision=(commitDecisionMarkup(task));
  else if(task.changes.length&&['approved','completed','awaiting_reply'].includes(task.status))decision=(`<section class="chat-result">${icon('file')}<div><strong>Changes are saved; review isn’t finished yet.</strong><p>You can keep chatting. To finish this saved patch, cheapoS can complete the missing verification and review.</p><div class="button-row">${button('request-review','Finish review',true)}${button('changes','View diff')}</div></div></section>`);
  else if(!taskBusy(task)&&task.status!=='awaiting_reply')decision=(`<section class="chat-decision"><strong>${esc(failure?.title||guide.title)}</strong><p>${esc(failure?.description||guide.description)}</p>${errorDetails}<div class="button-row">${button(guide.primary==='retry-wait'?'retry-wait':guide.primary==='clarify'?'clarify':task.status==='error'?'start':'resume',guide.primary==='retry-wait'?'Retry when available':guide.primary==='clarify'?guide.primaryLabel||'Continue in chat':task.status==='error'?'Retry':task.status==='takeover_requested'?'Review takeover request':task.status==='budget_paused'?guide.primaryLabel:'Resume',true)}${task.status==='error'||task.error_code==='routing_unavailable'?button('connections','Model settings'):''}${task.changes.length?button('changes','View changes'):''}</div></section>`);
  if(task.archived_at||task.trashed_at||task.branch_run)decision=task.branch_run&&task.pending_approval?permissionMarkup(task):'';
  const lastReply=conversation.findLast(entry=>entry.kind==='assistant');
  $('#chat-view').innerHTML=(task.demo?'<div class="demo-banner">Local demo · scripted models, real edits and checks</div>':task.sample?`<div class="demo-banner">${esc(CheapOSGuide.sampleOutcome(task))}<button class="text-link" data-sample-diagnostics>Connection diagnostics</button></div>`:'')+conversation.map(entry=>CheapOSChatView.message(entry,task,entry===lastReply?decision:'')).join('')+pendingMessageMarkup();
  if($('[data-sample-diagnostics]'))$('[data-sample-diagnostics]').onclick=()=>openConnections();
  $$('[data-environment]').forEach(b=>b.onclick=async()=>{try{if(b.dataset.environment==='recheck'){b.disabled=true;await api('/tasks/'+task.id+'/environment-recheck',{});await refresh()}else{await navigator.clipboard.writeText(b.dataset.environment==='path'?task.workspace:task.environment_setup.setup_commands[Number(b.dataset.environment)]);toast('Copied')}}catch(e){toast(e.message)}finally{b.disabled=false}});
  for(const d of $$('#chat-view details[data-event]')){
    const key=detailKey(d.dataset.event);
    if(state.chatDetails.has(key))d.open=state.chatDetails.get(key);
    d.ontoggle=()=>state.chatDetails.set(key,d.open);
    if(d.classList.contains('workflow-step'))$('summary',d).onclick=()=>{
      if(!d.open)requestAnimationFrame(()=>$('.workflow-stream,.command-panel',d)?.scrollIntoView({block:'nearest',behavior:'instant'}));
    };
    if(d.dataset.event===focused)$('summary',d)?.focus({preventScroll:true});
  }
  if(task.branch_run&&!task.archived_at&&!task.trashed_at)branchUI.render(task);
  const workerStall=task.error_code==='progress_limit'&&task.active_role==='worker'||task.branch_run?.pause_detail?.cause==='repeated_work'&&task.branch_run?.pause_detail?.role==='worker';
  if(workerStall&&['paused','interrupted'].includes(task.status)&&!task.demo&&!task.archived_at&&!task.trashed_at){
    const pause=$('#chat-view .branch-pause')||$('#chat-view .chat-decision');
    if(pause){
      const notice=document.createElement('section');notice.className='coordinator-task-notice';
      notice.innerHTML=coordinatorTaskNotice(task,true)+coordinatorReassessmentMarkup(task)+button('coordinator-settings','Coordinator settings');
      const details=$('details',pause)||$('.button-row',pause);pause.insertBefore(notice,details);
    }
  }
  if(task.error&&!task.branch_run){const logs=document.createElement('button');logs.className='text-link';logs.textContent='View technical logs';logs.onclick=()=>setView('logs');$('#chat-view').append(logs);}
  $$('[data-workflow-logs]').forEach(b=>b.onclick=()=>{setView('logs');const routing=$('#routing-diagnostics');if(routing){routing.open=true;routing.scrollIntoView({block:'start',behavior:'instant'});$('summary',routing)?.focus({preventScroll:true});}});
  updateProgressClock();bindCommitDecision(task);bindTerminalCopy();bindPermissions(task);
  $$('#chat-view [data-chat-action]').forEach(b=>b.onclick=async()=>{
    const action=b.dataset.chatAction;
    if(action==='changes'||action==='activity'){setView(action);return}
    if(action==='clarify'){setView('chat');$('#chat-input')?.focus();return}
    if(action==='stop'){await stopTask();return}
    if(action==='connections'){openConnections(undefined,task);return}
    if(action==='coordinator-settings'){executionPreferences();return}
    if(action==='coordinator-reassess'){await reassessCoordinator(b,task);return}
    if(action==='request-review'){await requestCommitReview(b);return}
    if(action==='boost-headroom'){await boostHeadroom(b);return}
    if(action==='retry-wait'){await startTask(task.id,{retry_when_available:true});return}
    if(action==='resume'){await resumeTask(b);return}
    b.disabled=true;
    if(action==='start'){await startTask(task.id);b.disabled=false;return}
    try{await api('/tasks/'+task.id+'/approval',{approved:action!=='decline',remember:action==='approve-session',approval_id:task.pending_approval.id});await loadTaskPermissions(task,true);await refresh()}catch(e){toast(e.message);b.disabled=false}
  });
}
function reviewDisputeMarkup(task){
 const records=Object.values(task.branch_run?.dispute_ledger?.findings||{}).filter(r=>r.status!=='independently_resolved').slice(-8);
 if(!records.length)return '';
 return `<section class="activity-status"><h3>Review disputes</h3><p>Worker counterevidence is a claim for independent review, not approval.</p>${records.map(r=>{const h=(r.history||[]).at(-1)||{},f=h.finding||{},c=r.worker_counterevidence;return `<details><summary>${esc(r.id)} · ${esc(r.structural?.criterion||'')} · ${Number(r.attempts)||0} repair attempts</summary><p>${esc(f.location||'')} · ${esc(f.expected||'')}</p><p>Reviewer observed: ${esc(f.observed||'')}</p><p>Support: ${esc(f.support||'')}</p><p>Candidate: ${esc(h.candidate_id||'')}</p>${c?`<p>Worker disposition: ${esc(c.disposition)} · ${esc(c.evidence)}</p>`:'<p>No worker counterevidence recorded.</p>'}</details>`;}).join('')}<p>Showing up to eight unresolved disputes. Repetition never grants approval.</p></section>`;
}
function renderActivity() {
  const task=state.task,a=CheapOSGuide.activity(task),guide=CheapOSGuide.taskGuide(task),pause=CheapOSBranchUI.pausePresentation(task),failure=task.status==='error'?CheapOSGuide.failure(task):null;
  const action=(view,label)=>`<button class="outline-button" data-activity-view="${view}">${label}</button>`;
  const timeline=a.items.slice(0,40).reverse().map(item=>`<details class="activity-step ${item.failed?'failed':''}" data-event="step-${item.event.id}"><summary><span class="step-icon">${icon(item.icon)}</span><span><strong>${esc(item.title)}</strong>${item.note?`<small>${esc(item.note)}</small>`:''}</span><time>${new Date(item.event.time).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</time>${icon('chevron')}</summary><div class="step-body">${eventDetail(item.event)}${item.path&&task.changes.some(c=>c.path===item.path)?`<button class="text-link" data-activity-file="${esc(item.path)}">View current diff →</button>`:''}</div></details>`).join('');

  const status=task.pending_approval?permissionMarkup(task):taskBusy(task)?progressMarkup(task):`<section class="activity-status"><span class="activity-eyebrow">${['approved','completed'].includes(task.status)?'RESULT':'CURRENT STATUS'}</span><h3>${esc(failure?.title||guide.title)}</h3><p>${esc(failure?.description||guide.description)}</p>${task.error&&task.error!==guide.description?`<p>${esc(task.error)}</p>`:''}<div class="button-row">${['approved','completed'].includes(task.status)?action('changes','Review changes'):''}${action('chat','Back to chat')}${['paused','budget_paused','interrupted','error','takeover_requested'].includes(task.status)?`<button class="outline-button" id="activity-resume">${pause?'Review pause in chat':task.status==='error'?'Retry':guide.primaryLabel}</button>`:''}${task.error_code==='routing_unavailable'?'<button class="outline-button" id="activity-models">Models</button>':''}</div></section>`;
  $('#activity-view').innerHTML=`<div class="view-title"><div><h2>What’s happening</h2><p>${task.demo?'Scripted demo · real files and checks':'Real actions and saved results from this chat.'}</p></div></div>${status}${reviewDisputeMarkup(task)}${task.check_stream?commandMarkup(task.check_stream,{live:true}):''}<div class="activity-facts"><button data-activity-view="changes"><span>Saved changes · whole chat</span><strong>${a.files} file${a.files===1?'':'s'}</strong><small>Inspect the diff →</small></button><button data-activity-view="tests"><span>Checks · this request</span><strong>${esc(a.checks)}</strong><small>View command output →</small></button><button id="activity-review" ${!a.checkpoint?'disabled':''}><span>Review · this request</span><strong>${esc(a.review)}</strong><small>${a.checkpoint?'Inspect the decision →':'A passing check alone is not approval'}</small></button></div><section class="activity-timeline"><h3>Latest request</h3><p class="activity-request">${esc(a.request)}</p><p class="small muted">Chronological actions${a.items.length>40?' · showing the latest 40':''}</p>${timeline||'<p class="activity-empty">No file actions yet. Conversation and live model output are in Chat.</p>'}</section><button class="text-link" data-activity-view="logs">View technical logs →</button>`;
  $$('[data-activity-view]').forEach(b=>b.onclick=()=>setView(b.dataset.activityView));
  $$('#activity-view [data-chat-action]').forEach(b=>b.onclick=()=>b.dataset.chatAction==='stop'?stopTask():b.dataset.chatAction==='connections'?openConnections():setView('chat'));
  $$('[data-activity-file]').forEach(b=>b.onclick=()=>{state.file=task.changes.findIndex(c=>c.path===b.dataset.activityFile);setView('changes')});
  bindPermissions(task);
  $$('[data-checkpoint]').forEach(b=>b.onclick=()=>checkpointDialog(Number(b.dataset.checkpoint)));
  $('#activity-review').onclick=()=>a.checkpoint&&checkpointDialog(a.checkpoint.number);
  if($('#activity-resume'))$('#activity-resume').onclick=e=>guide.primary==='retry-wait'?startTask(task.id,{retry_when_available:true}):guide.primary==='clarify'?(setView('chat'),$('#chat-input')?.focus()):resumeTask(e.currentTarget);
  if($('#activity-models'))$('#activity-models').onclick=openConnections;
  updateProgressClock();
}
function renderTechnicalLogs(){
 const view=$('#logs-view');view.innerHTML=CheapOSBranchUI.technicalMarkup(state.task)+CheapOSChatView.routingDetails(state.task);const back=$('[data-log-chat]',view);if(back)back.onclick=()=>setView('chat');
}
function checkpointDialog(number) {
  const checkpoint=state.task.checkpoints.find(c=>c.number===number);if(!checkpoint)return;
  const isRunning=taskBusy(state.task);
  const d=dialog(`${modalHeader('REVIEW EVIDENCE','Checkpoint #'+number)}<p class="modal-description">This is the evidence captured for this review. The reviewer can also read the current workspace.</p><div class="checkpoint-section"><h3>Original task</h3><p>${esc(checkpoint.original_task)}</p></div><div class="checkpoint-section"><h3>Worker summary</h3><p>${esc(checkpoint.worker_summary)}</p><p>${esc(checkpoint.uncertainties)}</p></div><div class="checkpoint-section"><h3>Verification</h3><pre>${esc(checkpoint.checks.output)}</pre></div><div class="checkpoint-section"><h3>Patch at this checkpoint</h3><pre>${esc(checkpoint.diff)}</pre></div><div class="checkpoint-section"><h3>${esc(checkpoint.decision)}</h3><p>${esc(checkpoint.feedback)}</p></div><div class="modal-footer"><span>Revert files to this exact checkpoint.</span><button type="button" class="outline-button" id="modal-rollback" ${isRunning?'disabled title="Pause task first"':''}>Rollback to Checkpoint #${number}</button></div>`,'checkpoint-modal');
  const rollbackBtn=$('#modal-rollback',d);
  if(rollbackBtn)rollbackBtn.onclick=async()=>{
    if(isRunning)return;
    rollbackBtn.disabled=true;
    try{
      await api('/tasks/'+state.task.id+'/rollback',{checkpoint:number});
      d.close();
      toast('Rolled back workspace to Checkpoint #'+number);
      await refresh();
    }catch(err){
      toast(err.message);
      rollbackBtn.disabled=false;
    }
  };
}
function patchTotals(patch) {const lines=patch.split('\n');return {add:lines.filter(l=>l.startsWith('+')&&!l.startsWith('+++')).length,remove:lines.filter(l=>l.startsWith('-')&&!l.startsWith('---')).length};}
function diffLines(before,after) {
  const a=before?before.replace(/\n$/,'').split('\n'):[],b=after?after.replace(/\n$/,'').split('\n'):[];
  // Keep very large files responsive; their exact Git patch is always available for export.
  if(a.length*b.length>2_000_000)return [...a.map((text,i)=>({type:'remove',old:i+1,new:'',text})),...b.map((text,i)=>({type:'add',old:'',new:i+1,text}))];
  const dp=Array.from({length:a.length+1},()=>new Uint32Array(b.length+1));
  for(let i=a.length-1;i>=0;i--)for(let j=b.length-1;j>=0;j--)dp[i][j]=a[i]===b[j]?1+dp[i+1][j+1]:Math.max(dp[i+1][j],dp[i][j+1]);
  let i=0,j=0;const rows=[];
  while(i<a.length||j<b.length){if(i<a.length&&j<b.length&&a[i]===b[j])rows.push({type:'context',old:++i,new:++j,text:a[i-1]});else if(j<b.length&&(i===a.length||dp[i][j+1]>dp[i+1][j]))rows.push({type:'add',old:'',new:++j,text:b[j-1]});else rows.push({type:'remove',old:++i,new:'',text:a[i-1]})}return rows;
}
function renderChanges() {
  const task=state.task,files=task.changes;
  if(!files.length){const last=task.commits?.at(-1);$('#changes-view').innerHTML=last?`<section class="commit-success">${icon('check')}<h2>Committed to your project.</h2><p>${esc(last.message)}</p><p><code>${esc(last.commit.slice(0,8))}</code> on <strong>${esc(last.branch)}</strong></p><p class="muted">Your next edits in this chat will build on this commit.</p><details class="patch-help"><summary>View committed patch (${last.files.length} files)</summary><pre>${esc(last.patch)}</pre></details></section>`:'<div class="empty-state">'+icon('code')+'<h2>No changes yet.</h2><p>File edits will appear here as the worker makes them.</p></div>';return}
  state.file=Math.min(state.file,files.length-1);const file=files[state.file],rows=diffLines(file.before,file.after);
  const line=r=>`<div class="diff-line ${r.type}"><span class="line-number">${r.old}</span><span class="line-number">${r.new}</span><span class="diff-sign">${r.type==='add'?'+':r.type==='remove'?'−':' '}</span><span class="source">${esc(r.text)||' '}</span></div>`;
  $('#changes-view').innerHTML=`<div class="view-title"><div><h2>Review the work.</h2><p>${files.length} changed files in the task copy</p></div><div class="button-row"><a class="subtle-button" href="/api/tasks/${task.id}/patch" download>${icon('file')}Export patch</a>${!task.branch_run&&!CheapOSGuide.canCommit(task)&&task.status==='awaiting_reply'?'<button class="primary-button" id="commit-review">Finish review</button>':''}</div></div>${CheapOSGuide.canCommit(task)?commitDecisionMarkup(task):''}<div class="file-list">${files.map((f,i)=>`<button class="file-item ${i===state.file?'selected':''}" data-file="${i}">${icon('file')}<span>${esc(f.path)}</span><span class="file-status">${f.before?'M':'A'}</span></button>`).join('')}</div><div class="diff-panel"><div class="diff-toolbar"><span>${icon('file')}${esc(file.path)}</span><div class="segmented"><button data-diff="unified" class="${state.diff==='unified'?'selected':''}">Unified</button><button data-diff="split" class="${state.diff==='split'?'selected':''}">Split</button></div></div>${file.binary?'<p class="modal-description">Binary change. Inspect the exported Git patch.</p>':state.diff==='unified'?`<div class="diff-code" tabindex="0" aria-label="Unified code diff">${rows.map(line).join('')}</div>`:`<div class="split-diff">${['before','after'].map(side=>`<div class="diff-code" tabindex="0" aria-label="${side==='before'?'Original':'Modified'} file"><div class="split-label">${side==='before'?'Before':'After'}</div>${rows.filter(r=>r.type!==(side==='before'?'add':'remove')).map(r=>`<div class="diff-line ${r.type}"><span class="line-number">${side==='before'?r.old:r.new}</span><span class="source">${esc(r.text)||' '}</span></div>`).join('')}</div>`).join('')}</div>`}</div><div class="diff-bottom">${icon('shield')}${CheapOSGuide.canCommit(task)?'Approve the reviewed patch above, or keep chatting to request changes.':'The task copy is saved. Verification and review must finish before committing.'}</div><details class="patch-help"><summary>Apply manually instead</summary><p>From your original repository, check the downloaded patch first, then apply it:</p><pre>git apply --check /path/to/cheapos-${task.id.slice(0,8)}.patch\ngit apply /path/to/cheapos-${task.id.slice(0,8)}.patch</pre><p>For large files, the visual comparison shows whole blocks; the exported Git patch preserves the exact change, including file modes and final newlines.</p></details>`;
  if($('#commit-review'))$('#commit-review').onclick=e=>requestCommitReview(e.currentTarget);
  bindCommitDecision(task);
  $$('[data-file]').forEach(b=>b.onclick=()=>{state.file=Number(b.dataset.file);renderChanges()});$$('[data-diff]').forEach(b=>b.onclick=()=>{state.diff=b.dataset.diff;renderChanges()});
}
async function requestCommitReview(trigger) {
  const task=state.task;if(!task)return;
  trigger.disabled=true;trigger.textContent='Requesting review…';
  try {
    await api('/tasks/'+task.id+'/message',{message:'Prepare the current saved patch for review and commit. Keep the implementation unchanged unless verification or reviewer feedback requires a fix. Reuse the configured verification command and submit a checkpoint for reviewer approval. The app will present the final diff for the user to approve and commit afterward; do not run Git commit or push.'});
    await refresh();setView('chat');
  } catch(e){toast(e.message);trigger.disabled=false;trigger.textContent='Finish review'}
}
const commitPreviews=new Map();
const previewKey=task=>(task.workspace_generation||0)+':'+task.patch_digest+':'+(task.checkpoints?.at(-1)?.number??task.checkpoints?.length??0);
function renderPatchPreview(patch) {
  if(!patch)return '';
  const lines=patch.split('\n');
  const rendered=lines.map(l=>{
    if(l.startsWith('diff --git')||l.startsWith('index ')||l.startsWith('new file'))return `<div class="diff-meta-line header">${esc(l)}</div>`;
    if(l.startsWith('---')||l.startsWith('+++'))return `<div class="diff-meta-line">${esc(l)}</div>`;
    if(l.startsWith('@@'))return `<div class="diff-hunk">${esc(l)}</div>`;
    if(l.startsWith('+'))return `<div class="diff-line add"><span class="diff-sign">+</span><span class="source">${esc(l.slice(1))||' '}</span></div>`;
    if(l.startsWith('-'))return `<div class="diff-line remove"><span class="diff-sign">−</span><span class="source">${esc(l.slice(1))||' '}</span></div>`;
    return `<div class="diff-line"><span class="diff-sign"> </span><span class="source">${esc(l.startsWith(' ')?l.slice(1):l)||' '}</span></div>`;
  }).join('');
  return `<div class="commit-diff-preview diff-code" tabindex="0" aria-label="Reviewed patch">${rendered}</div>`;
}
function commitDecisionMarkup(task) {
  if(task.branch_run)return '';
  if(CheapOSGuide.commitDeferred(task))return `<section class="chat-result"><div><strong>Changes are saved, without a commit.</strong><p>You can keep chatting or reconsider this patch whenever you’re ready.</p><button class="subtle-button" data-commit-action="reopen">Reopen decision</button></div></section>`;
  const entry=commitPreviews.get(task.id),current=entry?.key===previewKey(task)?entry:null;
  if(!current){ensureCommitPreview(task);return '<section class="chat-result"><div><strong>Checks and review are complete.</strong><p>Preparing your final diff and commit message…</p></div></section>'}
  if(current.loading)return '<section class="chat-result"><div><strong>Checks and review are complete.</strong><p>Preparing your final diff and commit message…</p></div></section>';
  if(current.error){
    const conflict=current.code==='project_conflict';
    return `<section class="chat-result"><div><strong>${conflict?'Let’s combine this with your current project.':'Your changes are saved.'}</strong><p>${esc(current.error)}</p>${conflict?`<p class="small muted">Files in this patch: ${(current.files||[]).map(esc).join(', ')}. I’ll preserve the previous task copy, combine the versions here, and send the result through checks and review before you approve a commit.</p>`:''}<div class="button-row">${conflict?'<button class="primary-button" data-commit-action="reconcile">Reconcile in this chat</button>':''}<button class="${conflict?'subtle-button':'primary-button'}" data-commit-action="refresh">${conflict?'Recheck project':'Refresh commit preview'}</button><button class="subtle-button" data-commit-action="change">Keep chatting</button>${task.commit_pending?'':'<button class="subtle-button" data-commit-action="defer">Decline</button>'}</div></div></section>`;
  }
  const p=current.preview;
  return `<section class="commit-decision" aria-label="Your decision"><h3>${p.retry?'Finish your approved commit.':'Ready for your approval.'}</h3><p class="muted">${esc(p.review)} · checks passed. ${p.retry?'Finish the saved attempt before starting more work.':'You can approve this patch, ask for changes, or keep chatting.'}</p><dl class="commit-target"><div><dt>Project</dt><dd>${esc(p.source)}</dd></div><div><dt>Commit to</dt><dd>${esc(p.branch)} <span class="muted">at ${esc(p.head.slice(0,8))}</span></dd></div></dl><details class="commit-patch" data-event="commit-patch-${esc(task.patch_digest)}" open><summary>Final diff · ${p.files.length} file${p.files.length===1?'':'s'}</summary>${renderPatchPreview(p.patch)}</details><form id="commit-form"><label>Commit message<textarea name="message" rows="2" maxlength="2000" required ${p.retry?'readonly':''}>${esc(current.message)}</textarea></label><p class="form-error" role="alert">${esc(current.submitError||'')}</p><div class="button-row"><button type="submit" class="primary-button" ${current.submitting?'disabled':''}>${current.submitting?'Committing…':p.retry?'Finish commit':'Approve & commit'}</button>${p.retry?'':`<button type="button" class="subtle-button" data-commit-action="change" ${current.submitting?'disabled':''}>Request changes</button>`}${p.retry?'':`<button type="button" class="subtle-button" data-commit-action="defer" ${current.submitting?'disabled':''}>Decline</button>`}</div><p class="small muted">${p.retry?'Your approved commit was interrupted. Finish the saved attempt to continue chatting.':'Approval applies this reviewed patch and creates a local commit. Declining keeps your edits saved.'} Pushing is separate.</p></form></section>`;
}
async function ensureCommitPreview(task,force=false) {
  const key=previewKey(task),existing=commitPreviews.get(task.id);
  if(!force&&existing?.key===key)return;
  const entry={key,loading:true,message:existing?.key===key?existing.message:undefined};commitPreviews.set(task.id,entry);
  try {
    const p=await api('/tasks/'+task.id+'/commit-preview',{});
    entry.preview=p;entry.message=entry.message??p.message;
  } catch(e){entry.error=e.message;entry.code=e.code;entry.files=e.files}
  finally {entry.loading=false;if(state.task?.id===task.id&&previewKey(state.task)===key&&commitPreviews.get(task.id)===entry)renderTask()}
}
function requestChanges() {
  setView('chat');const input=$('#chat-input');input.placeholder='Tell cheapoS what to change, or ask a question…';input.focus();input.scrollIntoView({block:'nearest'});
}
function bindCommitDecision(task) {
  if(task.archived_at||task.trashed_at)return;
  $$('[data-commit-action]').forEach(b=>b.onclick=async()=>{
    const action=b.dataset.commitAction;
    if(action==='change'){requestChanges();return}
    if(action==='refresh'){b.disabled=true;b.textContent='Checking project…';try{await ensureCommitPreview(task,true)}finally{b.disabled=false}return}
    b.disabled=true;
    if(action==='reconcile'){
      b.textContent='Combining saved work…';
      try{
        const updated=await api('/tasks/'+task.id+'/reconcile',{patch_digest:task.patch_digest});
        commitPreviews.delete(task.id);
        if(state.task?.id===task.id){state.task=updated;renderTask()}
        if(updated.status==='paused')await api('/tasks/'+task.id+'/start',{});
        await refresh();setView('chat');
      }catch(e){toast(e.message);b.disabled=false;b.textContent='Reconcile in this chat';await refresh()}
      return;
    }
    try {
      const updated=await api('/tasks/'+task.id+'/commit-decision',{decision:action==='defer'?'defer':'review',patch_digest:task.patch_digest});
      commitPreviews.delete(task.id);
      if(state.task?.id===task.id){state.task=updated;renderTask()}
    }catch(e){toast(e.message);b.disabled=false}
  });
  const form=$('#commit-form');if(!form)return;
  const entry=commitPreviews.get(task.id);
  $('textarea',form).oninput=e=>{entry.message=e.target.value};
  form.onsubmit=e=>{e.preventDefault();if(entry.submitting)return;formAction(form,async()=>{
    entry.submitting=true;entry.submitError='';$('button[type="submit"]',form).textContent='Committing…';$$('[data-commit-action]',form).forEach(b=>b.disabled=true);
    try {
      const result=await api('/tasks/'+task.id+'/commit',{approved:true,approval_id:entry.preview.approval_id,message:entry.message});
      commitPreviews.delete(task.id);await refresh();toast('Committed '+result.commit.slice(0,8)+' to '+result.branch);
      if(state.task?.id===task.id&&CheapOSConversation.readyForNext(state.task)){
        setView('chat');
        if(!task.demo)$('#chat-input').focus({preventScroll:true});
      }
    } catch(error) {entry.submitError=error.message;entry.error=error.message;entry.code=error.code;entry.files=error.files;throw error}
    finally {entry.submitting=false;if(state.task?.id===task.id)renderTask()}
  })};
}
function renderTests() {
  const checks=state.task.checks;
  if(!checks.length){$('#tests-view').innerHTML='<div class="empty-state">'+icon('tests')+'<h2>No checks run yet.</h2><p>The configured verification command will run in the task copy. Results appear here.</p></div>';return}
  const index=state.run<0?checks.length-1:Math.min(state.run,checks.length-1),check=checks[index];
  const formattedOutput=CheapOSGuide.formatTerminalOutput(check.output);
  const exitPill=check.passed?`<span class="term-status-pill pass">Exit 0 · ${check.duration.toFixed(2)}s${check.allowed_seconds?` / ${Number(check.allowed_seconds).toFixed(1)}s allowed`:''}</span>`:`<span class="term-status-pill fail">Exit ${check.exit_code} · ${check.duration.toFixed(2)}s${check.allowed_seconds?` / ${Number(check.allowed_seconds).toFixed(1)}s allowed`:''}</span>`;
  $('#tests-view').innerHTML=`<div class="view-title"><div><h2>Evidence, before approval.</h2><p>Actual output from your configured command</p></div></div><div class="test-run-picker"><span>Verification history</span><select id="run-picker" aria-label="Verification run">${checks.map((c,i)=>`<option value="${i}" ${i===index?'selected':''}>Run ${i+1} · ${c.passed?'Passed':'Failed'}</option>`).join('')}</select></div><div class="test-summary ${check.passed?'':'failure'}">${icon(check.passed?'check':'x')}<strong>${check.passed?'Command passed':'Command failed'}</strong><span>Exit ${check.exit_code} · ${check.duration.toFixed(2)}s${check.allowed_seconds?` / ${Number(check.allowed_seconds).toFixed(1)}s allowed`:''}</span></div><code class="check-command">${esc(check.command.join(' '))}</code>${check.reason?`<p class="form-error">${esc(check.reason)}. ${esc(check.next_action||'')}</p>`:''}<div class="terminal-window ${check.passed?'passed':'failed'}"><div class="terminal-header"><div class="traffic-dots"><span class="dot-red"></span><span class="dot-yellow"></span><span class="dot-green"></span></div><span class="terminal-title"><code>${esc(check.command.join(' '))}</code></span><div class="terminal-actions">${exitPill}<button type="button" class="terminal-copy-btn" data-copy-terminal="tests-run-output" title="Copy output">${icon('file')} Copy</button></div></div><div class="terminal-viewport"><pre class="command-output terminal-body" tabindex="0" data-command-output="tests-run-output">${formattedOutput}</pre></div></div>${rawCheckLink(check)}<p class="muted small" style="margin-top:14px">Passed means this command exited successfully. The reviewer still checks whether the implementation satisfies the task.</p>`;
  $('#run-picker').onchange=e=>{state.run=Number(e.target.value);renderTests()};
  bindTerminalCopy();
}
function bindTerminalCopy() {
  $$('[data-raw-check]').forEach(btn=>btn.onclick=async()=>{
    const url='/api/tasks/'+encodeURIComponent(state.task.id)+'/checks/'+encodeURIComponent(btn.dataset.rawCheck)+'/raw';
    try{
      const response=await fetch(url),text=await response.text();
      if(!response.ok)throw new Error(JSON.parse(text).error||'Raw output unavailable');
      dialog(`${modalHeader('VERIFICATION EVIDENCE','Original check output')}<p>Unfiltered retained bytes decoded as UTF-8. At most 2 MB; latest 8 runs. See the check result for truncation and exit status.</p><pre class="raw-check-output" style="max-height:60vh;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere">${esc(text)}</pre><a href="${url}" download="check-output.log">Download original bytes</a>`,'project-modal setup-modal');
    }catch(error){toast(error.message)}
  });

  $$('[data-copy-terminal]').forEach(btn=>{
    btn.onclick=async()=>{
      const key=btn.dataset.copyTerminal;
      const pre=$(`[data-command-output="${key}"]`);
      if(!pre)return;
      const text=pre.innerText||pre.textContent||'';
      try{
        await navigator.clipboard.writeText(text);
        toast('Command output copied to clipboard');
      }catch{
        toast('Could not copy to clipboard');
      }
    };
  });
}
function renderInspector() {
  const t=state.task,config=t&&!t.demo?t.providers:state.config;
  const roles=['coordinator','worker','reviewer','planner'].filter(role=>!['coordinator','planner'].includes(role)||config[role]||t?.usage?.[role]?.tokens).map(role=>`<div class="role-row"><span class="role-icon ${role}-icon">${icon(role==='worker'?'code':'spark')}</span><span><span class="role-label">${role.toUpperCase()}</span><strong>${esc(t?.demo?'Scripted demo':(role==='planner'?(t?.request_metrics?.findLast(r=>r.role==='planner')?.served_model||t?.request_metrics?.findLast(r=>r.role==='planner')?.model):null)||config[role]?.model||'Choose a model')}</strong></span></div>`);
  const intro=t?`<section class="economy-intro compact-intro"><div class="mode-badge">${icon('leaf')}Economy mode</div><p>Work, verify, then ask for a second opinion.</p></section>`:`<section class="economy-intro"><div class="economy-icon">${icon('leaf')}</div><h2>A little patience.<br>A little more in your pocket.</h2><p>Spend less on the loop.<br>Save the stronger model for review.</p><div class="mode-badge">${icon('leaf')}Economy mode</div></section>`;
  const models=`<section class="model-roles">${roles.join('<div class="role-connection"><span></span></div>')}</section>`;
  const usage=t?`<section class="usage"><div class="section-title">Compute, thoughtfully spent</div><div class="cost-total"><strong>${money(t.usage.cost)}</strong><span>${t.demo?'no model charges':'accounted session cost'}</span></div><div class="usage-table">${['coordinator','worker','reviewer','planner'].filter(role=>t.usage[role]).map(role=>`<div><span>${role==='worker'?'Worker':role==='coordinator'?'Local chat / coordinator':role==='planner'?'Planner':'Reviewer'}</span><span>${t.usage[role].tokens.toLocaleString()} <small>tokens</small></span><strong>${money(t.usage[role].cost)}</strong></div>`).join('')}</div><div class="budget-meter"><span style="width:${Math.min(100,t.limits.dollars>0?t.usage.cost/t.limits.dollars*100:0)}%"></span></div><p class="small muted">${money(t.limits.dollars)} estimated cap · ${t.limits.reviewer_tokens.toLocaleString()} reviewer tokens</p><p class="small muted">${t.usage.uncertain_requests?`${t.usage.uncertain_requests} uncertain request(s): reservations remain counted.`:t.usage.estimated_requests?'Some costs use your configured token prices.':t.demo?'Demo usage is zero. No savings are claimed.':'Reported cost when available; configured prices otherwise.'}</p>${!taskBusy(t)&&!['approved','completed'].includes(t.status)?'<button class="text-link" id="edit-limits">Review limits →</button>':''}</section>`:'';
  const journey=t?`<section class="journey"><div class="section-title">This session</div><ol class="journey-list">${[['Worker turns',t.worker_turns],['Tool actions',t.tool_actions],['Checkpoints',t.checkpoints.length],['Reviewer calls',t.review_count],['Planner calls',t.metrics?.calls?.planner??'Unknown'],['Latest check',t.checks.length?(t.checks.at(-1).passed?'Passed':'Failed'):'Not run']].map(([label,value])=>`<li><span class="journey-dot">${icon('check')}</span><span>${label}</span><strong>${value}</strong></li>`).join('')}</ol></section>`:'';
  const workspace=t?`<details class="workspace-info"><summary>Workspace details</summary><p>Task copy</p><code>${esc(t.workspace)}</code><p>Snapshot: ${t.snapshot.files} files · ${t.snapshot.skipped.length} excluded</p><p class="small">Snapshot excludes common secret files and dependency folders. Review your repository before sending its contents to a provider.</p></details>`:`<section class="usage"><div class="section-title">Yours, from the start</div><p class="small muted">Open source. Local task history. Your providers, your keys, your limits.</p><button class="subtle-button" id="inspector-connect">Set up connections →</button></section>`;
  $('#session-details').innerHTML=intro+models+usage+journey+workspace+(t?'<button class="subtle-button" id="session-permissions">Session permissions</button><button class="subtle-button" id="open-activity">See activity →</button>':'');if($('#open-activity'))$('#open-activity').onclick=()=>setView('activity');
  if($('#session-permissions'))$('#session-permissions').onclick=sessionPermissions;
  if($('#edit-limits'))$('#edit-limits').onclick=chatLimits;if($('#inspector-connect'))$('#inspector-connect').onclick=openConnections;
}
const numberField=(name,label,value,min,max,step='1')=>`<label>${label}<input name="${name}" type="number" min="${min}" max="${max}" step="${step}" value="${value}" required></label>`;
function limitFields(limits={dollars:0,reviewer_tokens:200000,iterations:5,worker_turns:40,output_tokens:2048,run_minutes:15}) {
  const preset=CheapOSGuide.workPreset(limits);
  return `<div class="field-grid"><label class="checkbox-field"><input type="checkbox" name="free_only" ${limits.dollars===0?'checked':''}><span>Free only</span></label><div data-spending-cap ${limits.dollars===0?'hidden':''}>${numberField('dollars','Explicit spending cap ($)',limits.dollars,limits.dollars===0?0:.01,100,'0.01')}</div><label>Working time<select name="work_preset">${[['interactive','Standard · 15 minutes'],['extended','Extended · 45 minutes'],['custom','Custom']].map(([value,label])=>`<option value="${value}" ${preset===value?'selected':''}>${label}</option>`).join('')}</select><small data-work-duration>${limits.run_minutes??15} minutes of working time per run</small></label></div><details class="advanced"><summary>Advanced limits</summary><p class="small muted">Working time covers the whole run, including cooldown waits. A verification timeout bounds one command and cannot extend the run.</p><div class="field-grid">${numberField('reviewer_tokens','Reviewer token limit',limits.reviewer_tokens,512,1000000)}${numberField('iterations','Max worker iterations',limits.iterations,1,20)}${numberField('worker_turns','Worker turns per request',limits.worker_turns,1,200)}${numberField('output_tokens','Output tokens per request',limits.output_tokens,128,16384)}${numberField('checkpoint_turns','Checkpoint interval (turns)',limits.checkpoint_turns??12,2,200)}${numberField('run_minutes','Minutes per run (excludes approval waits)',limits.run_minutes??15,1,720)}${numberField('check_seconds','Seconds per verification command',limits.check_seconds??90,1,1800)}</div></details>`;
}
function bindLimitFields(form){
  const preset=$('[name="work_preset"]',form);if(!preset)return;
  const sync=()=>{const limits=readLimits(new FormData(form));preset.value=CheapOSGuide.workPreset(limits);$('[data-work-duration]',form).textContent=`${limits.run_minutes} minutes of working time per run`;};
  preset.onchange=()=>{if(preset.value==='custom'){$('details.advanced',form).open=true;return}const next=CheapOSGuide.presetLimits(readLimits(new FormData(form)),preset.value);for(const key of ['run_minutes','worker_turns','iterations'])$(`[name="${key}"]`,form).value=next[key];sync()};
  for(const input of $$('input[type="number"]',form))input.addEventListener('input',sync);
  $('[name="free_only"]',form).onchange=e=>{const cap=$('[name="dollars"]',form);if(e.target.checked)cap.value=0;cap.min=e.target.checked?0:.01;$('[data-spending-cap]',form).hidden=e.target.checked;};
}
const readLimits=f=>Object.fromEntries(['dollars','reviewer_tokens','iterations','worker_turns','output_tokens','checkpoint_turns','run_minutes','check_seconds'].map(k=>[k,Number(f.get(k))]));
function newTask(prefill='',preset={}) {
  home();
  branchUI.newChat();
  if(preset.repository){state.project={path:preset.repository,name:basename(preset.repository)};renderHome();restoreDraft()}
  if(prefill){$('#chat-input').value=prefill;saveDraft();renderComposer()}
  if(!state.project)openProject();else $('#chat-input').focus();
}
const executionLabel=mode=>({delegate:'Delegate heavy work',local:'All local',remote:'All remote',manual:'Manual model pair'}[mode]||'Manual model pair');
function coordinatorTaskNotice(task,paused=false){
  if(!task||task.demo)return '';
  const status=CheapOSGuide.coordinatorStatus(task);
  return `<div class="execution-notice"><strong>This chat · Coordinator assistance: ${status.label}</strong><p>${esc(paused&&status.pauseNote?status.pauseNote:status.detail)}</p><p>Restarting keeps this chat's saved choice. Execution defaults apply to new chats.</p></div>`;
}
function coordinatorReassessmentMarkup(task){
  const available=task.coordinator_reassessment;
  if(!available)return '';
  if(!available.available)return `<p class="small">${esc(available.reason)}</p>`;
  const busy=state.coordinatorReassessing?.has(task.id),error=state.coordinatorErrors?.get(task.id);
  return `<p>Use ${esc(available.model)} to reassess these saved files once, then continue only if it provides a next step. Keeps remaining limits, permissions and review requirements. No new prompt needed.</p><button class="primary-button" data-chat-action="coordinator-reassess" ${busy?'disabled':''}>${busy?'Requesting reassessment…':CheapOSGuide.coordinatorStatus(task).enabled?'Reassess with coordinator':'Enable coordinator &amp; reassess'}</button>${error?`<p role="alert">${esc(error)}</p>`:''}`;
}
async function reassessCoordinator(button,task){
  state.coordinatorReassessing ||= new Set();state.coordinatorErrors ||= new Map();
  if(state.coordinatorReassessing.has(task.id))return;
  state.coordinatorReassessing.add(task.id);state.coordinatorErrors.delete(task.id);
  button.disabled=true;button.textContent='Requesting reassessment…';
  try{const saved=await api('/tasks/'+task.id+'/start',{coordinator_reassessment:true});if(state.task?.id===task.id){state.task=saved;renderTask();}}
  catch(error){state.coordinatorErrors.set(task.id,error.message);toast(error.message);}
  finally{state.coordinatorReassessing.delete(task.id);if(state.task?.id===task.id)renderChat();}
}
function coordinatorSettings(saved,models){
  const selected=saved.coordinator_model||saved.local_model||'',known=Array.isArray(models),choices=known?models:[];
  return `<section class="execution-notice"><h3>Coordinator assistance — recommended</h3><p><strong>Defaults for new chats</strong> · ${saved.coordinator_assistance===true?'On':'Off'}</p><p>Optional and Off until you enable it. Restarting restores your saved choice; it does not turn assistance on.</p><p>Let a local model help redirect stalled work. Coding and independent review keep their selected models.</p><label class="full-field">Assistance for new chats<select name="coordinator_assistance"><option value="off" ${saved.coordinator_assistance!==true?'selected':''}>Off</option><option value="on" ${saved.coordinator_assistance===true?'selected':''}>On · help when work stalls</option></select></label><label class="full-field">Installed local coordinator<select name="coordinator_model"><option value="">Use configured local chat model</option>${selected&&!choices.includes(selected)?`<option selected value="${esc(selected)}">${esc(selected)} · availability not confirmed</option>`:''}${choices.map(name=>`<option value="${esc(name)}" ${name===selected?'selected':''}>${esc(name)}</option>`).join('')}</select></label><p data-coordinator-status>${known?(choices.length?'Installed models advertise local completion and tools. The saved model is checked again when needed.':'No eligible installed local model is available. Ordinary remote work remains usable.'):'Local model availability is not checked. Ordinary remote work remains usable.'}</p><button type="button" class="outline-button" data-coordinator-refresh>Refresh installed models</button><p>Idle until a worker stalls, then one bounded consultation per request or unattended item. Returns to idle afterward. Local inference uses laptop resources; no background thinking, downloads or remote fallback. Applies only to new tasks.</p></section>`;
}
function executionPreferences() {
  const saved=state.preferences.execution||{},local=state.config.worker?.base_url?.includes(':11434')?state.config.worker.model:'';
  const d=dialog(`<form>${modalHeader('EXECUTION','Where should the work run?')}<p class="modal-description">Choose how new chats use your laptop and connected providers.</p>${state.task?`<p class="execution-notice">This chat keeps <strong>${esc(executionLabel(state.task.execution?.mode))}</strong> and its saved models. Start a new chat to use a different setup.</p>`:''}${coordinatorTaskNotice(state.task)}<div class="execution-options">${[
    ['delegate','Delegate heavy work','Short local chats. Free remote models inspect files, implement changes, and review. Your local model goes idle after handoff.'],
    ['local','All local','Work and review on your own hardware. No remote model requests.'],
    ['remote','All remote','A responding free OmniRoute model handles chat and work; a different free model reviews.'],
    ['manual','Manual model pair','Use the worker and reviewer selected in Models, including paid models when your spending cap allows.']
  ].map(([value,title,description])=>`<label class="execution-option"><input type="radio" name="mode" value="${value}" ${(saved.mode||'manual')===value?'checked':''}><span><strong>${title}</strong><small>${description}</small></span></label>`).join('')}</div><div id="execution-local"><label class="full-field">Installed Ollama model<input name="local_model" value="${esc(saved.local_model||local)}" placeholder="Your installed model ID" autocomplete="off"><small>Used for short chat in Delegate mode, and implementation in All local.</small></label><label class="full-field" id="execution-reviewer">Local reviewer model · optional<input name="local_reviewer" value="${esc(saved.local_reviewer||'')}" placeholder="Use the same local model" autocomplete="off"></label><label class="full-field">Local planner model · optional<input name="local_planner" value="${esc(saved.local_planner||'')}" placeholder="Use the local reviewer" autocomplete="off"></label></div><p id="execution-remote" class="execution-notice">Uses providers you enabled in OmniRoute. Project context is sent when work is handed off. cheapoS checks up to four free candidates per role without project data. A worker handles chat and edits; a different reviewer is selected at a checkpoint. Failed models cool down; up to two free-model handoffs per request continue saved work automatically. Saved edits wait if review is unavailable. No automatic paid or local fallback.</p>${coordinatorSettings(saved,state.readiness?.paths?.local?.models)}<p class="small muted">Free routing uses advertised prices. Check OmniRoute’s fallback and billing settings. Automatic chats can switch between free models after failures. Manual and local choices stay fixed. Saving does not start inference or download anything.</p><p class="form-error" role="alert"></p><div class="modal-footer"><span>Applies to new chats.</span><button class="primary-button" type="submit">Save defaults for new chats</button></div></form>`,'execution-modal');
  const form=$('form',d),layout=()=>{const mode=new FormData(form).get('mode');$('#execution-local',d).hidden=!['local','delegate'].includes(mode);$('#execution-reviewer',d).hidden=mode!=='local';$('#execution-remote',d).hidden=!['remote','delegate'].includes(mode);$('[name="local_model"]',d).required=['local','delegate'].includes(mode)};
  $$('[name="mode"]',d).forEach(input=>input.onchange=layout);layout();
  $('[data-coordinator-refresh]',d).onclick=async()=>{const status=$('[data-coordinator-status]',d);status.textContent='Checking installed local models…';try{const readiness=await api('/readiness?refresh=1');if(!d.isConnected)return;const models=readiness.paths?.local?.models,select=$('[name="coordinator_model"]',d),selected=select.value;if(!Array.isArray(models)){status.textContent='Local inspection is pending or unavailable. Refresh again later; other work is unaffected.';return;}for(const name of models)if(![...select.options].some(o=>o.value===name))select.add(new Option(name,name));select.value=selected;status.textContent=models.length?'Installed eligible local models refreshed. Saved choice is preserved.':'No eligible local models found. Assistance will be skipped if unavailable.';}catch{if(d.isConnected)status.textContent='Could not check local models. Other work remains usable.';}};
  form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{const f=new FormData(form);state.preferences=await api('/preferences',{execution:{...saved,...Object.fromEntries(['mode','local_model','local_reviewer','local_planner','coordinator_model'].map(k=>[k,String(f.get(k)||'')])),coordinator_assistance:f.get('coordinator_assistance')==='on'}});d.close();renderComposer();toast(state.task?'Defaults saved for new chats. This chat keeps its saved coordinator setting.':'Defaults saved for new chats.');})};
}
function chatLimits({defaults=false}={}) {
  const task=defaults?null:state.task,limits=task?.limits||state.preferences.limits;
  const d=dialog(`<form>${modalHeader('SPENDING & LIMITS',task?'Limits for this chat':'Defaults for new chats')}<p class="modal-description">Choose a bounded work session. Presets change working time and task turns; they keep your spending cap and model placement.</p>${limitFields(limits)}<p class="small muted">Free only uses configured prices; it is not a provider billing guarantee.</p>${task?'<button type="button" class="text-link" data-new-defaults>Edit defaults for new chats</button>':''}<p class="small muted">${task?'Usage is cumulative across this chat. Saving does not resume it.':'These defaults apply when you send the first message in a new chat.'}</p><p class="form-error" role="alert"></p><div class="modal-footer"><span>Cost estimates use your configured prices.</span><button class="primary-button" type="submit">Save limits</button></div></form>`);
  const form=$('form',d);bindLimitFields(form);if($('[data-new-defaults]',d))$('[data-new-defaults]',d).onclick=()=>{d.close();chatLimits({defaults:true})};if(task&&taskBusy(task)){ $('[type="submit"]',form).disabled=true;$('.form-error',form).textContent='Pause this chat before changing its limits. New-chat defaults can be edited separately.';}form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{const limits=readLimits(new FormData(form));if(task){state.task=await api('/tasks/'+task.id+'/limits',{limits})}else state.preferences=await api('/preferences',{limits});d.close();renderComposer();if(state.task)renderInspector()})};
}
const submissionEntries=new Set();
async function sendChat(){const owner=draftKey();if(submissionEntries.has(owner))return;submissionEntries.add(owner);try{await dispatchChat();}finally{submissionEntries.delete(owner);}}
async function dispatchChat() {
  const task=state.task,busy=task&&taskBusy(task);
  if(sendingHere())return;
  if(!busy&&!submissionAvailability(task).allowed){renderComposer();return;}
  if(await branchUI.interceptSubmit())return;
  if(state.task!==task)return;
  if(task?.branch_run||busy){await steerTask();return;}
  if(task?.status==='ready'){await startTask(task.id);return;}
  const message=$('#chat-input').value.trim();if(!message)return;
  if(!state.project){openProject(()=>{$('#chat-input').value=message;saveDraft();renderComposer()});return;}
  if((state.preferences.execution?.mode||'manual')==='manual'&&(!state.config.worker||!state.config.reviewer)){openConnections(()=>{$('#chat-input').focus()});return;}
  const key=draftKey(),selection=state.selection,repository=state.project.path;beginMessageSend(key,message);
  try {
    if(task){const saved=await api('/tasks/'+task.id+'/message',{message});state.pendingMessages.delete(key);clearOwnedDraft(key,message);if(state.selection===selection&&state.task?.id===task.id){state.task=saved;renderTask();}void refreshContext();}
    else {const created=await api('/tasks',{repository,prompt:message,conversational:true,limits:state.preferences.limits});await loadTasks();if(state.selection===selection){await selectTask(created.id);}state.pendingSends.add(created.id);try{const started=await startTask(created.id);if(started)clearOwnedDraft(key,message);}finally{state.pendingSends.delete(created.id);}}
    if(state.selection===selection)$('#view-container').scrollTop=$('#view-container').scrollHeight;
  }catch(e){state.sendErrors.set(key,e.message);toast(e.message);}
  finally{state.pendingMessages.delete(key);state.pendingSends.delete(key);if(draftKey()===key){if(state.task)renderChat();else renderHome();}renderComposer();if(state.selection===selection)$('#chat-input').focus();}
}
async function steerTask(text) {
  const task=state.task,message=text||$('#chat-input').value.trim();
  if(!task||!message||sendingHere()||task.status==='stopping'||state.pausingTask===task.id)return;
  const key=draftKey(),selection=state.selection;state.pendingSends.add(key);saveDraft();renderComposer();
  try {await api('/tasks/'+task.id+(task.branch_run?'/branch-message':'/steer'),{message});clearOwnedDraft(key,message);await refresh();if(state.selection===selection){toast('cheapoS will use your update on the next step.');$('#view-container').scrollTop=$('#view-container').scrollHeight;}}
  catch(e){toast(e.message);}finally{state.pendingSends.delete(key);renderComposer();if(state.selection===selection)$('#chat-input').focus();}
}
async function boostHeadroom(button) {
  const task=state.task;if(!task)return;
  if(button)button.disabled=true;
  try {
    await api('/tasks/'+task.id+'/headroom',{reviewer_tokens:100000,worker_turns:10});
    toast('⚡ Headroom boosted (+100k reviewer tokens, +10 turns)');
    await startTask(task.id);
  }catch(e){toast(e.message);if(button)button.disabled=false}
}
async function startTask(id,changes={}) {
  const task=state.task?.id===id?state.task:state.tasks.find(t=>t.id===id),availability=submissionAvailability(task,'interactive');
  if(!availability.allowed){state.startErrors.set(id,availability.reason);if(state.task?.id===id)renderTask();return false;}
  try{await api('/tasks/'+id+'/start',changes);state.startErrors.delete(id);await refresh();return true;}
  catch(e){
    // A lost response may hide a successful start. Reconcile the same saved task.
    let saved;try{saved=await api('/tasks/'+id);}catch{}
    if(saved&&saved.status!=='ready'&&!saved.start_error){state.startErrors.delete(id);if(state.task?.id===id){state.task=saved;renderTask();}return true;}
    state.startErrors.set(id,saved?.start_error||e.message||'Could not confirm start. Retry this saved task.');
    if(state.task?.id===id){if(saved)state.task=saved;renderTask();}return false;
  }
}
async function resumeTask(button) {
  const paused=CheapOSBranchUI.pausePresentation(state.task);
  if(paused&&state.task?.branch_run?.pause_detail?.next_action!=='resume'){setView('chat');return;}

  if(CheapOSGuide.taskGuide(state.task).primary==='new-planning'){await newTask();return;}
  if(state.task?.branch_run){try{await resumeBranchRun(state.task);}catch(e){toast(e.message);}return;}
  const task=state.task;if(!task)return;
  if(['budget_paused','takeover_requested'].includes(task.status)){resumeDialog();return}
  if(button)button.disabled=true;
  try{await startTask(task.id)}finally{if(button)button.disabled=false}
}
function resumeDialog() {
  const task=state.task,takeover=task.status==='takeover_requested';
  const hit=task.limit_hit||(task.error_code==='worker_turn_limit'?{key:'worker_turns',used:task.request_worker_turns??task.worker_turns,allowed:task.limits.worker_turns,remaining:0}:null);
  const fields={worker_turns:['Worker turns allowed for this request',1,200,'1'],run_minutes:['Working minutes for the next run',1,720,'1'],reviewer_tokens:['Reviewer tokens allowed',512,1000000,'1'],iterations:['Worker iterations allowed',1,20,'1'],dollars:['Explicit spending cap ($)',0,100,'0.01']};
  if(!takeover&&(!hit||!fields[hit.key])){
    const d=dialog(`${modalHeader('SAVED WORK NEEDS ATTENTION','Inspect the specific blocker')}<p>${esc(task.error||'Review the saved evidence before continuing.')}</p><p class="small muted">Changing unrelated limits will not resolve this condition.</p><div class="modal-footer"><button type="button" data-inspect-models>Inspect Models</button><button type="button" data-inspect-changes>View saved changes</button><button type="button" data-close>Close</button></div>`);
    $('[data-inspect-models]',d).onclick=()=>{d.close();openConnections(undefined,task)};$('[data-inspect-changes]',d).onclick=()=>{d.close();setView('changes')};return;
  }
  const key=hit?.key,spec=fields[key],used=hit?.used??0;
  const proposed=key==='worker_turns'?Math.min(200,Math.max(task.limits[key],used+10)):task.limits[key];
  const d=dialog(`<form>${modalHeader(takeover?'REVIEWER TAKEOVER':'TASK LIMIT',takeover?'Let the reviewer take over?':'Review this allowance')}<p class="modal-description">${takeover?'The reviewer will implement changes within these explicit limits. You still approve the final patch.':`${esc(task.error||'This allowance was reached.')} Used ${esc(hit.used)} of ${esc(hit.allowed)}; ${esc(hit.remaining)} remaining.`}</p>${takeover?limitFields(task.limits):numberField(key,...[spec[0],proposed,spec[1],spec[2],spec[3]])}<p class="small muted">Saved work and cumulative usage are retained. This changes ${takeover?'only the limits you select':'only this allowance'}; model placement and other limits stay the same.</p><p class="form-error" role="alert"></p><div class="modal-footer"><button type="submit" class="primary-button">${takeover?'Approve takeover':'Save adjustment & resume'}</button></div></form>`);
  const form=$('form',d);bindLimitFields(form);form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{const f=new FormData(form),limits=takeover?readLimits(f):{...task.limits,[key]:Number(f.get(key))};if(!takeover&&limits[key]<=Math.max(hit.allowed,used))throw new Error('Choose a higher allowance before continuing.');await api('/tasks/'+task.id+'/start',{limits,approve_takeover:takeover});d.close();await refresh()})};
}
async function renameTask(task=state.task) {
  if(!task)return;
  const d=dialog(`<form>${modalHeader('TASK NAME','Rename task')}<label class="full-field">Task title<input name="title" maxlength="120" required value="${esc(task.title)}" autocomplete="off"></label><p class="form-error" role="alert"></p><div class="modal-footer"><button type="button" class="text-link" data-automatic>Use automatic title</button><button type="button" class="subtle-button" data-close>Cancel</button><button type="submit" class="primary-button">Save</button></div></form>`);
  const form=$('form',d), input=$('input',d);
  const save=async title=>{await api('/tasks/'+task.id+'/metadata',{custom_title:title});d.close();await refresh()};
  form.onsubmit=e=>{e.preventDefault();formAction(form,()=>save(input.value))};
  $('[data-automatic]',d).onclick=()=>formAction(form,()=>save(null));
  input.focus();input.select();
}

async function loadTaskPermissions(task, force=false) {
  const key=[task.id,task.workspace,task.status,task.pending_approval?.id].join('|');
  if(!force&&state.permissionKey===key)return;
  state.permissionKey=key;
  try{const result=await api('/tasks/'+task.id+'/permissions');if(state.task?.id!==task.id)return;state.taskPermissions={id:task.id,...result};renderComposer()}catch{state.permissionKey=null}
}
async function sessionPermissions() {
  const task=state.task;if(!task)return;
  try{
    const permissions=await api('/tasks/'+task.id+'/permissions'), grants=permissions.project_grants||[];
    const d=dialog(`${modalHeader('SESSION PERMISSIONS','Tests and commands you’ve allowed')}<p>Permissions expire when cheapoS restarts. Revocation affects future commands; running commands continue.</p><h3>Project tests</h3>${grants.length?grants.map(g=>`<section><p>${esc(g.profile.project)} · unittest</p><p>Test roots: ${g.profile.roots.map(root=>esc(root==='.'?'Project root (.)':root)).join(', ')}</p><button class="outline-button" data-revoke-grant="${g.id}">Revoke project tests</button></section>`).join(''):'<p>No project test grants.</p>'}<h3>Exact commands in this chat</h3>${permissions.commands.length?permissions.commands.map(c=>`<code class="approval-command">${esc(c.join(' '))}</code>`).join(''):'<p>No exact-command grants.</p>'}${permissions.commands.length?'<button class="outline-button" id="clear-session-permissions">Clear exact commands</button>':''}<p class="form-error" role="alert"></p>`);
    const revoke=async(button,body)=>{button.disabled=true;try{await api('/tasks/'+task.id+'/permissions',body);await loadTaskPermissions(task,true);d.close();toast('Permission revoked. Future commands may ask again.');await refresh()}catch(error){$('.form-error',d).textContent=error.message;button.disabled=false;await refresh()}};
    $$('[data-revoke-grant]',d).forEach(b=>b.onclick=()=>revoke(b,{revoke_project_grant:b.dataset.revokeGrant}));
    const clear=$('#clear-session-permissions',d);if(clear)clear.onclick=()=>revoke(clear,{clear:true});
  }catch(error){toast(error.message)}
}
async function startDemo() {
  const availability=submissionAvailability(null,'interactive');if(!availability.allowed){toast(availability.reason);return;}
  if(!state.online){toast('The local server is unavailable. Start it with python3 run.py');return}
  try{const task=await api('/demo',{});await loadTasks();await selectTask(task.id);await startTask(task.id)}catch(e){toast(e.message)}
}
function sampleDialog() {
  const d=dialog(`${modalHeader('SAMPLE TASK','Try the complete workflow')}<p>Fix a small clamp function in a new disposable repository. Your selected project is untouched. Saved results stay available in history and can be moved to Trash.</p><h3>Scripted demonstration</h3><p>Predetermined worker and reviewer responses, actual local checks, no model requests. This demonstrates the interface; it does not validate your models.</p><button class="outline-button" data-sample="scripted">Run scripted demonstration</button><h3>Real loop with selected models</h3><p>Uses your current placement and models for file edits, actual unittest checks, and a separate review request. Up to 5 minutes, 20 worker turns, 3 iterations, and the smaller of your current spending cap or $0.25. Free only remains $0. A same-model local review is labeled as such.</p><p>Starting authorizes only the sample’s exact Python unittest discovery command in its disposable task copy for this server session. Other commands and projects still ask. You approve any final commit.</p><button class="primary-button" data-sample="real">Start real sample</button><p class="form-error" role="alert"></p>`,'project-modal setup-modal');
  $$('[data-sample]',d).forEach(button=>button.onclick=async()=>{
    const availability=submissionAvailability(null,'interactive');if(!availability.allowed){$('.form-error',d).textContent=availability.reason;return;}
    $$('[data-sample]',d).forEach(b=>b.disabled=true);
    try{if(button.dataset.sample==='scripted'){d.close();await startDemo();return}const task=await api('/sample',{});d.close();await loadTasks();await selectTask(task.id);await startTask(task.id)}catch(e){$('.form-error',d).textContent=e.message;$$('[data-sample]',d).forEach(b=>b.disabled=false)}
  });
}
function openConnections(afterSave, taskContext=null) {
  const c=state.config, gateway=state.gateway||{}, settings=gateway.settings||{base_url:'http://127.0.0.1:20128/v1',auto_start:true,keep_running:true};
  const isOmni=p=>p.gateway==='omniroute'||!p.base_url||p.base_url.replace('localhost','127.0.0.1').replace(/\/$/,'')===settings.base_url.replace('localhost','127.0.0.1');
  const providerFields=role=>{
    const p=c[role]||{}, preset=p.route_error?'blocked':isOmni(p)?'omniroute':'ollama';
    return `<fieldset class="provider-fields" data-role="${role}"><legend>${role==='worker'?'Worker · does the work':role==='planner'?'Planner · prepares the plan':'Reviewer · checks the evidence'}</legend>
      <label class="full-field">Connection<select data-preset="${role}">${[['omniroute','OmniRoute (shared local gateway)'],['ollama','Ollama (local)'],...(preset==='blocked'?[['blocked','Unavailable direct connection · choose a new connection']]:[])].map(([v,n])=>`<option value="${v}" ${v==='blocked'?'disabled':''} ${v===preset?'selected':''}>${n}</option>`).join('')}</select></label>
      <p class="small" data-route-error="${role}" role="status"></p><div data-direct="${role}"><label class="full-field">Local Ollama URL<input type="url" name="${role}_url" value="${esc(p.base_url||settings.base_url)}" readonly required></label></div>
      <div data-catalog="${role}"><label class="checkbox-field"><input type="checkbox" data-free="${role}" checked><span>Show public-free and included models</span></label><label class="full-field">Catalog models<select data-model-picker="${role}"><option value="">Loading catalog…</option></select></label></div>
      <label class="full-field">Model ID<input name="${role}_model" type="text" value="${esc(p.model||'')}" placeholder="Choose above or enter an exact model ID" required autocomplete="off"></label>
      <p class="model-capabilities small" data-capabilities="${role}"></p>
      <label class="checkbox-field" data-included-label="${role}"><input type="checkbox" data-included="${role}" ${p.access==='included'?'checked':''}><span>Use included access for this exact model<small>Authorize its ID in the gateway list above first.</small></span></label><div class="field-grid" data-prices="${role}">${numberField(role+'_input','Input $ / million tokens',p.input_rate??'',0,10000,'any')}${numberField(role+'_output','Output $ / million tokens',p.output_rate??'',0,10000,'any')}</div>
      <p class="small muted" data-price-note="${role}">Unknown prices need your input. Verify them with the provider.</p></fieldset>`;
  };
  const d=dialog(`${modalHeader('MODEL CONNECTIONS','Choose where the work runs.')}<button class="outline-button" id="models-execution">Execution: ${esc(executionLabel(state.preferences.execution?.mode))} · Coordinator ${CheapOSGuide.coordinatorStatus({execution:state.preferences.execution}).label} for new chats →</button>${coordinatorTaskNotice(taskContext||state.task)}<p class="modal-description">All remote model requests go through OmniRoute during development. Configure OpenRouter and other providers in its dashboard. Direct Ollama remains available for installed local models.</p>${taskContext?`<div class="connection-context"><strong>Checking a stopped task</strong><p>Worker: <b>${esc(taskContext.providers.worker?.model||'not set')}</b><br>Reviewer: <b>${esc(taskContext.providers.reviewer?.model||'not set')}</b><br>Automatic remote chats check another free model after a recoverable failure when you resume. Manual and local chats keep their selected models; choices below apply to new chats.</p></div>`:''}
    <form class="gateway-card" id="gateway-form"><div class="gateway-heading"><div><strong>OmniRoute</strong><span class="gateway-badge" id="gateway-status" role="status"></span></div><a id="gateway-dashboard" class="subtle-button" href="${esc(gateway.dashboard_url||'http://127.0.0.1:20128')}" target="_blank" rel="noopener noreferrer">Open OmniRoute ↗</a></div>
      <p id="gateway-message" class="small muted"></p><p id="gateway-instance" class="small muted"></p>
      <details class="advanced"><summary id="free-pool-title">Authorized remote model pool</summary><p class="small muted">Refreshes every five minutes, including OpenRouter’s current free models. Failed models cool down for 15–60 minutes. Provider cooldowns follow the gateway’s retry time and do not count as individual model failures. A response or tool check does not prove coding quality.</p><div id="free-model-pool" class="free-model-pool"></div></details>
      <div class="included-access"><label class="full-field">Models included in my account<textarea id="included-model-ids" rows="4" spellcheck="false" placeholder="One exact gateway model ID per line">${esc((settings.included_models||[]).join('\n'))}</textarea></label><p class="small muted">Authorize only models covered by your existing account. This applies to this gateway connection. New models and changed connections need new authorization. Included access uses a $0 marginal estimate; it is not public-free pricing or a billing receipt.</p><button type="button" class="outline-button" id="save-included-models">Save included access</button><p id="included-access-status" class="small" role="status"></p></div><div class="gateway-actions"><button type="button" class="outline-button" data-gateway-action="start">Connect / start</button><button type="button" class="subtle-button" data-gateway-action="refresh">Refresh models</button><button type="button" class="subtle-button" data-gateway-action="stop" hidden>Stop instance</button></div>
      <details class="advanced"><summary>Startup & connection settings</summary><label class="full-field">Local API URL<input name="gateway_url" type="url" value="${esc(settings.base_url)}" required></label>
        <label class="full-field">Gateway client API key · optional<input name="gateway_key" type="password" placeholder="${gateway.key_configured?'Configured · leave blank to keep':'Only if OmniRoute requires a client key'}" autocomplete="new-password"></label>
        ${gatewayRememberField(gateway,'gateway_remember')}
        <p id="gateway-key-status" class="small muted" role="status">${esc(gatewayKeyStatus(gateway))}</p>
        <button type="button" class="text-link" id="gateway-forget-key" ${gateway.key_configured||gateway.key_storage?.saved?'':'hidden'}>Forget client key</button>
        <label class="checkbox-field"><input name="auto_start" type="checkbox" ${settings.auto_start?'checked':''}><span>Start installed OmniRoute when cheapoS launches<small>Reuses an existing instance. Does not install or update software.</small></span></label>
        <label class="checkbox-field"><input name="keep_running" type="checkbox" ${settings.keep_running?'checked':''}><span>Keep OmniRoute running when cheapoS closes<small>cheapoS only stops an instance it started in this session.</small></span></label>
        <button class="outline-button gateway-save" type="submit">Save gateway settings</button></details><p class="form-error" role="alert"></p></form>
    <form id="models-form"><details class="advanced" ${(state.preferences.execution?.mode||'manual')==='manual'?'open':''}><summary>Explicit model choices · Manual mode and remote preferences</summary><div class="provider-grid">${providerFields('worker')}${providerFields('reviewer')}</div><label class="checkbox-field"><input type="checkbox" id="dedicated-planner" ${c.planner?'checked':''}><span>Use a dedicated planner</span></label><p id="planner-fallback" class="small muted"></p><details id="planner-options" ${c.planner?'open':''}><summary>Planner connection and model</summary>${providerFields('planner')}</details>
      <p class="small muted">Catalog connection and advertised tool support do not guarantee a successful model run. These explicit choices apply in Manual mode. Automatic remote modes select only authorized eligible routes. Access labels do not establish remaining quota or successful inference.</p>
      </details><p class="form-error" role="alert"></p><div class="modal-footer"><span>Applies to new tasks.<br>Saving makes no inference request.</span><button class="primary-button" type="submit">${taskContext?'Save & prepare new chat':'Save connections'} ${icon('check')}</button></div></form>`,'connections-modal');
  $('#models-execution',d).onclick=()=>{d.close();executionPreferences()};
  const field=(role,name)=>$(`[name="${role}_${name}"]`,d);
  const usingOmni=role=>$(`[data-preset="${role}"]`,d).value==='omniroute';
  let includedRevision=settings.connection_revision;
  const includedSelected=role=>$(`[data-included="${role}"]`,d).checked;
  function capability(role) {
    const model=usingOmni(role)?state.gatewayModels.find(m=>m.id===field(role,'model').value.trim()):null;
    const included=usingOmni(role)&&includedSelected(role);
    $(`[data-prices="${role}"]`,d).hidden=included;
    for(const name of ['input','output'])field(role,name).disabled=included;
    $(`[data-included-label="${role}"]`,d).hidden=!usingOmni(role);
    $(`[data-price-note="${role}"]`,d).textContent=included?'Included account access · $0 marginal estimate, not a provider price. Exact ID must be authorized above.':'Unknown prices need your input. Verify them with the provider.';
    $(`[data-capabilities="${role}"]`,d).textContent=model?`${CheapOSGuide.modelAccess(model)} · `+`${model.tool_calling===true?'Tool calling advertised':model.tool_calling===false?'Tool calling not advertised':'Tool support unknown'}${model.context_length?' · '+Intl.NumberFormat().format(model.context_length)+' context':''}${model.free?' · Free variant':''}`:'Use a model that supports tool calling. Availability has not been tested.';
  }
  function picker(role) {
    const select=$(`[data-model-picker="${role}"]`,d), free=$(`[data-free="${role}"]`,d).checked, current=field(role,'model').value.trim();
    const models=state.gatewayModels.filter(m=>!free||m.free||m.access_class==='included');
    select.innerHTML=`<option value="">${models.length?'Choose from '+models.length+' models':'No matching models · refresh or enter an ID'}</option>`+models.map(m=>`<option value="${esc(m.id)}">${esc(m.id)} · ${esc(CheapOSGuide.modelAccess(m))}${m.tool_calling===true?' · tools':m.tool_calling===false?' · no tools advertised':''}</option>`).join('');
    select.value=models.some(m=>m.id===current)?current:'';
    capability(role);
  }
  function layout(role) {
    const omni=usingOmni(role);
    $(`[data-direct="${role}"]`,d).hidden=omni;
    for(const input of $$('input',$(`[data-direct="${role}"]`,d)))input.disabled=omni;
    $(`[data-catalog="${role}"]`,d).hidden=!omni;
    $(`[data-route-error="${role}"]`,d).textContent=$(`[data-preset="${role}"]`,d).value==='blocked'?(c[role]?.route_error||'Select OmniRoute or local Ollama.') : '';
    picker(role);
  }
  const gatewayForm=$('#gateway-form',d);
  function updateGateway() {
    if(!d.open)return;
    const g=state.gateway||{};
    if(includedRevision!==g.settings?.connection_revision){includedRevision=g.settings?.connection_revision;$('#included-model-ids',d).value=(g.settings?.included_models||[]).join('\n');for(const role of ['worker','reviewer','planner'])$(`[data-included="${role}"]`,d).checked=false;}
    const badge=$('#gateway-status',d);badge.textContent=({ready:'Catalog connected',checking:'Connecting…',starting:'Starting…',offline:'Offline',auth_required:'Client key needed',not_installed:'Not installed',unavailable:'Unavailable',error:'Startup failed'})[g.status]||'Not checked';badge.dataset.status=g.status||'unchecked';
    $('#gateway-message',d).textContent=g.message||'Connect your local gateway to load its model catalog.';
    $('#gateway-key-status',d).textContent=gatewayKeyStatus(g);
    const forget=$('#gateway-forget-key',d);forget.hidden=!g.key_configured&&!g.key_storage?.saved;forget.disabled=Boolean(g.busy);
    $('[name="gateway_key"]',d).placeholder=g.key_configured?'Configured · leave blank to keep':'Only if OmniRoute requires a client key';
    $('#gateway-instance',d).textContent=g.status==='ready'?`${g.model_count} models · ${g.owned?'Started by cheapoS':'Reusing an existing instance'}`:'';
    const freeModels=state.gatewayModels.filter(m=>(m.free||m.access_class==='included')&&m.tool_calling===true&&!m.local&&!m.id.startsWith('auto/'));
    const cooling=freeModels.filter(m=>(m.health?.retry_at||0)*1000>Date.now()).length;
    $('#free-pool-title',d).textContent=`Authorized remote model pool · ${freeModels.length-cooling} candidates${cooling?' · '+cooling+' cooling down':''}`;
    $('#free-model-pool',d).innerHTML=freeModels.map(m=>`<div class="pool-model"><strong>${esc(m.id)}</strong><span>${esc(CheapOSGuide.modelAccess(m))} · ${esc(CheapOSGuide.modelHealth(m))}${m.reasoning===true?' · reasoning advertised':''}</span><small>${esc(CheapOSGuide.metadataEvidence(m))}</small>${m.health?.last_error?`<small>${esc(m.health.last_error)}</small>`:''}</div>`).join('')||'<p class="small muted">No public-free or explicitly included remote models advertising tool support are listed in this catalog.</p>';
    $('#gateway-dashboard',d).href=g.dashboard_url||'http://127.0.0.1:20128';
    $$('[data-gateway-action]',d).forEach(b=>{b.disabled=Boolean(g.busy);if(b.dataset.gatewayAction==='stop')b.hidden=!g.owned});
    $('button[type="submit"]',gatewayForm).disabled=Boolean(g.busy);
    for(const role of ['worker','reviewer','planner'])picker(role);
  }
  state.gatewayListener=updateGateway;
  d.addEventListener('close',()=>{if(state.gatewayListener===updateGateway)state.gatewayListener=null});
  $$('[data-gateway-action]',d).forEach(button=>button.onclick=()=>formAction(gatewayForm,async()=>{state.gateway=await api('/gateway/'+button.dataset.gatewayAction,{});updateGateway();await loadGateway()}));
  $('#save-included-models',d).onclick=()=>formAction(gatewayForm,async()=>{
    const included_models=CheapOSGuide.includedScope($('#included-model-ids',d).value);
    state.gateway=await api('/gateway/config',{included_models,expected_connection_revision:includedRevision});
    $('#included-access-status',d).textContent='Included access saved for these exact IDs. No model request was made.';
    updateGateway();await loadGateway();
  });
  $('#gateway-forget-key',d).onclick=()=>formAction(gatewayForm,async()=>{
    state.gateway=await api('/gateway/config',{api_key:'',remember_key:false});
    $('[name="gateway_key"]',d).value='';$('[name="gateway_remember"]',d).checked=false;
    updateGateway();toast('Client key removed from cheapoS and its credential store. Launch environment variables are unchanged.');
    state.gateway=await api('/gateway/refresh',{});updateGateway();
  });
  gatewayForm.onsubmit=e=>{e.preventDefault();formAction(gatewayForm,async()=>{
    const f=new FormData(gatewayForm), values={base_url:String(f.get('gateway_url')).trim(),auto_start:f.has('auto_start'),keep_running:f.has('keep_running'),remember_key:f.has('gateway_remember')},key=String(f.get('gateway_key')).trim();if(key)values.api_key=key;
    state.gateway=await api('/gateway/config',values);$('[name="gateway_key"]',d).value='';$('[name="gateway_remember"]',d).checked=Boolean(state.gateway.key_storage?.saved);
    state.gateway=await api('/gateway/refresh',{});updateGateway();toast('Gateway settings saved. Use Connect / start if it is offline.');
  })};
  for(const role of ['worker','reviewer','planner']) {
    layout(role);
    $(`[data-included="${role}"]`,d).onchange=()=>capability(role);
    $(`[data-free="${role}"]`,d).onchange=()=>picker(role);
    $(`[data-model-picker="${role}"]`,d).onchange=e=>{
      if(!e.target.value)return;
      const model=state.gatewayModels.find(m=>m.id===e.target.value);field(role,'model').value=model.id;$(`[data-included="${role}"]`,d).checked=model.access_class==='included';
      field(role,'input').value=model.input_rate??'';field(role,'output').value=model.output_rate??'';capability(role);
    };
    field(role,'model').oninput=()=>{
      $(`[data-included="${role}"]`,d).checked=false;
      const model=usingOmni(role)?state.gatewayModels.find(m=>m.id===field(role,'model').value.trim()):null;
      for(const price of ['input','output'])field(role,price).value=usingOmni(role)?(model?.[price+'_rate']??''):0;
      picker(role);
    };
    $(`[data-preset="${role}"]`,d).onchange=e=>{
      const preset=e.target.value, p=c[role]||{};
      field(role,'url').value=preset==='omniroute'?state.gateway.settings.base_url:'http://127.0.0.1:11434/v1';
      field(role,'model').value='';$(`[data-included="${role}"]`,d).checked=false;
      for(const price of ['input','output'])field(role,price).value=preset==='ollama'?'0':'';
      if(preset==='omniroute'&&isOmni(p)){field(role,'model').value=p.model||'';field(role,'input').value=p.input_rate??'';field(role,'output').value=p.output_rate??''}
      layout(role);
    };
  }
  function plannerChoice() {
    const dedicated=$('#dedicated-planner',d).checked;
    $('#planner-options',d).hidden=!dedicated;
    $('[data-role="planner"]',d).disabled=!dedicated;
    $('#planner-fallback',d).textContent=dedicated?'Dedicated planning applies to new proposals. Automatic remote placement still requires authorized free or included access.':`Planner follows reviewer: ${field('reviewer','model').value||'choose a reviewer model'}.`;
  }
  $('#dedicated-planner',d).onchange=plannerChoice;
  field('reviewer','model').addEventListener('input',plannerChoice);
  plannerChoice();
  const form=$('#models-form',d);
  form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{
    const f=new FormData(form),values={};
    for(const role of ['worker','reviewer','planner']) {
      if(role==='planner'&&!$('#dedicated-planner',d).checked){values.planner=null;continue}
      if($(`[data-preset="${role}"]`,d).value==='blocked')throw new Error('Select OmniRoute or local Ollama for each role before saving.');
      const omni=usingOmni(role);
      if(omni&&state.gateway.status!=='ready')throw new Error('Connect OmniRoute before saving its model choices.');
      values[role]={gateway:omni?'omniroute':'openai',base_url:omni?state.gateway.settings.base_url:String(f.get(role+'_url')).trim(),model:String(f.get(role+'_model')).trim(),input_rate:Number(f.get(role+'_input')),output_rate:Number(f.get(role+'_output'))};
      if(omni&&includedSelected(role)){
        if(!CheapOSGuide.includedChoice(values[role].model,state.gateway.settings,true))throw new Error('Save included access for this exact model ID first.');
        values[role].access='included';delete values[role].input_rate;delete values[role].output_rate;
      }
    }
    state.config=await api('/config',values);form.reset();d.close();renderSidebar();if(state.task)renderInspector();else renderHome();toast('Connections saved for new tasks.');if(taskContext){const command=taskContext.check_command.map(arg=>"'"+arg.replaceAll("'","'\"'\"'")+"'").join(' ');newTask((taskContext.requests||[taskContext.prompt]).join('\n\nFollow-up:\n'),{repository:taskContext.source,check_command:command})}else if(typeof afterSave==='function')afterSave();
  })};
  updateGateway();
  api('/gateway/refresh',{}).then(g=>{state.gateway=g;updateGateway();return loadGateway()}).catch(e=>toast(e.message));
}
function renderConnectionNotice() {
  const element=$('#connection-notice');if(!element)return;
  element.hidden=Boolean(state.task); // This check describes defaults for new chats, not a pinned task's models.
  const notice=CheapOSGuide.connectionNotice(state.readiness,state.gateway,state.preferences.execution,state.config);
  const html=`<div><strong>${esc(notice.title)}</strong><p>${esc(notice.detail)}</p></div>${notice.tone==='attention'?'<div class="button-row"><button class="text-link" data-connection-setup>Fix setup</button><button class="text-link" data-connection-recheck>Re-check</button></div>':''}`;
  element.dataset.tone=notice.tone;
  if(element.dataset.rendered!==html){element.innerHTML=html;element.dataset.rendered=html;}
  const setup=$('[data-connection-setup]',element);if(setup)setup.onclick=openSetup;
  const recheck=$('[data-connection-recheck]',element);if(recheck)recheck.onclick=()=>loadReadiness(true).catch(e=>toast(e.message));
}
async function loadReadiness(force=false) {
  const selection=JSON.stringify([state.preferences.execution,state.config]);
  if(!force&&state.readinessSelection===selection&&Date.now()-(state.readinessAt||0)<(state.readiness?.checking?1500:15000))return;
  state.readinessSelection=selection;
  try{state.readiness=await api('/readiness'+(force?'?refresh=1':''));state.readinessAt=Date.now();}
  catch{state.readiness={diagnostic_code:'readiness_request_failed'};state.readinessAt=Date.now();}
  renderConnectionNotice();renderSidebar();
}
async function loadGateway() {
  const previous=state.gateway, g=await api('/gateway');state.gateway=g;
  if(state.catalogRevision!==g.revision){const catalog=await api('/gateway/models');state.gatewayModels=catalog.models;state.catalogRevision=catalog.revision}
  if(JSON.stringify(previous)!==JSON.stringify(g)){renderSidebar();if(!state.task)renderHome();state.gatewayListener?.()}
}
async function openSearch() {
  let all;try{all=(await Promise.all([api('/tasks'),api('/tasks?view=archived')])).flat()}catch(e){toast(e.message);return}
  const d=dialog(`<div class="search-box">${icon('search')}<input id="task-search" type="search" placeholder="Find a task or project…" aria-label="Search tasks" autofocus><kbd>ESC</kbd></div><div id="search-results"></div><div class="search-footer">Saved on this computer</div>`,'search-modal');
  const render=(q='')=>{const found=all.filter(t=>(t.title+' '+t.source).toLowerCase().includes(q.toLowerCase()));$('#search-results',d).innerHTML=found.length?found.map(t=>`<button class="search-result" data-result="${t.id}">${icon('chat')}<span><strong>${esc(t.title)}</strong><small>${esc(t.demo?'Local demo':basename(t.source))} · ${(state.hiddenProjects||[]).some(p=>p.path===t.source)?'Hidden project · ':''}${t.archived_at?'Archived · ':''}${esc(labels[t.status])}</small></span>${icon('chevron')}</button>`).join(''):'<div class="no-results">No matching tasks.</div>';$$('[data-result]',d).forEach(b=>b.onclick=()=>{d.close();selectTask(b.dataset.result)})};$('#task-search',d).oninput=e=>render(e.target.value);render();
}
async function loadTasks() {const [tasks,projects,hidden]=await Promise.all([api('/tasks?view='+(state.historyView||'active')),api('/projects'),api('/projects/hidden')]);const changed=JSON.stringify([tasks,projects,hidden])!==JSON.stringify([state.tasks,state.projects,state.hiddenProjects]);state.tasks=tasks;state.projects=projects;state.hiddenProjects=hidden;if(changed){renderSidebar();renderComposer();if(!state.task)renderHome()}}
let contextRefresh=null;
function refreshContext() {
  if(!contextRefresh)contextRefresh=Promise.allSettled([
    (async()=>{await loadStartup();await loadReadiness();})(),loadGateway(),loadTasks(),loadAdmission()
  ]).then(results=>{
    const failure=results.find(result=>result.status==='rejected');
    if(failure){console.error('cheapoS connection/sidebar refresh failed',failure.reason);toast('Could not refresh connection or sidebar status. Retrying…');}
  }).finally(()=>{contextRefresh=null});
  return contextRefresh;
}
function receiveStartedTask(task) {
  if(state.task?.id!==task?.id||!task?.branch_run)return;
  if(Date.parse(task.updated_at)<Date.parse(state.task.updated_at))return;
  state.task=task;
}
async function refresh({background=false}={}) {
  if(state.loading)return;
  const context=refreshContext(),previous=state.task,selected=previous?.id,selection=state.selection;
  if(selected){
    const task=await api('/tasks/'+selected);
    // A slow request must not replace a newer Start response or another chat.
    if(state.selection===selection&&state.task?.id===selected&&!(state.task!==previous&&Date.parse(task.updated_at)<=Date.parse(state.task.updated_at))){
      if(state.renderFailed||['updated_at','status','title','custom_title','pinned','archived_at','trashed_at'].some(key=>task[key]!==state.task[key])){state.task=task;renderTask();state.renderFailed=false}
    }
  }
  if(!background)await context;
}
async function resumeBranchRun(task,savedResult) {
  const result=savedResult||await api('/tasks/'+task.id+'/branch-resume',{});
  if(result.needs_merge_recovery){
    const operation=result.operation||result.merge_operation||task.branch_run?.merge_operation;
    if(!operation?.target_ref||!operation?.feature_tip)throw new Error('Saved integration details are unavailable. Refresh this task before recovery.');
    const d=dialog(`<form>${modalHeader('SAVED INTEGRATION','Finish the approved local merge')}<p>Reconcile the saved integration of <code>${esc(operation.feature_tip)}</code> into <strong>${esc(operation.target_ref)}</strong>. This finishes only that recorded operation and preserves external changes.</p><p class="form-error" role="alert"></p><div class="modal-footer"><button type="button" data-close>Keep saved</button><button type="submit" class="primary-button">Finish saved integration</button></div></form>`);
    const form=$('form',d);form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{await api('/tasks/'+task.id+'/branch-merge',{recover:true,approved:true});d.close();await refresh();});};return;
  }
  if(!result.needs_consent){await refresh();return;}
  const d=dialog(`<form>${modalHeader('RESUME UNATTENDED','Renew test permissions')}<p>These session permissions expired or their environment changed. Resume keeps the same run and remaining allowance.</p><ul>${(result.scopes||[]).map(scope=>`<li><code>${esc(scope.command.join(' '))}</code><br><small>${esc(scope.directory)}</small></li>`).join('')}</ul><p class="form-error" role="alert"></p><div class="modal-footer"><button type="button" data-close>Keep paused</button><button type="submit" class="primary-button">Allow tests & resume</button></div></form>`);
  const form=$('form',d);form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{await api('/tasks/'+task.id+'/branch-resume',{proposal_id:result.proposal_id,approved:true});d.close();await refresh();});};
}
async function bootstrap() {
  try {const data=await api('/bootstrap');state.token=data.token;state.config=data.config;state.gateway=data.gateway||{};state.startup=data.startup||{};state.tasks=data.tasks;state.projects=data.projects||[];state.hiddenProjects=data.hidden_projects||[];state.preferences=data.preferences||state.preferences;await loadAdmission({render:false});try{const path=localStorage.getItem('cheapos-project');state.project=state.projects.find(p=>p.path===path)||null}catch{}state.online=true;renderSidebar();let selected;try{selected=localStorage.getItem('cheapos-selected')}catch{}let freshStartup=false;try{freshStartup=Boolean(state.startup.started_at)&&localStorage.getItem('cheapos-startup-session')!==state.startup.session_id;localStorage.setItem('cheapos-startup-session',state.startup.session_id||'')}catch{}if(!freshStartup&&state.tasks.some(t=>t.id===selected))await selectTask(selected);else home();await loadReadiness(true);}
  catch(e){console.error('cheapoS bootstrap failed',e);state.online=false;$('#chat-view').innerHTML='<div class="empty-state"><h2>Start cheapoS locally.</h2><p>Run <code>python3 run.py</code> in the project directory, then refresh this page. No sign-in is needed.</p></div>';renderInspector()}
}
async function poll() {try{if(state.online)await refresh({background:true})}catch(e){console.error('cheapoS refresh failed',e);state.renderFailed=true;toast(/fetch|network/i.test(e.message||'')?'Cannot reach the local server. Retrying…':'Could not refresh this view. Retrying…');}finally{setTimeout(poll,1500)}}
$$('.tab').forEach(b=>{b.onclick=()=>setView(b.dataset.view);b.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const tabs=$$('.tab').filter(t=>!t.hidden),i=tabs.indexOf(b),next=e.key==='Home'?tabs[0]:e.key==='End'?tabs.at(-1):tabs[(i+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length];setView(next.dataset.view);next.focus();};});
$('#home-trigger').onclick=()=>openProject();$('.brand').onclick=e=>{e.preventDefault();home()};$('#new-task').onclick=()=>newTask();$('#search-trigger').onclick=openSearch;$('#settings-trigger').onclick=()=>openConnections();$('#session-settings').onclick=()=>openConnections();$('#demo-trigger').onclick=sampleDialog;$('#composer-project').onclick=()=>openProject();$('#chat-budget').onclick=chatLimits;$('#execution-choice').onclick=executionPreferences;$('#chat-input').oninput=()=>{saveDraft();renderComposer()};$('#chat-form').onsubmit=e=>{e.preventDefault();sendChat()};if($('#chat-steer'))$('#chat-steer').onclick=()=>steerTask();$('#chat-input').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();sendChat()}};$('#chat-stop').onclick=stopFromComposer;
function toggleInspector(){ $('#toggle-inspector').click() }
const panelLayout=CheapOSPanels.mount();
const branchUI=CheapOSBranchUI.mount({api,receiveStartedTask,getState:()=>state,selectTask,refresh,toast,showLogs:()=>setView('logs'),showPlan:()=>setView('plan'),showChat:()=>setView('chat'),planningGuidance:id=>{if(state.task?.id===id)setView('chat');else selectTask(id);},renderCurrent:()=>renderTask(),openStartedChat:id=>{if(state.task?.id===id){setView('chat');return;}selectTask(id);},openPlanningChat:()=>{home();return state.selection;},newChat:()=>newTask(),pauseAction:async(action,task)=>{if(action==='models'){openConnections(undefined,task);return;}if(action==='limits'){chatLimits();return;}if(['reply','correction'].includes(action)){setView('chat');$('#chat-input')?.focus();return;}if(action==='authorization'){await resumeBranchRun(task);return;}if(action==='environment'||action==='permission'){setView('chat');const selector=action==='environment'?'[data-environment]':'[data-chat-action=approve]';const control=$(selector);if(control){control.scrollIntoView({block:'center'});control.focus();return;}throw new Error('No active setup or command permission request is available. Inspect Activity.');}setView('activity');},resume:resumeBranchRun,handleResumeResult:resumeBranchRun,onDraftChange:()=>renderComposer()});
document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&['k','n',','].includes(e.key.toLowerCase())){e.preventDefault();if($('dialog[open]'))return;if(e.key.toLowerCase()==='k')openSearch();else if(e.key.toLowerCase()==='n')newTask();else openConnections()}});
bootstrap();setTimeout(poll,1500);setInterval(updateProgressClock,1000);

$('#rename-task').onclick=()=>renameTask();

$('#composer-permissions').onclick=sessionPermissions;

// Restart modal wiring
(function(){
  const btn=$('#restart-button');
  const modal=document.getElementById('restart-modal');
  const closeBtn=$('#restart-modal-close');
  if(!btn||!modal)return;
  btn.onclick=()=>modal.showModal();
  if(closeBtn)closeBtn.onclick=()=>modal.close();
  modal.addEventListener('click',e=>{if(e.target===modal)modal.close();});
  const restartWebapp=$('#restart-webapp');
  const restartBoth=$('#restart-webapp-omni');
  const restartOmniroute=$('#restart-omni');
  async function callGatewayRefresh(){
    try{await fetch('/api/gateway/refresh',{method:'POST'});}catch(e){console.warn('OmniRoute refresh failed',e);}
  }
  if(restartWebapp)restartWebapp.onclick=()=>{modal.close();window.location.reload();};
  if(restartBoth)restartBoth.onclick=async()=>{modal.close();await callGatewayRefresh();window.location.reload();};
  if(restartOmniroute)restartOmniroute.onclick=async()=>{modal.close();await callGatewayRefresh();toast('OmniRoute restarted');};
})();

$('#lifetime-usage-trigger').onclick=()=>CheapOSLifetimeUsage.open({dialog,api,header:modalHeader});
