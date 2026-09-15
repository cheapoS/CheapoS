(function(root){
'use strict';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function fields(c={}){
 return '<p>Commands run in a separate copy of the saved task commit. They are local programs, not a security sandbox. Use test services and a separate database.</p>'+[
 ['command','Start command','python3 -B run.py --no-open --port 5174 --data-dir {profile}'],
 ['setup','Setup command (optional)','npm ci'],
 ['directory','Working directory (relative to copy)','.'],
 ['url','Local URL with port','http://127.0.0.1:5174'],
 ['environment','Environment · one NAME=value per line','PORT={port}'],
 ['checklist','How to test · action → expected result, one per line','Click Cancel → section remains visible']
 ].map(([name,label,placeholder])=>'<label style="display:block;margin:12px 0">'+label+'<textarea style="display:block;width:100%;box-sizing:border-box" name="'+name+'" placeholder="'+esc(placeholder)+'" rows="'+(['environment','checklist'].includes(name)?3:1)+'">'+esc(c[name])+'</textarea></label>').join('')+
 '<p>Use {profile} for the separate test data directory and {port} for the URL port. Commands use arguments directly; shell operators are not expanded. Environment values are stored locally in the app profile; prefer credential references over secrets.</p>';
}
function values(form){return Object.fromEntries(new FormData(form));}
function settings(api,repository){
 const d=document.createElement('dialog');d.style.cssText='width:min(760px,90vw);max-height:90vh;overflow:auto';
 d.innerHTML='<form><h2>Project preview</h2><div data-fields>Loading…</div><p role="alert"></p><button type="button" data-close>Cancel</button> <button type="submit">Save preview settings</button></form>';
 document.body.append(d);d.showModal();d.onclose=()=>d.remove();d.querySelector('[data-close]').onclick=()=>d.close();
 api('/projects/preview',{repository}).then(c=>{d.querySelector('[data-fields]').innerHTML=fields(c);}).catch(e=>d.querySelector('[role=alert]').textContent=e.message);
 d.querySelector('form').onsubmit=async e=>{e.preventDefault();try{await api('/projects/preview',{repository,config:values(e.currentTarget)});d.close();}catch(error){d.querySelector('[role=alert]').textContent=error.message;}};
}
function mount(host,task,api,tip){
 const section=document.createElement('details');section.className='preview-panel';
 section.innerHTML='<summary>Try it before merging</summary><p data-status></p><p data-revision></p><div data-checklist></div><details><summary>Preview configuration · overrides for this launch</summary><form data-config></form><button type="button" data-save>Save as project defaults</button></details><div class="branch-actions"><button type="button" data-launch>Launch preview</button><button type="button" data-stop>Stop preview</button><button type="button" data-refresh-preview>Refresh status</button><a data-open target="_blank" rel="noopener" hidden>Open preview ↗</a></div><details><summary>Preview logs</summary><pre data-logs style="white-space:pre-wrap;max-height:220px;overflow:auto"></pre></details><p data-error role="alert"></p>';
 host.append(section);let editing=false;
 const q=s=>section.querySelector(s),call=(action,body={})=>api('/tasks/'+task.id+'/preview-'+action,body);
 q('[data-launch]').disabled=true;
 function show(r){
  q('[data-status]').textContent=r.status+(r.outdated?' · Outdated: task changes have moved on. Stop and relaunch to test the new revision.':'');
  q('[data-revision]').textContent=r.tip?(r.branch+' · '+r.tip.slice(0,12)+' · '+r.root):'Preview has not been launched.';
  q('[data-logs]').textContent=r.logs||'No output yet.';
  q('[data-open]').hidden=!r.url||r.status!=='running';if(r.url)q('[data-open]').href=r.url;
  q('[data-stop]').disabled=!['starting','setting_up','running','stopping'].includes(r.status);
  q('[data-launch]').disabled=['starting','setting_up','running','stopping'].includes(r.status);
  if(!editing){q('[data-config]').innerHTML=fields(r.config);q('[data-config]').oninput=()=>editing=true;}
  const checks=(r.config?.checklist||'').split('\n').filter(Boolean);
  q('[data-checklist]').innerHTML='<h4>Operator checks · not automatically verified</h4>'+(checks.length?'<ul>'+checks.map(s=>'<li>'+esc(s)+'</li>').join('')+'</ul>':'<p>Add action → expected result steps in the preview configuration. Include the changed feature and nearby controls.</p>');
  const criteria=(task.branch_run?.plan?.items||[]).flatMap(item=>item.acceptance_criteria||[]);
  if(criteria.length)q('[data-checklist]').insertAdjacentHTML('beforeend','<details><summary>Expected behavior from this task</summary><ul>'+criteria.map(s=>'<li>'+esc(s)+'</li>').join('')+'</ul></details>');

 }
 async function perform(fn){q('[data-error]').textContent='';try{const r=await fn();if(r)show(r);}catch(e){q('[data-error]').textContent=e.message;}}
 q('[data-launch]').onclick=()=>perform(()=>call('start',{config:values(q('[data-config]')),expected_tip:tip}));
 q('[data-stop]').onclick=()=>perform(()=>call('stop'));
 q('[data-refresh-preview]').onclick=()=>perform(()=>call('status'));
 q('[data-save]').onclick=()=>perform(async()=>{await api('/projects/preview',{repository:task.source,config:values(q('[data-config]'))});q('[data-status]').textContent='Project defaults saved';});
 perform(()=>call('status'));
 const timer=setInterval(()=>{if(!section.isConnected){clearInterval(timer);return;}if(section.open)perform(()=>call('status'));},2000);
}
const api={fields,settings,mount};
if(typeof module!=='undefined')module.exports=api;else root.CheapOSPreview=api;
})(typeof globalThis!=='undefined'?globalThis:this);
