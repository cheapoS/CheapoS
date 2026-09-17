/* Unattended proposals and branch outcomes; authorization stays server-owned. */
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.CheapOSBranchUI=value;})(typeof globalThis==='object'?globalThis:this,function(){
'use strict';
const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const short=ref=>String(ref||'').replace(/^refs\/heads\//,'');
function intent(text){
 const clean=String(text||'').replace(/```[\s\S]*?```/g,'').replace(/`[^`]*`|"[^"\n]*"|'[^'\n]*'|“[^”]*”/g,'').split('\n').filter(line=>!/^\s*>/.test(line)).join(' ').trim();
 if(/\b(?:do not|don't|never|avoid)\s+(?:start|begin|launch|run|implement|complete|build|finish)\b/i.test(clean))return 'interactive';
 if(!clean||/^(?:what|why|how|explain|summari[sz]e|describe|does|is|can you explain)\b/i.test(clean))return 'interactive';
 if(/\b(?:start|begin|launch|run)\s+(?:an?\s+)?(?:unattended|branch)\s+run\b/i.test(clean)||/\b(?:implement|complete|build|finish)\b.+\b(?:on|in)\s+(?:an?\s+)?(?:new\s+)?feature branch\b/i.test(clean))return 'offer';
 return 'interactive';
}
function terminalRun(task){return ['merged','left_on_branch'].includes(task?.branch_run?.status);}
function hasRun(task){return Boolean(task?.branch_run);}
function isPlanning(task){return Boolean(task?.planning_request&&task.branch_run&&!task.branch_run.authorization_ref);}
function duration(seconds){const value=Math.max(0,Math.floor(Number(seconds)||0));return value<60?`${value}s`:`${Math.floor(value/60)}m ${value%60}s`;}
function isBusy(task){return Boolean(task&&(task.branch_run?['running','finalizing','merging'].includes(task.branch_run.status)||(task.branch_run.status==='draft'&&['running','waiting_retry'].includes(task.status))||task.status==='stopping':['running','reviewing','waiting_approval','waiting_retry','stopping'].includes(task.status)));}
function isRevisionTarget(task,revisionId){return Boolean(task?.id&&revisionId&&revisionId===task.id);}
function resumeAction(result){return result?.needs_merge_recovery?'merge_recovery':result?.needs_consent?'consent':'resumed';}
function proposedLimits(preferences={}){
 const defaults={dollars:0,output_tokens:2048,reviewer_tokens:50000,check_seconds:90};const limits={};
 for(const [key,fallback] of Object.entries(defaults)){const value=preferences[key]??fallback;if(typeof value!=='number'||!Number.isFinite(value)||value<0)throw new Error('Invalid saved budget: '+key);limits[key]=value;}
 const minutes=preferences.run_minutes??15;if(typeof minutes!=='number'||!Number.isFinite(minutes)||minutes<=0)throw new Error('Invalid saved working-time allowance');limits.working_seconds=Math.round(minutes*60);
 // Item-count-dependent request, worker-turn and action bounds come from the
 // controller and are shown in the returned proposal, never copied per request.
 return limits;
}
function pausePresentation(task) {
 const run=task?.branch_run,d=run?.pause_detail;
 if(!d||d.version!==1||!['paused','blocked'].includes(run.status))return null;
 const names={reviewer_recovery_required:'Choose a reviewer for fresh review',review_identity_unknown:'Historical model identity needs your decision',review_identity_conflict:'Reviewer conflicts with worker history',operator:'Work paused',restart:'Saved work was interrupted',provider_quota:'Provider quota stopped the request',provider_connection:'Provider connection needs attention',missing_setup:'Verification needs setup',command_grant:'A command needs permission',exhausted_work:'Work allowance reached',branch_drift:'Branch changed',authority_changed:'Authorization changed',malformed_output:'Model response could not be used',repeated_work:'Work stopped making progress',essential_clarification:'A decision is needed',repeated_review_dispute:'Review disagreement needs a decision',unknown:'Work stopped'};
 const actions={reviewer:'Choose reviewer',resume:'Resume saved work',models:'Inspect Models',environment:'Inspect task environment',permission:'Review requested permission',limits:'Inspect work limits',reply:'Reply to the question',authorization:'Inspect authorization',inspect:'Inspect saved details',correction:'Review and add a correction',review_dispute:'Inspect review disagreement'};
 const action=run.merge_operation?'resume':d.next_action;
 const details=[d.item_id?'Item: '+d.item_id:'',d.stage?'Stage: '+d.stage:'',d.role?'Role: '+d.role:'',d.model?'Model: '+d.model:'',d.diagnostic_id?'Diagnostic: '+d.diagnostic_id:'',d.cooldown_scope?'Cooldown scope: '+d.cooldown_scope:''].filter(Boolean);
 if(d.cause==='provider_quota')details.push(typeof d.retry_at==='number'&&Number.isFinite(d.retry_at)&&Number.isFinite(new Date(d.retry_at*1000).getTime())?'Reported reset: '+new Date(d.retry_at*1000).toISOString():'Reset time unavailable');
 const saved=task.changes?.length?'Saved edits remain in the task copy.':'The saved task record is retained.';
 return {headline:d.cause==='repeated_work'&&d.role==='worker'?'Worker could not choose the next step after recovery.':names[d.cause]||names.unknown,explanation:String(d.explanation||'Inspect the retained diagnostic.'),saved,action:actions[action]?action:'inspect',actionLabel:run.merge_operation?'Finish saved integration':action==='correction'&&d.cause==='repeated_work'?'Review saved work and continue in chat':actions[action]||actions.inspect,details,question:d.cause==='essential_clarification'?String(run.waiting_for_user||''):''};
}
function projectRun(task){
 const run=task?.branch_run;if(!run)return null;
 const seen=new Set(),items=(run.items||[]).map(item=>{
  const receipt=item.commit_receipt,valid=receipt?.stage==='completed'&&receipt.item_id===item.id&&receipt.run_id===run.id;
  const committed=item.status==='committed'&&valid&&/^[a-f0-9]{40,64}$/.test(receipt.new_tip||'');
  const unchanged=item.status==='satisfied_without_change'&&valid&&receipt.outcome==='satisfied_without_change';
  return {id:item.id,title:item.title,status:item.status,done:committed||unchanged,commit:committed?receipt.new_tip:null,unchanged};
 });
 const milestones=[];
 for(const event of run.events||[]){if(event.kind!=='item_completed'||seen.has(event.id||event.event_key))continue;const item=items.find(i=>i.id===event.detail?.item_id);if(!item?.done||((event.detail?.commit||null)!==item.commit))continue;seen.add(event.id||event.event_key);milestones.push({id:event.id||event.event_key,text:item.unchanged?`${item.title}: reviewed and already satisfied.`:`${item.title} completed and committed as ${item.commit.slice(0,7)}.`});}
 const current=items.findIndex(i=>i.id===run.current_item_id);
 const labels={draft:'Draft',awaiting_authorization:'Ready to inspect',running:'Working',paused:'Paused',blocked:'Needs attention',finalizing:'Final checks and review',ready_for_merge:'Ready for your review',merging:'Merging locally',merged:'Merged locally',left_on_branch:'Saved on feature branch'};
 return {planning:isPlanning(task),measurement:run.plan?.measurement===true,id:run.id,status:run.status,label:isPlanning(task)&&isBusy(task)?'Planning':isPlanning(task)&&/handoffs were tried/.test(task.error||'')?'Planning stopped':isPlanning(task)&&run.pause_reason==='missing_information'?'Needs your reply':run.status==='merged'&&run.merge_receipt?.stage!=='completed'?'Confirming integration':labels[run.status]||'Status unavailable',branch:short(run.feature_ref),target:short(run.target_ref),items,milestones,current:current<0?null:current+1,currentTitle:current<0?'':items[current].title,currentStage:current<0?'':items[current].status,total:items.length,activeSeconds:Number(run.consumption?.working_seconds||0),reason:task.error||run.pause_reason||'',ready:run.status==='ready_for_merge',pendingMerge:Boolean(run.merge_operation),canRecheck:!run.merge_operation&&items.length>0&&items.every(i=>i.done)&&(['ready_for_merge','paused','blocked'].includes(run.status)||(run.status==='finalizing'&&task.status==='paused')),merged:run.status==='merged'&&run.merge_receipt?.stage==='completed'};
}
function proposalReadiness(proposal={}) {
 const value=proposal.readiness;
 if(!value)return {blocked:false,html:''};
 const checks=Array.isArray(value.checks)?value.checks:[];
 const blocked=value.ready!==true||checks.some(c=>c.status!=='ready');
 const blockers=checks.filter(c=>c.status!=='ready');
 const assumptions=Array.isArray(value.assumptions)?value.assumptions:[];
 return {blocked,html:`<section class="branch-readiness" aria-label="Unattended readiness"><strong>${blocked?'Resolve before starting unattended':'Ready to start unattended'}</strong><ul>${checks.map(c=>`<li><strong>${escape(c.label)}</strong> · ${c.status==='ready'?'Ready':'Blocked'}${c.detail?`<br>${escape(c.detail)}`:''}</li>`).join('')}</ul>${blocked?`<p role="alert">${escape(blockers.length?blockers.map(c=>c.detail||c.label).join(' '):'Readiness has not been confirmed. Prepare a refreshed proposal before Start.')}</p>`:''}${assumptions.length?`<h4>Working assumptions</h4><ul>${assumptions.map(a=>`<li>${escape(a)}</li>`).join('')}</ul>`:''}${value.policy?`<p>${escape(value.policy)}</p>`:''}<p>Start authorizes reads and writes in the task copy and the displayed scoped commands once for this run. New authority or environment changes may still pause work.</p></section>`};
}
function savedPlan(task){
 const run=task?.branch_run;if(!run)return null;
 const approved=Boolean(run.authorization_ref),contract=approved?run.authorization?.contract:run;
 const plan=contract?.plan;
 if(approved&&!plan?.items?.length)return {run,approved,incomplete:true};
 if(!plan?.items?.length||(!approved&&run.status==='draft'))return null;
 return {run,contract,plan,approved};
}
function planMarkup(task){
 const saved=savedPlan(task);if(!saved)return '<p class="empty-state">No complete saved proposal is available for this task.</p>';
 if(saved.incomplete)return '<article class="saved-plan"><h2>Approved plan unavailable</h2><p>This older task retains run progress but lacks the original approved plan. Current item text cannot reconstruct its approved scope.</p></article>';
 const {run,contract,plan,approved}=saved;
 const command=c=>typeof c==='string'?c:(c?.argv||c?.command||[]).join(' ');
 const checks=values=>`<ul>${(values||[]).map(c=>`<li><code>${escape(command(c))}</code></li>`).join('')}</ul>`;
 const itemMarkup=(item,prefix)=>{const current=(run.items||[]).find(i=>i.id===item.id);return `<li><details data-event="plan-${escape(prefix+'-'+item.id)}"><summary><strong>${escape(item.title)}</strong> · ${escape((current?.status||'status unavailable').replace(/_/g,' '))}${run.current_item_id===item.id?' · Current item':''}</summary><p class="plan-instructions">${escape(item.instructions)}</p><h4>Acceptance criteria</h4><ul>${(item.acceptance_criteria||[]).map(c=>`<li>${escape(c)}</li>`).join('')}</ul><h4>Required checks</h4>${checks(item.required_checks)}</details></li>`;};
 return `<article class="saved-plan"><h2>${approved?'Approved plan':'Draft proposal'}</h2><p>${escape(contract.original_request||task.title)}</p><p>${escape(short(contract.feature_ref))} · base ${escape(short(contract.base_ref))} · target ${escape(short(contract.target_ref))}</p><p>${approved?'Original approved scope. Progress below comes from saved item state.':'Not yet authorized. Inspect the proposal in Chat before starting.'}</p><ol>${plan.items.map(i=>itemMarkup(i,'original')).join('')}</ol><h3>Final checks</h3>${checks(plan.final_checks)}<details data-event="plan-limits"><summary>${plan.measurement?'Measurement run · uncapped work':plan.uncapped_work?'Uncapped work · ∞':'Work limits'}</summary><ul>${Object.entries(contract.limits||plan.limits||{}).map(([k,v])=>`<li>${escape(k.replace(/_/g,' '))}: ${(plan.uncapped_work||plan.measurement)&&['worker_turns','tool_actions','requests','reviewer_tokens','working_seconds'].includes(k)?'Uncapped':escape(v)}</li>`).join('')}</ul></details>${(run.amendments||[]).length?`<h3>Authorized revisions</h3><p>Added after the original plan; original requirements remain unchanged.</p>${run.amendments.map((a,i)=>`<section><p>Revision ${i+1} · ${escape(a.origin||'origin unavailable')} · authorization ${escape(a.authorization_id||'unavailable')}</p><ol>${a.item?itemMarkup(a.item,'revision'):'<li>Revision content unavailable.</li>'}</ol></section>`).join('')}`:''}</article>`;
}
const HELP=`<details class="branch-help"><summary>How work modes and triggers work</summary><p><strong>Interactive</strong> keeps the ordinary chat and approval flow. <strong>Unattended</strong> prepares a bounded plan from your submitted prompt, project document, or both. Send prepares the plan directly in Chat. Review & start authorizes the inspected plan.</p><p>Prompt example: “Implement a CSV reader and its CLI on a feature branch.” Document example: select <code>docs/utility-plan.md</code>, choose Unattended, then submit. No pasted copy or checkboxes needed.</p><p>Explicit requests to start a branch run in Interactive offer the mode choice. Mentioning a branch, quoting a request, selecting a document, or opening this selector does not start work. Document instructions cannot authorize execution.</p><p>Pause stops the current run; Resume revalidates it. Request changes proposes revision work. Approve &amp; merge locally authorizes only the inspected final integration; a prompt saying “merge when done” does not replace that button.</p></details>`;
function diffSections(text){return String(text||'').split(/(?=^diff --git )/m).filter(Boolean).map(part=>({title:part.startsWith('diff --git ')?part.split('\n',1)[0].slice(11):'Diff continuation',text:part}));}
// Git quotes non-ASCII paths as UTF-8 octal bytes, not JSON escapes.
function diffPath(value,stripPrefix=true){
 let path=String(value||'');
 if(path.startsWith('"')&&path.endsWith('"')){
  const bytes=[];const body=path.slice(1,-1);
  for(let i=0;i<body.length;i++){
   if(body[i]==='\\'){
    const octal=body.slice(i+1).match(/^[0-7]{1,3}/);
    if(octal){bytes.push(parseInt(octal[0],8));i+=octal[0].length;continue;}
    i++;bytes.push(...new TextEncoder().encode(({t:'\t',n:'\n',r:'\r',b:'\b',f:'\f',v:'\v',a:'\x07'}[body[i]])??body[i]));
   }else {const point=String.fromCodePoint(body.codePointAt(i));bytes.push(...new TextEncoder().encode(point));i+=point.length-1;}
  }
  path=new TextDecoder().decode(new Uint8Array(bytes));
 }
 return path==='/dev/null'?null:stripPrefix?path.replace(/^[ab]\//,''):path;
}
function reviewDiffs(text){
 return diffSections(text).map(section=>{
  const lines=section.text.split('\n'),header=lines[0].match(/^diff --git ("(?:\\.|[^"\\])*"|a\/.*?) ("(?:\\.|[^"\\])*"|b\/.*)$/);
  let oldPath=header?diffPath(header[1]):null,path=header?diffPath(header[2]):null;
  const same=lines[0].match(/^diff --git a\/(.*) b\/\1$/);if(same)oldPath=path=same[1];
  for(const line of lines){if(line.startsWith('@@'))break;if(line.startsWith('--- '))oldPath=diffPath(line.slice(4).replace(/\t$/,''));if(line.startsWith('+++ '))path=diffPath(line.slice(4).replace(/\t$/,''));if(line.startsWith('rename from '))oldPath=diffPath(line.slice(12),false);if(line.startsWith('rename to '))path=diffPath(line.slice(10),false);}
  return {...section,path:path||oldPath,oldPath,binary:lines.some(l=>l==='GIT binary patch'||l.startsWith('Binary files '))};
 });
}
function reviewFiles(preview){return (Array.isArray(preview.manifest)?preview.manifest:preview.manifest?.files||preview.files||[]).map(f=>typeof f==='string'?{path:f}:f);}
function fileStats(file){return file.binary||file.added_lines===null?'Binary':Number.isInteger(file.added_lines)?`+${file.added_lines} −${file.removed_lines}`:'Stats unavailable';}
function changedSpan(text, other){
 let start=0,end=0;
 while(start<text.length&&start<other.length&&text[start]===other[start])start++;
 while(end<text.length-start&&end<other.length-start&&text[text.length-1-end]===other[other.length-1-end])end++;
 return escape(text.slice(0,start))+'<mark class="review-inline-change">'+escape(text.slice(start,text.length-end))+'</mark>'+escape(end?text.slice(-end):'');
}
function diffCharacterSummary(lines){
 const changed=lines.filter(l=>/^[+-]/.test(l)&&!l.startsWith('--- ')&&!l.startsWith('+++ '));
 const count=sign=>changed.filter(l=>l[0]===sign).reduce((n,l)=>n+Array.from(l.slice(1)).length,0);
 const dense=changed.some(l=>l.length>301);
 return '<p class="review-character-summary">'+count('-')+' removed characters · '+count('+')+' added characters'+(dense?' · Long changed lines: inspect the removed code, not just the line count.':'')+'</p>';
}
function reviewDiffMarkup(section,raw=false){
 if(!section)return '<p class="review-empty">This file’s diff has not loaded yet.</p>';
 if(raw||section.binary)return `${section.binary?'<p class="review-empty">Binary content cannot be displayed as a text diff. The saved Git patch is shown below.</p>':''}<pre class="review-raw">${escape(section.text)}</pre>`;
 let old=null,next=null;const lines=section.text.split('\n');if(lines.at(-1)==='')lines.pop();
 return diffCharacterSummary(lines)+'<div class="review-code" aria-label="Unified diff; old and new line numbers">'+lines.map((line,index)=>{
  const hunk=line.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
  if(hunk){old=Number(hunk[1]);next=Number(hunk[2]);return `<div class="review-diff-meta hunk">${escape(line)}</div>`;}
  if(old===null&&/^(diff --git |index |--- |\+\+\+ )/.test(line))return '';
  if(old===null||![' ','+','-'].includes(line[0]))return `<div class="review-diff-meta">${escape(line)}</div>`;
  const kind=line[0]==='+'?'add':line[0]==='-'?'remove':'context',before=kind==='add'?'':old++,after=kind==='remove'?'':next++;
  const other=kind==='remove'&&lines[index+1]?.startsWith('+')?lines[index+1]:kind==='add'&&lines[index-1]?.startsWith('-')?lines[index-1]:null;
  const code=other?changedSpan(line.slice(1),other.slice(1)):escape(line.slice(1));
  return `<div class="review-diff-line ${kind}"><span class="review-line-number">${before}</span><span class="review-line-number">${after}</span><span class="review-sign">${escape(line[0])}</span><code>${code||' '}</code></div>`;
 }).join('')+'</div>';
}
function finalReviewMarkup(task,preview){
 const files=reviewFiles(preview),checks=task.branch_run.readiness?.checks||[],review=task.branch_run.readiness?.review;
 const passed=checks.filter(c=>c.record?.passed===true).length;
 const command=c=>{const v=c?.command||c?.argv||[];return Array.isArray(v)?v.join(' '):String(v);};
 const total=key=>files.reduce((n,f)=>n+(Number.isInteger(f[key])?f[key]:0),0);
 return `<div class="review-overview"><p class="review-task-title">${escape(task.title||'Saved branch changes')}</p><p class="review-branch-route"><strong>${escape(short(task.branch_run.feature_ref))}</strong><span>→</span><strong>${escape(short(preview.target_ref||task.branch_run.target_ref))}</strong><span>Local merge · no push</span></p><div class="review-summary"><span>${files.length} files</span><span class="review-add">+${total('added_lines')}</span><span class="review-remove">−${total('removed_lines')}</span><button type="button" data-evidence aria-expanded="false">${checks.length?`${passed}/${checks.length} checks passed`:'Check evidence unavailable'} · ${review?.decision==='APPROVE'?'Final review approved':'Inspect final review'}</button></div><p class="review-blocker" role="status" ${preview.blocker?'':'hidden'}>${escape(preview.blocker)}</p></div>
 <div class="review-workspace"><aside class="review-sidebar" aria-label="Changed files"><label class="review-filter">Find a file<input type="search" data-file-search placeholder="Filter files…"></label><p class="review-progress" data-review-progress></p><nav class="review-file-list" aria-label="Files in this branch"></nav><p class="review-session-note">Review marks are a checklist for this open preview.</p></aside><section class="review-main" aria-label="Selected change"><div class="review-file-toolbar"><div><strong data-file-title></strong><span data-file-stats></span></div><div class="review-diff-controls"><button type="button" data-expand aria-pressed="false">Expand review</button><button type="button" data-previous aria-label="Previous file">←</button><button type="button" data-next aria-label="Next file">→</button><button type="button" data-viewed aria-pressed="false">Mark reviewed</button><button type="button" data-raw aria-pressed="false">Raw patch</button><button type="button" data-wrap aria-pressed="true">Wrap lines</button></div></div><div class="review-diff-viewport wraps" tabindex="0" aria-label="File changes"></div></section></div>
 <section class="review-evidence" hidden tabindex="-1" aria-label="Verification and review evidence"><h3>Verification and final review</h3><p>Evidence saved for feature <code>${escape((preview.feature_tip||'').slice(0,12))}</code>. Opening this preview does not rerun checks.</p><ul>${checks.map(c=>`<li><strong>${c.record?.passed===true?'Passed':c.record?.passed===false?'Failed':'Result unavailable'}</strong><code>${escape(command(c))}</code></li>`).join('')||'<li>No check evidence is available.</li>'}</ul><h4>Independent final review · ${escape(review?.decision||'unavailable')}</h4><p class="review-feedback">${escape(review?.feedback||'No final reviewer feedback was saved.')}</p><h4>Completed work</h4><ul>${(task.branch_run.items||[]).map(i=>`<li>${escape(i.title)} · ${escape(String(i.status||'unknown').replace(/_/g,' '))}${i.commit_receipt?.new_tip?` · <code>${escape(i.commit_receipt.new_tip.slice(0,12))}</code>`:''}</li>`).join('')}</ul><details><summary>Exact revisions and complete manifest</summary><p>Feature <code>${escape(preview.feature_tip)}</code><br>Inspected target <code>${escape(preview.target_tip)}</code><br>Base <code>${escape(preview.base_sha)}</code></p><ul>${files.map(f=>`<li><code>${escape(f.path)}</code> · ${escape(f.status||'Changed')} · ${fileStats(f)}</li>`).join('')}</ul></details><button type="button" data-back-diff>Back to files</button></section>
 <footer class="review-footer"><div><span data-load-status role="status"></span><button type="button" data-retry-diff hidden>Retry loading diff</button><p class="branch-error" role="alert"></p></div><div class="branch-actions"><button type="button" data-refresh>Refresh preview</button><button type="button" data-recheck>Recheck changes</button>${preview.resolve_available?'<button type="button" data-resolve-conflicts>Resolve conflicts &amp; recheck</button>':''}${preview.update_available&&!preview.resolve_available?'<button type="button" data-update-branch>Update branch &amp; recheck</button>':''}<button type="button" data-leave>Leave on branch</button><button type="button" data-revise>Request changes</button><button type="button" class="primary" data-merge>Approve &amp; merge locally</button></div></footer>`;
}
function finalDiffState(preview){
 let text=typeof preview.diff==='string'?preview.diff:'',cursor=preview.next_cursor??null;
 const complete=()=>cursor===null&&typeof preview.diff==='string'&&(!Number.isInteger(preview.diff_length)||Array.from(text).length===preview.diff_length);
 return {get:()=>({text,cursor,complete:complete()}),append(page){
  if(page.offset!==cursor||typeof page.diff!=='string'||(preview.manifest?.id&&page.manifest_id!==preview.manifest.id)||page.total!==preview.diff_length)throw Error('The saved diff changed. Refresh the preview before merging.');
  if(page.next_cursor!==null&&(!Number.isInteger(page.next_cursor)||page.next_cursor<=cursor))throw Error('Invalid diff page. Refresh the preview.');
  text+=page.diff;cursor=page.next_cursor;
  if(cursor===null&&!complete())throw Error('The complete diff was not received. Refresh the preview before merging.');
 }};
}
function mountFinalDiff(d,task,preview,api){
 const files=reviewFiles(preview),state=finalDiffState(preview),viewed=new Set(),positions=new Map();
 const nav=d.querySelector('.review-file-list'),viewport=d.querySelector('.review-diff-viewport'),merge=d.querySelector('[data-merge]'),status=d.querySelector('[data-load-status]'),retry=d.querySelector('[data-retry-diff]');
 let selected=0,raw=false,loading=false,invalid=false,blocked=Boolean(preview.blocker),sections=[];
 function update(){
  const current=state.get();merge.disabled=terminalRun(task)||Boolean(task.archived_at||task.trashed_at)||!preview.preview_id||preview.merge_available!==true||blocked||invalid||!current.complete;
  d.querySelector('[data-viewed]').disabled=!current.complete||!files.length||!sections.some(s=>s.path===files[selected]?.path||s.oldPath===files[selected]?.path);
  status.textContent=loading?'Loading the complete saved diff…':current.complete?(terminalRun(task)?'Complete diff loaded · saved branch is read-only.':'Complete diff loaded · merge uses the inspected revisions.'):'Diff incomplete · merge is unavailable until it finishes loading.';
  d.querySelector('[data-review-progress]').textContent=`${viewed.size} of ${files.length} files reviewed`;
 }
 function navigation(){
  const filter=d.querySelector('[data-file-search]').value.toLowerCase();
  nav.innerHTML=files.map((f,i)=>({f,i})).filter(({f})=>f.path.toLowerCase().includes(filter)).map(({f,i})=>`<button type="button" data-file="${i}" ${selected===i?'aria-current="true"':''}><span class="review-file-name">${escape(f.path)}</span><span class="review-file-meta">${escape(({A:'Added',M:'Modified',D:'Deleted',T:'Type changed'}[f.status])||'Changed')} · ${fileStats(f)}${viewed.has(i)?' · Reviewed':''}</span></button>`).join('')||'<p class="review-empty">No matching files.</p>';
  for(const button of nav.querySelectorAll('[data-file]'))button.onclick=()=>{positions.set(selected,viewport.scrollTop);selected=Number(button.dataset.file);navigation();content();viewport.scrollTop=positions.get(selected)||0;nav.querySelector('[aria-current]')?.focus({preventScroll:true});};
 }
 function content(){
  const file=files[selected],section=sections.find(s=>s.path===file?.path||s.oldPath===file?.path);
  d.querySelector('[data-file-title]').textContent=file?.path||'No changed files';d.querySelector('[data-file-stats]').textContent=file?fileStats(file):'';
  const button=d.querySelector('[data-viewed]');button.textContent=viewed.has(selected)?'Reviewed ✓':'Mark reviewed';button.setAttribute('aria-pressed',String(viewed.has(selected)));
  d.querySelector('[data-previous]').disabled=selected===0;d.querySelector('[data-next]').disabled=selected>=files.length-1;
  viewport.innerHTML=file?reviewDiffMarkup(section,raw):'<p class="review-empty">There are no file changes in this saved branch.</p>';update();
 }
 function move(delta){const index=selected+delta;if(index<0||index>=files.length)return;positions.set(selected,viewport.scrollTop);selected=index;navigation();content();viewport.scrollTop=positions.get(selected)||0;nav.querySelector('[aria-current]')?.scrollIntoView({block:'nearest'});}
 d.querySelector('[data-previous]').onclick=()=>move(-1);d.querySelector('[data-next]').onclick=()=>move(1);
 d.querySelector('[data-file-search]').oninput=navigation;
 d.querySelector('[data-viewed]').onclick=()=>{const top=viewport.scrollTop;viewed.has(selected)?viewed.delete(selected):viewed.add(selected);navigation();content();viewport.scrollTop=top;};
 d.querySelector('[data-raw]').onclick=e=>{raw=!raw;e.currentTarget.setAttribute('aria-pressed',String(raw));content();};
 const expand=d.querySelector('[data-expand]');
 if(expand)expand.onclick=()=>{const active=d.classList.toggle('review-expanded');expand.textContent=active?'Exit expanded review':'Expand review';expand.setAttribute('aria-pressed',String(active));};
 d.querySelector('[data-wrap]').onclick=e=>{const wrap=viewport.classList.toggle('wraps');e.currentTarget.setAttribute('aria-pressed',String(wrap));};
 const evidence=d.querySelector('.review-evidence'),workspace=d.querySelector('.review-workspace');
 d.querySelector('[data-evidence]').onclick=e=>{workspace.hidden=true;evidence.hidden=false;e.currentTarget.setAttribute('aria-expanded','true');evidence.focus();};
 d.querySelector('[data-back-diff]').onclick=()=>{evidence.hidden=true;workspace.hidden=false;d.querySelector('[data-evidence]').setAttribute('aria-expanded','false');viewport.focus();};
 async function load(){
  if(loading)return;loading=true;retry.hidden=true;update();
  try{
   while(state.get().cursor!==null&&d.isConnected){
    const page=await api('/tasks/'+task.id+'/branch-final-diff',{preview_id:preview.preview_id,cursor:state.get().cursor});
    if(!d.isConnected)return;
    state.append(page);if(page.blocker){blocked=true;const banner=d.querySelector('.review-blocker');banner.hidden=false;banner.textContent=page.blocker;}
    const top=viewport.scrollTop;sections=reviewDiffs(state.get().text);content();viewport.scrollTop=top;
   }
   if(!state.get().complete)throw Error('The complete diff is unavailable. Refresh this preview before merging.');
  }catch(error){invalid=true;if(d.isConnected){d.querySelector('.branch-error').textContent=error.message||String(error);retry.hidden=state.get().cursor===null;}}
  finally{loading=false;if(d.isConnected)update();}
 }
 retry.onclick=()=>{invalid=false;d.querySelector('.branch-error').textContent='';load();};
 sections=reviewDiffs(state.get().text);navigation();content();load();
 return {state,viewed};
}
function technicalEvents(task){return [...(task?.events||[])].reverse();}
function technicalText(value){return String(value??'').slice(0,8192).replace(/((?:api[_ -]?key|authorization|password|secret|access[_ -]?token)\s*[=:]\s*)[^\s,;]+/gi,'$1[redacted]').replace(/Bearer\s+[^\s,;]+/gi,'Bearer [redacted]').replace(/sk-[A-Za-z0-9_-]{8,}/g,'[redacted]');}
function technicalMarkup(task){
 const events=technicalEvents(task),pause=pausePresentation(task);
 const cause=pause?`<section class="activity-status"><h3>${escape(pause.headline)}</h3><p>${escape(pause.explanation)}</p><p>${escape(pause.actionLabel)} · ${escape(pause.saved)}</p><button class="outline-button" data-log-chat>Back to chat actions</button></section>`:task?.error?`<section class="activity-status"><h3>Saved failure</h3><p>${escape(technicalText(task.error))}</p><button class="outline-button" data-log-chat>Back to chat actions</button></section>`:'';
 const fields=['error','error_code','code','reason','failure_reason','stage','role','model','requested_model','selected_model','actual_model','request_id','diagnostic_id','exit_code','status','summary','message','command','output','retry_at','cooldown_scope'];
 const rows=events.map(e=>{const d=e.detail&&typeof e.detail==='object'?e.detail:{};const values=fields.filter(k=>d[k]!==undefined&&(typeof d[k]!=='object'||Array.isArray(d[k])&&d[k].every(v=>typeof v==='string'))).map(k=>`<div><dt>${escape(k.replace(/_/g,' '))}</dt><dd><pre>${escape(technicalText(Array.isArray(d[k])?d[k].join(' '):d[k]))}</pre></dd></div>`).join('');return `<details class="activity-card" data-event="raw-${escape(e.id)}"><summary><strong>${escape(technicalText(e.title||e.kind||'Saved event'))}</strong><span>${escape(e.kind||'')} · ${escape(d.role||e.role||'')} ${escape(technicalText(d.model||d.actual_model||''))}</span><time>${escape(e.time||'Time unavailable')}</time></summary><div class="detail-body"><dl>${values}</dl>${typeof e.detail==='string'?`<p>${escape(technicalText(e.detail))}</p>`:!values?'<p>No additional diagnostic fields were saved for this event.</p>':''}</div></details>`;}).join('');
 return `<div class="view-title"><div><h2>Technical logs</h2><p>Newest saved event first · ${events.length} retained events. Text is bounded; raw provider payloads and credentials are omitted.</p></div></div>${cause}${task?.events_truncated||task?.history_truncated?'<p>Older history was truncated in the saved record.</p>':''}${rows||'<p class="empty-state">No technical events have been saved for this task.</p>'}`;
}
function fullSuiteConsent(response){const checks=response.full_suite_checks||[];if(!checks.length)return '';const seconds=response.full_suite_last_seconds;return `<section class="execution-notice"><h3>Full-suite test approval</h3><p>These broad checks can take longer than focused tests. Last measured runtime: ${Number.isFinite(seconds)?escape(seconds)+' seconds':'unknown'}. Approve once before starting this plan.</p><ul>${checks.map(c=>`<li><code>${escape(typeof c==='string'?c:Array.isArray(c)?c.join(' '):Array.isArray(c.argv||c.command)?(c.argv||c.command).join(' '):String(c.command||''))}</code></li>`).join('')}</ul><label><input type="checkbox" name="full_suite_approved">I approve these full-suite checks for this plan</label></section>`;}
async function mergeAndPublish({api,task,values,onTask=()=>{},refresh=()=>Promise.resolve()}){
 const saved=await api('/tasks/'+task.id+'/branch-merge',values);
 if(saved?.id===task.id&&saved.branch_run)onTask(saved);
 // Sidebar/connection refresh must not delay the confirmed task result.
 Promise.resolve().then(()=>refresh({background:true})).catch(()=>{});
 return saved;
}
function startController({api,onChange=()=>{},onTask=()=>{},transition=()=>{}}){
 const records=new Map();
 async function reconcile(id){const record=records.get(id);if(!record)return;try{const task=await api('/tasks/'+id);record.status=task.branch_run?.authorization_ref?(['draft','awaiting_authorization'].includes(task.branch_run.status)?'partial':'accepted'):'rejected';record.error=record.status==='accepted'?'':record.status==='partial'?'Authorization was saved, but startup did not complete. '+(record.error||task.error||'Inspect the saved task setup before continuing.'):(record.error||'Start was not accepted. Inspect the saved proposal before starting again.');if(task.id===id)onTask(task);}catch(_){record.status='unknown';record.error='The Start outcome is unknown. Check saved status before trying again.';}onChange(id);return record;}
 function start(proposal){const id=proposal.task_id,prior=records.get(id);if(prior&&['pending','unknown','partial','accepted'].includes(prior.status))return prior.promise||Promise.resolve(prior);
 const captured=structuredClone(proposal),record={status:'pending',proposal:captured,error:'',started_at:new Date().toISOString()};records.set(id,record);transition(id);onChange(id);
 record.promise=(async()=>{try{const task=await api('/tasks/'+id+'/branch-start',{proposal_id:captured.proposal_id,approved:true,...(captured.full_suite_approved===true?{full_suite_approved:true}:{})});record.status='accepted';if(task?.id===id)onTask(task);onChange(id);}catch(error){record.error=error.message||String(error);await reconcile(id);}return record;})();return record.promise;
 }
 function retry(id){const record=records.get(id);if(record?.status!=='partial')return Promise.resolve(record);record.status='rejected';return start(record.proposal);}
 return {start,retry,reconcile,get:id=>records.get(id)};
}
function planningPayload(values,defaults={}){
 if(!values.repository)throw new Error('Open a project before preparing a plan.');
 if(!String(values.prompt||'').trim()&&!String(values.document||'').trim())throw new Error('Enter a prompt or a project document path.');
 return {...values,prompt:String(values.prompt||'').trim(),document:String(values.document||'').trim(),base_ref:values.base_ref||defaults.base_ref,target_ref:values.target_ref||defaults.target_ref,measurement:values.measurement===true};
}
function proposalValidation(initial,validate){
 let current=initial,revision=0,dirty=false,pending=false;
 return {edit(){revision++;dirty=true;},get:()=>({current,dirty,pending,canStart:!dirty&&!pending&&Boolean(current?.proposal_id)}),async validate(values){if(pending)return null;pending=true;const version=revision;try{const result=await validate(values);if(version!==revision)return null;current=result;dirty=false;return result;}finally{pending=false;}}};
}
function mount(options){
 const {api,getState,selectTask,refresh,toast=()=>{}}=options;
 const starts=startController({api,onTask:task=>options.receiveStartedTask?.(task),transition:id=>options.openStartedChat?options.openStartedChat(id):selectTask(id),onChange:id=>{if(getState().task?.id===id)options.renderCurrent?.();}});
 const controls=options.controls||document.querySelector('.composer-controls'),input=options.input||document.querySelector('#chat-input');
 if(!controls||!input)throw new Error('Branch UI needs the chat composer');
 const storageKey='cheapos-branch-drafts-v1';let drafts={};try{drafts=JSON.parse(localStorage.getItem(storageKey)||'{}');if(!drafts||typeof drafts!=='object')drafts={};}catch(_){}
 let currentKey=null,busy=false,busySelection=null,interactiveOnce=false,proposal=null,finalPreview=null,summaryHTML='',activeDialog=null,startState=null;const detailStates=new Map();
 const group=document.createElement('div');group.className='branch-mode-control';
 group.innerHTML='<label>Work mode <select aria-label="Work mode"><option value="interactive">Interactive</option><option value="unattended">Unattended</option></select></label>';
 controls.prepend(group);const selector=group.querySelector('select');
 const documentRow=document.createElement('div');documentRow.className='branch-document-row';documentRow.hidden=true;documentRow.innerHTML='<label>Project document <input type="text" placeholder="docs/plan.md (optional)" aria-label="Project document path" autocomplete="off"></label><details class="planning-overrides"><summary>Planning settings · optional</summary><p>Uses the open project’s committed default branch. Uncommitted source edits stay outside the run.</p><label>Committed base override<input data-planning="base_ref" placeholder="Project default branch"></label><label>Local target override<input data-planning="target_ref" placeholder="Project default branch"></label><label>Feature branch override<input data-planning="feature_ref" placeholder="Generate a new feature branch"></label><label class="planning-measurement"><input data-planning="measurement" type="checkbox">Measurement run · track usage without work limits</label><p>Choose measurement before Send for a live qualification trial. Planning uses the configured planner and current spending policy. Execution is approved later.</p></details><p class="branch-input-error" role="alert"></p>'+HELP;
 input.after(documentRow);const documentInput=documentRow.querySelector('input');
 const key=()=>getState().task?.id||getState().project?.path||'new';
 function save(){drafts[key()]={mode:selector.value,document:documentInput.value,prompt:input.value,overrides:Object.fromEntries([...documentRow.querySelectorAll('[data-planning]')].map(el=>[el.dataset.planning,el.type==='checkbox'?el.checked:el.value]))};try{localStorage.setItem(storageKey,JSON.stringify(drafts));}catch(_){} }
 function sync(){const next=key();if(next!==currentKey){currentKey=next;const draft=drafts[next]||{};selector.value=draft.mode==='unattended'?'unattended':'interactive';documentInput.value=draft.document||'';for(const el of documentRow.querySelectorAll('[data-planning]')){const value=draft.overrides?.[el.dataset.planning];if(el.type==='checkbox')el.checked=value===true;else el.value=value||'';}if(!input.value&&draft.prompt)input.value=draft.prompt;finalPreview=null;summaryHTML='';}const run=getState().task?.branch_run;selector.disabled=hasRun(getState().task);if(selector.disabled)selector.value='unattended';documentRow.hidden=selector.value!=='unattended'||selector.disabled;}
 selector.onchange=()=>{save();sync();options.onDraftChange?.();};documentInput.oninput=()=>{save();options.onDraftChange?.();};input.addEventListener('input',save);for(const el of documentRow.querySelectorAll('[data-planning]'))el.addEventListener('input',save);
 function dialog(title,body){const previous=document.activeElement,d=document.createElement('dialog');d.className='branch-dialog modal'+(['Review & start','Inspect revision work'].includes(title)?' planner-dialog':'');d.innerHTML=`<div class="branch-dialog-heading"><h2>${escape(title)}</h2><button type="button" data-close aria-label="Close">×</button></div>${body}<p class="branch-error" role="alert"></p>`;document.body.append(d);d.querySelector('[data-close]').onclick=()=>d.close();d.addEventListener('close',()=>{d.remove();if(activeDialog===d)activeDialog=null;previous?.isConnected&&previous.focus();});d.showModal();activeDialog=d;return d;}
 function error(d,e){const node=d.querySelector('.branch-error');if(node){node.textContent=e.message||String(e);node.tabIndex=-1;node.focus();}else toast(e.message||String(e));}
 async function guarded(button,fn,d){if(button.disabled)return;button.disabled=true;try{await fn();}catch(e){error(d,e);}finally{if(button.isConnected)button.disabled=false;}}
 function settings(){const state=getState(),overrides=Object.fromEntries([...documentRow.querySelectorAll('[data-planning]')].map(el=>[el.dataset.planning,el.type==='checkbox'?el.checked:el.value.trim()]));return {repository:state.project?.path||state.task?.source,prompt:input.value.trim(),document:documentInput.value.trim(),...overrides,feature_ref:overrides.feature_ref||'refs/heads/feature/job-'+Date.now().toString(36),uncapped_work:state.preferences?.limits?.uncapped_work===true,limits:proposedLimits(state.preferences?.limits||{})};}
 async function submitPlanning(retry){
  if(busy)return;let values;const errorNode=documentRow.querySelector('.branch-input-error');errorNode.textContent='';
  try{values=planningPayload(retry||settings());}catch(err){errorNode.textContent=err.message;errorNode.tabIndex=-1;errorNode.focus();return;}
  busy=true;save();const submittedInput=input.value,submittedKey=key(),draftSignature=JSON.stringify(drafts[key()]);
  const selection=options.openPlanningChat?.();busySelection=selection;const payload={...values,planning_id:values.planning_id||(globalThis.crypto?.randomUUID?.()||String(Date.now()))};startState={request:payload,selection,draftSignature,error:null};renderStart();options.onDraftChange?.();
  try{
   if(!payload.base_ref||!payload.target_ref){const defaults=await api('/branch-runs/project',{repository:payload.repository});Object.assign(payload,planningPayload(payload,defaults));}
   const result=await api('/branch-runs/plan-start',payload);
   if(startState?.selection===selection&&getState().selection===selection){startState=null;if(input.value===submittedInput){input.value='';delete drafts[submittedKey];try{localStorage.setItem(storageKey,JSON.stringify(drafts));}catch(_){}}await selectTask(result.task_id);}await refresh();
  }catch(err){if(getState().selection===selection){startState={request:payload,selection,draftSignature,error:err.message||String(err)};renderStart();}}
  finally{busy=false;options.onDraftChange?.();}
 }
 function renderStart(){
  if(!startState||getState().task||getState().selection!==startState.selection)return false;
  const view=document.querySelector('#chat-view');if(!view)return false;
  const {request,error:failure}=startState;
  view.innerHTML=`<article class="branch-summary"><strong>You</strong><p>${escape(request.prompt||'Plan work from '+request.document)}</p></article><article class="branch-summary cheapos-response"><strong>cheapoS</strong><p ${failure?'role="alert"':'role="status"'}>${escape(failure||'Starting your planning chat…')}</p>${failure?'<p>Your request is saved. Adjust it below or try again.</p><button type="button" data-retry-planning>Try again</button>':''}</article>`;
  const retry=view.querySelector('[data-retry-planning]');if(retry)retry.onclick=()=>submitPlanning(request);return true;
 }
 function commandText(value){if(typeof value==='string')return value;const command=value?.argv||value?.command||[];return typeof command==='string'?command:command.join(' ');}
 function showProposal(existingDialog){
  const captured=proposal,contract=captured.contract,plan=contract?.plan,task=getState().task;
  if(!plan?.items?.length){toast('The planner did not return a valid finite plan. Your draft is preserved.');return;}
  const readiness=proposalReadiness(captured),metrics=(task?.request_metrics||[]).filter(r=>r.role==='planner'),last=metrics.at(-1),planner=last?.served_model||last?.model||task?.providers?.planner?.model||'Identity unavailable';
  const usage=task?.usage?.planner;
  const body=`<div class="branch-review-body"><p><strong>${escape(contract.original_request||task?.title||'Document-based job')}</strong></p>${contract.inputs?.document?.path?`<p>Captured document: <code>${escape(contract.inputs.document.path)}</code></p>`:''}<button type="button" class="text-link" data-revise-scope>Discuss scope changes in this chat</button><p class="branch-subtle">Project <code>${escape(contract.project?.source||captured.request?.repository)}</code> · committed base ${escape(short(contract.base_ref))} at ${escape((contract.base_sha||'').slice(0,12))}. Uncommitted source edits are excluded. Changing the source or committed base requires a new captured planning request.</p><form><h3>Proposed work</h3><ol class="branch-plan-items">${plan.items.map((item,i)=>`<li><label>Task ${i+1}<input data-title="${i}" value="${escape(item.title)}" maxlength="120" required></label><label>Instructions<textarea data-instructions="${i}" rows="3" required>${escape(item.instructions)}</textarea></label><label>Acceptance criteria · one per line<textarea data-criteria="${i}" rows="3" required>${escape(item.acceptance_criteria.join('\n'))}</textarea></label><label>Required checks · one command per line<textarea data-checks="${i}" rows="2" required>${escape(item.required_checks.map(commandText).join('\n'))}</textarea></label></li>`).join('')}</ol><label>Final integration checks<textarea data-final-checks rows="2" required>${escape((plan.final_checks||[]).map(commandText).join('\n'))}</textarea></label><h3>Execution settings</h3><p>Planner used: <strong>${escape(planner)}</strong>${last?.served_model?' · reported model identity':last?' · requested identity; served model unavailable':task?.providers?.planner?.model?' · saved configuration; actual identity unavailable':''}</p><p>Planning already accounted: ${usage?`${Number(usage.tokens||0).toLocaleString()} tokens · $${Number(usage.cost||0).toFixed(4)}`:'usage unavailable in this saved record'}. Execution edits do not renew or increase the planning allowance.</p><p>${escape(contract.model_policy?.execution?.mode||'Configured placement')} · ${escape(['worker','reviewer'].map(role=>role+': '+(contract.model_policy?.providers?.[role]?.model||'authorized automatic route, selected when needed')).join(' · '))}</p><p class="branch-subtle">Model access stays bound to this captured policy. Changing providers or destinations requires a new planning request with those configured choices.</p><label class="planning-measurement"><input name="uncapped_work" type="checkbox" ${plan.uncapped_work||plan.measurement?'checked':''}>Uncapped work · ∞</label><p>Remove cumulative work caps while keeping spending limits, permissions and review. Per-command timeouts and output limits remain in effect.</p><details class="review-execution"><summary>Branches, allowances and measurement</summary><div class="branch-ref-fields"><label>Local target<input name="target_ref" value="${escape(contract.target_ref)}" required></label><label>Feature branch<input name="feature_ref" value="${escape(contract.feature_ref)}" required></label></div><label class="planning-measurement"><input name="measurement" type="checkbox" ${plan.measurement?'checked':''}>Measurement execution · track usage without work limits</label><p>Measurement is an explicit execution choice. It does not change previously authorized planning or permit paid fallback.</p><div class="review-limit-grid">${Object.entries(plan.limits||contract.limits||{}).map(([name,value])=>`<label>${escape(name.replace(/_/g,' '))}<input data-limit="${escape(name)}" type="number" min="0" step="${name==='dollars'?'0.01':'1'}" value="${escape(value)}" required></label>`).join('')}</div></details><details class="review-permissions"><summary>Exact test permission scopes</summary><ul>${(contract.check_scope||[]).map(scope=>`<li><code>${escape(commandText(scope))}</code>${scope.kind?` · ${escape(scope.kind)}`:''}</li>`).join('')||'<li>Inspect the required checks above. Complete validated command scopes must be available before Start.</li>'}</ul><p>Start authorizes only the displayed checks in this private task copy. New commands or changed scope may still need approval. Feature commits are local; merge and push remain separate decisions.</p></details>${fullSuiteConsent(captured)}<div data-review-readiness>${readiness.html}</div><p data-review-status role="status">${readiness.blocked?'Resolve the listed setup issue before Start.':'This proposal is current and ready for your review.'}</p><p class="branch-error" role="alert"></p><div class="branch-actions"><button type="submit" class="primary" ${readiness.blocked?'disabled':''}>Start run</button><button type="button" data-validate hidden>Validate changes</button><button type="button" data-close-plan>Keep draft</button></div></form></div>`;
  const d=existingDialog?.isConnected?existingDialog:dialog('Review & start',body);
  if(existingDialog?.isConnected)d.querySelector('.branch-review-body').outerHTML=body;
  const form=d.querySelector('form'),start=form.querySelector('[type=submit]'),validate=form.querySelector('[data-validate]'),status=form.querySelector('[data-review-status]');
  const validation=proposalValidation(captured,values=>api('/tasks/'+captured.task_id+'/branch-proposal-edit',values));
  const edited=event=>{if(event?.target?.name==='full_suite_approved')return;validation.edit();start.disabled=true;validate.hidden=false;validate.disabled=validation.get().pending;status.textContent='Changes need validation. Start is disabled until this displayed proposal is current.';};
  const workChoice=form.elements.uncapped_work,measurementChoice=form.elements.measurement;
  const showWorkLimits=()=>{for(const el of form.querySelectorAll('[data-limit]'))if(['worker_turns','requests','tool_actions','reviewer_tokens','working_seconds'].includes(el.dataset.limit))el.closest('label').hidden=workChoice.checked;};
  workChoice.onchange=()=>{if(!workChoice.checked)measurementChoice.checked=false;showWorkLimits();};
  measurementChoice.onchange=()=>{if(measurementChoice.checked)workChoice.checked=true;showWorkLimits();};
  showWorkLimits();
  form.oninput=edited;form.onchange=edited;d.querySelector('[data-close-plan]').onclick=()=>d.close();
  d.querySelector('[data-revise-scope]').onclick=()=>{d.close();options.planningGuidance?.(captured.task_id);input.focus();};
  validate.onclick=async()=>{
   if(!form.reportValidity()||validation.get().pending)return;
   const next=structuredClone(plan);next.items.forEach((item,i)=>{item.title=form.querySelector(`[data-title="${i}"]`).value;item.instructions=form.querySelector(`[data-instructions="${i}"]`).value;item.acceptance_criteria=form.querySelector(`[data-criteria="${i}"]`).value.split('\n').filter(x=>x.trim());item.required_checks=form.querySelector(`[data-checks="${i}"]`).value.split('\n').filter(x=>x.trim());});next.final_checks=form.querySelector('[data-final-checks]').value.split('\n').filter(x=>x.trim());next.measurement=form.elements.measurement.checked;next.uncapped_work=form.elements.uncapped_work.checked;for(const el of form.querySelectorAll('[data-limit]'))next.limits[el.dataset.limit]=Number(el.value);
   const values={repository:contract.project?.source||captured.request?.repository,prompt:contract.original_request,inputs:contract.inputs,base_ref:contract.base_ref,target_ref:form.elements.target_ref.value,feature_ref:form.elements.feature_ref.value,plan:next};
   validate.disabled=true;status.textContent='Validating the displayed plan and execution settings…';form.querySelector('.branch-error').textContent='';
   try{const result=await validation.validate(values);if(!result){status.textContent='Fields changed during validation. Validate the current values before Start.';return;}proposal={...result,request:captured.request};showProposal(d);}catch(err){error(form,err);status.textContent='Validation failed. Your edits are preserved; correct the reported field or setup issue and validate again.';const message=String(err.message||'');for(const el of form.querySelectorAll('[name],[data-limit]'))if(message.toLowerCase().includes((el.name||el.dataset.limit).replace(/_/g,' ').toLowerCase()))el.setAttribute('aria-invalid','true');}finally{if(validate.isConnected)validate.disabled=false;}
  };
  form.onsubmit=e=>{e.preventDefault();if(!validation.get().canStart||readiness.blocked)return;if((captured.full_suite_checks||[]).length&&!form.elements.full_suite_approved?.checked){error(form,new Error('Approve the listed full-suite checks before starting, or revise the checks.'));return;}guarded(start,async()=>{const exact={...validation.get().current,...(form.elements.full_suite_approved?.checked?{full_suite_approved:true}:{})},submittedInput=input.value,submittedKey=key();d.close();const result=await starts.start(exact);if(result.status==='accepted'){if(key()===submittedKey&&input.value===submittedInput){delete drafts[submittedKey];try{localStorage.setItem(storageKey,JSON.stringify(drafts));}catch(_){}input.value='';}if(proposal===captured)proposal=null;}await refresh();},d);};
 }
 function render(task){sync();const view=document.querySelector('#chat-view');if(!view)return;let panel=view.querySelector('#branch-run-summary');const p=projectRun(task),pause=pausePresentation(task),owner=view.querySelector('[data-operation-actions]');if(!p||!owner){panel?.remove();return;}if(!panel){panel=document.createElement('section');panel.id='branch-run-summary';panel.className='branch-operation-actions';owner.append(panel);summaryHTML='';}
 const starting=starts.get(task.id);const startup=starting&&(starting.status!=='accepted'||!task.branch_run.authorization_ref)?`<section class="branch-start-status" role="${['pending','accepted'].includes(starting.status)?'status':'alert'}"><p>${escape(starting.status==='pending'?'Starting your approved plan… Awaiting server confirmation.':starting.status==='accepted'?'Plan accepted. Loading the saved run…':starting.error)}</p>${['pending','accepted'].includes(starting.status)?`<span data-start-time="${escape(starting.started_at)}">0s</span>`:''}${['unknown','partial'].includes(starting.status)?`<button type="button" data-reconcile-start>Check saved start status</button>${starting.status==='partial'?'<button type="button" data-retry-start>Retry saved startup</button>':''}`:starting.status==='rejected'?'<p>Inspect the saved proposal to correct or start it again.</p>':''}</section>`:'';
 const continuation=getState().branchResumeStatus?.get(task.id);
 const continuationHTML=continuation?`<section class="branch-start-status" role="${continuation.status==='pending'?'status':'alert'}"><strong>${continuation.status==='pending'?'Continuing saved work…':'Could not continue saved work'}</strong><p>${continuation.status==='pending'?'Checking the saved run and its existing permissions. Your guidance and edits are kept.':escape(continuation.message)}</p></section>`:'';
 const html=`${startup}${continuationHTML}${pause?`<section class="branch-pause" aria-label="Paused work"><strong>${escape(pause.headline)}</strong><p>${escape(pause.explanation)} ${escape(pause.saved)}</p>${pause.question?`<p>${escape(pause.question)}</p>`:''}<details data-pause-details><summary>Pause details</summary><ul>${pause.details.map(line=>`<li>${escape(line)}</li>`).join('')}</ul></details><button type="button" data-pause-action>${escape(pause.actionLabel)}</button>${pause.action!=='resume'&&task.branch_run.authorization_ref&&!p.planning?`<button type="button" data-resume ${continuation?.status==='pending'?'disabled':''}>Resume</button>`:''}<button type="button" data-view-logs>View technical logs</button></section>`:''}${!pause&&p.reason?`<p class="branch-run-reason">${escape(p.reason.replace(/_/g,' '))}</p>`:''}<div class="branch-actions">${['merged','left_on_branch'].includes(p.status)?'<button type="button" data-new-chat>Start a new chat</button>':''}${!pause&&!p.planning&&(['paused','blocked'].includes(p.status)||p.pendingMerge)&&!p.canRecheck?`<button type="button" data-resume>${p.pendingMerge?'Finish saved integration':'Resume run'}</button>`:''}${!pause&&!p.planning&&p.canRecheck?'<button type="button" data-recheck-run>Recheck changes</button>':''}${!p.planning&&(p.ready||p.canRecheck||p.status==='left_on_branch')?'<button type="button" data-preview>Review changes</button>':''}${p.status==='awaiting_authorization'&&!['pending','unknown','accepted'].includes(starting?.status)?(task.branch_run.authorization_ref?'<button type="button" data-finish-startup>Finish saved startup</button>':'<button type="button" data-proposal>Review &amp; start</button>'):''}</div><p class="branch-error" role="alert"></p>`;
 if(html===summaryHTML)return;const pauseExpanded=panel.querySelector('[data-pause-details]')?.open??detailStates.get(p.id+':pause');const expanded=panel.querySelector('[data-branch-details]')?.open??detailStates.get(p.id);panel.innerHTML=html;summaryHTML=html;const details=panel.querySelector('[data-branch-details]');if(details){if(expanded)details.open=true;details.ontoggle=()=>detailStates.set(p.id,details.open);}
 const pauseDetails=panel.querySelector('[data-pause-details]');if(pauseDetails){pauseDetails.open=Boolean(pauseExpanded);pauseDetails.ontoggle=()=>detailStates.set(p.id+':pause',pauseDetails.open);}
 const pauseButton=panel.querySelector('[data-pause-action]');if(pauseButton)pauseButton.onclick=()=>guarded(pauseButton,async()=>{if(pause.action==='resume')return options.resume?.(task);if(options.pauseAction)return options.pauseAction(pause.action,task);throw new Error('Open the saved task details to continue.');},panel);
 const retryStart=panel.querySelector('[data-retry-start]');if(retryStart)retryStart.onclick=()=>guarded(retryStart,async()=>{await starts.retry(task.id);await refresh();},panel);
 const reconcile=panel.querySelector('[data-reconcile-start]');if(reconcile)reconcile.onclick=()=>guarded(reconcile,()=>starts.reconcile(task.id),panel);
 const logs=panel.querySelector('[data-view-logs]');if(logs)logs.onclick=()=>options.showLogs?.();
 const finishStartup=panel.querySelector('[data-finish-startup]');if(finishStartup)finishStartup.onclick=()=>guarded(finishStartup,()=>options.resume(task),panel);
 const nextChat=panel.querySelector('[data-new-chat]');if(nextChat)nextChat.onclick=()=>options.newChat?.();
 const recheck=panel.querySelector('[data-recheck-run]');if(recheck)recheck.onclick=()=>guarded(recheck,async()=>{const result=await api('/tasks/'+task.id+'/branch-final-recheck',{});await options.handleResumeResult?.(task,result);await refresh();},panel);
 const resume=panel.querySelector('[data-resume]');if(resume){resume.disabled=!options.resume;resume.onclick=()=>guarded(resume,()=>options.resume(task),panel);if(!options.resume)resume.title='Resume needs command permission revalidation';}
 const preview=panel.querySelector('[data-preview]');if(preview)preview.onclick=()=>guarded(preview,()=>showFinal(task),panel);
 const inspect=panel.querySelector('[data-proposal]');if(inspect)inspect.onclick=()=>guarded(inspect,async()=>{const result=await api('/tasks/'+task.id+'/branch-proposal',{});proposal={...result,request:{repository:task.source,prompt:result.contract.original_request,document:result.contract.inputs?.document?.path||''}};showProposal();},panel);
 }
 function renderPlan(task){
  const panel=document.querySelector('#plan-view');if(!panel)return;
  if(panel.dataset.task!==task.id||!panel.querySelector('[data-plan-content]')){panel.dataset.task=task.id;panel.innerHTML='<div class="plan-review-heading"><div><h2>Plan &amp; review</h2><p>Compare the completed work with the plan you approved.</p></div><button type="button" data-jump-changes class="primary-button">Review changes in Changes tab →</button><button type="button" data-jump-review>Jump to results ↓</button></div><details class="plan-contract" data-event="review-plan" open><summary>Plan and acceptance criteria</summary><div data-plan-content></div></details><div data-review-slot></div>';panel.querySelector('[data-jump-review]').onclick=()=>panel.querySelector('[data-review-slot]').scrollIntoView({block:'start',behavior:'instant'});panel.querySelector('[data-jump-changes]').onclick=()=>options.showChanges?options.showChanges():panel.querySelector('[data-jump-review]').click();}
  const plan=panel.querySelector('[data-plan-content]'),markup=planMarkup(task);if(plan._markup!==markup){plan._markup=markup;plan.innerHTML=markup;}
  const slot=panel.querySelector('[data-review-slot]'),run=task.branch_run;
  const signature=JSON.stringify([run?.readiness?.id,run?.status,run?.expected_feature_tip,task.archived_at,task.trashed_at]);
  if(slot.dataset.signature===signature)return;slot.dataset.signature=signature;
  if(!run?.readiness){slot.innerHTML='<section class="review-pending"><h3>Results will appear here</h3><p>The cumulative changes, verification evidence, and merge decision will be available after final review finishes. You can follow current work in Chat.</p></section>';return;}
  loadFinal(task,slot);
 }
 function showFinal(task){
  if(options.showChanges){options.showChanges();return;}
  options.showPlan?.();renderPlan(task);
  document.querySelector('#plan-view [data-review-slot]')?.scrollIntoView({block:'start',behavior:'instant'});
 }
 async function loadFinal(task,slot){
  // Render before awaiting the expensive, server-owned readiness validation.
  const d=document.createElement('section');d.className='final-review';d.setAttribute('aria-label','Review branch changes');d.setAttribute('aria-busy','true');
  d.innerHTML='<div class="review-heading"><h2>Review results</h2><button type="button" data-open-changes>Open in Changes view ↗</button><button type="button" data-back-plan>Back to plan ↑</button></div><div data-final-content class="review-loading" role="status"><span class="spinner" aria-hidden="true"></span><h3>Preparing your review…</h3><p>Loading the saved changes and checking whether the target branch can accept them.</p><p>You can keep using the other tabs. No merge has started.</p></div><p class="branch-error" role="alert"></p>';
  slot.replaceChildren(d);d.querySelector('[data-back-plan]').onclick=()=>{const plan=slot.closest('#plan-view')?.querySelector('.plan-contract');if(plan){plan.open=true;plan.scrollIntoView({block:'start',behavior:'instant'});}};d.querySelector('[data-open-changes]').onclick=()=>options.showChanges?.();let preview;
  try{preview=await api('/tasks/'+task.id+'/branch-final-preview',{});}
  catch(e){if(d.isConnected){d.removeAttribute('aria-busy');d.querySelector('[data-final-content]').innerHTML='<h3>Could not load the review</h3><p>The saved branch has not been merged.</p><button type="button" data-retry-preview>Try again</button>';error(d,e);d.querySelector('[data-retry-preview]').onclick=()=>loadFinal(task,slot);}return;}
  if(!d.isConnected)return;
  finalPreview=preview;d.removeAttribute('aria-busy');d.querySelector('[data-final-content]').remove();d.querySelector('.branch-error').remove();
  d.insertAdjacentHTML('beforeend',finalReviewMarkup(task,preview));
  mountFinalDiff(d,task,preview,api);
  if(typeof CheapOSPreview!=='undefined')CheapOSPreview.mount(d.querySelector('.review-overview'),task,api,preview.feature_tip);
  const merge=d.querySelector('[data-merge]');const readOnly=terminalRun(task)||Boolean(task.archived_at||task.trashed_at);if(readOnly)merge.disabled=true;
  for(const selector of ['[data-revise]','[data-recheck]','[data-leave]'])d.querySelector(selector).hidden=readOnly;
  merge.onclick=()=>guarded(merge,()=>mergeAndPublish({api,task,values:{preview_id:preview.preview_id,approved:true},onTask:saved=>{slot.dataset.signature='';options.showChat?.();options.receiveUpdatedTask?.(saved);toast('Reviewed changes merged locally.');},refresh}),d);
  const resolve=d.querySelector('[data-resolve-conflicts]');if(resolve){resolve.hidden=readOnly;resolve.onclick=()=>guarded(resolve,async()=>{const result=await api('/tasks/'+task.id+'/branch-resolve-conflicts',{approved:true,update_token:preview.update_token});slot.dataset.signature='';await options.handleResumeResult?.(task,result);await refresh();},d);}
  const update=d.querySelector('[data-update-branch]');if(update){update.hidden=readOnly;update.onclick=()=>guarded(update,async()=>{const result=await api('/tasks/'+task.id+'/branch-update',{approved:true,update_token:preview.update_token});slot.dataset.signature='';if(result.needs_conflict_resolution){await loadFinal(task,slot);}else{await options.handleResumeResult?.(task,result);await refresh();}},d);}
  const leave=d.querySelector('[data-leave]');leave.onclick=()=>guarded(leave,async()=>{await api('/tasks/'+task.id+'/branch-leave',{});slot.dataset.signature='';await refresh();},d);
  d.querySelector('[data-recheck]').onclick=()=>guarded(d.querySelector('[data-recheck]'),async()=>{const result=await api('/tasks/'+task.id+'/branch-final-recheck',{});await options.handleResumeResult?.(task,result);await refresh();},d);
  d.querySelector('[data-revise]').onclick=()=>{options.showChat?.();input.focus();input.placeholder='Describe the changes you want in this run…';group.dataset.revising=task.id;};
  d.querySelector('[data-refresh]').onclick=()=>loadFinal(task,slot);
 }
 async function requestRevision(task,message){
  let result=await api('/tasks/'+task.id+'/branch-revise',{message});
  if(result.needs_selection){
   const choose=dialog('Select requirements to repair',`<p>Select 1–12 original requirements. The complete original plan still receives final review.</p><form>${result.requirements.map(r=>`<label><input type="checkbox" name="requirement" value="${escape(r.id)}"> ${escape(r.id)} · ${escape(r.criterion)}</label>`).join('')}<button type="submit">Prepare scoped revision</button><p class="branch-error" role="alert"></p></form>`);
   choose.querySelector('form').onsubmit=e=>{e.preventDefault();const ids=[...choose.querySelectorAll('input:checked')].map(x=>x.value);guarded(choose.querySelector('button'),async()=>{if(ids.length<1||ids.length>12)throw new Error('Select 1–12 requirements.');const selected=await api('/tasks/'+task.id+'/branch-revise',{message,requirement_ids:ids});choose.close();showRevision(task,selected);},choose);};return;
  }
  return showRevision(task,result);
 }
 function showRevision(task,result){const revision=result.revision_proposal;
  if(!revision?.proposal_id||!revision.contract?.item)throw new Error('The server did not return a reviewable revision proposal. Your message is preserved.');
  const item=revision.contract.item,d=dialog('Inspect revision work',`<p>This adds bounded revision work to the existing run. The remaining allowance stays unchanged.</p><h3>${escape(item.title)}</h3><p>${escape(item.instructions)}</p><ul>${(item.acceptance_criteria||[]).map(c=>`<li>${escape(c)}</li>`).join('')}</ul><p>Required checks</p><ul>${(item.required_checks||[]).map(c=>`<li><code>${escape(commandText(c))}</code></li>`).join('')}</ul><div class="branch-actions"><button type="button" class="primary" data-confirm>Start revision</button><button type="button" data-keep>Keep for later</button></div>`);
  d.querySelector('[data-keep]').onclick=()=>d.close();const button=d.querySelector('[data-confirm]');button.onclick=()=>guarded(button,async()=>{const result=await api('/tasks/'+task.id+'/branch-revise',{proposal_id:revision.proposal_id,approved:true});delete group.dataset.revising;input.value='';save();d.close();await options.handleResumeResult?.(task,result);await refresh();},d);
 }
 async function interceptSubmit(){sync();if(busy&&busySelection===getState().selection)return true;const task=getState().task;if(isRevisionTarget(task,group.dataset.revising)){const message=input.value.trim();if(!message)return true;busy=true;busySelection=getState().selection;try{await requestRevision(task,message);}catch(e){toast(e.message);}finally{busy=false;}return true;}
 if(['merged','left_on_branch'].includes(task?.branch_run?.status)){toast('Start a new chat to continue with a new job.');return true;}
 if(isPlanning(task))return false;
 if(task?.branch_run&&!task.branch_run.authorization_ref){toast('Inspect the proposal to edit or start this run.');return true;}
 if(task?.branch_run?.authorization_ref)return false;
 if(interactiveOnce){interactiveOnce=false;return false;}
 if(selector.value==='unattended'){save();submitPlanning(startState?.error&&getState().selection===startState.selection&&startState.draftSignature===JSON.stringify(drafts[key()])?startState.request:undefined);return true;}
 if(intent(input.value)==='offer'){const d=dialog('Choose how to work',`<p>This sounds like a branch run. Unattended prepares a bounded plan for your approval.</p><div class="branch-actions"><button type="button" data-unattended>Prepare unattended proposal</button><button type="button" data-interactive>Keep Interactive</button></div>`);d.querySelector('[data-unattended]').onclick=()=>{selector.value='unattended';save();sync();d.close();submitPlanning();};d.querySelector('[data-interactive]').onclick=()=>{interactiveOnce=true;d.close();toast('Interactive selected. Send your message to continue conversationally.');};return true;}return false;
 }
 sync();return {clearSubmittedDraft:(owner,message)=>{if(drafts[owner]?.prompt?.trim()===message){drafts[owner].prompt='';try{localStorage.setItem(storageKey,JSON.stringify(drafts));}catch(_){}}},isSubmitting:()=>busy&&busySelection===getState().selection,interceptSubmit,render,renderPlan,renderStart,showProposal,showFinal,sync,restoreDraft:()=>{sync();if(!input.value&&drafts[key()]?.prompt)input.value=drafts[key()].prompt;},hasDocument:()=>selector.value==='unattended'&&Boolean(documentInput.value.trim()),getMode:()=>selector.value,newChat:()=>{sync();selector.value='interactive';documentInput.value='';delete group.dataset.revising;save();sync();options.onDraftChange?.();}};
}
return {mergeAndPublish,fullSuiteConsent,diffPath,reviewDiffs,reviewFiles,reviewDiffMarkup,finalReviewMarkup,finalDiffState,mountFinalDiff,planningPayload,proposalValidation,technicalEvents,technicalText,technicalMarkup,startController,savedPlan,planMarkup,pausePresentation,proposalReadiness,mount,intent,terminalRun,hasRun,isPlanning,duration,isBusy,isRevisionTarget,resumeAction,proposedLimits,projectRun,diffSections,escape};
});
