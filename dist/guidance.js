/* Translate saved execution evidence into a clear next step. No model calls. */
const CheapOSGuide = (() => {
  const active = new Set(['running', 'reviewing', 'waiting_approval', 'stopping']);
  function taskGuide(task) {
    const checkpoints=task.checkpoints||[], checks=task.checks||[], events=task.events||[];
    const latestReview=checkpoints.at(-1), latestCheck=checks.at(-1);
    const request=[...events].reverse().find(event=>event.kind==='model');
    const reviewerStopped=task.status==='error'&&latestReview?.decision==='PENDING'&&request?.title.startsWith('Requesting reviewer:');
    const hasPatch=Boolean(task.changes?.length);
    const facts={
      worker:hasPatch?`${task.changes.length} file${task.changes.length===1?'':'s'} changed`:task.worker_turns?'No edits yet':'Not started',
      checks:latestCheck?(latestCheck.passed?'Latest check passed':'Latest check failed'):'Not run yet',
      reviewer:latestReview?({PENDING:reviewerStopped?'No decision returned':'Awaiting a decision',APPROVE:'Approved',REQUEST_CHANGES:'Changes requested',TAKE_OVER:'Takeover requested'}[latestReview.decision]||'No decision yet'):'Not reached yet',
      you:['approved','completed'].includes(task.status)?'Review and apply':'Review comes last'
    };
    const result={facts,tone:'neutral',eyebrow:'NEXT STEP',title:'Your task is saved.',description:'Open the activity log to see the saved work.',primary:'activity',primaryLabel:'View activity',secondary:hasPatch?'changes':null,secondaryLabel:'Inspect saved changes',retry:false};
    switch(task.status) {
      case 'awaiting_reply': return {...result,title:'Ready for your next message.',description:hasPatch?'Edits are saved in this chat. A chat answer does not mean the patch was reviewed.':'Continue the conversation whenever you’re ready.',primary:'chat',primaryLabel:'Back to chat'};
      case 'ready': return {...result,title:'Your task is ready to start.',description:'CheapOS has created a separate task copy. Start the worker to make changes, run your checks, and request a review.',primary:'start',primaryLabel:task.demo?'Start the local demo':'Start this task',secondary:null};
      case 'running': return {...result,tone:'working',eyebrow:'IN PROGRESS',title:task.active_role==='reviewer'?'The reviewer is making the changes.':'The worker is working on your task.',description:'No action needed right now. CheapOS will ask before running a command that needs your approval.',primary:'activity',primaryLabel:'Follow activity'};
      case 'reviewing': return {...result,tone:'working',eyebrow:'IN PROGRESS',title:'The reviewer is checking the patch.',description:'The checkpoint reached review. Wait for a decision: approve the change, request revisions, or ask to take over.',primary:'activity',primaryLabel:'Follow the review'};
      case 'waiting_approval': return {...result,tone:'attention',title:'Approve the verification command.',description:'The worker is waiting for permission to run the command below in the task copy.',primary:'approve',primaryLabel:'Run this command',secondary:'decline',secondaryLabel:'Decline & pause'};
      case 'stopping': return {...result,eyebrow:'PAUSING',title:'Waiting for the current request to finish.',description:'No new tool work will start. An in-flight model request can take up to three minutes to return.',primary:'activity',primaryLabel:'View activity',secondary:null};
      case 'error': return {...result,tone:'attention',title:reviewerStopped?'The reviewer didn’t finish.':'This task stopped before it finished.',description:reviewerStopped?'The worker’s changes are saved, but the latest checkpoint has no reviewer decision. Check the model connection before trying again.':'Your saved work is still available. Read the failure below and check the model connection before retrying.',primary:'connections',primaryLabel:'Check model connection',retry:true};
      case 'budget_paused': return {...result,tone:'attention',title:'This task reached a limit.',description:'CheapOS paused to respect your limits. Inspect what it produced, then review the remaining budget before continuing.',primary:'resume',primaryLabel:'Review limits & resume'};
      case 'paused': case 'interrupted': return {...result,title:task.error_code==='progress_limit'?'Paused to avoid repeated work.':task.error_code==='routing_unavailable'?'A working free route is needed.':task.status==='interrupted'?'This task was interrupted.':'Your work is paused.',description:task.error_code?task.error:'The task copy and usage are saved. Resume with the same models and limits.',primary:'resume',primaryLabel:'Resume'};
      case 'takeover_requested': return {...result,tone:'attention',title:'The reviewer wants to take over.',description:'Read the reviewer’s feedback below. You decide whether it can implement changes using the remaining task budget.',primary:'resume',primaryLabel:'Review takeover request'};
      case 'approved': return {...result,tone:'success',eyebrow:'YOUR REVIEW',title:'The reviewer approved this patch.',description:'Inspect the changes, then export the patch when you’re ready to apply it. Your original project has not been changed by the file tools.',primary:'changes',primaryLabel:'Review the patch',secondary:'export',secondaryLabel:'Export patch'};
      case 'completed': return {...result,tone:'attention',eyebrow:'YOUR REVIEW',title:'Takeover finished. Your review is next.',description:'The implementing model finished, but this is not an independent reviewer approval. Inspect the patch before applying it to your project.',primary:'changes',primaryLabel:'Review the patch',secondary:'export',secondaryLabel:'Export patch'};
      default:return result;
    }
  }
  function projectName(task) {
    if(task.demo)return 'Local demo';
    if(/[/\\]\.cheapos[/\\]examples[/\\][a-f0-9]+$/.test(task.source))return 'Sample Python project';
    return String(task.source||'').split(/[/\\]/).filter(Boolean).pop()||'Your project';
  }
  function workLabel(events) {
    const reads=events.filter(e=>e.kind==='tool'&&['read file','search','list files'].includes(e.title)).length;
    const edits=events.filter(e=>e.kind==='tool'&&['write file','replace text'].includes(e.title)).length;
    const checks=events.filter(e=>e.kind==='checks').length;
    return [reads?`Explored the project (${reads})`:null,edits?`Made ${edits} edit${edits===1?'':'s'}`:null,checks?`Ran ${checks} check${checks===1?'':'s'}`:null].filter(Boolean).join(' · ')||'Work details';
  }
  function duration(seconds) {
    seconds=Math.max(0,Math.floor(seconds));
    return seconds<60?`${seconds}s`:`${Math.floor(seconds/60)}m ${seconds%60}s`;
  }
  function progress(task, at=Date.now()) {
    if(!active.has(task.status))return null;
    const events=task.events||[],latest=events.at(-1),request=[...events].reverse().find(e=>e.kind==='model');
    const completed=[...events].reverse().find(e=>e.kind==='checks'||e.kind==='tool'&&e.title!=='Running verification');
    const args=completed?.detail?.arguments||{};
    const action=completed?({'read file':`Read ${args.path||'a file'}`,'write file':`Created ${args.path||'a file'}`,'replace text':`Edited ${args.path||'a file'}`,'list files':'Listed project files','search':`Searched for ${args.query||'text'}`}[completed.title]||completed.title):'No tool actions completed yet';
    const files=(task.changes||[]).length,evidence=files?`${files} changed file${files===1?'':'s'} saved`:'No files changed yet';
    let stage='working',title='Preparing the next step',detail='',since=latest?.time||task.updated_at;
    if(task.status==='waiting_approval'){stage='approval';title='Waiting for your approval';detail=(task.pending_approval?.command||[]).join(' ')}
    else if(task.status==='stopping'){stage='stopping';title='Stop requested';detail='Waiting for the current operation to finish. No new tools will start.'}
    else if(latest?.kind==='model'){
      stage='model';const role=latest.title.startsWith('Requesting reviewer:')?'reviewer':latest.title.startsWith('Requesting coordinator:')?'coordinator':'worker';
      title=role==='reviewer'?'Waiting for the reviewer’s response':'Waiting for the model’s response';
      detail=task.providers?.[role]?.model||latest.title.replace(/^Requesting (worker|reviewer|coordinator): /,'');since=latest.time;
    }else if(latest?.title==='Running verification'){stage='checks';title='Running checks';detail=(latest.detail?.command||task.check_command||[]).join(' ')}
    const timestamp=Date.parse(since),seconds=Number.isFinite(timestamp)?Math.max(0,(at-timestamp)/1000):0;
    const limit=request?.detail?.timeout_seconds||180;
    let slow=stage==='model'&&seconds>=30;
    let hint=stage==='model'?(seconds>=limit-30?`Still waiting. The response limit is ${duration(limit)}.`:seconds>=30?'No response has arrived yet. You can stop this request.':'The model’s response will appear when it arrives.'):' ';
    if(stage==='model'&&task.stream&&task.stream.phase!=='waiting'){
      const stream=task.stream,phase=stream.phase;
      title=phase==='thinking'?'Receiving the model’s thinking':phase==='answer'?'Receiving the model’s answer':'The model is preparing a tool call';
      const updated=Date.parse(stream.updated_at),ago=Number.isFinite(updated)?Math.max(0,(at-updated)/1000):0;
      slow=ago>=30;
      detail=stream.model+(phase==='tool'&&stream.tool?' · '+stream.tool:'');
      hint=ago>=10?`Last output ${duration(ago)} ago. Waiting for the next chunk.`:'Live output is arriving from the model.';
    }
    return {stage,title,detail,elapsed:duration(seconds),action,evidence,hint,slow};
  }
  function failure(task) {
    const events=task.events||[],request=[...events].reverse().find(e=>e.kind==='model'),error=[...events].reverse().find(e=>e.kind==='error');
    const elapsed=request&&error?(Date.parse(error.time)-Date.parse(request.time))/1000:0;
    const legacyTimeout=task.error?.startsWith('Model request did not complete.')&&Math.round(elapsed)>=(request?.detail?.timeout_seconds||180);
    const timeout=['model_timeout','stream_timeout'].includes(task.error_code)||legacyTimeout;
    const files=(task.changes||[]).length;
    return {timeout,title:timeout?'The model didn’t respond before the time limit.':taskGuide(task).title,
      description:timeout?`${request?request.title.replace(/^Requesting (worker|reviewer): /,''):'The model'} ${task.error_code==='stream_timeout'?'reached the streaming time limit':request?.detail?.streaming?'stopped sending output before the response completed':`was given ${duration(request?.detail?.timeout_seconds||180)}`}. ${files?`${files} changed file${files===1?' is':'s are'} saved.`:'No files were changed.'} Retry when you’re ready.`:'The request stopped. Your saved work is available; check the details before retrying.'};
  }
  function activityItem(event) {
    const d=event.detail||{},args=d.arguments||{},result=d.result;
    let title=event.title,icon='code',note='',path=null;
    if(event.kind==='tool'){
      path=args.path||null;
      if(title==='Running verification')return null;
      const names={'read file':`Read ${path||'a file'}`,'write file':`Created ${path||'a file'}`,'replace text':`Edited ${path||'a file'}`,'list files':'Listed project files','search':`Searched for “${args.query||''}”`,'get diff':'Inspected the saved changes'};
      title=names[title]||title;icon=path?'file':'search';
      note=Array.isArray(result)?`${result.length} results`:result?.total_lines?`${result.total_lines} lines in file`:['write file','replace text'].includes(event.title)?'Saved in the task copy':'';
      if(d.model)note=[d.model,note].filter(Boolean).join(' · ');
    }else if(event.kind==='checks'){icon='tests';note=(d.command||[]).join(' ')}
    else if(event.kind==='review'){icon='shield';note=d.feedback||''}
    else if(event.kind==='handoff'){icon='branch';note=`${d.from} → ${d.to}`}
    else if(event.kind==='checkpoint'){icon='shield';note=d.worker_summary||''}
    else if(event.kind==='tool_error'){icon='x';title='Action could not finish';note=d.error||''}
    else if(event.kind==='guard'){icon='clock';note=typeof d==='string'?d:''}
    else if(event.kind==='routing'){icon='branch';note=[d.model,d.error].filter(Boolean).join(' · ')||d.summary||''}
    else if(event.kind==='permission'){icon='shield';note=(d.command||[]).join(' ')}
    else return null;
    return {event,title,icon,note,path,failed:event.kind==='tool_error'||event.kind==='checks'&&!d.passed};
  }
  function activity(task) {
    const events=task.events||[],boundary=events.reduce((n,e,i)=>e.kind==='user'?i:n,-1),recent=events.slice(boundary+1);
    const check=[...recent].reverse().find(e=>e.kind==='checks')?.detail;
    const review=[...recent].reverse().find(e=>e.kind==='review')?.detail;
    const checkpoint=review&&(task.checkpoints||[]).find(c=>c.number===review.checkpoint);
    const checkCurrent=Boolean(check?.digest&&check.digest===task.patch_digest);
    const reviewCurrent=Boolean(checkpoint&&checkpoint.diff===task.patch);
    return {request:boundary>=0?events[boundary].detail:task.prompt,
      files:(task.changes||[]).length,
      checks:check?`${check.passed?'Passed':'Failed'}${checkCurrent?'':' · earlier patch'}`:'Not run for this request',
      review:review?`${{APPROVE:'Approved',REQUEST_CHANGES:'Changes requested',TAKE_OVER:'Takeover requested'}[review.decision]||'Decision saved'}${reviewCurrent?'':' · earlier patch'}`:task.status==='reviewing'?'Reviewing now':'Not reviewed for this request',
      check,checkpoint,items:recent.map(activityItem).filter(Boolean).reverse()};
  }
  return {taskGuide,projectName,workLabel,progress,failure,duration,activity,activityItem,isActive:status=>active.has(status)};
})();
if(typeof module!=='undefined')module.exports=CheapOSGuide;
