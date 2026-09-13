'use strict';
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
const activeStatuses = new Set(['running', 'reviewing', 'waiting_approval', 'stopping']);
const labels = {awaiting_reply:'Ready for your message',ready:'Ready to start',running:'CheapOS is working',reviewing:'Checking your changes',waiting_approval:'Command approval needed',paused:'Paused',budget_paused:'Paused at a limit',interrupted:'Interrupted',error:'Needs attention',takeover_requested:'Takeover requested',approved:'Reviewer approved',completed:'Ready for your review'};
const state = {startup:{},token:'',config:{},projects:[],project:null,preferences:{limits:{dollars:0,reviewer_tokens:50000,iterations:5,worker_turns:40,output_tokens:2048}},sending:false,drafts:new Map(),gateway:{},gatewayModels:[],catalogRevision:-1,gatewayListener:null,tasks:[],task:null,selection:0,view:'chat',file:0,diff:'unified',run:-1,online:false,loading:false};
const money = value => '$' + Number(value || 0).toFixed(Number(value || 0) > 0 && value < .01 ? 4 : 2);
const date = value => new Date(value).toLocaleString([], {month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});
const basename = value => String(value).split('/').filter(Boolean).pop() || 'Repository';
let toastTimer;
function toast(message) { clearTimeout(toastTimer); $('#toast').textContent=message; $('#toast').classList.add('visible'); toastTimer=setTimeout(()=>$('#toast').classList.remove('visible'),5000); }
async function api(path, body) {
  const response = await fetch('/api' + path, body === undefined ? {cache:'no-store'} : {method:'POST',headers:{'Content-Type':'application/json','X-CheapOS-Token':state.token},body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'The local server could not complete this action');
  return data;
}
function dialog(html, cls='') {
  const previous=document.activeElement, d=document.createElement('dialog'); d.className='modal '+cls; d.innerHTML=html; $('#overlay-root').append(d);
  d.addEventListener('close',()=>{d.remove();previous?.focus()});
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
function renderSidebar() {
  $('#task-total').textContent=state.projects.length;
  $('#connection-indicator').textContent=state.startup.busy?'Connecting…':state.startup.status==='ready'?'Ready':state.config.worker&&state.config.reviewer?'Configured':'Set up';
  const groups=state.projects.map(project=>({project,tasks:state.tasks.filter(t=>!t.demo&&t.source===project.path)}));
  const demos=state.tasks.filter(t=>t.demo);if(demos.length)groups.push({project:{path:'demo',name:'Local demo'},tasks:demos});
  $('#task-list').innerHTML=groups.map(({project,tasks})=>`<div class="project-group"><button class="project-label ${state.project?.path===project.path?'selected':''}" data-project="${esc(project.path)}" title="${esc(project.path)}">${icon('folder')}<span>${esc(CheapOSGuide.projectName({source:project.path,demo:project.path==='demo'}))}</span></button>${tasks.slice(0,12).map(t=>`<button class="task ${state.task?.id===t.id?'active':''}" data-task="${t.id}" title="${esc(t.title)}"><span class="task-dot ${['approved','awaiting_reply'].includes(t.status)?'done':''} ${activeStatuses.has(t.status)?'pulsing':''}"></span><span class="task-list-title">${esc(t.title)}</span>${['error','budget_paused','waiting_approval'].includes(t.status)?'<span class="task-attention" aria-label="Needs attention">•</span>':''}</button>`).join('')}</div>`).join('')||'<p class="sidebar-empty">Open a project to start.<br>Your chats will appear here.</p>';
  $$('[data-task]').forEach(b=>b.onclick=()=>selectTask(b.dataset.task));
  $$('[data-project]').forEach(b=>b.onclick=()=>b.dataset.project==='demo'?selectTask(demos[0].id):chooseProject(state.projects.find(p=>p.path===b.dataset.project)));
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
  const actions=busy?`<button class="subtle-button" data-startup="stop">Stop connecting</button>`:!ready?`<button class="primary-button" data-startup="start">${icon('play')}${startup.status==='unavailable'?'Try again':'Connect a free model'}</button>${!startup.settings?.allow_cloud?'<button class="outline-button" data-startup="cloud">Use free cloud models</button>':''}<button class="text-link" data-startup="models">Models</button>`:'';
  return `<div class="welcome-mark">${busy?'<span class="spinner"></span>':icon('code')}</div><h1>${title}</h1>${model?`<div class="startup-model ${ready?'ready':''}"><span class="task-dot ${ready?'done':'pulsing'}"></span>${esc(modelText)}</div>`:''}<p class="welcome-greeting">${esc(ready?startup.content:startup.content||startup.message||'Open a local project, then talk to CheapOS.')}</p>${startup.thinking?thinkingMarkup({thinking:startup.thinking,request_id:'startup',model:model?.id||''},true):''}${ready?'<span class="startup-verified">Greeting received · no API cost reported</span>':''}<div class="startup-actions">${actions}</div>${startup.attempts?.some(a=>a.status==='failed')?`<details class="startup-attempts"><summary>Connection details</summary>${startup.attempts.filter(a=>a.status==='failed').map(a=>`<p><strong>${esc(a.model)}</strong><br>${esc(a.error)}</p>`).join('')}</details>`:''}`;
}
function bindStartupActions(root=document) {
  $$('[data-startup]',root).forEach(button=>button.onclick=async()=>{
    const action=button.dataset.startup;
    if(action==='models'){openConnections();return}
    if(action==='preferences'){startupPreferences();return}
    button.disabled=true;
    try{
      if(action==='cloud')await api('/startup/config',{allow_cloud:true,enabled:true});
      await api('/startup/'+(action==='stop'?'stop':'start'),{});await loadStartup();
    }catch(e){toast(e.message);button.disabled=false}
  });
}
function startupPreferences() {
  const settings=state.startup.settings||{enabled:true,allow_cloud:false};
  const d=dialog(`<form>${modalHeader('STARTUP','Ready when you open CheapOS')}<p class="modal-description">Start with an installed local model, or a configured free route through OmniRoute. A small greeting checks that it responds.</p><label class="checkbox-field"><input name="enabled" type="checkbox" ${settings.enabled?'checked':''}><span>Connect to a free model on launch</span></label><label class="checkbox-field"><input name="allow_cloud" type="checkbox" ${settings.allow_cloud?'checked':''}><span>Allow free cloud models through OmniRoute<small>Uses providers you have already set up. Project contents are sent only when you start a chat with that model.</small></span></label><p class="small muted">At most three free models are tried per connection check, with a 512-token output cap each. No paid fallback, model downloads, or provider enrollment. A saved model choice takes priority. Saving preferences makes no inference request.</p><p class="form-error" role="alert"></p><div class="modal-footer"><span>Reviewers remain under Models.</span><button type="submit" class="primary-button">Save preferences</button></div></form>`,'project-modal');
  const form=$('form',d);form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{const values=new FormData(form);await api('/startup/config',{enabled:values.has('enabled'),allow_cloud:values.has('allow_cloud')});d.close();await loadStartup()})};
}
function renderHome() {
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
  $('#composer-area').hidden=Boolean(task?.demo)||state.view!=='chat';
  $('#composer-project span').textContent=task?CheapOSGuide.projectName(task):state.project?CheapOSGuide.projectName({source:state.project.path}):'Open project';
  $('#composer-project').disabled=Boolean(task);
  $('#chat-input').disabled=state.sending;
  $('#chat-input').placeholder=state.project?'Ask about your project or describe a change…':'Open a project to get started…';
  const other=state.tasks.find(t=>t.id!==task?.id&&activeStatuses.has(t.status));
  $('#chat-send').disabled=state.sending||busy||Boolean(other)||state.startup.busy||!$('#chat-input').value.trim();
  $('#chat-stop').hidden=!busy&&!state.startup.busy;
  $('#execution-choice').textContent=executionLabel(task?(task.execution?.mode||'manual'):state.preferences.execution?.mode);
  $('#execution-choice').title=task?'This chat keeps its saved execution choice':'Choose where new chats run';
  $('#chat-budget').textContent=money((task?.limits||state.preferences.limits).dollars)+' limit';
  $('#composer-note').textContent=state.startup.busy?'Checking your free model. You can draft a message while it connects.':other?'Another chat is running. Open it in the sidebar to continue or pause it.':busy?'CheapOS is working. You can draft your next message.':task?(task.changes.length?'Continue in the same task copy. See saved edits in Changes.':'Follow up here. This chat keeps its project context.'):'Edits stay in a separate copy. You review the result.';
}
function openProject(afterOpen) {
  const d=dialog(`<form>${modalHeader('LOCAL PROJECT','Open a project')}<p class="modal-description">Choose your project once, then chat. CheapOS will work in a separate copy when you send your first message.</p><label class="full-field">Project folder<input name="repository" placeholder="/Users/you/projects/my-project" required autocomplete="off" autofocus><small>Use the root folder of a local Git repository.</small></label><p class="form-error" role="alert"></p><div class="modal-footer"><span>Opening a project makes no model request.</span><button type="submit" class="primary-button">Open project ${icon('chevron')}</button></div></form>`,'project-modal');
  const form=$('form',d);form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{const project=await api('/projects',{repository:new FormData(form).get('repository')});state.projects=await api('/projects');d.close();chooseProject(project);if(afterOpen)afterOpen()})};
}
async function selectTask(id) {
  saveDraft();const request=++state.selection;state.loading=true;
  try {const task=await api('/tasks/'+id);if(request!==state.selection)return;state.task=task;state.project={path:task.source,name:basename(task.source)};state.file=0;state.run=-1;state.view='chat';try{localStorage.setItem('cheapos-selected',id)}catch{}renderTask({resetScroll:true});restoreDraft();renderSidebar();$('#sidebar').classList.remove('show');}
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
  $('.task-heading').hidden=false;$('.tabs').hidden=false;$('#compact-session').hidden=false;$('#toggle-inspector').hidden=false;$('#inspector').classList.remove('home-hidden');
  const scroller=$('#view-container'), oldScroll=scroller.scrollTop, bottom=scroller.scrollHeight-scroller.clientHeight-oldScroll<60;
  const expanded=new Map((resetScroll?[]:$$('details[data-event]')).map(d=>[d.dataset.event,d.open]));
  const outputScroll=new Map((resetScroll?[]:$$('[data-thinking], [data-command-output]')).map(el=>[el.dataset.thinking||el.dataset.commandOutput,{top:el.scrollTop,bottom:el.scrollHeight-el.clientHeight-el.scrollTop<30}]));
  $('#task-title').textContent=task.title;$('#task-title').title=task.title;
  $('#project-name').textContent=CheapOSGuide.projectName(task);
  $('#task-status').textContent=labels[task.status]||task.status;
  $('#task-date').textContent=date(task.created_at);
  $('#task-eyebrow').classList.toggle('running',activeStatuses.has(task.status));
  $('#task-subtitle').textContent=task.demo?'Scripted models. Real edits, checks, and checkpoint reviews.':task.status==='approved'?'Review the patch, then apply it to your project when you are ready.':'Working in a separate copy of your repository.';
  $('#change-count').textContent=task.changes.length;$('#check-count').textContent=task.checks.length;
  const sums=patchTotals(task.patch);$('#diff-tally').innerHTML=`<span>+${sums.add}</span><span>−${sums.remove}</span>`;
  $('#compact-cost').textContent=money(task.usage.cost);
  $('#task-actions').innerHTML=activeStatuses.has(task.status)?`<button class="subtle-button" id="pause-task">${icon('x')}Pause</button>`:'<button class="subtle-button" id="task-overview">Details</button>';
  if($('#pause-task'))$('#pause-task').onclick=stopTask;
  if($('#task-overview'))$('#task-overview').onclick=toggleInspector;
  renderView();renderInspector();renderComposer();
  for(const d of $$('details[data-event]'))if(expanded.has(d.dataset.event))d.open=expanded.get(d.dataset.event);
  for(const el of $$('[data-thinking], [data-command-output]')){const saved=outputScroll.get(el.dataset.thinking||el.dataset.commandOutput);el.scrollTop=!saved||saved.bottom?el.scrollHeight:saved.top}
  scroller.scrollTop=resetScroll?scroller.scrollHeight:state.view==='chat'&&activeStatuses.has(task.status)&&bottom?scroller.scrollHeight:oldScroll;
}
function renderView() {
  $('#compact-session').hidden=true;
  $$('.tab').forEach(b=>{const selected=b.dataset.view===state.view;b.classList.toggle('active',selected);b.setAttribute('aria-selected',String(selected))});
  $$('.view').forEach(v=>{v.classList.toggle('hidden',v.id!==state.view+'-view');if(v.id!==state.view+'-view')v.innerHTML=''});
  if(!state.task){renderHome();return}
  if(state.view==='chat')renderChat();else if(state.view==='activity')renderActivity();else if(state.view==='changes')renderChanges();else renderTests();
}
function eventDetail(event) {
  const detail=event.detail;
  if(event.kind==='tool'){
    const result=detail?.result,args=detail?.arguments||{};
    if(event.title==='read url')return `<p>${sourceLink(result.source_url,'Open source page')} · Read ${esc(result.fetched_at)}</p><pre class="output">${esc(result.content)}</pre><p class="muted">${result.has_more?'More lines are available. ':''}${result.truncated||result.excerpt_truncated?'Document preview was shortened. ':''}External source text.</p>`;
    if(event.title==='read file')return `<pre class="output">${esc(result?.content||'No content returned.')}</pre>`;
    if(['write file','replace text'].includes(event.title))return `<p>Saved ${esc(args.path)} in the task copy.</p>`;
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
  return `<section class="request-progress ${task.stream&&task.stream.phase!=='waiting'?'is-streaming':''}" aria-label="Current activity"><div class="request-progress-heading"><span class="spinner"></span><strong id="request-stage">${esc(p.title)}</strong><span id="request-elapsed" aria-label="Time in current step">${p.elapsed}</span></div><div class="request-model" id="request-detail">${esc(p.detail)}</div><p class="request-hint" id="request-hint">${esc(p.hint)}</p><div class="request-evidence"><span>${icon('code')}${esc(p.action)}</span><span>${icon('file')}${esc(p.evidence)}</span></div><div class="request-actions"><button class="text-link" data-chat-action="activity">${state.view==='activity'?'View live chat':'View activity'}</button><button class="subtle-button" data-chat-action="stop" ${p.stage==='stopping'?'disabled':''}>${p.stage==='stopping'?'Stopping…':'Stop'}</button></div></section>`;
}
function updateProgressClock() {
  if(!state.task||!$('#request-elapsed'))return;
  const p=CheapOSGuide.progress(state.task);if(!p)return;
  $('#request-stage').textContent=p.title;$('#request-detail').textContent=p.detail;$('#request-elapsed').textContent=p.elapsed;$('#request-hint').textContent=p.hint;
  $('.request-progress').classList.toggle('slow',p.slow);
}
async function stopTask() {
  try{await api('/tasks/'+state.task.id+'/stop',{});await refresh()}catch(e){toast(e.message)}
}
function thinkingMarkup(detail,live=false) {
  if(!detail.thinking)return '';
  const key='generation-'+detail.request_id;
  return `<details class="thinking-panel ${live?'is-live':''}" data-event="${key}" ${live?'open':''}><summary>${icon('spark')}<strong>${detail.interrupted?'Thinking · interrupted':'Thinking'}</strong><span>${live?'Live':esc(detail.model)}</span>${icon('chevron')}</summary><div class="thinking-output" data-thinking="${key}">${esc(detail.thinking)}</div>${detail.truncated?'<p class="thinking-note">Showing the first 16,000 characters.</p>':''}</details>`;
}
function commandMarkup(check,{live=false,open=false,key=check.run_id}={}) {
  const status=live?'Running check':check.passed?'Check passed':check.reason==='cancelled'?'Check stopped':'Check failed';
  return `<details class="command-panel ${live?'is-live':check.passed?'passed':'failed'}" data-event="command-${esc(key)}" ${live||open?'open':''}><summary>${live?'<span class="spinner"></span>':icon(check.passed?'check':'x')}<strong>${status}</strong><span>${live?'Live output':`Exit ${check.exit_code??'—'} · ${Number(check.duration||0).toFixed(1)}s`}</span>${icon('chevron')}</summary><code class="command-line">${esc(check.command.join(' '))}</code><div class="command-body"><pre class="command-output" tabindex="0" data-command-output="command-${esc(key)}" aria-label="${live?'Live command output':'Command output'}">${esc(check.output||(live?'Waiting for command output…':'(No output)'))}</pre>${check.truncated?'<p class="command-note">Showing the first 32 KB of output.</p>':''}${check.reason?`<p class="command-note">${esc(check.reason)}</p>`:''}</div></details>`;
}
function renderChat() {
  const task=state.task,guide=CheapOSGuide.taskGuide(task),failure=task.status==='error'?CheapOSGuide.failure(task):null;
  const message=(role,text)=>`<article class="chat-message ${role==='You'?'from-user':'from-agent'}"><div class="chat-author">${role==='You'?'<span class="mini-avatar">Y</span>':icon(role==='Review'?'spark':'code')}<strong>${role}</strong></div><div class="chat-message-body">${messageText(text)}</div></article>`;
  const parts=[task.demo?'<div class="demo-banner">Local demo · scripted models, real edits and checks</div>':'',message('You',task.prompt)];
  const lastUser=task.events.reduce((index,e,i)=>e.kind==='user'?i:index,-1);
  const latestCheck=task.events.slice(lastUser+1).filter(e=>e.kind==='checks').at(-1);
  const visibleRuns=new Set(task.events.filter(e=>e.kind==='checks').map(e=>e.detail.run_id).filter(Boolean));
  if(task.check_stream)visibleRuns.add(task.check_stream.run_id);
  let work=[];
  const flush=()=>{
    if(!work.length)return;
    const actions=work.filter(e=>['tool','checks','tool_error','web'].includes(e.kind));
    for(const event of actions){
      if(event.kind==='checks'){parts.push(commandMarkup(event.detail,{key:event.detail.run_id||event.id,open:event===latestCheck}));continue}
      if(event.title==='Running verification'&&visibleRuns.has(event.detail?.run_id))continue;
      const item=CheapOSGuide.activityItem(event)||{title:'Started check',icon:'tests',note:(event.detail?.command||[]).join(' ')};
      parts.push(`<details class="chat-action ${item.failed?'failed':''}" data-event="action-${event.id}"><summary>${icon(item.icon)}<span><strong>${esc(item.title)}</strong>${item.note?`<small>${esc(item.note)}</small>`:''}</span>${icon('chevron')}</summary><div class="detail-body">${eventDetail(event)}</div></details>`);
    }
    work=[];
  };
  for(const event of task.events){
    if(event.kind==='guard'&&task.status==='paused'&&event.detail===task.error)continue;
    if(['user','assistant','review','checkpoint','generation','handoff','guard','routing','commit'].includes(event.kind)){
      flush();
      if(['handoff','guard','routing','commit'].includes(event.kind)){const item=CheapOSGuide.activityItem(event);parts.push(`<aside class="chat-handoff">${icon(item.icon)}<div><strong>${esc(item.title)}</strong><p>${esc(item.note)}</p>${event.kind==='handoff'?`<small>${esc(event.detail.summary)}</small>`:''}</div></aside>`)}
      else if(event.kind==='user'||event.kind==='assistant')parts.push(message(event.kind==='user'?'You':'CheapOS',event.detail));
      else if(event.kind==='generation'){parts.push(thinkingMarkup(event.detail));if(event.detail.interrupted&&event.detail.content)parts.push(`<div class="partial-response"><span>Partial response · interrupted</span>${messageText(event.detail.content)}</div>`)}
      else if(event.kind==='checkpoint')parts.push(message('CheapOS',event.detail.worker_summary));
      else parts.push(message('Review',event.detail.feedback));
    }else work.push(event);
  }
  flush();
  const streamedOutput=task.stream?thinkingMarkup(task.stream,true)+(task.stream.content?`<article class="chat-message from-agent streaming-answer"><div class="chat-author">${icon('code')}<strong>CheapOS</strong><span>Writing…</span></div><div class="chat-message-body">${messageText(task.stream.content)}</div></article>`:''):'';
  const button=(action,label,primary=false)=>`<button class="${primary?'primary-button':'subtle-button'}" data-chat-action="${action}">${label}</button>`;
  const routeFailures=task.error_code==='routing_unavailable'?(task.route?.failures||[]):[];
  const errorDetails=routeFailures.length?`<details class="chat-error"><summary>Model check results (${routeFailures.length})</summary>${routeFailures.map(f=>`<p><strong>${esc(f.model)}</strong><br>${esc(f.error)}</p>`).join('')}</details>`:task.error&&task.error!==(failure?.description||guide.description)?`<details class="chat-error"><summary>Details</summary><p>${esc(task.error)}</p></details>`:'';
  if(task.pending_approval)parts.push(`<section class="chat-decision"><strong>Can I run this check?</strong><code class="approval-command">${esc(task.pending_approval.command.join(' '))}</code><p>Runs in this chat’s task copy. Session permission remembers this exact command until CheapOS restarts.</p><div class="button-row">${button('approve','Run once',true)}${button('approve-session','Allow for this session')}${button('decline','Decline')}</div></section>`);
  else if(activeStatuses.has(task.status))parts.push(progressMarkup(task),streamedOutput,task.check_stream?commandMarkup(task.check_stream,{live:true}):'');
  else if(task.status==='ready')parts.push(`<div class="chat-decision"><p>Your message is saved and ready to send.</p>${button('start','Send to CheapOS',true)}</div>`);
  else if(['approved','completed'].includes(task.status))parts.push(`<section class="chat-result">${icon('check')}<div><strong>${task.status==='approved'?'Changes are ready to review.':'Implementation finished. Your review is next.'}</strong><p>${task.changes.length} changed files · ${task.checks.at(-1)?.passed?'Latest checks passed':'Check the verification output'}</p><div class="button-row">${button('changes','Review changes',true)}${CheapOSGuide.canCommit(task)?button('commit','Apply & commit'):''}<a class="subtle-button" href="/api/tasks/${task.id}/patch" download>Export patch</a></div></div></section>`);
  else if(task.status==='awaiting_reply'&&task.changes.length)parts.push(`<div class="chat-saved">${icon('file')}<span>${task.changes.length} changed files saved in this chat.</span>${button('changes','View changes')}${CheapOSGuide.canCommit(task)?button('commit','Apply & commit',true):''}</div>`);
  else if(task.status!=='awaiting_reply')parts.push(`<section class="chat-decision"><strong>${esc(failure?.title||guide.title)}</strong><p>${esc(failure?.description||guide.description)}</p>${errorDetails}<div class="button-row">${button(task.status==='error'?'start':'resume',task.status==='error'?'Retry':task.status==='takeover_requested'?'Review takeover request':task.status==='budget_paused'?(task.error_code==='worker_turn_limit'?'Review turn limit':'Review limits'):'Resume',true)}${task.status==='error'||task.error_code==='routing_unavailable'?button('connections','Model settings'):''}${task.changes.length?button('changes','View changes'):''}</div></section>`);
  $('#chat-view').innerHTML=parts.join('');updateProgressClock();
  $$('[data-chat-action]').forEach(b=>b.onclick=async()=>{
    const action=b.dataset.chatAction;
    if(action==='changes'||action==='activity'){setView(action);return}
    if(action==='stop'){await stopTask();return}
    if(action==='connections'){openConnections(undefined,task);return}
    if(action==='commit'){await openCommit(b);return}
    if(action==='resume'){await resumeTask(b);return}
    b.disabled=true;
    if(action==='start'){await startTask(task.id);b.disabled=false;return}
    try{await api('/tasks/'+task.id+'/approval',{approved:action!=='decline',remember:action==='approve-session',approval_id:task.pending_approval.id});await refresh()}catch(e){toast(e.message);b.disabled=false}
  });
}
function renderActivity() {
  const task=state.task,a=CheapOSGuide.activity(task),guide=CheapOSGuide.taskGuide(task),failure=task.status==='error'?CheapOSGuide.failure(task):null;
  const action=(view,label)=>`<button class="outline-button" data-activity-view="${view}">${label}</button>`;
  const timeline=a.items.slice(0,40).map(item=>`<details class="activity-step ${item.failed?'failed':''}" data-event="step-${item.event.id}"><summary><span class="step-icon">${icon(item.icon)}</span><span><strong>${esc(item.title)}</strong>${item.note?`<small>${esc(item.note)}</small>`:''}</span><time>${new Date(item.event.time).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</time>${icon('chevron')}</summary><div class="step-body">${eventDetail(item.event)}${item.path&&task.changes.some(c=>c.path===item.path)?`<button class="text-link" data-activity-file="${esc(item.path)}">View current diff →</button>`:''}</div></details>`).join('');
  const technical=task.events.map(e=>`<details class="activity-card" data-event="raw-${e.id}"><summary><strong>${esc(CheapOSGuide.activityItem(e)?.title||e.title)}</strong>${icon('chevron')}</summary><div class="detail-body">${eventDetail(e)}</div></details>`).join('');
  const status=task.pending_approval?`<section class="chat-decision"><strong>Waiting for your approval</strong><code class="approval-command">${esc(task.pending_approval.command.join(' '))}</code><p>Runs in this chat’s task copy. Session permission remembers this exact command until CheapOS restarts.</p><div class="button-row"><button class="primary-button" data-activity-approve="true">Run once</button><button class="outline-button" data-activity-approve="session">Allow for this session</button><button class="subtle-button" data-activity-approve="false">Decline & pause</button></div></section>`:activeStatuses.has(task.status)?progressMarkup(task):`<section class="activity-status"><span class="activity-eyebrow">${['approved','completed'].includes(task.status)?'RESULT':'CURRENT STATUS'}</span><h3>${esc(failure?.title||guide.title)}</h3><p>${esc(failure?.description||guide.description)}</p>${task.error&&task.error!==guide.description?`<p>${esc(task.error)}</p>`:''}<div class="button-row">${['approved','completed'].includes(task.status)?action('changes','Review changes'):''}${action('chat','Back to chat')}${['paused','budget_paused','interrupted','error','takeover_requested'].includes(task.status)?`<button class="outline-button" id="activity-resume">${task.status==='error'?'Retry':guide.primaryLabel}</button>`:''}${task.error_code==='routing_unavailable'?'<button class="outline-button" id="activity-models">Models</button>':''}</div></section>`;
  $('#activity-view').innerHTML=`<div class="view-title"><div><h2>What’s happening</h2><p>${task.demo?'Scripted demo · real files and checks':'Real actions and saved results from this chat.'}</p></div></div>${status}${task.check_stream?commandMarkup(task.check_stream,{live:true}):''}<div class="activity-facts"><button data-activity-view="changes"><span>Saved changes · whole chat</span><strong>${a.files} file${a.files===1?'':'s'}</strong><small>Inspect the diff →</small></button><button data-activity-view="tests"><span>Checks · this request</span><strong>${esc(a.checks)}</strong><small>View command output →</small></button><button id="activity-review" ${!a.checkpoint?'disabled':''}><span>Review · this request</span><strong>${esc(a.review)}</strong><small>${a.checkpoint?'Inspect the decision →':'A passing check alone is not approval'}</small></button></div><section class="activity-timeline"><h3>Latest request</h3><p class="activity-request">${esc(a.request)}</p><p class="small muted">Newest actions first${a.items.length>40?' · showing the latest 40':''}</p>${timeline||'<p class="activity-empty">No file actions yet. Conversation and live model output are in Chat.</p>'}</section><details class="technical-log" data-event="technical"><summary>${icon('code')}Technical log <span>${task.events.length} events</span>${icon('chevron')}</summary><div>${technical}</div></details>`;
  $$('[data-activity-view]').forEach(b=>b.onclick=()=>setView(b.dataset.activityView));
  $$('[data-chat-action]').forEach(b=>b.onclick=()=>b.dataset.chatAction==='stop'?stopTask():setView('chat'));
  $$('[data-activity-file]').forEach(b=>b.onclick=()=>{state.file=task.changes.findIndex(c=>c.path===b.dataset.activityFile);setView('changes')});
  $$('[data-activity-approve]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await api('/tasks/'+task.id+'/approval',{approved:b.dataset.activityApprove!=='false',remember:b.dataset.activityApprove==='session',approval_id:task.pending_approval.id});await refresh()}catch(e){toast(e.message);b.disabled=false}});
  $$('[data-checkpoint]').forEach(b=>b.onclick=()=>checkpointDialog(Number(b.dataset.checkpoint)));
  $('#activity-review').onclick=()=>a.checkpoint&&checkpointDialog(a.checkpoint.number);
  if($('#activity-resume'))$('#activity-resume').onclick=e=>resumeTask(e.currentTarget);
  if($('#activity-models'))$('#activity-models').onclick=openConnections;
  updateProgressClock();
}
function checkpointDialog(number) {
  const checkpoint=state.task.checkpoints.find(c=>c.number===number);if(!checkpoint)return;
  dialog(`${modalHeader('REVIEW EVIDENCE','Checkpoint #'+number)}<p class="modal-description">This is the evidence captured for this review. The reviewer can also read the current workspace.</p><div class="checkpoint-section"><h3>Original task</h3><p>${esc(checkpoint.original_task)}</p></div><div class="checkpoint-section"><h3>Worker summary</h3><p>${esc(checkpoint.worker_summary)}</p><p>${esc(checkpoint.uncertainties)}</p></div><div class="checkpoint-section"><h3>Verification</h3><pre>${esc(checkpoint.checks.output)}</pre></div><div class="checkpoint-section"><h3>Patch at this checkpoint</h3><pre>${esc(checkpoint.diff)}</pre></div><div class="checkpoint-section"><h3>${esc(checkpoint.decision)}</h3><p>${esc(checkpoint.feedback)}</p></div>`,'checkpoint-modal');
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
  $('#changes-view').innerHTML=`<div class="view-title"><div><h2>Review the work.</h2><p>${files.length} changed files in the task copy</p></div><div class="button-row"><a class="subtle-button" href="/api/tasks/${task.id}/patch" download>${icon('file')}Export patch</a>${CheapOSGuide.canCommit(task)?'<button class="primary-button" id="apply-commit">Apply & commit</button>':''}</div></div><div class="file-list">${files.map((f,i)=>`<button class="file-item ${i===state.file?'selected':''}" data-file="${i}">${icon('file')}<span>${esc(f.path)}</span><span class="file-status">${f.before?'M':'A'}</span></button>`).join('')}</div><div class="diff-panel"><div class="diff-toolbar"><span>${icon('file')}${esc(file.path)}</span><div class="segmented"><button data-diff="unified" class="${state.diff==='unified'?'selected':''}">Unified</button><button data-diff="split" class="${state.diff==='split'?'selected':''}">Split</button></div></div>${file.binary?'<p class="modal-description">Binary change. Inspect the exported Git patch.</p>':state.diff==='unified'?`<div class="diff-code" tabindex="0" aria-label="Unified code diff">${rows.map(line).join('')}</div>`:`<div class="split-diff">${['before','after'].map(side=>`<div class="diff-code" tabindex="0" aria-label="${side==='before'?'Original':'Modified'} file"><div class="split-label">${side==='before'?'Before':'After'}</div>${rows.filter(r=>r.type!==(side==='before'?'add':'remove')).map(r=>`<div class="diff-line ${r.type}"><span class="line-number">${side==='before'?r.old:r.new}</span><span class="source">${esc(r.text)||' '}</span></div>`).join('')}</div>`).join('')}</div>`}</div><div class="diff-bottom">${icon('shield')}${CheapOSGuide.canCommit(task)?'Ready for your approval. Apply & commit will update your project and create a local Git commit.':'Edits are saved in the task copy. Finish verification and review to enable Apply & commit.'}</div><details class="patch-help"><summary>Apply manually instead</summary><p>From your original repository, check the downloaded patch first, then apply it:</p><pre>git apply --check /path/to/cheapos-${task.id.slice(0,8)}.patch\ngit apply /path/to/cheapos-${task.id.slice(0,8)}.patch</pre><p>For large files, the visual comparison shows whole blocks; the exported Git patch preserves the exact change, including file modes and final newlines.</p></details>`;
  if($('#apply-commit'))$('#apply-commit').onclick=e=>openCommit(e.currentTarget);
  $$('[data-file]').forEach(b=>b.onclick=()=>{state.file=Number(b.dataset.file);renderChanges()});$$('[data-diff]').forEach(b=>b.onclick=()=>{state.diff=b.dataset.diff;renderChanges()});
}
async function openCommit(trigger) {
  const task=state.task;if(!task)return;
  if(trigger){trigger.disabled=true;trigger.textContent='Checking project…'}
  try {
    const preview=await api('/tasks/'+task.id+'/commit-preview',{});
    const d=dialog(`<form>${modalHeader('YOUR APPROVAL',preview.retry?'Finish the saved commit.':'Apply these changes & commit?')}<p class="modal-description">${esc(preview.review)} · task-copy checks passed. Approving updates your local project and creates one commit.</p><dl class="commit-target"><div><dt>Project</dt><dd>${esc(preview.source)}</dd></div><div><dt>Branch</dt><dd>${esc(preview.branch)} <span class="muted">at ${esc(preview.head.slice(0,8))}</span></dd></div></dl><label>Commit message<textarea name="message" rows="3" maxlength="2000" required ${preview.retry?'readonly':''}>${esc(preview.message)}</textarea></label><details class="commit-patch" open><summary>Review the exact patch · ${preview.files.length} files</summary><pre tabindex="0" aria-label="Patch to apply">${esc(preview.patch)}</pre></details><p class="form-error" role="alert"></p><div class="modal-footer"><span>Local commit · pushing is separate</span><div class="button-row"><button type="button" class="subtle-button" data-close>Cancel</button><button type="submit" class="primary-button">${preview.retry?'Approve & finish commit':'Approve & commit'}</button></div></div></form>`,'commit-modal');
    const form=$('form',d);let committing=false;
    d.addEventListener('cancel',e=>{if(committing)e.preventDefault()});
    form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{
      committing=true;const submit=$('button[type="submit"]',form);submit.textContent='Applying & committing…';$$('[data-close]',d).forEach(b=>b.disabled=true);
      try {
        const result=await api('/tasks/'+task.id+'/commit',{approved:true,approval_id:preview.approval_id,message:new FormData(form).get('message')});
        d.close();await refresh();toast('Committed '+result.commit.slice(0,8)+' to '+result.branch);
      } finally {committing=false;submit.textContent='Approve & commit';$$('[data-close]',d).forEach(b=>b.disabled=false)}
    })};
  } catch(e) {
    dialog(`${modalHeader('APPLY & COMMIT','Your edits are saved.')}<p class="modal-description">${esc(e.message)}</p><div class="modal-footer"><span>Resolve this, then reopen Apply & commit.</span><button class="primary-button" data-close>Got it</button></div>`);
  } finally {if(trigger){trigger.disabled=false;trigger.textContent='Apply & commit'}}
}
function renderTests() {
  const checks=state.task.checks;
  if(!checks.length){$('#tests-view').innerHTML='<div class="empty-state">'+icon('tests')+'<h2>No checks run yet.</h2><p>The configured verification command will run in the task copy. Results appear here.</p></div>';return}
  const index=state.run<0?checks.length-1:Math.min(state.run,checks.length-1),check=checks[index];
  $('#tests-view').innerHTML=`<div class="view-title"><div><h2>Evidence, before approval.</h2><p>Actual output from your configured command</p></div></div><div class="test-run-picker"><span>Verification history</span><select id="run-picker" aria-label="Verification run">${checks.map((c,i)=>`<option value="${i}" ${i===index?'selected':''}>Run ${i+1} · ${c.passed?'Passed':'Failed'}</option>`).join('')}</select></div><div class="test-summary ${check.passed?'':'failure'}">${icon(check.passed?'check':'x')}<strong>${check.passed?'Command passed':'Command failed'}</strong><span>Exit ${check.exit_code} · ${check.duration.toFixed(2)}s</span></div><code class="check-command">${esc(check.command.join(' '))}</code>${check.reason?`<p class="form-error">${esc(check.reason)}</p>`:''}<pre class="output test-output">${esc(check.output||'(No output)')}</pre><p class="muted small">Passed means this command exited successfully. The reviewer still checks whether the implementation satisfies the task.</p>`;
  $('#run-picker').onchange=e=>{state.run=Number(e.target.value);renderTests()};
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
function limitFields(limits={dollars:1,reviewer_tokens:50000,iterations:5,worker_turns:40,output_tokens:2048}) {
  return `<div class="field-grid">${numberField('dollars','Estimated spending cap ($)',limits.dollars,0,100,'0.01')}${numberField('reviewer_tokens','Reviewer token limit',limits.reviewer_tokens,512,1000000)}</div><details class="advanced"><summary>Advanced limits</summary><div class="field-grid">${numberField('iterations','Max worker iterations',limits.iterations,1,20)}${numberField('worker_turns','Worker turns per request',limits.worker_turns,1,200)}${numberField('output_tokens','Output tokens per request',limits.output_tokens,128,16384)}${numberField('checkpoint_turns','Turns before a checkpoint pause',limits.checkpoint_turns??12,2,200)}${numberField('run_minutes','Minutes per run (excludes approval waits)',limits.run_minutes??15,1,720)}</div></details>`;
}
const readLimits=f=>Object.fromEntries(['dollars','reviewer_tokens','iterations','worker_turns','output_tokens','checkpoint_turns','run_minutes'].map(k=>[k,Number(f.get(k))]));
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
  ].map(([value,title,description])=>`<label class="execution-option"><input type="radio" name="mode" value="${value}" ${(saved.mode||'manual')===value?'checked':''}><span><strong>${title}</strong><small>${description}</small></span></label>`).join('')}</div><div id="execution-local"><label class="full-field">Installed Ollama model<input name="local_model" value="${esc(saved.local_model||local)}" placeholder="Your installed model ID" autocomplete="off"><small>Used for short chat in Delegate mode, and implementation in All local.</small></label><label class="full-field" id="execution-reviewer">Local reviewer model · optional<input name="local_reviewer" value="${esc(saved.local_reviewer||'')}" placeholder="Use the same local model" autocomplete="off"></label></div><p id="execution-remote" class="execution-notice">Uses providers you enabled in OmniRoute. Project context is sent when work is handed off. CheapOS checks up to four free candidates per role without project data. A worker handles chat and edits; a different reviewer is selected at a checkpoint. Saved edits wait if review is unavailable. No automatic paid or local fallback.</p><p class="small muted">Free routing uses advertised prices. Check OmniRoute’s fallback and billing settings. Existing chats retain their models. Saving does not start inference or download anything.</p><p class="form-error" role="alert"></p><div class="modal-footer"><span>Applies to new chats.</span><button class="primary-button" type="submit">Save execution choice</button></div></form>`,'execution-modal');
  const form=$('form',d),layout=()=>{const mode=new FormData(form).get('mode');$('#execution-local',d).hidden=!['local','delegate'].includes(mode);$('#execution-reviewer',d).hidden=mode!=='local';$('#execution-remote',d).hidden=!['remote','delegate'].includes(mode);$('[name="local_model"]',d).required=['local','delegate'].includes(mode)};
  $$('[name="mode"]',d).forEach(input=>input.onchange=layout);layout();
  form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{const f=new FormData(form);state.preferences=await api('/preferences',{execution:Object.fromEntries(['mode','local_model','local_reviewer'].map(k=>[k,String(f.get(k)||'')]))});d.close();renderComposer();toast('Execution choice saved for new chats.');})};
}
function chatLimits() {
  const task=state.task,limits=task?.limits||state.preferences.limits;
  const d=dialog(`<form>${modalHeader('SPENDING & LIMITS',task?'Limits for this chat':'Defaults for new chats')}<p class="modal-description">CheapOS uses the saved models and stops at these limits. A zero-dollar cap is intended for local or free models.</p>${limitFields(limits)}<p class="small muted">${task?'Usage is cumulative across this chat. Saving does not resume it.':'These defaults apply when you send the first message in a new chat.'}</p><p class="form-error" role="alert"></p><div class="modal-footer"><span>Cost estimates use your configured prices.</span><button class="primary-button" type="submit">Save limits</button></div></form>`);
  const form=$('form',d);form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{const limits=readLimits(new FormData(form));if(task){state.task=await api('/tasks/'+task.id+'/limits',{limits})}else state.preferences=await api('/preferences',{limits});d.close();renderComposer();if(state.task)renderInspector()})};
}
async function sendChat() {
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
async function startTask(id,changes={}) {try{await api('/tasks/'+id+'/start',changes);await refresh()}catch(e){toast(e.message)}}
async function resumeTask(button) {
  const task=state.task;if(!task)return;
  if(['budget_paused','takeover_requested'].includes(task.status)){resumeDialog();return}
  if(button)button.disabled=true;
  try{await startTask(task.id)}finally{if(button)button.disabled=false}
}
function resumeDialog() {
  const task=state.task,takeover=task.status==='takeover_requested',turnLimit=task.error_code==='worker_turn_limit';
  const used=task.request_worker_turns??task.worker_turns;
  const fields=turnLimit?numberField('worker_turns','Worker turns allowed for this request',Math.min(200,Math.max(task.limits.worker_turns,used+10)),1,200):limitFields(task.limits);
  const d=dialog(`<form>${modalHeader(takeover?'REVIEWER TAKEOVER':turnLimit?'WORKER TURNS':'TASK LIMITS',takeover?'Let the reviewer take over?':turnLimit?'Continue this request?':'Continue from saved work.')}<p class="modal-description">${takeover?'The reviewer will implement changes using the same task budget. You will review its final patch.':turnLimit?`${used} worker turns used on this request. Choose a higher allowance to continue from saved work. Your ${money(task.limits.dollars)} spending cap stays unchanged.`:`Usage already counted: ${money(task.usage.cost)}. Resuming keeps your saved edits and accounting.`}</p>${fields}<p class="small muted">${turnLimit?'New messages get their own worker-turn allowance. Resume keeps the turns already used. Costs and token usage remain cumulative.':'A stopped or failed provider request may still be billable. Its reservation stays counted. A resumed task uses its original model settings; updated keys from Connections are available.'}</p><p class="form-error" role="alert"></p><div class="modal-footer"><span>Source project stays separate.</span><button type="submit" class="primary-button">${takeover?'Approve takeover':'Save limits & resume'} ${icon('play')}</button></div></form>`);
  const form=$('form',d);form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{const f=new FormData(form),limits=turnLimit?{...task.limits,worker_turns:Number(f.get('worker_turns'))}:readLimits(f);if(turnLimit&&limits.worker_turns<=used)throw new Error('Choose an allowance above the turns already used.');await api('/tasks/'+task.id+'/start',{limits,approve_takeover:takeover});d.close();await refresh()})};
}
async function sessionPermissions() {
  const task=state.task;if(!task)return;
  try {
    const permissions=await api('/tasks/'+task.id+'/permissions');
    const d=dialog(`${modalHeader('SESSION PERMISSIONS','Commands you’ve allowed')}<p class="modal-description">These exact commands may repeat in this chat’s task copy, including after Pause and Resume. Different commands ask again. Permissions expire when CheapOS restarts.</p>${permissions.commands.length?permissions.commands.map(command=>`<code class="approval-command">${esc(command.join(' '))}</code>`).join(''):'<p>No commands are remembered for this session.</p>'}<p class="small muted">Clearing permissions makes future runs ask again; commands already running continue.</p><p class="form-error" role="alert"></p><div class="modal-footer"><span>Applies only to this chat.</span>${permissions.commands.length?'<button class="outline-button" id="clear-session-permissions">Clear permissions</button>':''}</div>`);
    const clear=$('#clear-session-permissions',d);
    if(clear)clear.onclick=async()=>{clear.disabled=true;try{await api('/tasks/'+task.id+'/permissions',{clear:true});d.close();toast('Session permissions cleared. Future commands will ask again.')}catch(e){$('.form-error',d).textContent=e.message;clear.disabled=false}};
  }catch(e){toast(e.message)}
}
async function startDemo() {
  if(!state.online){toast('The local server is unavailable. Start it with python3 run.py');return}
  try{const task=await api('/demo',{});await loadTasks();await selectTask(task.id);await startTask(task.id)}catch(e){toast(e.message)}
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
  const d=dialog(`${modalHeader('MODEL CONNECTIONS','Choose where the work runs.')}<button class="outline-button" id="models-execution">Execution: ${esc(executionLabel(state.preferences.execution?.mode))} →</button><p class="modal-description">OmniRoute handles provider access. CheapOS handles the work, checks, and review.</p>${taskContext?`<div class="connection-context"><strong>Checking a stopped task</strong><p>Worker: <b>${esc(taskContext.providers.worker?.model||'not set')}</b><br>Reviewer: <b>${esc(taskContext.providers.reviewer?.model||'not set')}</b><br>To fix access and retry the same models, update the gateway and return to Retry options. To try different models, choose them below and prepare a fresh task.</p></div>`:''}
    <form class="gateway-card" id="gateway-form"><div class="gateway-heading"><div><strong>OmniRoute</strong><span class="gateway-badge" id="gateway-status" role="status"></span></div><a id="gateway-dashboard" class="subtle-button" href="${esc(gateway.dashboard_url||'http://127.0.0.1:20128')}" target="_blank" rel="noopener noreferrer">Open OmniRoute ↗</a></div>
      <p id="gateway-message" class="small muted"></p><p id="gateway-instance" class="small muted"></p>
      <div class="gateway-actions"><button type="button" class="outline-button" data-gateway-action="start">Connect / start</button><button type="button" class="subtle-button" data-gateway-action="refresh">Refresh models</button><button type="button" class="subtle-button" data-gateway-action="stop" hidden>Stop instance</button></div>
      <details class="advanced"><summary>Startup & connection settings</summary><label class="full-field">Local API URL<input name="gateway_url" type="url" value="${esc(settings.base_url)}" required></label>
        <label class="full-field">Gateway client API key · optional<input name="gateway_key" type="password" placeholder="${gateway.key_configured?'Configured · leave blank to keep':'Only if OmniRoute requires a client key'}" autocomplete="new-password"></label>
        <p class="small muted">Manage provider credentials in OmniRoute. This client key is separate from your dashboard password and stays in CheapOS memory.</p>
        <label class="checkbox-field"><input name="auto_start" type="checkbox" ${settings.auto_start?'checked':''}><span>Start installed OmniRoute when CheapOS launches<small>Reuses an existing instance. Does not install or update software.</small></span></label>
        <label class="checkbox-field"><input name="keep_running" type="checkbox" ${settings.keep_running?'checked':''}><span>Keep OmniRoute running when CheapOS closes<small>CheapOS only stops an instance it started in this session.</small></span></label>
        <button class="outline-button gateway-save" type="submit">Save gateway settings</button></details><p class="form-error" role="alert"></p></form>
    <form id="models-form"><details class="advanced" ${(state.preferences.execution?.mode||'manual')==='manual'?'open':''}><summary>Explicit model choices · Manual mode and remote preferences</summary><div class="provider-grid">${providerFields('worker')}${providerFields('reviewer')}</div>
      <p class="small muted">Catalog connection and advertised tool support do not guarantee a successful model run. These explicit choices apply in Manual mode. Automatic remote modes prefer eligible choices here, check free candidates, and pin the selected pair for that chat.</p>
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
function openSearch() {
  const d=dialog(`<div class="search-box">${icon('search')}<input id="task-search" type="search" placeholder="Find a task or project…" aria-label="Search tasks" autofocus><kbd>ESC</kbd></div><div id="search-results"></div><div class="search-footer">Saved on this computer</div>`,'search-modal');
  const render=(q='')=>{const found=state.tasks.filter(t=>(t.title+' '+t.source).toLowerCase().includes(q.toLowerCase()));$('#search-results',d).innerHTML=found.length?found.map(t=>`<button class="search-result" data-result="${t.id}">${icon('chat')}<span><strong>${esc(t.title)}</strong><small>${esc(t.demo?'Local demo':basename(t.source))} · ${esc(labels[t.status])}</small></span>${icon('chevron')}</button>`).join(''):'<div class="no-results">No matching tasks.</div>';$$('[data-result]',d).forEach(b=>b.onclick=()=>{d.close();selectTask(b.dataset.result)})};$('#task-search',d).oninput=e=>render(e.target.value);render();
}
async function loadTasks() {const tasks=await api('/tasks');const changed=JSON.stringify(tasks)!==JSON.stringify(state.tasks);state.tasks=tasks;if(changed){renderSidebar();renderComposer();if(!state.task)renderHome()}}
async function refresh() {
  if(state.loading)return;
  await loadStartup();await loadGateway();await loadTasks();const selected=state.task?.id;if(!selected)return;
  const task=await api('/tasks/'+selected);if(state.task?.id!==selected)return;
  if(task.updated_at!==state.task.updated_at||task.status!==state.task.status){state.task=task;renderTask()}
}
async function bootstrap() {
  try {const data=await api('/bootstrap');state.token=data.token;state.config=data.config;state.gateway=data.gateway||{};state.startup=data.startup||{};state.tasks=data.tasks;state.projects=data.projects||[];state.preferences=data.preferences||state.preferences;try{const path=localStorage.getItem('cheapos-project');state.project=state.projects.find(p=>p.path===path)||null}catch{}state.online=true;renderSidebar();let selected;try{selected=localStorage.getItem('cheapos-selected')}catch{}let freshStartup=false;try{freshStartup=Boolean(state.startup.started_at)&&localStorage.getItem('cheapos-startup-session')!==state.startup.session_id;localStorage.setItem('cheapos-startup-session',state.startup.session_id||'')}catch{}if(!freshStartup&&state.tasks.some(t=>t.id===selected))await selectTask(selected);else home();}
  catch(e){state.online=false;$('#chat-view').innerHTML='<div class="empty-state"><h2>Start CheapOS locally.</h2><p>Run <code>python3 run.py</code> in the project directory, then refresh this page. No sign-in is needed.</p></div>';renderInspector()}
}
async function poll() {try{if(state.online)await refresh()}catch(e){toast('Local server disconnected. Restart CheapOS and refresh to reconnect.');state.online=false}finally{setTimeout(poll,1500)}}
$$('.tab').forEach(b=>b.onclick=()=>setView(b.dataset.view));
$('#home-trigger').onclick=()=>openProject();$('.brand').onclick=e=>{e.preventDefault();home()};$('#new-task').onclick=()=>newTask();$('#search-trigger').onclick=openSearch;$('#settings-trigger').onclick=()=>openConnections();$('#session-settings').onclick=()=>openConnections();$('#demo-trigger').onclick=startDemo;$('#composer-project').onclick=()=>openProject();$('#chat-budget').onclick=chatLimits;$('#execution-choice').onclick=executionPreferences;$('#chat-input').oninput=()=>{saveDraft();renderComposer()};$('#chat-form').onsubmit=e=>{e.preventDefault();sendChat()};$('#chat-input').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();sendChat()}};$('#chat-stop').onclick=async()=>{if(state.startup.busy){try{await api('/startup/stop',{});await loadStartup()}catch(e){toast(e.message)}}else await stopTask()};
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
