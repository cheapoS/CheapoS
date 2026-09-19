(function(root){
'use strict';
function settings(api,repository){
 const d=document.createElement('dialog');d.className='modal setup-modal';
 d.innerHTML='<form><div class="modal-header"><h2>Project context</h2><button type="button" class="icon-button" data-close aria-label="Close">×</button></div><p>Carto automatically maps projects to help agents find related code and understand dependencies. Its suggestions help agents navigate; they do not approve changes.</p><label class="checkbox-field"><input type="checkbox" name="enabled"><span>Use Carto for this project</span></label><p class="small muted">On by default for each project. Mapping starts in the background when a project is added or reopened, and indexes stay local in cheapoS’s cache. Each task copy refreshes changed files automatically. You can turn it off here; agents can always inspect files normally.</p><p data-status role="status">Loading…</p><p data-install hidden>Install the optional runtime from the cheapoS repository:<br><code>python3 scripts/install_carto.py</code></p><p class="form-error" role="alert"></p><div class="modal-footer"><button type="button" class="outline-button" data-refresh>Refresh status</button><button type="button" class="outline-button" data-rebuild>Rebuild index</button><button type="submit" class="primary-button">Save</button></div></form>';
 document.body.append(d);d.showModal();d.addEventListener('close',()=>d.remove());d.querySelector('[data-close]').onclick=()=>d.close();
 const form=d.querySelector('form'),error=d.querySelector('.form-error');
 async function update(values={}){
  error.textContent='';form.querySelectorAll('button:not([data-close])').forEach(b=>b.disabled=true);
  try{const result=await api('/projects/carto',{repository,...values});if(!d.isConnected)return;
   form.elements.enabled.checked=result.enabled;d.querySelector('[data-install]').hidden=result.installed;
   const info=result.index||{};d.querySelector('[data-status]').textContent=info.status==='ready'?`Ready · ${info.indexed_files} source files · ${info.extraction_errors||0} extraction issues`:info.status==='disabled'?'Off for this project':info.message||info.status;
  }catch(e){error.textContent=e.message;}finally{form.querySelectorAll('button:not([data-close])').forEach(b=>b.disabled=false);}
 }
 form.onsubmit=e=>{e.preventDefault();update({enabled:form.elements.enabled.checked})};
 d.querySelector('[data-refresh]').onclick=()=>update();d.querySelector('[data-rebuild]').onclick=()=>update({rebuild:true});update();
}
root.CheapOSCarto={settings};
})(typeof window==='undefined'?globalThis:window);
