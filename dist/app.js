'use strict';
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
const activeStatuses = new Set(['running', 'reviewing', 'waiting_approval', 'stopping']);
const labels = {ready:'Ready to start',running:'Worker is working',reviewing:'Reviewer is checking',waiting_approval:'Command approval needed',paused:'Paused',budget_paused:'Paused at a limit',interrupted:'Interrupted',error:'Needs attention',takeover_requested:'Takeover requested',approved:'Reviewer approved',completed:'Ready for your review'};
const state = {token:'',config:{},tasks:[],task:null,view:'activity',file:0,diff:'unified',run:-1,online:false,loading:false};
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
  $('#task-total').textContent=state.tasks.length;
  $('#connection-indicator').textContent=state.config.worker && state.config.reviewer ? 'Configured' : 'Set up';
  const groups=new Map();
  for(const task of state.tasks){const key=task.demo?'Local demo':task.source;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(task)}
  $('#task-list').innerHTML=groups.size?[...groups].map(([project,tasks])=>`<div class="project-group"><div class="project-label" title="${esc(project)}">${icon('folder')}${esc(project==='Local demo'?project:basename(project))}</div>${tasks.map(t=>`<button class="task ${state.task?.id===t.id?'active':''}" data-task="${t.id}" title="${esc(t.title)}"><span class="task-dot ${t.status==='approved'?'done':''} ${activeStatuses.has(t.status)?'pulsing':''}"></span><span>${esc(t.title)}</span></button>`).join('')}</div>`).join(''):'<p class="sidebar-empty">Your tasks will live here.<br>Start small. See what it costs.</p>';
  $$('[data-task]').forEach(b=>b.onclick=()=>selectTask(b.dataset.task));
}
function welcome() {
  $('#activity-view').innerHTML=`<div class="welcome"><div class="welcome-symbol">${icon('leaf')}</div><span class="welcome-kicker">MORE PATIENCE. LESS PREMIUM COMPUTE.</span><h2>A worker that keeps going.<br>A reviewer that knows when to step in.</h2><p>CheapOS gives the coding loop to an inexpensive model. When the checks pass, a stronger model reviews the patch and sends back a decision.</p><div class="welcome-flow"><div>${icon('code')}<strong>Work</strong><small>Inspect, edit, iterate</small></div><span>→</span><div>${icon('tests')}<strong>Verify</strong><small>Run your checks</small></div><span>→</span><div>${icon('spark')}<strong>Review</strong><small>Approve or revise</small></div></div><div class="welcome-actions"><button class="primary-button" id="welcome-new">${icon('plus')}Start a real task</button><button class="subtle-button" id="welcome-demo">${icon('play')}Try the local demo</button></div><p class="welcome-footnote">The demo uses scripted model decisions and real file edits, tests, and patches. No API key or model charges.</p></div>`;
  $('#welcome-new').onclick=()=>newTask(); $('#welcome-demo').onclick=startDemo;
  renderInspector();
}
async function selectTask(id) {
  const wanted=id; state.loading=true;
  try {const task=await api('/tasks/'+wanted);state.task=task;state.file=0;state.run=-1;state.view='activity';try{localStorage.setItem('cheapos-selected',id)}catch{} renderTask();renderSidebar();$('#sidebar').classList.remove('show');}
  catch(e){toast(e.message)} finally {state.loading=false}
}
function setView(view) {state.view=view;renderView();$('#view-container').scrollTo({top:0,behavior:'instant'});}
function renderTask() {
  const task=state.task;if(!task)return;
  const scroller=$('#view-container'), oldScroll=scroller.scrollTop, bottom=scroller.scrollHeight-scroller.clientHeight-oldScroll<60;
  const expanded=new Map($$('details[data-event]').map(d=>[d.dataset.event,d.open]));
  $('#task-title').textContent=task.title;
  $('#project-name').textContent=task.demo?'Local demo':basename(task.source);
  $('#task-status').textContent=labels[task.status]||task.status;
  $('#task-date').textContent=date(task.created_at);
  $('#task-eyebrow').classList.toggle('running',activeStatuses.has(task.status));
  $('#task-subtitle').textContent=task.demo?'Scripted models. Real edits, checks, and checkpoint reviews.':task.status==='approved'?'Review the patch, then apply it to your project when you are ready.':'Working in a separate copy of your repository.';
  $('#change-count').textContent=task.changes.length;$('#check-count').textContent=task.checks.length;
  const sums=patchTotals(task.patch);$('#diff-tally').innerHTML=`<span>+${sums.add}</span><span>−${sums.remove}</span>`;
  $('#compact-cost').textContent=money(task.usage.cost);
  $('#task-actions').innerHTML=activeStatuses.has(task.status)?`<button class="subtle-button" id="pause-task">${icon('x')}Pause</button>`:!['approved','completed'].includes(task.status)?`<button class="primary-button" id="resume-task">${icon('play')}${task.status==='ready'?'Start task':task.status==='takeover_requested'?'Review takeover':'Resume'}</button>`:`<a class="subtle-button" href="/api/tasks/${task.id}/patch" download>${icon('file')}Export patch</a>`;
  if($('#pause-task'))$('#pause-task').onclick=async()=>{try{await api('/tasks/'+task.id+'/stop',{});toast('Pausing. An in-flight model request may take up to 90 seconds.')}catch(e){toast(e.message)}};
  if($('#resume-task'))$('#resume-task').onclick=()=>task.status==='ready'?startTask(task.id):resumeDialog();
  renderView();renderInspector();
  for(const d of $$('details[data-event]'))if(expanded.has(d.dataset.event))d.open=expanded.get(d.dataset.event);
  scroller.scrollTop=bottom?scroller.scrollHeight:oldScroll;
}
function renderView() {
  $$('.tab').forEach(b=>{const selected=b.dataset.view===state.view;b.classList.toggle('active',selected);b.setAttribute('aria-selected',String(selected))});
  $$('.view').forEach(v=>v.classList.toggle('hidden',v.id!==state.view+'-view'));
  if(!state.task){if(state.view==='activity')welcome();else $('#'+state.view+'-view').innerHTML='<div class="empty-state"><h2>Your next task starts here.</h2><p>Create a task or run the local demo to see its changes and verification results.</p></div>';return}
  if(state.view==='activity')renderActivity();else if(state.view==='changes')renderChanges();else renderTests();
}
function eventDetail(event) {
  const detail=event.detail;
  if(event.kind==='review')return `<p>${esc(detail.feedback)}</p><span class="decision ${detail.decision==='APPROVE'?'approve':'revise'}">${esc(detail.decision.replaceAll('_',' '))}</span>`;
  if(event.kind==='checkpoint')return `<p>${esc(detail.worker_summary)}</p><p class="muted">${esc(detail.uncertainties)}</p><button class="checkpoint-button" data-checkpoint="${detail.number}">Inspect checkpoint #${detail.number}</button>`;
  if(event.kind==='checks')return `<pre class="output">${esc(detail.output)}</pre>${detail.reason?`<p>${esc(detail.reason)}</p>`:''}`;
  if(typeof detail==='string')return `<p class="preserve">${esc(detail)}</p>`;
  return detail?`<pre class="output">${esc(JSON.stringify(detail,null,2))}</pre>`:'';
}
function renderActivity() {
  const task=state.task;
  const events=task.events.map(event=>{
    const symbol=event.kind==='review'?'spark':event.kind==='checks'?'tests':event.kind==='checkpoint'?'file':event.kind==='error'?'x':'code';
    const prominent=['review','checkpoint'].includes(event.kind);
    return `<details class="${prominent?'review-card':'activity-card'} ${event.kind==='review'&&event.detail.decision==='APPROVE'?'approved':''}" data-event="${event.id}" ${prominent?'open':''}><summary><span class="activity-icon">${icon(symbol)}</span><strong>${esc(event.title)}</strong><time class="activity-time">${new Date(event.time).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</time>${icon('chevron')}</summary><div class="${prominent?'review-content':'detail-body'}">${eventDetail(event)}</div></details>`;
  }).join('');
  $('#activity-view').innerHTML=`${task.demo?'<div class="demo-banner">Local demo · model decisions are scripted · no paid requests</div>':''}<div class="user-message"><div class="message-meta"><span class="mini-avatar">Y</span><strong>You</strong><time>${date(task.created_at)}</time></div><p>${esc(task.prompt)}</p></div><div class="live-events">${events}</div>${task.error?`<div class="attention-card"><strong>${esc(labels[task.status])}</strong><p>${esc(task.error)}</p></div>`:''}${task.pending_approval?`<div class="approval-card"><strong>Run the verification command?</strong><code>${esc(task.pending_approval.command.join(' '))}</code><p>This executes repository code on your computer. The task copy isolates edits, but is not an operating-system sandbox.</p><div class="button-row"><button class="primary-button" data-approve="yes">Run command</button><button class="subtle-button" data-approve="no">Decline & pause</button></div></div>`:''}${activeStatuses.has(task.status)&&!task.pending_approval?`<div class="live-progress"><span class="spinner"></span>${esc(labels[task.status])}…</div>`:''}${['approved','completed'].includes(task.status)?`<div class="completion-note">${icon('check')}<span>${task.status==='approved'?'Review complete. Your patch is ready to inspect.':'Takeover finished. Review the patch before applying it.'}</span><button class="text-link" id="see-changes">Open changes →</button></div>`:''}`;
  $$('[data-checkpoint]').forEach(b=>b.onclick=()=>checkpointDialog(Number(b.dataset.checkpoint)));
  $$('[data-approve]').forEach(b=>b.onclick=async()=>{try{await api('/tasks/'+task.id+'/approval',{approved:b.dataset.approve==='yes'});await refresh()}catch(e){toast(e.message)}});
  if($('#see-changes'))$('#see-changes').onclick=()=>setView('changes');
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
  if(!files.length){$('#changes-view').innerHTML='<div class="empty-state">'+icon('code')+'<h2>No changes yet.</h2><p>File edits will appear here as the worker makes them.</p></div>';return}
  state.file=Math.min(state.file,files.length-1);const file=files[state.file],rows=diffLines(file.before,file.after);
  const line=r=>`<div class="diff-line ${r.type}"><span class="line-number">${r.old}</span><span class="line-number">${r.new}</span><span class="diff-sign">${r.type==='add'?'+':r.type==='remove'?'−':' '}</span><span class="source">${esc(r.text)||' '}</span></div>`;
  $('#changes-view').innerHTML=`<div class="view-title"><div><h2>Review the work.</h2><p>${files.length} changed files in the task copy</p></div><a class="subtle-button" href="/api/tasks/${task.id}/patch" download>${icon('file')}Export patch</a></div><div class="file-list">${files.map((f,i)=>`<button class="file-item ${i===state.file?'selected':''}" data-file="${i}">${icon('file')}<span>${esc(f.path)}</span><span class="file-status">${f.before?'M':'A'}</span></button>`).join('')}</div><div class="diff-panel"><div class="diff-toolbar"><span>${icon('file')}${esc(file.path)}</span><div class="segmented"><button data-diff="unified" class="${state.diff==='unified'?'selected':''}">Unified</button><button data-diff="split" class="${state.diff==='split'?'selected':''}">Split</button></div></div>${file.binary?'<p class="modal-description">Binary change. Inspect the exported Git patch.</p>':state.diff==='unified'?`<div class="diff-code" tabindex="0" aria-label="Unified code diff">${rows.map(line).join('')}</div>`:`<div class="split-diff">${['before','after'].map(side=>`<div class="diff-code" tabindex="0" aria-label="${side==='before'?'Original':'Modified'} file"><div class="split-label">${side==='before'?'Before':'After'}</div>${rows.filter(r=>r.type!==(side==='before'?'add':'remove')).map(r=>`<div class="diff-line ${r.type}"><span class="line-number">${side==='before'?r.old:r.new}</span><span class="source">${esc(r.text)||' '}</span></div>`).join('')}</div>`).join('')}</div>`}</div><div class="diff-bottom">${icon('shield')}Edits are in the task copy. Export a patch to apply them to your source repository.</div><details class="patch-help"><summary>How to apply this patch</summary><p>From your original repository, check the downloaded patch first, then apply it:</p><pre>git apply --check /path/to/cheapos-${task.id.slice(0,8)}.patch\ngit apply /path/to/cheapos-${task.id.slice(0,8)}.patch</pre><p>For large files, the visual comparison shows whole blocks; the exported Git patch preserves the exact change, including file modes and final newlines.</p></details>`;
  $$('[data-file]').forEach(b=>b.onclick=()=>{state.file=Number(b.dataset.file);renderChanges()});$$('[data-diff]').forEach(b=>b.onclick=()=>{state.diff=b.dataset.diff;renderChanges()});
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
  const roles=['worker','reviewer'].map(role=>`<div class="role-row"><span class="role-icon ${role}-icon">${icon(role==='worker'?'code':'spark')}</span><span><span class="role-label">${role.toUpperCase()}</span><strong>${esc(t?.demo?'Scripted demo':config[role]?.model||'Choose a model')}</strong></span></div>`);
  const intro=t?`<section class="economy-intro compact-intro"><div class="mode-badge">${icon('leaf')}Economy mode</div><p>Work, verify, then ask for a second opinion.</p></section>`:`<section class="economy-intro"><div class="economy-icon">${icon('leaf')}</div><h2>A little patience.<br>A little more in your pocket.</h2><p>Spend less on the loop.<br>Save the stronger model for review.</p><div class="mode-badge">${icon('leaf')}Economy mode</div></section>`;
  const models=`<section class="model-roles">${roles[0]}<div class="role-connection"><span></span><small>codes → checks → checkpoint</small></div>${roles[1]}</section>`;
  const usage=t?`<section class="usage"><div class="section-title">Compute, thoughtfully spent</div><div class="cost-total"><strong>${money(t.usage.cost)}</strong><span>${t.demo?'no model charges':'accounted session cost'}</span></div><div class="usage-table">${['worker','reviewer'].map(role=>`<div><span>${role==='worker'?'Worker':'Reviewer'}</span><span>${t.usage[role].tokens.toLocaleString()} <small>tokens</small></span><strong>${money(t.usage[role].cost)}</strong></div>`).join('')}</div><div class="budget-meter"><span style="width:${Math.min(100,t.limits.dollars>0?t.usage.cost/t.limits.dollars*100:0)}%"></span></div><p class="small muted">${money(t.limits.dollars)} estimated cap · ${t.limits.reviewer_tokens.toLocaleString()} reviewer tokens</p><p class="small muted">${t.usage.uncertain_requests?`${t.usage.uncertain_requests} uncertain request(s): reservations remain counted.`:t.usage.estimated_requests?'Some costs use your configured token prices.':t.demo?'Demo usage is zero. No savings are claimed.':'Reported cost when available; configured prices otherwise.'}</p>${!activeStatuses.has(t.status)&&!['approved','completed'].includes(t.status)?'<button class="text-link" id="edit-limits">Review limits →</button>':''}</section>`:'';
  const journey=t?`<section class="journey"><div class="section-title">This session</div><ol class="journey-list">${[['Worker turns',t.worker_turns],['Tool actions',t.tool_actions],['Checkpoints',t.checkpoints.length],['Reviewer calls',t.review_count],['Latest check',t.checks.length?(t.checks.at(-1).passed?'Passed':'Failed'):'Not run']].map(([label,value])=>`<li><span class="journey-dot">${icon('check')}</span><span>${label}</span><strong>${value}</strong></li>`).join('')}</ol></section>`:'';
  const workspace=t?`<details class="workspace-info"><summary>Workspace details</summary><p>Task copy</p><code>${esc(t.workspace)}</code><p>Snapshot: ${t.snapshot.files} files · ${t.snapshot.skipped.length} excluded</p><p class="small">Snapshot excludes common secret files and dependency folders. Review your repository before sending its contents to a provider.</p></details>`:`<section class="usage"><div class="section-title">Yours, from the start</div><p class="small muted">Open source. Local task history. Your providers, your keys, your limits.</p><button class="subtle-button" id="inspector-connect">Set up connections →</button></section>`;
  $('#session-details').innerHTML=intro+models+usage+journey+workspace;
  if($('#edit-limits'))$('#edit-limits').onclick=resumeDialog;if($('#inspector-connect'))$('#inspector-connect').onclick=openConnections;
}
const numberField=(name,label,value,min,max,step='1')=>`<label>${label}<input name="${name}" type="number" min="${min}" max="${max}" step="${step}" value="${value}" required></label>`;
function limitFields(limits={dollars:1,reviewer_tokens:50000,iterations:5,worker_turns:40,output_tokens:2048}) {
  return `<div class="field-grid">${numberField('dollars','Estimated spending cap ($)',limits.dollars,0,100,'0.01')}${numberField('reviewer_tokens','Reviewer token limit',limits.reviewer_tokens,512,1000000)}</div><details class="advanced"><summary>Advanced limits</summary><div class="field-grid">${numberField('iterations','Max worker iterations',limits.iterations,1,20)}${numberField('worker_turns','Max worker model turns',limits.worker_turns,1,200)}${numberField('output_tokens','Output tokens per request',limits.output_tokens,128,16384)}</div></details>`;
}
const readLimits=f=>Object.fromEntries(['dollars','reviewer_tokens','iterations','worker_turns','output_tokens'].map(k=>[k,Number(f.get(k))]));
function newTask(prefill='') {
  if(!state.online){toast('Start the local server with python3 run.py');return}
  if(!state.config.worker||!state.config.reviewer){openConnections(()=>newTask(prefill));return}
  const d=dialog(`<form>${modalHeader('NEW LOCAL TASK','What are we working on?')}<p class="modal-description">Start with a focused fix in a personal project. CheapOS copies eligible files and leaves your source checkout untouched by its file tools.</p><label class="full-field">Git repository path<input name="repository" type="text" placeholder="/Users/you/projects/my-project" required autocomplete="off"></label><label class="full-field">Task<textarea name="prompt" rows="3" minlength="5" maxlength="8000" required placeholder="Describe the change and what success looks like…">${esc(prefill)}</textarea></label><label class="full-field">Verification command<input name="check_command" type="text" placeholder="python3 -m unittest discover -v" required><small>One command, split into arguments. Shell pipes and redirects are not interpreted.</small></label>${limitFields()}<label class="checkbox-field"><input name="auto_approve_checks" type="checkbox"><span>Allow this command without asking during this task<small>Runs repository code on your computer. The task copy is not an OS sandbox.</small></span></label><p class="small muted">Eligible source files and command output are sent to your configured model providers. Spending caps use your configured prices and conservative token estimates; set a provider-side cap for a billing guarantee.</p><p class="form-error" role="alert"></p><div class="modal-footer"><span>A snapshot is created first.<br>You start the model separately.</span><button type="submit" class="primary-button">Create task ${icon('arrow')}</button></div></form>`,'new-task-modal');
  const form=$('form',d);form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{const f=new FormData(form),task=await api('/tasks',{repository:f.get('repository'),prompt:f.get('prompt'),check_command:f.get('check_command'),auto_approve_checks:f.has('auto_approve_checks'),limits:readLimits(f)});d.close();$('#task-input').value='';await loadTasks();await selectTask(task.id)})};
}
async function startTask(id,changes={}) {try{await api('/tasks/'+id+'/start',changes);await refresh()}catch(e){toast(e.message)}}
function resumeDialog() {
  const task=state.task,takeover=task.status==='takeover_requested';
  const d=dialog(`<form>${modalHeader(takeover?'REVIEWER TAKEOVER':'TASK LIMITS',takeover?'Let the reviewer take over?':'Continue from saved work.')}<p class="modal-description">${takeover?'The reviewer will implement changes using the same task budget. You will review its final patch.':`Usage already counted: ${money(task.usage.cost)}. Resuming keeps your saved edits and accounting.`}</p>${limitFields(task.limits)}<p class="small muted">A stopped or failed provider request may still be billable. Its reservation stays counted. A resumed task uses its original model settings; updated keys from Connections are available.</p><p class="form-error" role="alert"></p><div class="modal-footer"><span>Source project stays separate.</span><button type="submit" class="primary-button">${takeover?'Approve takeover':'Save limits & resume'} ${icon('play')}</button></div></form>`);
  const form=$('form',d);form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{await api('/tasks/'+task.id+'/start',{limits:readLimits(new FormData(form)),approve_takeover:takeover});d.close();await refresh()})};
}
async function startDemo() {
  if(!state.online){toast('The local server is unavailable. Start it with python3 run.py');return}
  try{const task=await api('/demo',{});await loadTasks();await selectTask(task.id);await startTask(task.id)}catch(e){toast(e.message)}
}
function openConnections(afterSave) {
  const c=state.config;
  const providerFields=role=>{const p=c[role]||{};return `<fieldset class="provider-fields"><legend>${role==='worker'?'Worker · inexpensive, tool-capable':'Reviewer · stronger reasoning'}</legend><label class="full-field">Provider preset<select data-preset="${role}"><option value="openrouter">OpenRouter</option><option value="ollama" ${p.base_url?.includes('11434')?'selected':''}>Ollama (local)</option><option value="custom" ${p.base_url&&!p.base_url.includes('openrouter.ai')&&!p.base_url.includes('11434')?'selected':''}>OpenAI-compatible endpoint</option></select></label><label class="full-field">API base URL<input type="url" name="${role}_url" value="${esc(p.base_url||'https://openrouter.ai/api/v1')}" required></label><label class="full-field">Model ID<input name="${role}_model" type="text" value="${esc(p.model||'')}" placeholder="Exact tool-capable model ID from your provider" required autocomplete="off"></label><label class="full-field">API key ${p.key_configured?'· configured':''}<input name="${role}_key" type="password" placeholder="${p.key_configured?'Leave blank to keep the current key':'Optional for local Ollama'}" autocomplete="new-password"></label><div class="field-grid">${numberField(role+'_input','Input $ / million tokens',p.input_rate??'',0,10000,'any')}${numberField(role+'_output','Output $ / million tokens',p.output_rate??'',0,10000,'any')}</div><p class="small muted">Enter the current prices from your provider. Use 0 for free or local models.</p></fieldset>`};
  const d=dialog(`<form>${modalHeader('MODEL CONNECTIONS','One worker. One second opinion.')}<p class="modal-description">OpenRouter is the easiest starting point: one provider and one key for both roles. Choose an inexpensive tool-capable worker and a stronger reviewer.</p><div class="provider-grid">${providerFields('worker')}${providerFields('reviewer')}</div><label class="checkbox-field"><input type="checkbox" name="share_key" checked><span>Use the entered worker key for the reviewer when their API URLs match</span></label><p class="small muted">Keys entered here stay in server memory until it stops. To load keys on startup, set CHEAPOS_WORKER_API_KEY and CHEAPOS_REVIEWER_API_KEY in the launch environment. Keys are never stored in the browser or config file.</p><p class="form-error" role="alert"></p><div class="modal-footer"><span>Settings apply to new tasks.<br>No model request is made when saving.</span><button class="primary-button" type="submit">Save connections ${icon('check')}</button></div></form>`,'connections-modal');
  $$('[data-preset]',d).forEach(select=>select.onchange=()=>{const role=select.dataset.preset;if(select.value==='custom')return;$(`[name="${role}_url"]`,d).value=select.value==='ollama'?'http://127.0.0.1:11434/v1':'https://openrouter.ai/api/v1';$(`[name="${role}_model"]`,d).value='';$(`[name="${role}_key"]`,d).value='';for(const price of ['input','output'])$(`[name="${role}_${price}"]`,d).value=select.value==='ollama'?'0':''});
  const form=$('form',d);form.onsubmit=e=>{e.preventDefault();formAction(form,async()=>{const f=new FormData(form),values={};for(const role of ['worker','reviewer']){values[role]={base_url:String(f.get(role+'_url')).trim(),model:String(f.get(role+'_model')).trim(),input_rate:Number(f.get(role+'_input')),output_rate:Number(f.get(role+'_output'))};const key=String(f.get(role+'_key')).trim();if(key)values[role].api_key=key}if(f.has('share_key')&&values.worker.base_url.replace(/\/$/,'')===values.reviewer.base_url.replace(/\/$/,'')&&values.worker.api_key)values.reviewer.api_key=values.worker.api_key;state.config=await api('/config',values);form.reset();d.close();renderSidebar();renderInspector();toast('Connections saved. Keys stay in server memory.');if(typeof afterSave==='function')afterSave()})};
}
function openSearch() {
  const d=dialog(`<div class="search-box">${icon('search')}<input id="task-search" type="search" placeholder="Find a task or project…" aria-label="Search tasks" autofocus><kbd>ESC</kbd></div><div id="search-results"></div><div class="search-footer">Saved on this computer</div>`,'search-modal');
  const render=(q='')=>{const found=state.tasks.filter(t=>(t.title+' '+t.source).toLowerCase().includes(q.toLowerCase()));$('#search-results',d).innerHTML=found.length?found.map(t=>`<button class="search-result" data-result="${t.id}">${icon('chat')}<span><strong>${esc(t.title)}</strong><small>${esc(t.demo?'Local demo':basename(t.source))} · ${esc(labels[t.status])}</small></span>${icon('chevron')}</button>`).join(''):'<div class="no-results">No matching tasks.</div>';$$('[data-result]',d).forEach(b=>b.onclick=()=>{d.close();selectTask(b.dataset.result)})};$('#task-search',d).oninput=e=>render(e.target.value);render();
}
async function loadTasks() {const tasks=await api('/tasks');const changed=JSON.stringify(tasks)!==JSON.stringify(state.tasks);state.tasks=tasks;if(changed)renderSidebar();}
async function refresh() {
  if(state.loading)return;
  await loadTasks();const selected=state.task?.id;if(!selected)return;
  const task=await api('/tasks/'+selected);if(state.task?.id!==selected)return;
  if(task.updated_at!==state.task.updated_at||task.status!==state.task.status){state.task=task;renderTask()}
}
async function bootstrap() {
  try {const data=await api('/bootstrap');state.token=data.token;state.config=data.config;state.tasks=data.tasks;state.online=true;renderSidebar();let selected;try{selected=localStorage.getItem('cheapos-selected')}catch{}if(!state.tasks.some(t=>t.id===selected))selected=state.tasks[0]?.id;if(selected)await selectTask(selected);else welcome();}
  catch(e){state.online=false;$('#activity-view').innerHTML='<div class="empty-state"><h2>Start CheapOS locally.</h2><p>Run <code>python3 run.py</code> in the project directory, then refresh this page. No sign-in is needed.</p></div>';renderInspector()}
}
async function poll() {try{if(state.online)await refresh()}catch(e){toast('Local server disconnected. Restart CheapOS and refresh to reconnect.');state.online=false}finally{setTimeout(poll,1500)}}
$$('.tab').forEach(b=>b.onclick=()=>setView(b.dataset.view));
$('#new-task').onclick=()=>newTask();$('#search-trigger').onclick=openSearch;$('#settings-trigger').onclick=()=>openConnections();$('#session-settings').onclick=()=>openConnections();$('#demo-trigger').onclick=startDemo;
$('#mode-select').onclick=()=>{dialog(`${modalHeader('ECONOMY MODE','The inexpensive model does the legwork.')}<p class="modal-description">The worker inspects, edits, and runs your checks. A passing checkpoint goes to the reviewer, who approves, requests changes, or asks to take over.</p><div class="mode-explanation">Economy is the execution mode in this alpha. Both roles, spending limits, and verification permissions are configurable.</div>`)};
$('#composer').onsubmit=e=>{e.preventDefault();newTask($('#task-input').value.trim())};$('#task-input').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();newTask(e.target.value.trim())}};
$('#toggle-inspector').onclick=()=>{if(matchMedia('(max-width:1000px)').matches)$('#inspector').classList.toggle('show');else $('#inspector').classList.toggle('hidden')};$('#compact-session').onclick=()=>$('#inspector').classList.toggle('show');
$('#sidebar-toggle').onclick=()=>{if(matchMedia('(max-width:700px)').matches)$('#sidebar').classList.remove('show');else{$('#sidebar').classList.add('collapsed');$('#mobile-menu').style.display='flex'}};
$('#mobile-menu').onclick=()=>{if(matchMedia('(max-width:700px)').matches)$('#sidebar').classList.toggle('show');else{$('#sidebar').classList.remove('collapsed');$('#mobile-menu').style.display='none'}};
document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&['k','n',','].includes(e.key.toLowerCase())){e.preventDefault();if($('dialog[open]'))return;if(e.key.toLowerCase()==='k')openSearch();else if(e.key.toLowerCase()==='n')newTask();else openConnections()}if(e.key==='Escape'){$('#sidebar').classList.remove('show');$('#inspector').classList.remove('show')}});
bootstrap();setTimeout(poll,1500);
