(function(root){
'use strict';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const when=n=>new Date(n*1000).toLocaleString();
const intervals=[6,12,24,168];
const frequency=n=>n===168?'Every week':`Every ${n} hours`;
const intervalOptions=(selected=6,once=false)=>(once?'<option value="0">Run once</option>':'')+intervals.map(n=>`<option value="${n}" ${n===selected?'selected':''}>${frequency(n)}</option>`).join('');
function status(task){
 const saved=task?.schedule;
 if(saved)return {interval_hours:saved.interval_hours,label:saved.enabled===false?'Schedule disabled':'Scheduled',manage:true};
 if(task?.schedule_start)return {interval_hours:task.schedule_start.interval_hours,label:'Saving approved schedule'};
 if(!task?.branch_run?.authorization_ref&&task?.planning_request?.schedule_request)return {...task.planning_request.schedule_request,label:'Awaiting approval'};
 return null;
}
function approvalMarkup(preview,fullChecks=[]){
 if(!preview)return '';
 return `<section class="proposal-card schedule-approval"><h4>Repeat this task</h4><label>Repeat<select name="schedule_interval">${intervalOptions(preview.interval_hours,true)}</select></label><p>The first run starts after approval. Later runs get a new task and branch. Unfinished work or an unmerged PR holds the next run; reviewed no-change runs can repeat. Runs need cheapoS open. Nothing is published or merged automatically.</p>${preview.error?`<p role="alert">${esc(preview.error)} Choose Run once or revise the plan before scheduling.</p>`:''}<div data-recurring-consent><label class="schedule-consent"><input name="schedule_approved" type="checkbox"><span>Allow this plan to repeat with the displayed models, $0 API spending allowance, work limits and task commands until I disable it.</span></label>${fullChecks.length?`<label class="schedule-consent"><input name="schedule_full" type="checkbox"><span>Allow the listed full-suite checks on every scheduled run.</span></label>`:''}<p>Manage or disable it in Settings → Scheduled tasks.</p></div></section>`;
}
function approval(form,preview,fullChecks=[]){
 if(!preview||Number(form.elements.schedule_interval.value)===0)return null;
 if(preview.error)throw Error(preview.error);
 const interval=Number(form.elements.schedule_interval.value);
 if(!intervals.includes(interval))throw Error('Choose a supported repeat interval.');
 if(!form.elements.schedule_approved.checked)throw Error('Approve recurring runs, or choose Run once.');
 if(!form.elements.allow_task_commands.checked)throw Error('Allow task commands for the recurring plan, or choose Run once.');
 if(fullChecks.length&&!form.elements.schedule_full?.checked)throw Error('Approve full-suite checks on every run, or choose Run once.');
 return {interval_hours:interval,approval_digest:preview.approval_digest,approved:true,full_suite_approved:form.elements.schedule_full?.checked===true};
}
function setup({project,tasks=[],dialog,header,onNew,onExisting}){
 const candidates=tasks.filter(t=>t.source===project.path&&t.branch_run&&!t.trashed_at&&!['draft','awaiting_authorization'].includes(t.branch_run.status));
 const d=dialog(header('RECURRING PROJECT WORK','New scheduled task')+`<p>Project: <strong>${esc(project.name||project.path)}</strong></p><ol class="schedule-setup-steps"><li>Describe the work and choose how often it repeats.</li><li>Choose Prepare plan to start planning in chat.</li><li>Review the plan, then <strong>Approve &amp; start schedule</strong>.</li></ol><form data-new-schedule><label>What should this task do each time?<textarea name="prompt" rows="4" maxlength="8000" required placeholder="Check this project’s documentation for outdated setup instructions and propose a verified update…"></textarea></label><label>Repeat<select name="interval">${intervalOptions()}</select></label><p>Each run gets a fresh task and branch. Unfinished work or an unmerged PR holds the next run.</p><p>The new chat uses a $0 API spending allowance and your selected project’s other settings. Prepare plan starts planning immediately; execution and recurring runs wait for your approval.</p><div class="button-row"><button type="submit" class="primary-button">Prepare plan</button></div></form>${candidates.length?`<details><summary>Use an existing Unattended plan</summary><p>The saved plan must already be approved. Unfinished work holds the next scheduled run.</p><form data-existing-schedule><label>Saved task<select name="task_id">${candidates.map(t=>`<option value="${esc(t.id)}">${esc(t.title||'Untitled task')}</option>`).join('')}</select></label><button type="submit">Choose repeating plan</button></form></details>`:''}<p role="alert"></p>`,'schedule-settings');
 const q=s=>d.querySelector(s);let busy=false;
 async function submit(e,form,action){
  e.preventDefault();if(busy)return;
  busy=true;const button=form.querySelector('button[type=submit]');button.disabled=true;q('[role=alert]').textContent='';
  try{await action();}catch(error){if(d.open)q('[role=alert]').textContent=error.message;}
  finally{busy=false;if(d.open)button.disabled=false;}
 }
 const form=q('[data-new-schedule]');
 form.onsubmit=e=>submit(e,form,async()=>{
  const prompt=form.elements.prompt.value.trim();if(!prompt)throw new Error('Describe the work to repeat.');
  const interval=Number(form.elements.interval.value);if(!intervals.includes(interval))throw new Error('Choose a supported repeat interval.');
  await onNew({repository:project.path,prompt,schedule_request:{interval_hours:interval},isOpen:()=>d.open,close:()=>d.close()});
 });
 const existing=q('[data-existing-schedule]');
 if(existing)existing.onsubmit=e=>submit(e,existing,async()=>{
  const task=candidates.find(t=>t.id===existing.elements.task_id.value);if(!task)throw new Error('Choose an existing task.');
  await onExisting(task,()=>d.open,()=>d.close());
 });
 return d;
}
function rows(data){
 return data.schedules.map(s=>`<li class="schedule-card"><div class="schedule-heading"><h3>${esc(s.name)}</h3><span>${s.enabled?'Enabled':'Disabled'}</span></div><p>${esc(s.repository)}</p><p>Every ${s.interval_hours} hours · ${s.enabled?'Next eligible: '+esc(when(s.next_due)):'Future runs are disabled'}</p><p role="status">${esc(s.error||s.waiting||'Ready for the next scheduled run.')}</p><div class="button-row"><button data-task="${esc(s.last_task_id)}">Open latest task</button><button data-enabled="${esc(s.id)}" data-value="${!s.enabled}">${s.enabled?'Disable':'Enable'}</button><button data-run="${esc(s.id)}" ${!s.enabled||s.waiting?'disabled':''}>Run now</button>${!s.enabled?`<button data-remove="${esc(s.id)}">Remove schedule</button>`:''}</div></li>`).join('')||'<li class="schedule-empty">No scheduled tasks yet. Choose <strong>New scheduled task</strong> to get started, or open an approved chat’s Plan page → <strong>Schedule this task…</strong>.</li>';
}
async function open({api,dialog,header,selectTask,onNew}){
 const d=dialog(header('THIS INSTALLATION','Scheduled tasks')+'<p>Repeat approved plans in separate task copies while cheapoS is running. Missed runs are combined into one; existing work is never restarted by the clock.</p><p>Each run keeps its checks and independent review. Changes wait for your merge decision. Paused tasks and open PRs hold the next run. A reviewed run with no changes can repeat automatically.</p><p>Disabling a schedule leaves its current task alone. Pause that task in chat if needed.</p><p role="alert"></p><div class="button-row">'+(onNew?'<button class="primary-button" data-new>New scheduled task</button>':'')+'<button data-refresh>Refresh status</button></div><ul class="schedule-list"></ul>','schedule-settings');
 const q=s=>d.querySelector(s);let busy=false;
 if(q('[data-new]'))q('[data-new]').onclick=()=>{d.close();onNew();};
 async function load(){const data=await api('/schedules');if(!d.open)return;q('[role=alert]').textContent=data.error||'';q('.schedule-list').innerHTML=rows(data);
  d.querySelectorAll('[data-task]').forEach(b=>b.onclick=()=>{d.close();selectTask(b.dataset.task);});
  d.querySelectorAll('[data-enabled]').forEach(b=>b.onclick=()=>act(()=>api('/schedules/'+b.dataset.enabled+'/enabled',{enabled:b.dataset.value==='true'})));
  d.querySelectorAll('[data-run]').forEach(b=>b.onclick=()=>act(()=>api('/schedules/'+b.dataset.run+'/run',{})));
  d.querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>act(()=>api('/schedules/'+b.dataset.remove+'/remove',{})));
 }
 async function act(fn){if(busy)return;busy=true;q('[role=alert]').textContent='';try{await fn();await load();}catch(e){q('[role=alert]').textContent=e.message;}finally{busy=false;}}
 q('[data-refresh]').onclick=()=>act(async()=>{});await act(async()=>{});
}
async function create({task,api,dialog,header,onSaved}){
 const d=dialog(header('REPEAT AN APPROVED PLAN','Schedule this task')+'<p role="status">Loading the saved plan and settings…</p><p role="alert"></p><div data-schedule-form></div>','schedule-settings');
 const q=s=>d.querySelector(s);
 try{
  const preview=await api('/schedules/preview',{task_id:task.id});if(!d.open)return;
  const t=preview.template,settings=t.settings_snapshot.values;
  q('[role=status]').textContent='Each run uses this plan and captured setup. Later changes to chat defaults do not widen its permission.';
  q('[data-schedule-form]').innerHTML=`<form><label>Name<input name="name" maxlength="120" required value="${esc((task.title||task.prompt).slice(0,120))}"></label><label>Repeat<select name="interval">${[6,12,24,168].map(n=>`<option value="${n}">Every ${n===168?'week':n+' hours'}</option>`).join('')}</select></label><p>${esc(t.repository)} → ${esc(t.target_ref.replace('refs/heads/',''))}</p><p>Model placement: ${esc(settings.execution.mode)} · API spending allowance: $0 per run. Existing free/included access and model choices still apply. All usage is recorded in each chat.</p><details><summary>Review the repeating plan and settings</summary>${t.plan.items.map(i=>`<section><h3>${esc(i.title)}</h3><p>${esc(i.instructions)}</p><ul>${i.acceptance_criteria.map(c=>`<li>${esc(c)}</li>`).join('')}</ul><pre>${esc(JSON.stringify(i.required_checks,null,2))}</pre></section>`).join('')}<h3>Captured model choices and limits</h3><pre>${esc(JSON.stringify({roles:settings.roles,limits:t.plan.limits,measurement:t.plan.measurement===true,uncapped_work:t.plan.uncapped_work===true},null,2))}</pre><h3>Final checks</h3><pre>${esc(JSON.stringify(t.plan.final_checks,null,2))}</pre></details><p>Runs start while this installation is open. An unfinished task or unmerged changes hold the next run. The clock never merges, publishes a post, or starts a second copy of the same occurrence.</p><label class="schedule-consent"><input name="approved" type="checkbox" required><span>Allow this plan to repeat with its captured models, zero API spending allowance, and work limits until I disable the schedule.</span></label><label class="schedule-consent"><input name="commands" type="checkbox" required><span>Allow commands in each scheduled task copy. These are local programs with host access, not a security sandbox.</span></label>${preview.full_suite_checks.length?`<label class="schedule-consent"><input name="full" type="checkbox" required><span>Allow these full-suite checks on every run: ${esc(preview.full_suite_checks.join('; '))}</span></label>`:''}<div class="button-row"><button type="submit">Create schedule</button></div></form>`;
  q('form').onsubmit=async e=>{e.preventDefault();const f=q('form'),b=f.querySelector('button[type=submit]');b.disabled=true;q('[role=alert]').textContent='';try{await api('/schedules',{task_id:task.id,name:f.elements.name.value,interval_hours:Number(f.elements.interval.value),approval_digest:preview.approval_digest,approved:f.elements.approved.checked,allow_task_commands:f.elements.commands.checked,full_suite_approved:f.elements.full?.checked===true});d.close();onSaved();}catch(error){q('[role=alert]').textContent=error.message;b.disabled=false;}};
 }catch(e){q('[role=status]').textContent='';q('[role=alert]').textContent=e.message;}
}
const api={open,create,rows,setup,frequency,intervalOptions,status,approvalMarkup,approval};root.CheapOSSchedules=api;if(typeof module!=='undefined')module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:this);
