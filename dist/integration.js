(function(root){
'use strict';
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pending=new Map();
function markup(task,readiness){
 const op=task.integration_preparation;
 const permission=op?.authorized&&op.status==='decision'&&op.reason?.code==='command_permission_required';
 const summary=op?`<section class="integration-update" aria-label="Integration update"><h3>Integration update</h3><p role="status">${esc(op.label||op.stage||op.status)}</p>${op.target_tip?`<p class="small muted">Target for this update: <code>${esc(op.target_tip.slice(0,12))}</code></p>`:''}${(op.error||op.reason?.message)?`<p role="alert">${esc(op.error||op.reason.message)}</p>`:''}${permission?'<button type="button" class="primary-button" data-integration-permission>Review test permissions &amp; continue</button>':''}${(op.files||[]).length?`<p>Overlaps: ${op.files.map(esc).join(', ')}</p>`:''}<button type="button" class="subtle-button" data-integration-comparison>Changes from conflict resolution</button><p class="form-error" role="alert" data-integration-error></p></section>`:'';
 if(!readiness)return summary;
 const canUpdate=(readiness.actions||[]).includes('update_resolve');
 const checks=task.branch_run?.check_scope||[];
 const localNotice=canUpdate&&readiness.local_changes?.length?`<div class="integration-local-notice"><p>Local changes will stay untouched. This update uses the target branch’s committed changes; the final merge will wait until the destination is clean.</p><ul>${readiness.local_changes.map(p=>`<li>${esc(p)}</li>`).join('')}</ul></div>`:'';
 const checkConsent=canUpdate&&checks.length?`<details><summary>Verification included in this update</summary><p>This action allows these approved commands again if their environment is unchanged.</p><ul>${checks.map(s=>`<li><code>${esc(s.command.join(' '))}</code><br><small>${esc(s.directory)}</small></li>`).join('')}</ul></details>`:'';
 return summary+`<section class="integration-update" aria-label="Integration readiness"><h3>${canUpdate?'Bring this work up to date':esc(readiness.message||'Integration status')}</h3>${canUpdate?'<p>The project changed while this task was running. cheapoS will combine both versions, check the result, and request fresh review.</p><p class="small muted">This updates the task copy. Final approval is still required to change your project.</p>':''}${localNotice}${checkConsent}${(readiness.files||[]).length?`<ul>${readiness.files.map(p=>`<li>${esc(typeof p==='string'?p:p.path)}</li>`).join('')}</ul>`:''}<div class="button-row">${canUpdate?'<button type="button" class="primary-button" data-integration-prepare>Update &amp; resolve</button>':''}${(readiness.actions||[]).includes('inspect_local_changes')?'<button type="button" data-integration-local>Inspect local changes</button>':''}${canUpdate?`<button type="button" data-integration-keep>${task.branch_run?'Keep on branch':'Keep saved work'}</button>`:''}</div><p class="form-error" role="alert" data-integration-error></p></section>`;
}
function prepare(api,task,readiness){
 const key=task.id+':'+readiness.target_tip+':'+readiness.candidate;
 if(['failed','cancelled'].includes(task.integration_preparation?.status))pending.delete(key);
 if(pending.has(key))return pending.get(key).promise;
 const operation_id=typeof crypto!=='undefined'&&crypto.randomUUID?crypto.randomUUID():Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);
 const record={operation_id};pending.set(key,record);
 record.promise=api('/tasks/'+task.id+'/integration-prepare',{approved:true,target_tip:readiness.target_tip,target_ref:readiness.target_ref,candidate:readiness.candidate,operation_id}).catch(async error=>{
  // A lost response must inspect the acknowledged server operation, never start a second one.
  try{const saved=await api('/tasks/'+task.id);if(saved.integration_preparation?.id===operation_id)return saved;}catch(_){}
  pending.delete(key);throw error;
 });
 return record.promise;
}
function comparisonText(result,local=false){
 const files=(result.files||[]).map(p=>typeof p==='string'?p:p.path).filter(Boolean);
 const listing=files.length?`Files with ${local?'local changes':'overlaps'}:\n${files.join('\n')}\n\n`:'';
 return listing+(result.diff||(local&&files.length?'No tracked-file diff is available. New, untracked files do not appear in Git diff.':'No comparison is available yet.'));
}
function bind(host,task,readiness,api,onSaved,keep,resume){
 const button=host.querySelector('[data-integration-prepare]');
 if(button)button.onclick=async()=>{if(button.disabled)return;button.disabled=true;button.textContent='Saving update request…';
  try{await onSaved(await prepare(api,task,readiness));}catch(error){host.querySelector('[data-integration-error]').textContent=error.message;button.disabled=false;button.textContent='Update & resolve';}};
 const stay=host.querySelector('[data-integration-keep]');if(stay)stay.onclick=async()=>{stay.disabled=true;try{await onSaved(await api('/tasks/'+task.id+'/integration-defer',{}));keep?.();}catch(error){host.querySelector('[data-integration-error]').textContent=error.message;stay.disabled=false;}};
 const permission=host.querySelector('[data-integration-permission]');if(permission)permission.onclick=async()=>{if(permission.disabled)return;permission.disabled=true;try{await resume(task);}catch(error){host.querySelector('[data-integration-error]').textContent=error.message;}finally{permission.disabled=false;}};
 for(const [selector,endpoint,title] of [['[data-integration-local]','integration-local-changes','Local uncommitted changes'],['[data-integration-comparison]','integration-resolution-changes','Changes from conflict resolution']]){
  const control=host.querySelector(selector);if(!control)continue;
  control.onclick=async()=>{control.disabled=true;try{const result=await api('/tasks/'+task.id+'/'+endpoint);const d=document.createElement('dialog');d.className='modal setup-modal';d.innerHTML='<h2>'+title+'</h2><p></p><pre style="white-space:pre-wrap;overflow-wrap:anywhere"></pre><button type="button">Close</button>';d.querySelector('p').textContent=[result.label||result.message, result.base?'Base '+result.base+' → candidate '+(result.candidate||result.target||'current'):'',result.target_tip?'Incoming target '+result.target_tip:'',result.summary].filter(Boolean).join(' · ');d.querySelector('pre').textContent=comparisonText(result,endpoint==='integration-local-changes');d.querySelector('button').onclick=()=>d.close();d.onclose=()=>d.remove();document.body.append(d);d.showModal();}catch(error){const out=host.querySelector('[data-integration-error]');if(out)out.textContent=error.message;}finally{control.disabled=false;}};
 }
}
const exported={markup,prepare,bind,comparisonText};if(typeof module!=='undefined')module.exports=exported;else root.CheapOSIntegration=exported;
})(typeof globalThis!=='undefined'?globalThis:this);
