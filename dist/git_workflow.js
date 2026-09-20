(function(root){
'use strict';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const enabled=task=>task?.settings_snapshot?.values?.git?.workflow==='pull_request';
const lastStatus=new Map();
const safeURL=url=>/^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/(?:pull|actions)\//.test(String(url))?url:null;
function merged(task){
 const p=task?.pull_request;
 if(!enabled(task)||!p?.head||p.merged_head!==p.head||p.ci?.state!=='merged')return false;
 return task.branch_run?task.branch_run.status==='merged'&&task.branch_run.expected_feature_tip===p.head:typeof task.patch==='string'&&task.patch===p.patch;
}
function mergeSummary(p){
 const local=p.local_sync,branch=local?.branch||p.base||'destination branch';
 if(local?.state==='updated')return {title:`Merged · local ${branch} up to date`,description:`cheapoS pulled the merged changes into local ${branch}. New tasks will include them.`};
 if(local?.state==='current')return {title:`Merged · local ${branch} up to date`,description:`Local ${branch} already includes the merged changes. No pull was needed.`};
 if(local?.state==='ahead')return {title:`Merged · local ${branch} includes these changes`,description:local.message||'The local branch includes this merge and has additional local commits.'};
 return {title:local?.retryable===false?'Merged · local sync needs attention':'Merged · local sync pending',description:local?.message||'The PR is merged on GitHub. Local branch synchronization has not been confirmed yet.'};
}
function completionMarkup(task){
 if(!merged(task))return '';
 const p=task.pull_request,summary=mergeSummary(p);
 return `<section class="chat-result" aria-label="Merged pull request"><div><strong>${esc(summary.title)}</strong><p>${esc(summary.description)}</p><a class="subtle-button" href="${esc(safeURL(p.url)||'#')}" target="_blank" rel="noopener noreferrer">View merged PR #${Number(p.number)}</a><p class="small muted">You can archive this task or keep chatting. Start a new task for further changes.</p></div></section>`;
}
function markup(task){return '<section class="commit-decision" data-pull-request aria-label="GitHub pull request">'+(merged(task)?content(task.pull_request):'<h3>Pull request workflow</h3><p role="status">Preparing your reviewed branch…</p>')+'</section>';}
const needsSync=p=>p.ci?.state==='merged'&&p.local_sync?.retryable===true;
function content(p){
 if(p.url&&p.ci?.state==='merged'){
  const summary=mergeSummary(p);
  return `<h3>${esc(summary.title)}</h3><p role="status">${esc(summary.description)}</p><a class="subtle-button" href="${esc(safeURL(p.url)||'#')}" target="_blank" rel="noopener noreferrer">View merged PR #${Number(p.number)}</a>${needsSync(p)||!p.local_sync?'<button type="button" data-pr-refresh>Refresh local sync status</button>':''}<p class="small muted">This is the saved record of the merged work. You can archive this task or keep chatting.</p>`;
 }
 if(p.url)return `<h3>Pull request opened.</h3><p><a class="primary-button" href="${esc(safeURL(p.url)||'#')}" target="_blank" rel="noopener noreferrer">Open pull request #${Number(p.number)}</a></p><p role="status">${esc(p.ci?.message||'Your local destination branch is unchanged. Check GitHub CI and review before merging.')}</p>${p.local_sync?'<p role="status">'+esc(p.local_sync.message)+'</p>':''}${p.ci?.checks?.length?'<ul>'+p.ci.checks.map(c=>`<li>${esc(c.name)} · ${esc(c.state)}</li>`).join('')+'</ul>':''}${p.ci?`<p>${p.ci.protected===true?'GitHub branch protection is enabled.':p.ci.protected===false?'This destination has no GitHub branch protection. Configure required checks and PR rules in GitHub settings.':'Branch protection status is unavailable.'}</p>`:''}<button type="button" data-pr-refresh>Refresh GitHub status</button><p class="small muted">GitHub enforces this repository’s required checks, reviews and branch rules. Green local checks alone do not approve a remote merge.</p>`;
 return `<h3>${p.retry?'Finish publishing your reviewed branch.':p.update?'Ready to update your pull request.':'Ready to open a pull request.'}</h3><p><strong>${esc(p.repo)}</strong> · ${esc(p.branch)} → ${esc(p.base)}</p><p>${p.update?'Publishes the newly reviewed commit to the same pull request.':'Publishes the reviewed commit and opens a GitHub pull request.'} Your destination checkout stays unchanged. GitHub checks and your final merge decision follow.</p><button type="button" class="primary-button" data-pr-publish>${p.retry?'Finish publishing':p.update?'Approve & update pull request':'Approve & open pull request'}</button>`;
}
function mount(container,task,api,onPublished=()=>{}){
 const panel=container.querySelector('[data-pull-request]');if(!panel)return;
 if(panel.dataset.mounted)return;panel.dataset.mounted='true';
 let current=null,busy=false;
 async function load(status=false){
  if(busy)return;busy=true;
  if(status)lastStatus.set(task.id,Date.now());
  panel.setAttribute('aria-busy','true');
  try{current=await api('/tasks/'+task.id+(status?'/pull-request-status':'/pull-request-preview'),{});if(!panel.isConnected)return;panel.innerHTML=content(current);bind();
   if(current.update_blocker)panel.insertAdjacentHTML('beforeend','<p role="status">New changes are not ready to publish: '+esc(current.update_blocker)+'</p>');
   if(current.url&&(!['merged','closed','changed'].includes(current.ci?.state)||needsSync(current))){
    const delay=Math.max(0,60000-(Date.now()-(lastStatus.get(task.id)||0)));
    setTimeout(()=>{if(panel.isConnected)void load(true);},delay);
   }
  }
  catch(error){if(panel.isConnected){panel.innerHTML='<h3>Pull request</h3><p role="alert">'+esc(error.message)+'</p><button type="button" data-pr-retry>Retry publication preview</button>';panel.querySelector('[data-pr-retry]').onclick=()=>load(status);}}
  finally{busy=false;panel.removeAttribute('aria-busy');}
 }
 function bind(){
  panel.querySelector('[data-pr-refresh]')?.addEventListener('click',()=>load(true));
  panel.querySelector('[data-pr-publish]')?.addEventListener('click',async e=>{
   if(busy)return;busy=true;e.currentTarget.disabled=true;e.currentTarget.textContent='Publishing reviewed branch…';
   panel.insertAdjacentHTML('beforeend','<p role="status">Sending your approved branch to GitHub. This can take a moment.</p>');
   try{current=await api('/tasks/'+task.id+'/pull-request-publish',{approved:true,id:current.id});if(panel.isConnected){panel.innerHTML=content(current);bind();}onPublished(current);}
   catch(error){if(panel.isConnected){panel.innerHTML='<p role="alert">'+esc(error.message)+'</p><button type="button" data-pr-retry>Retry saved publication</button>';panel.querySelector('[data-pr-retry]').onclick=()=>load();}}
   finally{busy=false;}
  });
 }
 void load();
}
const exported={enabled,merged,mergeSummary,completionMarkup,markup,content,mount,safeURL,needsSync};if(typeof module!=='undefined')module.exports=exported;else root.CheapOSGitWorkflow=exported;
})(typeof globalThis!=='undefined'?globalThis:this);
