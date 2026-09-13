/* The conversation owns its execution details, streams, and approval controls. */
'use strict';
const CheapOSChatView = (() => {
  function detailEvent(event) {
    const d=event.detail||{};
    if(event.kind==='generation') return thinkingMarkup(d);
    if(event.kind==='assistant') return `<div class="workflow-note">${messageText(typeof d==='string'?d:'')}</div>`;
    if(event.kind==='checks') return commandMarkup(d,{key:d.run_id||event.id});
    if(event.kind==='model'||event.kind==='checkpoint'||event.kind==='permission') return '';
    const action=CheapOSGuide.activityItem(event);
    const title=action?.title||event.title||'Action';
    return `<details class="workflow-event" data-event="work-event-${event.id}"><summary>${icon(event.kind==='tool_error'?'x':'chevron')}<span>${esc(title)}</span>${event.time?`<time>${new Date(event.time).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'})}</time>`:''}</summary>${eventDetail(event)}</details>`;
  }
  function stepMarkup(step,task,stream) {
    const live=step.live;
    const symbol=step.outcome==='live'?'<span class="spinner"></span>':icon(['failed','revision','pending'].includes(step.outcome)?'clock':'check');
    const role={worker:'Worker',reviewer:'Reviewer',coordinator:'Chat model',controller:'CheapOS'}[step.role];
    const events=step.events.filter(e=>e.kind!=='model');
    const liveOutput=live&&task.check_stream?commandMarkup(task.check_stream,{live:true}):live&&stream?`<section class="workflow-stream" aria-label="Live ${role.toLowerCase()} output"><div class="stream-label"><span class="task-dot pulsing"></span>${stream.phase==='thinking'?'Thinking':stream.phase==='answer'?'Writing':'Waiting for output'}<span>Live</span></div><pre data-thinking="workflow-stream-${stream.request_id||step.id}">${esc(stream.thinking||stream.content||'Waiting for the next chunk…')}</pre>${stream.thinking&&stream.content?`<div class="workflow-note">${messageText(stream.content)}</div>`:''}</section>`:'';
    return `<details class="workflow-step ${live?'is-live':''} outcome-${step.outcome}" data-event="workflow-${step.id}" data-step="${step.id}"><summary><span class="workflow-symbol">${symbol}</span><span class="workflow-heading"><strong>${esc(step.title)}</strong><span class="workflow-status" ${live?'data-live-status':''}>${esc(step.detail)}</span>${live&&step.activity?`<small class="workflow-last-action">Latest: ${esc(step.activity)}</small>`:''}</span>${live?`<span class="workflow-elapsed" data-work-elapsed>${step.elapsed}</span>`:''}<span class="workflow-toggle">Details ${icon('chevron')}</span></summary><div class="workflow-details"><div class="workflow-model"><span>${role}</span><strong>${esc(step.model||'Scripted local model')}</strong></div>${liveOutput}${events.length>80?'<p class="small muted">Showing the latest 80 events in this step. The full history is in Activity.</p>':''}<div class="workflow-events">${events.slice(-80).map(detailEvent).join('')||(!liveOutput?'<p class="small muted">Waiting for the first action…</p>':'')}</div></div></details>`;
  }
  function message(entry,task,decision='') {
    if(entry.kind==='user') return `<article class="chat-message from-user ${entry.steer?'steer-bubble':''}" data-message="${entry.id}"><div class="chat-author"><strong>You</strong>${entry.steer?'<span>Follow-up while working</span>':''}</div><div class="chat-message-body">${messageText(entry.text)}</div></article>`;
    const steps=entry.steps, older=steps.length>4?steps.slice(0,-3):[], visible=older.length?steps.slice(-3):steps;
    if(!steps.length&&!entry.reply&&!decision&&!entry.live)return '';
    const history=older.length?`<details class="workflow-history" data-event="history-${entry.id}"><summary>${icon('clock')}Earlier steps <span>${older.length}</span>${icon('chevron')}</summary>${older.map(s=>stepMarkup(s,task,null)).join('')}</details>`:'';
    return `<article class="chat-message from-agent cheapos-response" data-message="${entry.id}"><div class="chat-author"><span class="cheapos-avatar">${icon('code')}</span><strong>CheapOS</strong>${entry.live?`<span class="response-live">${task.pending_approval?'Needs you':task.status==='stopping'?'Pausing':task.status==='waiting_retry'?'Waiting':'Working'}</span>`:''}</div><div class="chat-message-body">${entry.intro?`<p class="orchestration-intro">${esc(entry.intro)}</p>`:''}${steps.length?`<div class="workflow" aria-label="CheapOS work for this message">${history}${visible.map(s=>stepMarkup(s,task,entry.stream)).join('')}</div>`:''}${entry.reply?`<div class="cheapos-answer">${messageText(entry.reply)}</div>`:''}${decision}</div></article>`;
  }
  return {message};
})();

'use strict';
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => `<svg aria-hidden="true" focusable="false" tabindex="-1"><use href="#i-${name}"/></svg>`;
const activeStatuses = new Set(['running', 'reviewing', 'waiting_approval', 'waiting_retry', 'stopping']);
const labels = {awaiting_reply:'Ready for your message',ready:'Ready to start',running:'CheapOS is working',reviewing:'Checking your changes',waiting_approval:'Command approval needed',waiting_retry:'Waiting for a free route',paused:'Paused',budget_paused:'Paused at a limit',interrupted:'Interrupted',error:'Needs attention',takeover_requested:'Takeover requested',approved:'Reviewer approved',completed:'Ready for your review'};
const state = {startup:{},token:'',config:{},projects:[],project:null,preferences:{limits:{dollars:0,reviewer_tokens:50000,iterations:5,worker_turns:40,output_tokens:2048}},sending:false,pausingTask:null,stoppingStartup:false,drafts:new Map(),gateway:{},gatewayModels:[],catalogRevision:-1,gatewayListener:null,tasks:[],task:null,selection:0,view:'chat',file:0,diff:'unified',run:-1,online:false,loading:false};
const money = value => '$' + Number(value || 0).toFixed(Number(value || 0) > 0 && value < .01 ? 4 : 2);
const date = value => new Date(value).toLocaleString([], {month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});
const basename = value => String(value).split('/').filter(Boolean).pop() || 'Repository';
let toastTimer;
function toast(message) { clearTimeout(toastTimer); $('#toast').textContent=message; $('#toast').classList.add('visible'); toastTimer=setTimeout(()=>$('#toast').classList.remove('visible'),5000); }
async function api(path, body) {
  const response = await fetch('/api' + path, body === undefined ? {cache:'no-store'} : {method:'POST',headers:{'Content-Type':'application/json','X-CheapOS-Token':state.token},body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw Object.assign(new Error(data.error || 'The local server could not complete this action'),{code:data.code,files:data.files});
  return data;
}
function dialog(html, cls='') {
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
  $('#connection-indicator').textContent=state.startup.busy?'Connecting…':state.startup.status==='ready'?'Ready':state.config.worker&&state.config.reviewer?'Configured':'Set up';
  const groups=state.projects.map(project=>({project,tasks:state.tasks.filter(t=>!t.demo&&t.source===project.path)}));
  const demos=state.tasks.filter(t=>t.demo);if(demos.length)groups.push({project:{path:'demo',name:'Local demo'},tasks:demos});
  const html=`<label class="history-filter">History<select id="history-filter"><option value="active" ${!state.historyView||state.historyView==='active'?'selected':''}>Active</option><option value="archived" ${state.historyView==='archived'?'selected':''}>Archived</option><option value="trash" ${state.historyView==='trash'?'selected':''}>Trash</option></select></label>`+groups.map(({project,tasks})=>{
    const pref=sidebarPrefs[project.path]||{}, sorted=CheapOSGuide.sidebarOrder(tasks), shown=pref.more?sorted:sorted.slice(0,12);
    return `<div class="project-group"><div class="project-group-heading"><button class="icon-btn" data-collapse="${esc(project.path)}" aria-label="${pref.collapsed?'Expand':'Collapse'} ${esc(project.name||project.path)}" aria-expanded="${!pref.collapsed}">${icon('chevron')}</button><button class="project-label ${state.project?.path===project.path?'selected':''}" data-project="${esc(project.path)}" title="${esc(project.path)}">${icon('folder')}<span>${esc(CheapOSGuide.projectName({source:project.path,demo:project.path==='demo'}))}</span></button>${project.path!=='demo'?`<button class="task-menu-button" data-project-menu="${esc(project.path)}" aria-label="Project options for ${esc(project.name)}">⋯</button>`:''}</div>${pref.collapsed?'':shown.map(t=>`<div class="task-row"><button class="task ${state.task?.id===t.id?'active':''}" data-task="${t.id}" title="${esc(t.title)}"><span class="task-dot ${['approved','awaiting_reply'].includes(t.status)?'done':''} ${activeStatuses.has(t.status)?'pulsing':''}"></span><span class="task-list-title">${t.pinned?'★ ':''}${esc(t.title)}${t.trashed_at?`<small>Deleted ${esc(date(t.trashed_at))} · ${t.saved_change_count||0} saved changes${t.trash_archived_at?' · from Archived':''}</small>`:''}</span>${['error','budget_paused','waiting_approval'].includes(t.status)?'<span class="task-attention" aria-label="Needs attention">•</span>':''}</button><button class="task-menu-button" data-task-menu="${t.id}" aria-label="Options for ${esc(t.title)}" aria-haspopup="dialog">⋯</button></div>`).join('')+(sorted.length>12?`<button class="text-link show-more" data-more="${esc(project.path)}">${pref.more?'Show fewer':`Show more (${sorted.length-12})`}</button>`:'')}</div>`;
  }).join('');
  const list=$('#task-list');
  // Keep the existing DOM (and keyboard focus) when only live usage changed.
  if(list.dataset.rendered===html)return;
  const focused=document.activeElement, focusKey=focused?.getAttribute('data-task-menu')||focused?.getAttribute('data-task');
  const wasMenu=focused?.hasAttribute('data-task-menu');
  list.innerHTML=html;list.dataset.rendered=html;
  $('#history-filter').onchange=async e=>{const previous=state.historyView;state.historyView=e.target.value;try{await loadTasks()}catch(error){state.historyView=previous;renderSidebar();toast(error.message)}};
  $$('[data-project-menu]').forEach(b=>b.onclick=()=>projectMenu(b.dataset.projectMenu));
  $$('[data-task]').forEach(b=>b.onclick=()=>selectTask(b.dataset.task));
  $$('[data-task-menu]').forEach(b=>b.onclick=()=>taskMenu(state.tasks.find(t=>t.id===b.dataset.taskMenu)));
  $$('[data-project]').forEach(b=>b.onclick=()=>b.dataset.project==='demo'?selectTask(demos[0].id):chooseProject(state.projects.find(p=>p.path===b.dataset.project)));
  for(const [attr,key] of [['collapse','collapsed'],['more','more']])$$('[data-'+attr+']').forEach(b=>b.onclick=()=>{const path=b.dataset[attr];sidebarPrefs[path]||={};sidebarPrefs[path][key]=!sidebarPrefs[path][key];saveSidebarPrefs();renderSidebar();$$("[data-"+attr+"]").find(el=>el.dataset[attr]===path)?.focus()});
  if(focusKey)$$(wasMenu?'[data-task-menu]':'[data-task]').find(el=>(wasMenu?el.dataset.taskMenu:el.dataset.task)===focusKey)?.focus({preventScroll:true});
}
async function pauseForLifecycle(task) {
  if(activeStatuses.has(task.status)){
    await api('/tasks/'+task.id+'/stop',{});
    const deadline=Date.now()+190000;
    while(Date.now()<deadline){
      const latest=await api('/tasks/'+task.id);
      if(!activeStatuses.has(latest.status))break;
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
function taskMenu(task) {
  if(!task)return;
  if(task.trashed_at){trashMenu(task);return;}
  const d=dialog(`${modalHeader('CHAT OPTIONS',esc(task.title))}<div class="task-menu-actions"><button data-rename>Rename</button><button data-pin>${task.pinned?'Unpin':'Pin'}</button><button data-archive>${task.archived_at?'Restore':activeStatuses.has(task.status)?'Pause & archive':'Archive'}</button><button data-trash>Delete</button></div><p class="form-error" role="alert"></p>`);
  $('[data-rename]',d).onclick=()=>{d.close();renameTask(task)};
  $('[data-trash]',d).onclick=()=>{d.close();deleteTask(task)};
  const act=operation=>async()=>{const buttons=$$('button',d);buttons.forEach(b=>b.disabled=true);try{await operation();d.close()}catch(e){$('.form-error',d).textContent=e.message}finally{buttons.forEach(b=>b.disabled=false)}};
  $('[data-pin]',d).onclick=act(async()=>{await api('/tasks/'+task.id+'/metadata',{pinned:!task.pinned});await refresh()});
  $('[data-archive]',d).onclick=act(async()=>{if(activeStatuses.has(task.status))$('.form-error',d).textContent='Waiting for this task to stop…';await archiveTask(task,!task.archived_at)});
}
async function restoreTrash(task) {
  const restored=await api('/tasks/'+task.id+'/restore',{});
  state.historyView=restored.archived_at?'archived':'active';
  await refresh();toast(restored.archived_at?'Restored to Archived.':'Restored to active history.');
}
function trashMenu(task) {
  const d=dialog(`${modalHeader('TRASH',esc(task.title))}<p>${task.saved_change_count||0} saved changes. Files remain on disk.</p><div class="button-row"><button data-inspect>Inspect</button><button data-restore>Restore</button></div><p class="form-error" role="alert"></p>`);
  $('[data-inspect]',d).onclick=()=>{d.close();selectTask(task.id)};
  $('[data-restore]',d).onclick=async e=>{e.target.disabled=true;try{await restoreTrash(task);d.close()}catch(error){$('.form-error',d).textContent=error.message;e.target.disabled=false}};
}
function deleteTask(task) {
  const d=dialog(`<form>${modalHeader('DELETE CHAT','Move to Trash?')}<p>Move this chat and its saved task work to Trash? Your source project and commits stay unchanged.</p><p>${task.saved_change_count||task.changes?.length||0} saved changes. You can restore this chat later.</p><p class="form-error" role="alert"></p><div class="modal-footer"><button type="button" class="subtle-button" data-close>Cancel</button><button type="submit" class="primary-button">${activeStatuses.has(task.status)?'Pause & move to Trash':'Move to Trash'}</button></div></form>`);
  const form=$('form',d);form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{
    if(activeStatuses.has(task.status))$('.form-error',d).textContent='Waiting for this task to stop…';
    await pauseForLifecycle(task);await api('/tasks/'+task.id+'/trash',{});
    if(state.task?.id===task.id)home();await loadTasks();d.close();
    toast('Moved to Trash.');clearTimeout(toastTimer);
    const undo=document.createElement('button');undo.className='text-link';undo.textContent='Undo';
    undo.onclick=async()=>{undo.disabled=true;try{await restoreTrash(task)}catch(error){toast(error.message)}};
    $('#toast').append(' ',undo);toastTimer=setTimeout(()=>$('#toast').classList.remove('visible'),15000);
  })};
}
const draftKey=()=>state.task?.id||state.project?.path||'new';
function saveDraft(){state.drafts.set(draftKey(),$('#chat-input').value)}
function restoreDraft(){$('#chat-input').value=state.drafts.get(draftKey())||'';renderComposer()}
function home() {
  saveDraft();state.selection++;state.loading=false;state.task=null;state.view='chat';
  try{localStorage.removeItem('cheapos-selected')}catch{}
  renderHome();restoreDraft();renderSidebar();$('#sidebar').classList.remove('show');$('#view-container').scrollTop=0;
}
function chooseProject(project) {
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
  return `<div class="welcome-mark">${busy?'<span class="spinner"></span>':icon('code')}</div><h1>${title}</h1>${model?`<div class="startup-model ${ready?'ready':''}"><span class="task-dot ${ready?'done':'pulsing'}"></span>${esc(modelText)}</div>`:''}<p class="welcome-greeting">${esc(ready?startup.content:startup.content||startup.message||'Open a local project, then talk to CheapOS.')}</p>${startup.thinking?thinkingMarkup({thinking:startup.thinking,request_id:'startup',model:model?.id||''},true):''}${ready?'<span class="startup-verified">Greeting received · no API cost reported</span>':''}<div class="startup-actions">${actions}</div>${startup.attempts?.some(a=>a.status==='failed')?`<details class="startup-attempts"><summary>Connection details</summary>${startup.attempts.filter(a=>a.status==='failed').map(a=>`<p><strong>${esc(a.model)}</strong><br>${esc(a.error)}</p>`).join('')}</details>`:''}`;
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
function openSetup() {
  const d=dialog(`${modalHeader('GET CONNECTED','Choose a connection')}<p class="modal-description">Connect, open a project, then send your request.</p><div class="button-row"><button class="primary-button" data-setup="omni">OmniRoute · recommended</button><button class="outline-button" data-setup="local">Models on this computer</button></div><section id="setup-status" aria-live="polite"></section><p class="form-error" role="alert"></p><div class="modal-footer"><button class="text-link" data-setup="advanced">Advanced connections</button><button class="subtle-button" data-setup="history">Return to saved work</button></div>`,'project-modal setup-modal');
  let timer=null,busy=false,last='',readiness={},selected='';
  const stop=()=>{clearTimeout(timer);timer=null};
  d.addEventListener('close',stop);
  const perform=async operation=>{if(busy)return;busy=true;$('.form-error',d).textContent='';try{await operation()}catch(e){$('.form-error',d).textContent=e.message}finally{busy=false}};
  const render=()=>{
    const guide=CheapOSGuide.setupGuide(readiness), key=$('[name="setup_key"]',d)?.value||'';
    const signature=JSON.stringify([readiness.status,readiness.gateway,readiness.prerequisites]);if(signature===last)return;
    if(document.activeElement?.name==='setup_key')return;last=signature;
    const node=readiness.prerequisites?.node, cli=readiness.prerequisites?.omniroute;
    $('#setup-status',d).innerHTML=`<h3>${esc(guide.title)}</h3><p>${esc(guide.detail)}</p>${guide.install?`${!node?.installed?'<p><a href="https://nodejs.org/en/download" target="_blank" rel="noopener noreferrer">Install Node.js LTS and npm</a>, then restart CheapOS so it can find them.</p>':''}<p>Run this in your terminal. It installs the version used for the CheapOS integration.</p><code class="approval-command">npm install -g omniroute@3.8.49</code><button class="subtle-button" data-setup="copy">Copy install command</button>`:''}${cli?.installed?`<p class="small muted">Installed OmniRoute: ${esc(cli.version||'version unknown')}${cli.compatibility==='unverified'?' · compatibility unverified':''}</p>`:''}${guide.dashboard?`<p><a href="${esc(readiness.gateway.dashboard_url)}" target="_blank" rel="noopener noreferrer">Open OmniRoute dashboard ↗</a></p><p class="small muted">Sign in there if requested, then use Providers for provider credentials. Dashboard login and provider credentials are separate from a client API key.</p>`:''}${guide.key?'<form id="setup-key-form"><label>Gateway client API key<input name="setup_key" type="password" autocomplete="new-password" required></label><button class="outline-button" type="submit">Save client key and retry</button></form>':''}<div class="button-row">${guide.start?'<button class="primary-button" data-setup="start">Connect / start</button>':''}<button class="outline-button" data-setup="recheck">Re-check / I’m back</button>${guide.ready?'<button class="primary-button" data-setup="continue">Use this connection</button>':''}</div>${guide.ready?'<p class="small muted">Uses current eligible free routes. Automatic coding selects and checks a different reviewer. A saved explicit model pair is preserved. No project work starts until you send a request.</p>':''}`;
    if($('#setup-key-form',d)){ $('[name="setup_key"]',d).value=key;$('#setup-key-form',d).onsubmit=e=>{e.preventDefault();perform(async()=>{await api('/gateway/config',{api_key:$('[name="setup_key"]',d).value});$('[name="setup_key"]',d).value='';await api('/gateway/refresh',{});last='';await check()})}; }
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
  const d=dialog(`<form>${modalHeader('STARTUP','Ready when you open CheapOS')}<p class="modal-description">Start with an installed local model, or a configured free route through OmniRoute. A small greeting checks that it responds.</p><label class="checkbox-field"><input name="enabled" type="checkbox" ${settings.enabled?'checked':''}><span>Connect to a free model on launch</span></label><label class="checkbox-field"><input name="allow_cloud" type="checkbox" ${settings.allow_cloud?'checked':''}><span>Allow free cloud models through OmniRoute<small>Uses providers you have already set up. Project contents are sent only when you start a chat with that model.</small></span></label><p class="small muted">At most three free models are tried per connection check, with a 512-token output cap each. No paid fallback, model downloads, or provider enrollment. A saved model choice takes priority. Saving preferences makes no inference request.</p><p class="form-error" role="alert"></p><div class="modal-footer"><span>Reviewers remain under Models.</span><button type="submit" class="primary-button">Save preferences</button></div></form>`,'project-modal');
  const form=$('form',d);form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{const values=new FormData(form);await api('/startup/config',{enabled:values.has('enabled'),allow_cloud:values.has('allow_cloud')});d.close();await loadStartup()})};
}
function renderHome() {
  $('#task-title').textContent='New chat';$('#task-title').title='';$('#rename-task').hidden=true;document.title='CheapOS';
  $('.task-heading').hidden=true;$('.tabs').hidden=true;$('#compact-session').hidden=true;$('#toggle-inspector').hidden=true;$('#inspector').classList.add('home-hidden');
  $('.main-pane').classList.add('new-conversation');
  $('#project-name').textContent=state.project?CheapOSGuide.projectName({source:state.project.path}):'Your workspace';
  $$('.view').forEach(v=>v.classList.toggle('hidden',v.id!=='chat-view'));
  const opened=new Map($$('#chat-view details[data-event]').map(d=>[d.dataset.event,d.open]));
  $('#chat-view').innerHTML=`<div class="chat-welcome startup-welcome">${startupMarkup()}${state.project?`<div class="chat-suggestions"><button data-suggestion="Explain how this project works. Start by reading its README and main entry points.">Explain this project ${icon('chevron')}</button><button data-suggestion="Look through this project and suggest one small improvement. Explain it before making changes.">Find a small improvement ${icon('chevron')}</button></div>`:`<button class="primary-button" id="welcome-open">${icon('folder')}Open project</button>`}<button class="text-link startup-preferences" data-startup="preferences">Startup preferences</button></div>`;
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
function renderComposer() {
  const task=state.task, busy=task&&activeStatuses.has(task.status);
  $('#composer-permissions').hidden=!(task&&state.taskPermissions?.id===task.id&&(state.taskPermissions.commands.length||state.taskPermissions.project_grants?.length));
  $('#composer-permissions').textContent=state.taskPermissions?.project_grants?.length?'Tests allowed this session':'Commands allowed this session';
  $('#composer-permissions').title=state.taskPermissions?.project_grants?.length?'This project · until CheapOS restarts':'This chat · until CheapOS restarts';
  const chosenLimits=task?.limits||state.preferences.limits,preset=CheapOSGuide.workPreset(chosenLimits);
  $('#chat-budget').textContent=`${chosenLimits.dollars===0?'Free only':money(chosenLimits.dollars)+' cap'} · ${preset==='custom'?'Custom':preset==='extended'?'Extended':'Interactive'} ${chosenLimits.run_minutes??15} min`;
  $('#chat-budget').title=task?'Limits for this chat':'Defaults for new chats';
  const pausing=Boolean(task&&(task.status==='stopping'||state.pausingTask===task.id));
  $('#composer-area').hidden=Boolean(task?.demo||task?.archived_at||task?.trashed_at)||state.view!=='chat';
  $('#composer-project span').textContent=task?CheapOSGuide.projectName(task):state.project?CheapOSGuide.projectName({source:state.project.path}):'Open project';
  $('#composer-project').disabled=Boolean(task);
  $('#chat-input').disabled=state.sending;
  $('#chat-input').placeholder=state.project?'Ask about your project or describe a change…':'Open a project to get started…';
  const other=state.tasks.find(t=>t.id!==task?.id&&activeStatuses.has(t.status));
  if(busy){
    $('#chat-send').hidden=true;
    if($('#chat-steer')){
      $('#chat-steer').hidden=false;
      $('#chat-steer').disabled=pausing||state.sending||Boolean(other)||!$('#chat-input').value.trim();
    }
    $('#chat-input').placeholder='Add a detail or change direction…';
    $('#composer-note').textContent=pausing?'Pausing the current step. Your work and draft stay saved.':'Keep talking to CheapOS. Your message will guide the next step.';
  }else{
    const next=CheapOSConversation.readyForNext(task);
    $('#chat-send').hidden=false;
    if($('#chat-steer'))$('#chat-steer').hidden=true;
    $('#chat-send').disabled=state.sending||Boolean(other)||state.startup.busy||!$('#chat-input').value.trim();
    $('#chat-input').placeholder=next?'What should we work on next?':state.project?'Ask about your project or describe a change…':'Open a project to get started…';
    $('#composer-note').textContent=state.startup.busy?'Checking your free model. You can draft a message while it connects.':other?'Another chat is running. Open it in the sidebar to continue or pause it.':next?'Ready when you are. We’ll continue from the committed changes.':task?(task.changes.length?'Continue in the same task copy. See saved edits in Changes.':'Follow up here. This chat keeps its project context.'):'Edits stay in a separate copy. You review the result.';
  }
  if(task&&!task.demo)$('#composer-note').textContent+=` · Est. ${money(task.usage.cost)} used.`;
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
function projectMenu(path) {
  const d=dialog(`<form>${modalHeader('PROJECT','Remove from sidebar?')}<p>Repository files and chats are kept. Reopen this project from Hidden projects.</p><p class="small">${esc(path)}</p><p class="form-error" role="alert"></p><div class="modal-footer"><button type="button" data-close>Cancel</button><button type="submit">Remove from sidebar</button></div></form>`);
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
  const d=dialog(`<form>${modalHeader('LOCAL PROJECT','Open a project')}<p class="modal-description">Choose your project once, then chat. CheapOS will work in a separate copy when you send your first message.</p><label class="full-field">Project folder<input name="repository" placeholder="/Users/you/projects/my-project" required autocomplete="off" autofocus><small>Use the root folder of a local Git repository.</small></label><div class="hidden-project-list"></div><p class="form-error" role="alert"></p><div class="modal-footer"><span>Opening a project makes no model request.</span><button type="submit" class="primary-button">Open project ${icon('chevron')}</button></div></form>`,'project-modal');
  api('/projects/hidden').then(projects=>{if(!d.isConnected)return;$('.hidden-project-list',d).innerHTML=projects.length?`<details><summary>Hidden projects (${projects.length})</summary>${projects.map(p=>`<button type="button" data-hidden-project="${esc(p.path)}" aria-label="Reopen ${esc(p.name)} at ${esc(p.path)}">${esc(p.name)} · ${esc(p.path)}</button>`).join('')}</details>`:'';$$('[data-hidden-project]',d).forEach(b=>b.onclick=()=>{d.close();reopenHiddenProject(b.dataset.hiddenProject)})}).catch(e=>{$('.form-error',d).textContent=e.message});
  const form=$('form',d);form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{const project=await api('/projects',{repository:new FormData(form).get('repository')});state.projects=await api('/projects');d.close();chooseProject(project);if(afterOpen)afterOpen()})};
}
async function selectTask(id) {
  saveDraft();const request=++state.selection;state.loading=true;
  try {const task=await api('/tasks/'+id);if(request!==state.selection)return;if(!task.demo&&(state.hiddenProjects||[]).some(p=>p.path===task.source)){reopenHiddenProject(task.source,task.id);return;}state.task=task;state.project={path:task.source,name:basename(task.source)};state.file=0;state.run=-1;state.view='chat';try{localStorage.setItem('cheapos-selected',id)}catch{}renderTask({resetScroll:true});restoreDraft();renderSidebar();$('#sidebar').classList.remove('show');}
  catch(e){toast(e.message)}finally{if(request===state.selection)state.loading=false}
}
function setView(view) {
  state.view=view;renderView();renderComposer();
  const scroller=$('#view-container');
  scroller.scrollTo({top:view==='chat'?scroller.scrollHeight:0,behavior:'instant'});
  for(const output of $$('[data-command-output]'))output.scrollTop=output.scrollHeight;
}
function renderTask({resetScroll=false}={}) {
  const task=state.task;if(!task)return;$('.main-pane').classList.remove('new-conversation');
  loadTaskPermissions(task);
  $('.task-heading').hidden=false;$('.tabs').hidden=false;$('#compact-session').hidden=false;$('#toggle-inspector').hidden=false;$('#inspector').classList.remove('home-hidden');
  const scroller=$('#view-container'), oldScroll=scroller.scrollTop, bottom=scroller.scrollHeight-scroller.clientHeight-oldScroll<60;
  const expanded=new Map((resetScroll?[]:$$('details[data-event]')).map(d=>[d.dataset.event,d.open]));
  const outputScroll=new Map((resetScroll?[]:$$('[data-thinking], [data-command-output]')).map(el=>[el.dataset.thinking||el.dataset.commandOutput,{top:el.scrollTop,bottom:el.scrollHeight-el.clientHeight-el.scrollTop<30}]));
  $('#task-title').textContent=task.title;$('#task-title').title=task.title;$('#rename-task').hidden=Boolean(task.trashed_at);document.title=task.title+' — CheapOS';
  $('#project-name').textContent=CheapOSGuide.projectName(task);
  $('#task-status').textContent=labels[task.status]||task.status;
  $('#task-date').textContent=date(task.created_at);
  $('#task-eyebrow').classList.toggle('running',activeStatuses.has(task.status));
  $('#task-subtitle').textContent=task.demo?'Scripted models. Real edits, checks, and checkpoint reviews.':task.status==='approved'?'Ready for your decision. Approve and commit, or keep chatting.':'Working in a separate copy of your repository.';
  $('#change-count').textContent=task.changes.length;$('#check-count').textContent=task.checks.length;
  const sums=patchTotals(task.patch);$('#diff-tally').innerHTML=`<span>+${sums.add}</span><span>−${sums.remove}</span>`;
  $('#compact-cost').textContent=money(task.usage.cost);
  const totalTokens=(task.usage?.worker?.tokens||0)+(task.usage?.reviewer?.tokens||0)+(task.usage?.coordinator?.tokens||0);
  const actualCost=task.usage?.cost;
  const usagePill=$('#compute-savings-pill');
  if(usagePill){
    usagePill.hidden=totalTokens===0;
    usagePill.textContent=`${totalTokens.toLocaleString()} accounted tokens · ${actualCost==null?'cost unknown':money(actualCost)} · ${CheapOSGuide.costProvenance(task)}`;
    usagePill.title=`Cost provenance: ${task.metrics?.cost?.provenance||'unknown'}. Includes retained uncertain reservations when present. Configured accounting is not a billing receipt.`;
  }
  renderView();renderInspector();renderComposer();bindTerminalCopy();
  for(const d of $$('details[data-event]'))if(expanded.has(d.dataset.event))d.open=expanded.get(d.dataset.event);
  for(const el of $$('[data-thinking], [data-command-output]')){const saved=outputScroll.get(el.dataset.thinking||el.dataset.commandOutput);el.scrollTop=!saved||saved.bottom?el.scrollHeight:saved.top}
  scroller.scrollTop=resetScroll?scroller.scrollHeight:state.view==='chat'&&bottom?scroller.scrollHeight:oldScroll;
}
function renderView() {
  $('#compact-session').hidden=true;
  $$('.tab').forEach(b=>{const selected=b.dataset.view===state.view;b.classList.toggle('active',selected);b.setAttribute('aria-selected',String(selected))});
  $$('.view').forEach(v=>{v.classList.toggle('hidden',v.id!==state.view+'-view');if(v.id!==state.view+'-view')v.innerHTML=''});
  if(!state.task){renderHome();return}
  if(state.view==='chat')renderChat();else if(state.view==='activity')renderActivity();else if(state.view==='changes')renderChanges();else renderTests();
  if(state.task.archived_at||state.task.trashed_at){
    const view=$('#'+state.view+'-view');
    for(const el of $$('button,input,textarea',view))el.disabled=true;
    const banner=document.createElement('section');banner.className='chat-decision';banner.innerHTML=`<p>${state.task.trashed_at?'Trash · saved files retained':'Archived conversation'} · restore before continuing.</p><button class="primary-button">Restore</button>`;
    $('button',banner).onclick=async()=>{try{if(state.task.trashed_at)await restoreTrash(state.task);else await archiveTask(state.task,false)}catch(e){toast(e.message)}};view.prepend(banner);
  }
}
function eventDetail(event) {
  const detail=event.detail;
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

  if(event.kind==='review')return `<p>${esc(detail.feedback)}</p><span class="decision ${detail.decision==='APPROVE'?'approve':'revise'}">${esc(detail.decision.replaceAll('_',' '))}</span>`;
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
  if(state.task&&activeStatuses.has(state.task.status)){await stopTask();return}
  if(!state.startup.busy||state.stoppingStartup)return;
  state.stoppingStartup=true;renderComposer();
  try{await api('/startup/stop',{});await loadStartup()}
  catch(e){toast(e.message)}
  finally{state.stoppingStartup=false;renderComposer()}
}
function thinkingMarkup(detail,live=false) {
  if(!detail.thinking)return '';
  const key='generation-'+detail.request_id;
  return `<details class="thinking-panel ${live?'is-live':''}" data-event="${key}" ${live?'open':''}><summary>${icon('spark')}<strong>${detail.interrupted?'Thinking · interrupted':'Thinking'}</strong><span>${live?'Live':esc(detail.model)}</span>${icon('chevron')}</summary><div class="thinking-output" data-thinking="${key}">${esc(detail.thinking)}</div>${detail.truncated?'<p class="thinking-note">Showing the first 16,000 characters.</p>':''}</details>`;
}
function commandMarkup(check,{live=false,open=false,key=check.run_id}={}) {
  const status=live?'Running check':({passed:'Check passed',test_failure:'Test process failed',process_timeout:'Test process timed out',task_deadline:'Task deadline reached',output_limit:'Output limit reached',user_paused:'Check paused',inputs_changed:'Verification inputs changed'}[check.outcome]||(check.passed?'Check passed':check.reason==='cancelled'?'Check stopped':'Check failed'));
  const rawOutput=check.output||(live?'Waiting for command output…':'');
  const formatted=CheapOSGuide.formatTerminalOutput(rawOutput);
  const exitPill=live?'<span class="term-status-pill live"><span class="pulse-dot"></span>Live</span>':check.passed?`<span class="term-status-pill pass">Exit 0 · ${Number(check.duration||0).toFixed(1)}s</span>`:`<span class="term-status-pill fail">Exit ${check.exit_code??'1'} · ${Number(check.duration||0).toFixed(1)}s</span>`;
  return `<details class="command-panel ${live?'is-live':check.passed?'passed':'failed'}" data-event="command-${esc(key)}" ${live||open?'open':''}><summary>${live?'<span class="spinner"></span>':icon(check.passed?'check':'x')}<strong>${status}</strong><span>${live?'Live output':`Exit ${check.exit_code??'—'} · ${Number(check.duration||0).toFixed(1)}s`}</span>${icon('chevron')}</summary><code class="command-line">${esc(check.command.join(' '))}</code>${(check.allowed_seconds||check.timeout_seconds)?`<p class="command-note">Allowed: ${Number(check.allowed_seconds||check.timeout_seconds).toFixed(1)} seconds</p>`:''}<div class="command-body"><div class="terminal-window ${live?'is-live':check.passed?'passed':'failed'}"><div class="terminal-header"><div class="traffic-dots"><span class="dot-red"></span><span class="dot-yellow"></span><span class="dot-green"></span></div><span class="terminal-title"><code>${esc(check.command.join(' '))}</code></span><div class="terminal-actions">${exitPill}<button type="button" class="terminal-copy-btn" data-copy-terminal="command-${esc(key)}" title="Copy output">${icon('file')} Copy</button></div></div><div class="terminal-viewport"><pre class="command-output terminal-body" tabindex="0" data-command-output="command-${esc(key)}" aria-label="${live?'Live command output':'Command output'}">${formatted}</pre></div>${check.truncated?'<p class="command-note">Showing the first 32 KB of output.</p>':''}${check.reason?`<p class="command-note error">${esc(check.reason)}. ${esc(check.next_action||'')}</p>`:''}</div></div></details>`;
}
function permissionMarkup(task) {
  const pending=task.pending_approval, choice=CheapOSGuide.permissionChoice(pending), profile=pending.profile;
  const explanation=profile?`<p>Allow supported unittest variants in this project until CheapOS restarts or you revoke permission. Tests execute project code, including later test edits.</p><details><summary>Test permission scope</summary><p>Project: ${esc(profile.project)}</p><p>Runner: unittest · ${esc(profile.executable)}</p><p>Test roots: ${profile.roots.map(root=>esc(root==='.'?'Project root (.)':root)).join(', ')}. Supported selectors, discovery patterns, and verbosity flags.</p></details>`:'<p>This exact command in this chat’s task copy · until CheapOS restarts. Different commands ask again.</p>';
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
  else if(task.status==='ready')decision=(`<div class="chat-decision"><p>Your message is saved and ready to send.</p>${button('start','Send to CheapOS',true)}</div>`);
  else if(CheapOSGuide.canCommit(task))decision=(commitDecisionMarkup(task));
  else if(task.changes.length&&['approved','completed','awaiting_reply'].includes(task.status))decision=(`<section class="chat-result">${icon('file')}<div><strong>Changes are saved; review isn’t finished yet.</strong><p>You can keep chatting. To finish this saved patch, CheapOS can complete the missing verification and review.</p><div class="button-row">${button('request-review','Finish review',true)}${button('changes','View diff')}</div></div></section>`);
  else if(!activeStatuses.has(task.status)&&task.status!=='awaiting_reply')decision=(`<section class="chat-decision"><strong>${esc(failure?.title||guide.title)}</strong><p>${esc(failure?.description||guide.description)}</p>${errorDetails}<div class="button-row">${button(guide.primary==='retry-wait'?'retry-wait':guide.primary==='clarify'?'clarify':task.status==='error'?'start':'resume',guide.primary==='retry-wait'?'Retry when available':guide.primary==='clarify'?'Add a correction':task.status==='error'?'Retry':task.status==='takeover_requested'?'Review takeover request':task.status==='budget_paused'?guide.primaryLabel:'Resume',true)}${task.status==='error'||task.error_code==='routing_unavailable'?button('connections','Model settings'):''}${task.changes.length?button('changes','View changes'):''}</div></section>`);
  if(task.archived_at||task.trashed_at)decision='';
  const lastReply=conversation.findLast(entry=>entry.kind==='assistant');
  $('#chat-view').innerHTML=(task.demo?'<div class="demo-banner">Local demo · scripted models, real edits and checks</div>':task.sample?`<div class="demo-banner">${esc(CheapOSGuide.sampleOutcome(task))}<button class="text-link" data-sample-diagnostics>Connection diagnostics</button></div>`:'')+conversation.map(entry=>CheapOSChatView.message(entry,task,entry===lastReply?decision:'')).join('');
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
  updateProgressClock();bindCommitDecision(task);bindTerminalCopy();bindPermissions(task);
  $$('[data-chat-action]').forEach(b=>b.onclick=async()=>{
    const action=b.dataset.chatAction;
    if(action==='changes'||action==='activity'){setView(action);return}
    if(action==='clarify'){setView('chat');$('#chat-input')?.focus();return}
    if(action==='stop'){await stopTask();return}
    if(action==='connections'){openConnections(undefined,task);return}
    if(action==='request-review'){await requestCommitReview(b);return}
    if(action==='boost-headroom'){await boostHeadroom(b);return}
    if(action==='retry-wait'){await startTask(task.id,{retry_when_available:true});return}
    if(action==='resume'){await resumeTask(b);return}
    b.disabled=true;
    if(action==='start'){await startTask(task.id);b.disabled=false;return}
    try{await api('/tasks/'+task.id+'/approval',{approved:action!=='decline',remember:action==='approve-session',approval_id:task.pending_approval.id});await loadTaskPermissions(task,true);await refresh()}catch(e){toast(e.message);b.disabled=false}
  });
}
function renderActivity() {
  const task=state.task,a=CheapOSGuide.activity(task),guide=CheapOSGuide.taskGuide(task),failure=task.status==='error'?CheapOSGuide.failure(task):null;
  const action=(view,label)=>`<button class="outline-button" data-activity-view="${view}">${label}</button>`;
  const timeline=a.items.slice(0,40).map(item=>`<details class="activity-step ${item.failed?'failed':''}" data-event="step-${item.event.id}"><summary><span class="step-icon">${icon(item.icon)}</span><span><strong>${esc(item.title)}</strong>${item.note?`<small>${esc(item.note)}</small>`:''}</span><time>${new Date(item.event.time).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</time>${icon('chevron')}</summary><div class="step-body">${eventDetail(item.event)}${item.path&&task.changes.some(c=>c.path===item.path)?`<button class="text-link" data-activity-file="${esc(item.path)}">View current diff →</button>`:''}</div></details>`).join('');
  const technical=task.events.map(e=>`<details class="activity-card" data-event="raw-${e.id}"><summary><strong>${esc(CheapOSGuide.activityItem(e)?.title||e.title)}</strong>${icon('chevron')}</summary><div class="detail-body">${eventDetail(e)}</div></details>`).join('');
  const status=task.pending_approval?permissionMarkup(task):activeStatuses.has(task.status)?progressMarkup(task):`<section class="activity-status"><span class="activity-eyebrow">${['approved','completed'].includes(task.status)?'RESULT':'CURRENT STATUS'}</span><h3>${esc(failure?.title||guide.title)}</h3><p>${esc(failure?.description||guide.description)}</p>${task.error&&task.error!==guide.description?`<p>${esc(task.error)}</p>`:''}<div class="button-row">${['approved','completed'].includes(task.status)?action('changes','Review changes'):''}${action('chat','Back to chat')}${['paused','budget_paused','interrupted','error','takeover_requested'].includes(task.status)?`<button class="outline-button" id="activity-resume">${task.status==='error'?'Retry':guide.primaryLabel}</button>`:''}${task.error_code==='routing_unavailable'?'<button class="outline-button" id="activity-models">Models</button>':''}</div></section>`;
  $('#activity-view').innerHTML=`<div class="view-title"><div><h2>What’s happening</h2><p>${task.demo?'Scripted demo · real files and checks':'Real actions and saved results from this chat.'}</p></div></div>${status}${task.check_stream?commandMarkup(task.check_stream,{live:true}):''}<div class="activity-facts"><button data-activity-view="changes"><span>Saved changes · whole chat</span><strong>${a.files} file${a.files===1?'':'s'}</strong><small>Inspect the diff →</small></button><button data-activity-view="tests"><span>Checks · this request</span><strong>${esc(a.checks)}</strong><small>View command output →</small></button><button id="activity-review" ${!a.checkpoint?'disabled':''}><span>Review · this request</span><strong>${esc(a.review)}</strong><small>${a.checkpoint?'Inspect the decision →':'A passing check alone is not approval'}</small></button></div><section class="activity-timeline"><h3>Latest request</h3><p class="activity-request">${esc(a.request)}</p><p class="small muted">Newest actions first${a.items.length>40?' · showing the latest 40':''}</p>${timeline||'<p class="activity-empty">No file actions yet. Conversation and live model output are in Chat.</p>'}</section><details class="technical-log" data-event="technical"><summary>${icon('code')}Technical log <span>${task.events.length} events</span>${icon('chevron')}</summary><div>${technical}</div></details>`;
  $$('[data-activity-view]').forEach(b=>b.onclick=()=>setView(b.dataset.activityView));
  $$('[data-chat-action]').forEach(b=>b.onclick=()=>b.dataset.chatAction==='stop'?stopTask():b.dataset.chatAction==='connections'?openConnections():setView('chat'));
  $$('[data-activity-file]').forEach(b=>b.onclick=()=>{state.file=task.changes.findIndex(c=>c.path===b.dataset.activityFile);setView('changes')});
  bindPermissions(task);
  $$('[data-checkpoint]').forEach(b=>b.onclick=()=>checkpointDialog(Number(b.dataset.checkpoint)));
  $('#activity-review').onclick=()=>a.checkpoint&&checkpointDialog(a.checkpoint.number);
  if($('#activity-resume'))$('#activity-resume').onclick=e=>guide.primary==='retry-wait'?startTask(task.id,{retry_when_available:true}):guide.primary==='clarify'?(setView('chat'),$('#chat-input')?.focus()):resumeTask(e.currentTarget);
  if($('#activity-models'))$('#activity-models').onclick=openConnections;
  updateProgressClock();
}
function checkpointDialog(number) {
  const checkpoint=state.task.checkpoints.find(c=>c.number===number);if(!checkpoint)return;
  const isRunning=activeStatuses.has(state.task.status);
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
  $('#changes-view').innerHTML=`<div class="view-title"><div><h2>Review the work.</h2><p>${files.length} changed files in the task copy</p></div><div class="button-row"><a class="subtle-button" href="/api/tasks/${task.id}/patch" download>${icon('file')}Export patch</a>${!CheapOSGuide.canCommit(task)&&task.status==='awaiting_reply'?'<button class="primary-button" id="commit-review">Finish review</button>':''}</div></div>${CheapOSGuide.canCommit(task)?commitDecisionMarkup(task):''}<div class="file-list">${files.map((f,i)=>`<button class="file-item ${i===state.file?'selected':''}" data-file="${i}">${icon('file')}<span>${esc(f.path)}</span><span class="file-status">${f.before?'M':'A'}</span></button>`).join('')}</div><div class="diff-panel"><div class="diff-toolbar"><span>${icon('file')}${esc(file.path)}</span><div class="segmented"><button data-diff="unified" class="${state.diff==='unified'?'selected':''}">Unified</button><button data-diff="split" class="${state.diff==='split'?'selected':''}">Split</button></div></div>${file.binary?'<p class="modal-description">Binary change. Inspect the exported Git patch.</p>':state.diff==='unified'?`<div class="diff-code" tabindex="0" aria-label="Unified code diff">${rows.map(line).join('')}</div>`:`<div class="split-diff">${['before','after'].map(side=>`<div class="diff-code" tabindex="0" aria-label="${side==='before'?'Original':'Modified'} file"><div class="split-label">${side==='before'?'Before':'After'}</div>${rows.filter(r=>r.type!==(side==='before'?'add':'remove')).map(r=>`<div class="diff-line ${r.type}"><span class="line-number">${side==='before'?r.old:r.new}</span><span class="source">${esc(r.text)||' '}</span></div>`).join('')}</div>`).join('')}</div>`}</div><div class="diff-bottom">${icon('shield')}${CheapOSGuide.canCommit(task)?'Approve the reviewed patch above, or keep chatting to request changes.':'The task copy is saved. Verification and review must finish before committing.'}</div><details class="patch-help"><summary>Apply manually instead</summary><p>From your original repository, check the downloaded patch first, then apply it:</p><pre>git apply --check /path/to/cheapos-${task.id.slice(0,8)}.patch\ngit apply /path/to/cheapos-${task.id.slice(0,8)}.patch</pre><p>For large files, the visual comparison shows whole blocks; the exported Git patch preserves the exact change, including file modes and final newlines.</p></details>`;
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
  setView('chat');const input=$('#chat-input');input.placeholder='Tell CheapOS what to change, or ask a question…';input.focus();input.scrollIntoView({block:'nearest'});
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
  $('#tests-view').innerHTML=`<div class="view-title"><div><h2>Evidence, before approval.</h2><p>Actual output from your configured command</p></div></div><div class="test-run-picker"><span>Verification history</span><select id="run-picker" aria-label="Verification run">${checks.map((c,i)=>`<option value="${i}" ${i===index?'selected':''}>Run ${i+1} · ${c.passed?'Passed':'Failed'}</option>`).join('')}</select></div><div class="test-summary ${check.passed?'':'failure'}">${icon(check.passed?'check':'x')}<strong>${check.passed?'Command passed':'Command failed'}</strong><span>Exit ${check.exit_code} · ${check.duration.toFixed(2)}s${check.allowed_seconds?` / ${Number(check.allowed_seconds).toFixed(1)}s allowed`:''}</span></div><code class="check-command">${esc(check.command.join(' '))}</code>${check.reason?`<p class="form-error">${esc(check.reason)}. ${esc(check.next_action||'')}</p>`:''}<div class="terminal-window ${check.passed?'passed':'failed'}"><div class="terminal-header"><div class="traffic-dots"><span class="dot-red"></span><span class="dot-yellow"></span><span class="dot-green"></span></div><span class="terminal-title"><code>${esc(check.command.join(' '))}</code></span><div class="terminal-actions">${exitPill}<button type="button" class="terminal-copy-btn" data-copy-terminal="tests-run-output" title="Copy output">${icon('file')} Copy</button></div></div><div class="terminal-viewport"><pre class="command-output terminal-body" tabindex="0" data-command-output="tests-run-output">${formattedOutput}</pre></div></div><p class="muted small" style="margin-top:14px">Passed means this command exited successfully. The reviewer still checks whether the implementation satisfies the task.</p>`;
  $('#run-picker').onchange=e=>{state.run=Number(e.target.value);renderTests()};
}
function bindTerminalCopy() {
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
  const roles=['coordinator','worker','reviewer'].filter(role=>role!=='coordinator'||config[role]).map(role=>`<div class="role-row"><span class="role-icon ${role}-icon">${icon(role==='worker'?'code':'spark')}</span><span><span class="role-label">${role.toUpperCase()}</span><strong>${esc(t?.demo?'Scripted demo':config[role]?.model||'Choose a model')}</strong></span></div>`);
  const intro=t?`<section class="economy-intro compact-intro"><div class="mode-badge">${icon('leaf')}Economy mode</div><p>Work, verify, then ask for a second opinion.</p></section>`:`<section class="economy-intro"><div class="economy-icon">${icon('leaf')}</div><h2>A little patience.<br>A little more in your pocket.</h2><p>Spend less on the loop.<br>Save the stronger model for review.</p><div class="mode-badge">${icon('leaf')}Economy mode</div></section>`;
  const models=`<section class="model-roles">${roles.join('<div class="role-connection"><span></span></div>')}</section>`;
  const usage=t?`<section class="usage"><div class="section-title">Compute, thoughtfully spent</div><div class="cost-total"><strong>${money(t.usage.cost)}</strong><span>${t.demo?'no model charges':'accounted session cost'}</span></div><div class="usage-table">${['coordinator','worker','reviewer'].filter(role=>t.usage[role]).map(role=>`<div><span>${role==='worker'?'Worker':role==='coordinator'?'Local chat':'Reviewer'}</span><span>${t.usage[role].tokens.toLocaleString()} <small>tokens</small></span><strong>${money(t.usage[role].cost)}</strong></div>`).join('')}</div><div class="budget-meter"><span style="width:${Math.min(100,t.limits.dollars>0?t.usage.cost/t.limits.dollars*100:0)}%"></span></div><p class="small muted">${money(t.limits.dollars)} estimated cap · ${t.limits.reviewer_tokens.toLocaleString()} reviewer tokens</p><p class="small muted">${t.usage.uncertain_requests?`${t.usage.uncertain_requests} uncertain request(s): reservations remain counted.`:t.usage.estimated_requests?'Some costs use your configured token prices.':t.demo?'Demo usage is zero. No savings are claimed.':'Reported cost when available; configured prices otherwise.'}</p>${!activeStatuses.has(t.status)&&!['approved','completed'].includes(t.status)?'<button class="text-link" id="edit-limits">Review limits →</button>':''}</section>`:'';
  const journey=t?`<section class="journey"><div class="section-title">This session</div><ol class="journey-list">${[['Worker turns',t.worker_turns],['Tool actions',t.tool_actions],['Checkpoints',t.checkpoints.length],['Reviewer calls',t.review_count],['Latest check',t.checks.length?(t.checks.at(-1).passed?'Passed':'Failed'):'Not run']].map(([label,value])=>`<li><span class="journey-dot">${icon('check')}</span><span>${label}</span><strong>${value}</strong></li>`).join('')}</ol></section>`:'';
  const workspace=t?`<details class="workspace-info"><summary>Workspace details</summary><p>Task copy</p><code>${esc(t.workspace)}</code><p>Snapshot: ${t.snapshot.files} files · ${t.snapshot.skipped.length} excluded</p><p class="small">Snapshot excludes common secret files and dependency folders. Review your repository before sending its contents to a provider.</p></details>`:`<section class="usage"><div class="section-title">Yours, from the start</div><p class="small muted">Open source. Local task history. Your providers, your keys, your limits.</p><button class="subtle-button" id="inspector-connect">Set up connections →</button></section>`;
  $('#session-details').innerHTML=intro+models+usage+journey+workspace+(t?'<button class="subtle-button" id="session-permissions">Session permissions</button><button class="subtle-button" id="open-activity">See activity →</button>':'');if($('#open-activity'))$('#open-activity').onclick=()=>setView('activity');
  if($('#session-permissions'))$('#session-permissions').onclick=sessionPermissions;
  if($('#edit-limits'))$('#edit-limits').onclick=chatLimits;if($('#inspector-connect'))$('#inspector-connect').onclick=openConnections;
}
const numberField=(name,label,value,min,max,step='1')=>`<label>${label}<input name="${name}" type="number" min="${min}" max="${max}" step="${step}" value="${value}" required></label>`;
function limitFields(limits={dollars:0,reviewer_tokens:200000,iterations:5,worker_turns:40,output_tokens:2048,run_minutes:15}) {
  const preset=CheapOSGuide.workPreset(limits);
  return `<div class="field-grid"><label class="checkbox-field"><input type="checkbox" name="free_only" ${limits.dollars===0?'checked':''}><span>Free only</span></label><div data-spending-cap ${limits.dollars===0?'hidden':''}>${numberField('dollars','Explicit spending cap ($)',limits.dollars,limits.dollars===0?0:.01,100,'0.01')}</div><label>Working time<select name="work_preset">${[['interactive','Interactive · 15 minutes'],['extended','Extended · 45 minutes'],['custom','Custom']].map(([value,label])=>`<option value="${value}" ${preset===value?'selected':''}>${label}</option>`).join('')}</select><small data-work-duration>${limits.run_minutes??15} minutes of working time per run</small></label></div><details class="advanced"><summary>Advanced limits</summary><p class="small muted">Working time covers the whole run, including cooldown waits. A verification timeout bounds one command and cannot extend the run.</p><div class="field-grid">${numberField('reviewer_tokens','Reviewer token limit',limits.reviewer_tokens,512,1000000)}${numberField('iterations','Max worker iterations',limits.iterations,1,20)}${numberField('worker_turns','Worker turns per request',limits.worker_turns,1,200)}${numberField('output_tokens','Output tokens per request',limits.output_tokens,128,16384)}${numberField('checkpoint_turns','Checkpoint interval (turns)',limits.checkpoint_turns??12,2,200)}${numberField('run_minutes','Minutes per run (excludes approval waits)',limits.run_minutes??15,1,720)}${numberField('check_seconds','Seconds per verification command',limits.check_seconds??90,1,1800)}</div></details>`;
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
  if(preset.repository){state.project={path:preset.repository,name:basename(preset.repository)};renderHome();restoreDraft()}
  if(prefill){$('#chat-input').value=prefill;saveDraft();renderComposer()}
  if(!state.project)openProject();else $('#chat-input').focus();
}
const executionLabel=mode=>({delegate:'Delegate heavy work',local:'All local',remote:'All remote',manual:'Manual model pair'}[mode]||'Manual model pair');
function executionPreferences() {
  const saved=state.preferences.execution||{},local=state.config.worker?.base_url?.includes(':11434')?state.config.worker.model:'';
  const d=dialog(`<form>${modalHeader('EXECUTION','Where should the work run?')}<p class="modal-description">Choose how new chats use your laptop and connected providers.</p>${state.task?`<p class="execution-notice">This chat keeps <strong>${esc(executionLabel(state.task.execution?.mode))}</strong> and its saved models. Start a new chat to use a different setup.</p>`:''}<div class="execution-options">${[
    ['delegate','Delegate heavy work','Short local chats. Free remote models inspect files, implement changes, and review. Your local model goes idle after handoff.'],
    ['local','All local','Work and review on your own hardware. No remote model requests.'],
    ['remote','All remote','A responding free OmniRoute model handles chat and work; a different free model reviews.'],
    ['manual','Manual model pair','Use the worker and reviewer selected in Models, including paid models when your spending cap allows.']
  ].map(([value,title,description])=>`<label class="execution-option"><input type="radio" name="mode" value="${value}" ${(saved.mode||'manual')===value?'checked':''}><span><strong>${title}</strong><small>${description}</small></span></label>`).join('')}</div><div id="execution-local"><label class="full-field">Installed Ollama model<input name="local_model" value="${esc(saved.local_model||local)}" placeholder="Your installed model ID" autocomplete="off"><small>Used for short chat in Delegate mode, and implementation in All local.</small></label><label class="full-field" id="execution-reviewer">Local reviewer model · optional<input name="local_reviewer" value="${esc(saved.local_reviewer||'')}" placeholder="Use the same local model" autocomplete="off"></label></div><p id="execution-remote" class="execution-notice">Uses providers you enabled in OmniRoute. Project context is sent when work is handed off. CheapOS checks up to four free candidates per role without project data. A worker handles chat and edits; a different reviewer is selected at a checkpoint. Failed models cool down; up to two free-model handoffs per request continue saved work automatically. Saved edits wait if review is unavailable. No automatic paid or local fallback.</p><p class="small muted">Free routing uses advertised prices. Check OmniRoute’s fallback and billing settings. Automatic chats can switch between free models after failures. Manual and local choices stay fixed. Saving does not start inference or download anything.</p><p class="form-error" role="alert"></p><div class="modal-footer"><span>Applies to new chats.</span><button class="primary-button" type="submit">Save execution choice</button></div></form>`,'execution-modal');
  const form=$('form',d),layout=()=>{const mode=new FormData(form).get('mode');$('#execution-local',d).hidden=!['local','delegate'].includes(mode);$('#execution-reviewer',d).hidden=mode!=='local';$('#execution-remote',d).hidden=!['remote','delegate'].includes(mode);$('[name="local_model"]',d).required=['local','delegate'].includes(mode)};
  $$('[name="mode"]',d).forEach(input=>input.onchange=layout);layout();
  form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{const f=new FormData(form);state.preferences=await api('/preferences',{execution:Object.fromEntries(['mode','local_model','local_reviewer'].map(k=>[k,String(f.get(k)||'')]))});d.close();renderComposer();toast('Execution choice saved for new chats.');})};
}
function chatLimits({defaults=false}={}) {
  const task=defaults?null:state.task,limits=task?.limits||state.preferences.limits;
  const d=dialog(`<form>${modalHeader('SPENDING & LIMITS',task?'Limits for this chat':'Defaults for new chats')}<p class="modal-description">Choose a bounded work session. Presets change working time and task turns; they keep your spending cap and model placement.</p>${limitFields(limits)}<p class="small muted">Free only uses configured prices; it is not a provider billing guarantee.</p>${task?'<button type="button" class="text-link" data-new-defaults>Edit defaults for new chats</button>':''}<p class="small muted">${task?'Usage is cumulative across this chat. Saving does not resume it.':'These defaults apply when you send the first message in a new chat.'}</p><p class="form-error" role="alert"></p><div class="modal-footer"><span>Cost estimates use your configured prices.</span><button class="primary-button" type="submit">Save limits</button></div></form>`);
  const form=$('form',d);bindLimitFields(form);if($('[data-new-defaults]',d))$('[data-new-defaults]',d).onclick=()=>{d.close();chatLimits({defaults:true})};if(task&&activeStatuses.has(task.status)){ $('[type="submit"]',form).disabled=true;$('.form-error',form).textContent='Pause this chat before changing its limits. New-chat defaults can be edited separately.';}form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{const limits=readLimits(new FormData(form));if(task){state.task=await api('/tasks/'+task.id+'/limits',{limits})}else state.preferences=await api('/preferences',{limits});d.close();renderComposer();if(state.task)renderInspector()})};
}
async function sendChat() {
  const task=state.task, busy=task&&activeStatuses.has(task.status);
  $('#composer-permissions').hidden=!(task&&state.taskPermissions?.id===task.id&&(state.taskPermissions.commands.length||state.taskPermissions.project_grants?.length));
  $('#composer-permissions').textContent=state.taskPermissions?.project_grants?.length?'Tests allowed this session':'Commands allowed this session';
  $('#composer-permissions').title=state.taskPermissions?.project_grants?.length?'This project · until CheapOS restarts':'This chat · until CheapOS restarts';
  if(busy){
    await steerTask();
    return;
  }
  if(state.sending||state.startup.busy||state.tasks.some(t=>activeStatuses.has(t.status)))return;
  const message=$('#chat-input').value.trim();if(!message)return;
  if(!state.project){openProject(()=>{$('#chat-input').value=message;saveDraft();renderComposer()});return}
  if((state.preferences.execution?.mode||'manual')==='manual'&&(!state.config.worker||!state.config.reviewer)){openConnections(()=>{$('#chat-input').focus()});return}
  const key=draftKey();state.sending=true;renderComposer();
  try {
    if(state.task){await api('/tasks/'+state.task.id+'/message',{message});state.drafts.delete(key);$('#chat-input').value='';await refresh()}
    else {const task=await api('/tasks',{repository:state.project.path,prompt:message,conversational:true,limits:state.preferences.limits});state.drafts.delete(key);$('#chat-input').value='';await loadTasks();await selectTask(task.id);await startTask(task.id)}
    $('#view-container').scrollTop=$('#view-container').scrollHeight;
  }catch(e){toast(e.message)}finally{state.sending=false;renderComposer();$('#chat-input').focus()}
}
async function steerTask(text) {
  const message=text||$('#chat-input').value.trim();
  if(!state.task||!message||state.sending||state.task.status==='stopping'||state.pausingTask===state.task.id)return;
  const key=draftKey();state.sending=true;renderComposer();
  try {
    await api('/tasks/'+state.task.id+'/steer',{message});
    state.drafts.delete(key);$('#chat-input').value='';
    toast('CheapOS will use your update on the next step.');
    await refresh();
    $('#view-container').scrollTop=$('#view-container').scrollHeight;
  }catch(e){toast(e.message)}finally{state.sending=false;renderComposer();$('#chat-input').focus()}
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
async function startTask(id,changes={}) {try{await api('/tasks/'+id+'/start',changes);await refresh()}catch(e){toast(e.message)}}
async function resumeTask(button) {
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
    const d=dialog(`${modalHeader('SESSION PERMISSIONS','Tests and commands you’ve allowed')}<p>Permissions expire when CheapOS restarts. Revocation affects future commands; running commands continue.</p><h3>Project tests</h3>${grants.length?grants.map(g=>`<section><p>${esc(g.profile.project)} · unittest</p><p>Test roots: ${g.profile.roots.map(root=>esc(root==='.'?'Project root (.)':root)).join(', ')}</p><button class="outline-button" data-revoke-grant="${g.id}">Revoke project tests</button></section>`).join(''):'<p>No project test grants.</p>'}<h3>Exact commands in this chat</h3>${permissions.commands.length?permissions.commands.map(c=>`<code class="approval-command">${esc(c.join(' '))}</code>`).join(''):'<p>No exact-command grants.</p>'}${permissions.commands.length?'<button class="outline-button" id="clear-session-permissions">Clear exact commands</button>':''}<p class="form-error" role="alert"></p>`);
    const revoke=async(button,body)=>{button.disabled=true;try{await api('/tasks/'+task.id+'/permissions',body);await loadTaskPermissions(task,true);d.close();toast('Permission revoked. Future commands may ask again.');await refresh()}catch(error){$('.form-error',d).textContent=error.message;button.disabled=false;await refresh()}};
    $$('[data-revoke-grant]',d).forEach(b=>b.onclick=()=>revoke(b,{revoke_project_grant:b.dataset.revokeGrant}));
    const clear=$('#clear-session-permissions',d);if(clear)clear.onclick=()=>revoke(clear,{clear:true});
  }catch(error){toast(error.message)}
}
async function startDemo() {
  if(!state.online){toast('The local server is unavailable. Start it with python3 run.py');return}
  try{const task=await api('/demo',{});await loadTasks();await selectTask(task.id);await startTask(task.id)}catch(e){toast(e.message)}
}
function sampleDialog() {
  const d=dialog(`${modalHeader('SAMPLE TASK','Try the complete workflow')}<p>Fix a small clamp function in a new disposable repository. Your selected project is untouched. Saved results stay available in history and can be moved to Trash.</p><h3>Scripted demonstration</h3><p>Predetermined worker and reviewer responses, actual local checks, no model requests. This demonstrates the interface; it does not validate your models.</p><button class="outline-button" data-sample="scripted">Run scripted demonstration</button><h3>Real loop with selected models</h3><p>Uses your current placement and models for file edits, actual unittest checks, and a separate review request. Up to 5 minutes, 20 worker turns, 3 iterations, and the smaller of your current spending cap or $0.25. Free only remains $0. A same-model local review is labeled as such.</p><p>Starting authorizes only the sample’s exact Python unittest discovery command in its disposable task copy for this server session. Other commands and projects still ask. You approve any final commit.</p><button class="primary-button" data-sample="real">Start real sample</button><p class="form-error" role="alert"></p>`,'project-modal setup-modal');
  $$('[data-sample]',d).forEach(button=>button.onclick=async()=>{
    $$('[data-sample]',d).forEach(b=>b.disabled=true);
    try{if(button.dataset.sample==='scripted'){d.close();await startDemo();return}const task=await api('/sample',{});d.close();await loadTasks();await selectTask(task.id);await startTask(task.id)}catch(e){$('.form-error',d).textContent=e.message;$$('[data-sample]',d).forEach(b=>b.disabled=false)}
  });
}
function openConnections(afterSave, taskContext=null) {
  const c=state.config, gateway=state.gateway||{}, settings=gateway.settings||{base_url:'http://127.0.0.1:20128/v1',auto_start:true,keep_running:true};
  const isOmni=p=>p.gateway==='omniroute'||!p.base_url||p.base_url.replace('localhost','127.0.0.1').replace(/\/$/,'')===settings.base_url.replace('localhost','127.0.0.1');
  const providerFields=role=>{
    const p=c[role]||{}, preset=isOmni(p)?'omniroute':p.base_url.includes('openrouter.ai')?'openrouter':p.base_url.includes('11434')?'ollama':'custom';
    return `<fieldset class="provider-fields" data-role="${role}"><legend>${role==='worker'?'Worker · does the work':'Reviewer · checks the evidence'}</legend>
      <label class="full-field">Connection<select data-preset="${role}">${[['omniroute','OmniRoute (shared local gateway)'],['openrouter','OpenRouter (direct)'],['ollama','Ollama (local)'],['custom','OpenAI-compatible endpoint']].map(([v,n])=>`<option value="${v}" ${v===preset?'selected':''}>${n}</option>`).join('')}</select></label>
      <div data-direct="${role}"><label class="full-field">API base URL<input type="url" name="${role}_url" value="${esc(p.base_url||settings.base_url)}" required></label><label class="full-field">API key ${p.key_configured?'· configured':''}<input name="${role}_key" type="password" placeholder="Leave blank to keep the current key" autocomplete="new-password"></label></div>
      <div data-catalog="${role}"><label class="checkbox-field"><input type="checkbox" data-free="${role}" checked><span>Show free models only</span></label><label class="full-field">Available models<select data-model-picker="${role}"><option value="">Loading catalog…</option></select></label></div>
      <label class="full-field">Model ID<input name="${role}_model" type="text" value="${esc(p.model||'')}" placeholder="Choose above or enter an exact model ID" required autocomplete="off"></label>
      <p class="model-capabilities small" data-capabilities="${role}"></p>
      <div class="field-grid">${numberField(role+'_input','Input $ / million tokens',p.input_rate??'',0,10000,'any')}${numberField(role+'_output','Output $ / million tokens',p.output_rate??'',0,10000,'any')}</div>
      <p class="small muted">Unknown prices need your input. Verify them with the provider.</p></fieldset>`;
  };
  const d=dialog(`${modalHeader('MODEL CONNECTIONS','Choose where the work runs.')}<button class="outline-button" id="models-execution">Execution: ${esc(executionLabel(state.preferences.execution?.mode))} →</button><p class="modal-description">OmniRoute handles provider access. CheapOS handles the work, checks, and review.</p>${taskContext?`<div class="connection-context"><strong>Checking a stopped task</strong><p>Worker: <b>${esc(taskContext.providers.worker?.model||'not set')}</b><br>Reviewer: <b>${esc(taskContext.providers.reviewer?.model||'not set')}</b><br>Automatic remote chats check another free model after a recoverable failure when you resume. Manual and local chats keep their selected models; choices below apply to new chats.</p></div>`:''}
    <form class="gateway-card" id="gateway-form"><div class="gateway-heading"><div><strong>OmniRoute</strong><span class="gateway-badge" id="gateway-status" role="status"></span></div><a id="gateway-dashboard" class="subtle-button" href="${esc(gateway.dashboard_url||'http://127.0.0.1:20128')}" target="_blank" rel="noopener noreferrer">Open OmniRoute ↗</a></div>
      <p id="gateway-message" class="small muted"></p><p id="gateway-instance" class="small muted"></p>
      <details class="advanced"><summary id="free-pool-title">Free model pool</summary><p class="small muted">Refreshes every five minutes, including OpenRouter’s current free models. Failed models cool down for 15–60 minutes. Provider cooldowns follow the gateway’s retry time and do not count as individual model failures. A response or tool check does not prove coding quality.</p><div id="free-model-pool" class="free-model-pool"></div></details>
      <div class="gateway-actions"><button type="button" class="outline-button" data-gateway-action="start">Connect / start</button><button type="button" class="subtle-button" data-gateway-action="refresh">Refresh models</button><button type="button" class="subtle-button" data-gateway-action="stop" hidden>Stop instance</button></div>
      <details class="advanced"><summary>Startup & connection settings</summary><label class="full-field">Local API URL<input name="gateway_url" type="url" value="${esc(settings.base_url)}" required></label>
        <label class="full-field">Gateway client API key · optional<input name="gateway_key" type="password" placeholder="${gateway.key_configured?'Configured · leave blank to keep':'Only if OmniRoute requires a client key'}" autocomplete="new-password"></label>
        <p class="small muted">Manage provider credentials in OmniRoute. This client key is separate from your dashboard password and stays in CheapOS memory.</p>
        <label class="checkbox-field"><input name="auto_start" type="checkbox" ${settings.auto_start?'checked':''}><span>Start installed OmniRoute when CheapOS launches<small>Reuses an existing instance. Does not install or update software.</small></span></label>
        <label class="checkbox-field"><input name="keep_running" type="checkbox" ${settings.keep_running?'checked':''}><span>Keep OmniRoute running when CheapOS closes<small>CheapOS only stops an instance it started in this session.</small></span></label>
        <button class="outline-button gateway-save" type="submit">Save gateway settings</button></details><p class="form-error" role="alert"></p></form>
    <form id="models-form"><details class="advanced" ${(state.preferences.execution?.mode||'manual')==='manual'?'open':''}><summary>Explicit model choices · Manual mode and remote preferences</summary><div class="provider-grid">${providerFields('worker')}${providerFields('reviewer')}</div>
      <p class="small muted">Catalog connection and advertised tool support do not guarantee a successful model run. These explicit choices apply in Manual mode. Automatic remote modes prefer eligible choices here, check free candidates, and replace failing models with visible handoffs.</p>
      <label class="checkbox-field" id="share-key-field"><input type="checkbox" name="share_key" checked><span>Use the entered worker key for the reviewer when their direct API URLs match</span></label>
      </details><p class="form-error" role="alert"></p><div class="modal-footer"><span>Applies to new tasks.<br>Saving makes no inference request.</span><button class="primary-button" type="submit">${taskContext?'Save & prepare new chat':'Save connections'} ${icon('check')}</button></div></form>`,'connections-modal');
  $('#models-execution',d).onclick=()=>{d.close();executionPreferences()};
  const field=(role,name)=>$(`[name="${role}_${name}"]`,d);
  const usingOmni=role=>$(`[data-preset="${role}"]`,d).value==='omniroute';
  function capability(role) {
    const model=usingOmni(role)?state.gatewayModels.find(m=>m.id===field(role,'model').value.trim()):null;
    $(`[data-capabilities="${role}"]`,d).textContent=model?`${model.tool_calling===true?'Tool calling advertised':model.tool_calling===false?'Tool calling not advertised':'Tool support unknown'}${model.context_length?' · '+Intl.NumberFormat().format(model.context_length)+' context':''}${model.free?' · Free variant':''}`:'Use a model that supports tool calling. Availability has not been tested.';
  }
  function picker(role) {
    const select=$(`[data-model-picker="${role}"]`,d), free=$(`[data-free="${role}"]`,d).checked, current=field(role,'model').value.trim();
    const models=state.gatewayModels.filter(m=>!free||m.free);
    select.innerHTML=`<option value="">${models.length?'Choose from '+models.length+' models':'No matching models · refresh or enter an ID'}</option>`+models.map(m=>`<option value="${esc(m.id)}">${esc(m.id)}${m.tool_calling===true?' · tools':m.tool_calling===false?' · no tools advertised':''}</option>`).join('');
    select.value=models.some(m=>m.id===current)?current:'';
    capability(role);
  }
  function layout(role) {
    const omni=usingOmni(role);
    $(`[data-direct="${role}"]`,d).hidden=omni;
    for(const input of $$('input',$(`[data-direct="${role}"]`,d)))input.disabled=omni;
    $(`[data-catalog="${role}"]`,d).hidden=!omni;
    $('#share-key-field',d).hidden=usingOmni('worker')||usingOmni('reviewer');
    picker(role);
  }
  const gatewayForm=$('#gateway-form',d);
  function updateGateway() {
    if(!d.open)return;
    const g=state.gateway||{};
    const badge=$('#gateway-status',d);badge.textContent=({ready:'Catalog connected',checking:'Connecting…',starting:'Starting…',offline:'Offline',auth_required:'Client key needed',not_installed:'Not installed',unavailable:'Unavailable',error:'Startup failed'})[g.status]||'Not checked';badge.dataset.status=g.status||'unchecked';
    $('#gateway-message',d).textContent=g.message||'Connect your local gateway to load its model catalog.';
    $('#gateway-instance',d).textContent=g.status==='ready'?`${g.model_count} models · ${g.owned?'Started by CheapOS':'Reusing an existing instance'}`:'';
    const freeModels=state.gatewayModels.filter(m=>m.free&&m.tool_calling===true&&!m.local&&!m.id.startsWith('auto/'));
    const cooling=freeModels.filter(m=>(m.health?.retry_at||0)*1000>Date.now()).length;
    $('#free-pool-title',d).textContent=`Free model pool · ${freeModels.length-cooling} candidates${cooling?' · '+cooling+' cooling down':''}`;
    $('#free-model-pool',d).innerHTML=freeModels.map(m=>`<div class="pool-model"><strong>${esc(m.id)}</strong><span>${esc(CheapOSGuide.modelHealth(m))}${m.reasoning===true?' · reasoning advertised':''}</span>${m.health?.last_error?`<small>${esc(m.health.last_error)}</small>`:''}</div>`).join('')||'<p class="small muted">No free remote models advertising tool support are available in this catalog.</p>';
    $('#gateway-dashboard',d).href=g.dashboard_url||'http://127.0.0.1:20128';
    $$('[data-gateway-action]',d).forEach(b=>{b.disabled=Boolean(g.busy);if(b.dataset.gatewayAction==='stop')b.hidden=!g.owned});
    $('button[type="submit"]',gatewayForm).disabled=Boolean(g.busy);
    for(const role of ['worker','reviewer'])picker(role);
  }
  state.gatewayListener=updateGateway;
  d.addEventListener('close',()=>{if(state.gatewayListener===updateGateway)state.gatewayListener=null});
  $$('[data-gateway-action]',d).forEach(button=>button.onclick=()=>formAction(gatewayForm,async()=>{state.gateway=await api('/gateway/'+button.dataset.gatewayAction,{});updateGateway();await loadGateway()}));
  gatewayForm.onsubmit=e=>{e.preventDefault();formAction(gatewayForm,async()=>{
    const f=new FormData(gatewayForm), values={base_url:String(f.get('gateway_url')).trim(),auto_start:f.has('auto_start'),keep_running:f.has('keep_running')},key=String(f.get('gateway_key')).trim();if(key)values.api_key=key;
    state.gateway=await api('/gateway/config',values);$('[name="gateway_key"]',d).value='';
    state.gateway=await api('/gateway/refresh',{});updateGateway();toast('Gateway settings saved. Use Connect / start if it is offline.');
  })};
  for(const role of ['worker','reviewer']) {
    layout(role);
    $(`[data-free="${role}"]`,d).onchange=()=>picker(role);
    $(`[data-model-picker="${role}"]`,d).onchange=e=>{
      if(!e.target.value)return;
      const model=state.gatewayModels.find(m=>m.id===e.target.value);field(role,'model').value=model.id;
      field(role,'input').value=model.input_rate??'';field(role,'output').value=model.output_rate??'';capability(role);
    };
    field(role,'model').oninput=()=>{
      const model=usingOmni(role)?state.gatewayModels.find(m=>m.id===field(role,'model').value.trim()):null;
      for(const price of ['input','output'])field(role,price).value=model?.[price+'_rate']??'';
      picker(role);
    };
    $(`[data-preset="${role}"]`,d).onchange=e=>{
      const preset=e.target.value, p=c[role]||{};
      field(role,'url').value=preset==='omniroute'?state.gateway.settings.base_url:preset==='ollama'?'http://127.0.0.1:11434/v1':preset==='openrouter'?'https://openrouter.ai/api/v1':'';
      field(role,'key').value='';field(role,'model').value='';
      for(const price of ['input','output'])field(role,price).value=preset==='ollama'?'0':'';
      if(preset==='omniroute'&&isOmni(p)){field(role,'model').value=p.model||'';field(role,'input').value=p.input_rate??'';field(role,'output').value=p.output_rate??''}
      layout(role);
    };
  }
  const form=$('#models-form',d);
  form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{
    const f=new FormData(form),values={};
    for(const role of ['worker','reviewer']) {
      const omni=usingOmni(role);
      if(omni&&state.gateway.status!=='ready')throw new Error('Connect OmniRoute before saving its model choices.');
      values[role]={gateway:omni?'omniroute':'openai',base_url:omni?state.gateway.settings.base_url:String(f.get(role+'_url')).trim(),model:String(f.get(role+'_model')).trim(),input_rate:Number(f.get(role+'_input')),output_rate:Number(f.get(role+'_output'))};
      const key=omni?'':String(f.get(role+'_key')).trim();if(key)values[role].api_key=key;
    }
    if(!usingOmni('worker')&&!usingOmni('reviewer')&&f.has('share_key')&&values.worker.base_url.replace(/\/$/,'')===values.reviewer.base_url.replace(/\/$/,'')&&values.worker.api_key)values.reviewer.api_key=values.worker.api_key;
    state.config=await api('/config',values);form.reset();d.close();renderSidebar();if(state.task)renderInspector();else renderHome();toast('Connections saved for new tasks.');if(taskContext){const command=taskContext.check_command.map(arg=>"'"+arg.replaceAll("'","'\"'\"'")+"'").join(' ');newTask((taskContext.requests||[taskContext.prompt]).join('\n\nFollow-up:\n'),{repository:taskContext.source,check_command:command})}else if(typeof afterSave==='function')afterSave();
  })};
  updateGateway();
  api('/gateway/refresh',{}).then(g=>{state.gateway=g;updateGateway();return loadGateway()}).catch(e=>toast(e.message));
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
async function refresh() {
  if(state.loading)return;
  await loadStartup();await loadGateway();await loadTasks();const selected=state.task?.id;if(!selected)return;
  const task=await api('/tasks/'+selected);if(state.task?.id!==selected)return;
  if(['updated_at','status','title','custom_title','pinned','archived_at','trashed_at'].some(key=>task[key]!==state.task[key])){state.task=task;renderTask()}
}
async function bootstrap() {
  try {const data=await api('/bootstrap');state.token=data.token;state.config=data.config;state.gateway=data.gateway||{};state.startup=data.startup||{};state.tasks=data.tasks;state.projects=data.projects||[];state.hiddenProjects=data.hidden_projects||[];state.preferences=data.preferences||state.preferences;try{const path=localStorage.getItem('cheapos-project');state.project=state.projects.find(p=>p.path===path)||null}catch{}state.online=true;renderSidebar();let selected;try{selected=localStorage.getItem('cheapos-selected')}catch{}let freshStartup=false;try{freshStartup=Boolean(state.startup.started_at)&&localStorage.getItem('cheapos-startup-session')!==state.startup.session_id;localStorage.setItem('cheapos-startup-session',state.startup.session_id||'')}catch{}if(!freshStartup&&state.tasks.some(t=>t.id===selected))await selectTask(selected);else home();}
  catch(e){state.online=false;$('#chat-view').innerHTML='<div class="empty-state"><h2>Start CheapOS locally.</h2><p>Run <code>python3 run.py</code> in the project directory, then refresh this page. No sign-in is needed.</p></div>';renderInspector()}
}
async function poll() {try{if(state.online)await refresh()}catch(e){toast('Local server disconnected. Restart CheapOS and refresh to reconnect.');state.online=false}finally{setTimeout(poll,1500)}}
$$('.tab').forEach(b=>b.onclick=()=>setView(b.dataset.view));
$('#home-trigger').onclick=()=>openProject();$('.brand').onclick=e=>{e.preventDefault();home()};$('#new-task').onclick=()=>newTask();$('#search-trigger').onclick=openSearch;$('#settings-trigger').onclick=()=>openConnections();$('#session-settings').onclick=()=>openConnections();$('#demo-trigger').onclick=sampleDialog;$('#composer-project').onclick=()=>openProject();$('#chat-budget').onclick=chatLimits;$('#execution-choice').onclick=executionPreferences;$('#chat-input').oninput=()=>{saveDraft();renderComposer()};$('#chat-form').onsubmit=e=>{e.preventDefault();sendChat()};if($('#chat-steer'))$('#chat-steer').onclick=()=>steerTask();$('#chat-input').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();sendChat()}};$('#chat-stop').onclick=stopFromComposer;
function toggleInspector() {
  const panel=$('#inspector');
  if(matchMedia('(max-width:1280px)').matches){panel.classList.remove('hidden');panel.classList.toggle('show')}
  else{panel.classList.remove('show');panel.classList.toggle('hidden')}
}
$('#toggle-inspector').onclick=toggleInspector;$('#compact-session').onclick=toggleInspector;
$('#sidebar-toggle').onclick=()=>{if(matchMedia('(max-width:700px)').matches)$('#sidebar').classList.remove('show');else{$('#sidebar').classList.add('collapsed');$('#mobile-menu').style.display='flex'}};
$('#mobile-menu').onclick=()=>{if(matchMedia('(max-width:700px)').matches)$('#sidebar').classList.toggle('show');else{$('#sidebar').classList.remove('collapsed');$('#mobile-menu').style.display='none'}};
document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&['k','n',','].includes(e.key.toLowerCase())){e.preventDefault();if($('dialog[open]'))return;if(e.key.toLowerCase()==='k')openSearch();else if(e.key.toLowerCase()==='n')newTask();else openConnections()}if(e.key==='Escape'){$('#sidebar').classList.remove('show');$('#inspector').classList.remove('show')}});
bootstrap();setTimeout(poll,1500);setInterval(updateProgressClock,1000);

$('#rename-task').onclick=()=>renameTask();

$('#composer-permissions').onclick=sessionPermissions;
