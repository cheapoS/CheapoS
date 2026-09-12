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
      case 'ready': return {...result,title:'Your task is ready to start.',description:'CheapOS has created a separate task copy. Start the worker to make changes, run your checks, and request a review.',primary:'start',primaryLabel:task.demo?'Start the local demo':'Start this task',secondary:null};
      case 'running': return {...result,tone:'working',eyebrow:'IN PROGRESS',title:task.active_role==='reviewer'?'The reviewer is making the changes.':'The worker is working on your task.',description:'No action needed right now. CheapOS will ask before running a command that needs your approval.',primary:'activity',primaryLabel:'Follow activity'};
      case 'reviewing': return {...result,tone:'working',eyebrow:'IN PROGRESS',title:'The reviewer is checking the patch.',description:'The checkpoint reached review. Wait for a decision: approve the change, request revisions, or ask to take over.',primary:'activity',primaryLabel:'Follow the review'};
      case 'waiting_approval': return {...result,tone:'attention',title:'Approve the verification command.',description:'The worker is waiting for permission to run the command below in the task copy.',primary:'approve',primaryLabel:'Run this command',secondary:'decline',secondaryLabel:'Decline & pause'};
      case 'stopping': return {...result,eyebrow:'PAUSING',title:'Waiting for the current request to finish.',description:'No new tool work will start. An in-flight model request can take up to three minutes to return.',primary:'activity',primaryLabel:'View activity',secondary:null};
      case 'error': return {...result,tone:'attention',title:reviewerStopped?'The reviewer didn’t finish.':'This task stopped before it finished.',description:reviewerStopped?'The worker’s changes are saved, but the latest checkpoint has no reviewer decision. Check the model connection before trying again.':'Your saved work is still available. Read the failure below and check the model connection before retrying.',primary:'connections',primaryLabel:'Check model connection',retry:true};
      case 'budget_paused': return {...result,tone:'attention',title:'This task reached a limit.',description:'CheapOS paused to respect your limits. Inspect what it produced, then review the remaining budget before continuing.',primary:'resume',primaryLabel:'Review limits & resume'};
      case 'paused': case 'interrupted': return {...result,title:task.status==='interrupted'?'This task was interrupted.':'Your work is paused.',description:'The task copy and usage are saved. Review the limits, then resume with this task’s original models.',primary:'resume',primaryLabel:'Review & resume'};
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
  return {taskGuide,projectName,workLabel,isActive:status=>active.has(status)};
})();
if(typeof module!=='undefined')module.exports=CheapOSGuide;
