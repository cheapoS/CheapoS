/* Translate saved execution evidence into a clear next step. No model calls. */
const CheapOSGuide = (() => {
  const active = new Set(['running', 'reviewing', 'waiting_approval', 'waiting_retry', 'stopping']);
  function coordinatorStatus(task) {
    const enabled=task?.execution?.coordinator_assistance===true;
    return {
      enabled,label:enabled?'On':'Off',
      detail:enabled
        ?'Assistance is enabled for this chat. The local coordinator is consulted only when an eligible worker stall needs help; availability is checked then.'
        :'Assistance is disabled for this chat. Having a local chat model does not enable recovery assistance.',
      pauseNote:enabled?'':'Coordinator assistance was not attempted because it is Off for this chat.'
    };
  }
  function connectionNotice(readiness, gateway={}, execution={}, config={}) {
    if(readiness?.diagnostic_code==='readiness_request_failed'||readiness?.diagnostic_code==='readiness_probe_failed')return {tone:'attention',title:'Connection check could not finish',detail:'Re-check your connections or open setup. Availability has not been verified.'};
    const mode=execution.mode||'manual', roles=[config.worker,config.reviewer].filter(Boolean);
    const needsGateway=['remote','delegate'].includes(mode)||(mode==='manual'&&roles.some(p=>p.gateway==='omniroute'));
    const needsLocal=['local','delegate'].includes(mode);
    const problems=[];
    if(mode!=='local'&&[...roles,config.planner].some(p=>p?.route_error))problems.push('A saved model connection is disabled. Open Models and choose OmniRoute for remote models, or local Ollama.');
    if(needsGateway){
      if(gateway.key_storage?.error)problems.push(gateway.key_storage.error);
      else if(gateway.status==='auth_required')problems.push('OmniRoute needs its client API key. Enter it in Models and choose Remember to keep it after restart.');
      else if(['offline','not_installed','unavailable','error'].includes(gateway.status))problems.push('OmniRoute is unavailable. Open connection setup to reconnect.');
    }
    if(needsLocal&&readiness?.paths?.local){
      const selected=execution.local_model, installed=readiness.paths.local.models||[];
      if(!selected)problems.push('Choose an installed Ollama model for local chat.');
      else if(!installed.includes(selected))problems.push(`Ollama is unavailable or ${selected} is not available with tool support. Your saved choice is kept; start Ollama or check Models.`);
      if(mode==='local'&&execution.local_reviewer&&!installed.includes(execution.local_reviewer))problems.push(`Local reviewer ${execution.local_reviewer} is unavailable.`);
    }
    if(problems.length)return {tone:'attention',title:'Your connections need attention',detail:problems.join(' ')};
    if(!readiness?.paths||(needsGateway&&['unchecked','checking','starting',undefined].includes(gateway.status)))return {tone:'checking',title:'Checking your saved connections…',detail:'Reading gateway and local-model metadata. No inference or model loading.'};
    if(mode==='manual'&&roles.length<2)return {tone:'attention',title:'Choose your model connections',detail:'Open setup to connect OmniRoute or choose a local model.'};
    const direct=mode==='manual'&&roles.some(p=>p.gateway!=='omniroute');
    return {tone:'available',title:direct?'Model settings saved':'Connections available',detail:direct?'Local Ollama is selected. Installed model identity is checked before inference.':'Metadata checked · model responses and coding tools are verified when work runs.'};
  }
  const workPresets={interactive:{run_minutes:15,worker_turns:40,iterations:5},extended:{run_minutes:45,worker_turns:120,iterations:10}};
  function workPreset(limits){const standard={reviewer_tokens:200000,output_tokens:2048,checkpoint_turns:12,check_seconds:360};return Object.keys(workPresets).find(name=>Object.entries({...standard,...workPresets[name]}).every(([key,value])=>limits[key]===value))||'custom'}
  function presetLimits(limits,name){return {...limits,...(workPresets[name]||{})}}
  function setupGuide(readiness={}) {
    const gateway=readiness.gateway||{}; let status=readiness.status;
    if(status?.startsWith('local_'))status=gateway.status==='ready'?(gateway.eligible_free_count?'gateway_ready':'no_eligible_model'):'offline';
    const choices={checking:['Checking this computer','Reading connection metadata.'],starting:['Connecting…','Waiting for the gateway. Saved work remains accessible.'],gateway_absent:['Install the companion','Install Node.js first if it is missing, then install OmniRoute in your terminal and re-check.'],gateway_stopped:['Start OmniRoute','cheapoS can start the installed gateway on loopback.'],gateway_ready:['Connected',gateway.owned?'Using the gateway started by cheapoS.':'Reusing your existing OmniRoute instance.'],no_eligible_model:['Connect a provider','Open the dashboard and configure a provider with an eligible free, tool-capable model.'],foreign_service:['Another service is using this address','Choose a different gateway address in Advanced connections. cheapoS will not stop the other service.'],client_key_rejected:['Client API key needed','Dashboard login protects the dashboard. Provider credentials belong in its Providers page. cheapoS only needs a client API key if your gateway requires one.'],offline:['Connection unavailable','Check that OmniRoute is running, then retry.'],local_only_ready:['Local models ready','Your saved local-only choice remains active.'],local_unavailable:['Local model unavailable','Check the installed models on this computer.']};
    const [title,detail]=choices[status]||['Check your connection','Re-check or inspect Advanced connections.'];
    return {title,detail,ready:status==='gateway_ready',start:['gateway_stopped','offline'].includes(status),install:status==='gateway_absent',key:status==='client_key_rejected',dashboard:Boolean(gateway.identified&&gateway.dashboard_url)};
  }
  function sampleOutcome(task) {
    const same=task.providers?.worker?.model&&task.providers.worker.model===task.providers?.reviewer?.model;
    const success=Boolean(task.changes?.length&&canCommit(task));
    return `${success?'Real sample: edits, checks and review completed. Review the patch before approving a commit.':'Real sample: full-loop success has not been verified. Inspect the actual stages below.'}${same?' Review uses a separate request to the same model.':''}`;
  }
  function costProvenance(task) {
    const value=task.metrics?.cost?.provenance;
    return ({provider_reported:'Provider-reported cost',estimated:'Estimated cost',mixed_reported_and_estimated:'Reported + estimated cost',includes_estimates:'Includes estimates',includes_uncertain_reservations:'Includes uncertain reservations',scripted_no_model_requests:'Scripted · no model requests'})[value]||(task.usage?.uncertain_requests?'Includes uncertain reservations':'Cost provenance unknown');
  }
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
    if(task.status==='paused'&&task.planning_request&&task.branch_run&&!task.branch_run.authorization_ref&&/handoffs were tried/.test(task.error||'')) return {...result,tone:'attention',title:'Planning stopped before a proposal was ready.',description:'Automatic model recovery was exhausted. Resume cannot retry this saved attempt. Start a new planning chat with the same request; this attempt and its usage remain saved.',primary:'new-planning',primaryLabel:'New planning chat'};
    if(task.status==='paused'&&task.recovery_blocked!=null&&task.pause_summary){
      const coordinator=task.coordinator_recovery?.at(-1);
      if(coordinator?.state==='failed'&&String(task.error||'').startsWith('Coordinator reassessment')){
        if(task.coordinator_reassessment?.reuse_saved)return {...result,tone:'attention',title:'Saved coordinator guidance is ready.',description:'cheapoS previously rejected a file or API reference in the reply. It now passes validation. Continue below to reuse the reply with your saved files and current review feedback; no additional coordinator call is needed.',primary:'clarify',primaryLabel:'Change approach in chat'};
        const malformed=coordinator.error_code==='coordinator_format'||coordinator.diagnostic==='Coordinator must return one JSON object';
        const cause=malformed?'The local model replied, but its response was not valid JSON. No guidance reached the worker.':coordinator.diagnostic||coordinator.summary||'The local request did not return usable guidance.';
        return {...result,tone:'attention',title:malformed?'Coordinator reply could not be read.':'Coordinator could not help this time.',description:`${cause} ${task.changes?.length||0} saved file${task.changes?.length===1?'':'s'} remain${task.changes?.length===1?'s':''} in this chat. ${task.coordinator_reassessment?.format_repair?'Use Retry coordinator format below; you do not need to write another prompt.':'The attempt details are retained below; verification and review are still required.'}`,primary:'clarify',primaryLabel:'Continue in chat'};
      }
      const p=task.pause_summary,attempts=(p.attempted||[]).join(', ');
      return {...result,tone:'attention',title:p.question?'A decision is needed from you.':'Worker could not choose the next step after recovery.',description:`${p.saved_files.length} saved file${p.saved_files.length===1?'':'s'}. ${attempts?`Tried ${attempts}. `:''}${p.blocker} ${p.next_action}`,primary:'clarify',primaryLabel:p.question?'Reply in chat':'Review saved work and continue in chat'};
    }
    if(['paused','interrupted'].includes(task.status)&&task.route_unavailable?.can_wait)return {...result,title:'A free route is cooling down.',description:task.route_unavailable.message,primary:'retry-wait',primaryLabel:'Retry when available'};
    if(task.status==='budget_paused'&&task.limit_hit){const hit=task.limit_hit;return {...result,tone:'attention',title:'This task reached its '+({run_minutes:'working-time',worker_turns:'worker-turn',reviewer_tokens:'reviewer-token',iterations:'iteration',dollars:'spending'}[hit.key]||'work')+' limit.',description:`Used ${hit.used} of ${hit.allowed}; ${hit.remaining} remaining. ${task.error||'Review the saved work before explicitly adjusting this allowance.'}`,primary:'resume',primaryLabel:'Review this limit'};}
    switch(task.status) {
      case 'awaiting_reply': return {...result,title:'Ready for your next message.',description:hasPatch?'Edits are saved in this chat. A chat answer does not mean the patch was reviewed.':'Continue the conversation whenever you’re ready.',primary:'chat',primaryLabel:'Back to chat'};
      case 'ready': return {...result,title:'Your task is ready to start.',description:'cheapoS has created a separate task copy. Start the worker to make changes, run your checks, and request a review.',primary:'start',primaryLabel:task.demo?'Start the local demo':'Start this task',secondary:null};
      case 'running': return {...result,tone:'working',eyebrow:'IN PROGRESS',title:task.active_role==='reviewer'?'The reviewer is making the changes.':'The worker is working on your task.',description:'No action needed right now. cheapoS will ask before running a command that needs your approval.',primary:'activity',primaryLabel:'Follow activity'};
      case 'reviewing': return {...result,tone:'working',eyebrow:'IN PROGRESS',title:'The reviewer is checking the patch.',description:'The checkpoint reached review. Wait for a decision: approve the change, request revisions, or ask to take over.',primary:'activity',primaryLabel:'Follow the review'};
      case 'waiting_retry': return {...result,tone:'working',title:'Waiting for a free route.',description:'The retry stays within the remaining task time. Pause cancels waiting.',primary:'activity',primaryLabel:'View waiting status'};
      case 'waiting_approval': return {...result,tone:'attention',title:'Approve the verification command.',description:'The worker is waiting for permission to run the command below in the task copy.',primary:'approve',primaryLabel:'Run this command',secondary:'decline',secondaryLabel:'Decline & pause'};
      case 'stopping': return {...result,eyebrow:'PAUSING',title:'Waiting for the current request to finish.',description:'No new tool work will start. An in-flight model request can take up to three minutes to return.',primary:'activity',primaryLabel:'View activity',secondary:null};
      case 'error': return {...result,tone:'attention',title:reviewerStopped?'The reviewer didn’t finish.':'This task stopped before it finished.',description:reviewerStopped?'The worker’s changes are saved, but the latest checkpoint has no reviewer decision. Check the model connection before trying again.':'Your saved work is still available. Read the failure below and check the model connection before retrying.',primary:'connections',primaryLabel:'Check model connection',retry:true};
      case 'budget_paused': return {...result,tone:'attention',title:task.error_code==='worker_turn_limit'?'This request used its worker turns.':'This task reached a limit.',description:task.error_code==='worker_turn_limit'?`Used ${task.request_worker_turns??task.worker_turns} of ${task.limits.worker_turns} worker turns for this request. Your work is saved. Increase that allowance to continue; spending limits stay the same.`:'cheapoS paused to respect your limits. Inspect what it produced, then review the remaining budget before continuing.',primary:'resume',primaryLabel:task.error_code==='worker_turn_limit'?'Review turn limit':'Review limits & resume'};
      case 'paused': case 'interrupted': return {...result,title:task.error_code==='checkpoint_turn_limit'?'Checkpoint interval reached.':task.error_code==='progress_limit'?'Paused to avoid repeated work.':task.error_code==='routing_unavailable'?'A working free route is needed.':task.status==='interrupted'?'This task was interrupted.':'Your work is paused.',description:task.error_code?task.error:'The task copy and usage are saved. Resume from saved work with the same limits.',primary:'resume',primaryLabel:'Resume'};
      case 'takeover_requested': return {...result,tone:'attention',title:'The reviewer wants to take over.',description:'Read the reviewer’s feedback below. You decide whether it can implement changes using the remaining task budget.',primary:'resume',primaryLabel:'Review takeover request'};
      case 'approved': return {...result,tone:'success',eyebrow:'YOUR REVIEW',title:'The reviewer approved this patch.',description:'The final diff and commit message are ready in Chat. Approve and commit, request changes, or keep chatting.',primary:'changes',primaryLabel:'Review the patch',secondary:'export',secondaryLabel:'Export patch'};
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
    const reads=events.filter(e=>e.kind==='tool'&&['read file','outline file','search','list files'].includes(e.title)).length;
    const edits=events.filter(e=>e.kind==='tool'&&['write file','replace text','replace lines','append text'].includes(e.title)).length;
    const checks=events.filter(e=>e.kind==='checks').length;
    return [reads?`Explored the project (${reads})`:null,edits?`Made ${edits} edit${edits===1?'':'s'}`:null,checks?`Ran ${checks} check${checks===1?'':'s'}`:null].filter(Boolean).join(' · ')||'Work details';
  }
  function duration(seconds) {
    seconds=Math.max(0,Math.floor(seconds));
    return seconds<60?`${seconds}s`:`${Math.floor(seconds/60)}m ${seconds%60}s`;
  }
  function liveStream(task) {
    const stream=task.stream;
    if(!stream||!active.has(task.status)||task.pending_approval||task.check_stream||task.status==='waiting_retry')return null;
    const events=task.events||[],id=stream.request_id;
    if(id!=null){
      // A saved response or a later action supersedes this request's live view.
      // Guidance and transport notices can arrive while a request is still live.
      if(events.some(e=>e.kind==='generation'&&e.detail?.request_id===id))return null;
      const start=events.findIndex(e=>e.id===id);
      if(start>=0&&events.slice(start+1).some(e=>['model','tool','tool_error','checks','review','commit'].includes(e.kind)))return null;
    }
    return stream;
  }
  function progress(task, at=Date.now()) {
    if(!active.has(task.status))return null;
    task={...task,stream:liveStream(task)};
    const events=task.events||[],latest=events.at(-1),request=[...events].reverse().find(e=>e.kind==='model');
    const completed=[...events].reverse().find(e=>e.kind==='checks'||e.kind==='tool'&&e.title!=='Running verification');
    const args=completed?.detail?.arguments||{};
    const action=completed?({'read file':`Read ${args.path||'a file'}`,'outline file':`Outlined ${args.path||'a file'}`,'read url':`Read ${args.url||'web page'}`,'write file':`Created ${args.path||'a file'}`,'replace text':`Edited ${args.path||'a file'}`,'replace lines':`Edited ${args.path||'a file'}`,'append text':`Appended to ${args.path||'a file'}`,'list files':'Listed project files','search':`Searched project for ${args.query||'text'}`}[completed.title]||completed.title):'No tool actions completed yet';
    const files=(task.changes||[]).length,evidence=files?`${files} changed file${files===1?'':'s'} saved`:'No files changed yet';
    let stage='working',title='Preparing the next step',detail='',since=latest?.time||task.updated_at;
    if(task.status==='waiting_retry'){const wait=task.route_wait||{};return {stage:'waiting_retry',title:'Waiting for an available route',detail:`Retry eligibility in ${duration(Math.ceil(Math.max(0,(wait.retry_at||at/1000)-at/1000)))}`,elapsed:duration(Math.max(0,at/1000-(wait.started_at||at/1000))),action:'No model request is running',evidence:'Saved work and checks are retained',hint:'Your task will continue automatically when an authorized route is available. Pause cancels waiting.',slow:false}}
    if(task.status==='waiting_approval'){stage='approval';title='Waiting for your approval';detail=(task.pending_approval?.command||[]).join(' ')}
    else if(task.status==='stopping'){stage='stopping';title='Stop requested';detail='Waiting for the current operation to finish. No new tools will start.'}
    else if(task.check_stream){stage='checks';title='Running checks';detail=task.check_stream.command.join(' ');since=task.check_stream.started_at}
    else if(task.web_read){stage='web';title='Opening web page';detail=task.web_read.url;since=task.web_read.started_at}
    else if(latest?.kind==='model'){
      stage='model';const role=latest.title.startsWith('Requesting reviewer:')?'reviewer':latest.title.startsWith('Requesting coordinator:')?'coordinator':latest.title.startsWith('Requesting planner:')?'planner':'worker';
      title=role==='reviewer'?'Waiting for the reviewer’s response':'Waiting for the model’s response';
      if(task.answer_pending)title='Preparing an answer from gathered evidence';
      detail=latest.title.replace(/^Requesting (worker|reviewer|coordinator|planner): /,'');since=latest.time;
    }else if(latest?.kind==='routing'||latest?.kind==='handoff'){stage='routing';title=latest.title;detail=latest.detail?.summary||latest.detail?.error||latest.detail?.model||''}
    else if(latest?.title==='Running verification'){stage='checks';title='Running checks';detail=(latest.detail?.command||task.check_command||[]).join(' ')}
    const timestamp=Date.parse(since),seconds=Number.isFinite(timestamp)?Math.max(0,(at-timestamp)/1000):0;
    const limit=request?.detail?.timeout_seconds||180;
    let slow=stage==='model'&&seconds>=30;
    let hint=stage==='model'?(seconds>=limit-30?`Still waiting. The response limit is ${duration(limit)}.`:seconds>=30?'No response has arrived yet. You can stop this request.':'The model’s response will appear when it arrives.'):' ';
    if(stage==='checks')hint=task.check_stream?.output?'Command output is shown below as it arrives.':'The command is running. Some programs buffer their output until they finish.';
    if(stage==='web')hint='Reading the public page. Its text and source link will appear in Chat.';
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
    if(['invalid_response_json','invalid_stream_json','invalid_response_shape','invalid_tool_envelope'].includes(task.error_code)||task.error==='Provider returned an invalid JSON response')return {timeout:false,title:'The model response could not be read.',description:`${files?`${files} changed file${files===1?' is':'s are'} saved.`:'Your task is saved.'} No tool calls from this response were executed. Details identify the response problem.`};
    if(task.error_code==='output_limit'&&['delegate','remote'].includes(task.execution?.mode)&&task.active_role==='worker'&&!task.pending_review)return {timeout:false,title:'The response reached its output limit.',description:`${files?`${files} changed file${files===1?' is':'s are'} saved.`:'Your task is saved.'} Retry will request a smaller next action and reduce reasoning where supported, within the same limits. Incomplete tool calls were not executed; verification and review are still required for edits.`};
    if(['stream_error','stream_interrupted','output_limit'].includes(task.error_code))return {timeout:false,title:task.error_code==='output_limit'?'The response reached its output limit.':'The model response ended early.',description:`${files?`${files} changed file${files===1?' is':'s are'} saved.`:'Your task is saved.'} Incomplete tool calls were not executed. ${task.action_pending||task.answer_pending&&files?'Retry returns to the saved work; verification and review are still required.':'Check the response details before retrying.'}`};
    return {timeout,title:timeout?'The model didn’t respond before the time limit.':taskGuide(task).title,
      description:timeout?`${request?request.title.replace(/^Requesting (worker|reviewer): /,''):'The model'} ${task.error_code==='stream_timeout'?'reached the streaming time limit':request?.detail?.streaming?'stopped sending output before the response completed':`was given ${duration(request?.detail?.timeout_seconds||180)}`}. ${files?`${files} changed file${files===1?' is':'s are'} saved.`:'No files were changed.'} Retry when you’re ready.`:'The request stopped. Your saved work is available; check the details before retrying.'};
  }
  function activityItem(event) {
    const d=event.detail||{},args=d.arguments||{},result=d.result;
    let title=event.title,icon='code',note='',path=null;
    if(event.kind==='tool'){
      path=args.path||null;
      if(title==='Running verification')return null;
      const names={'read file':`Read ${path||'a file'}`,'outline file':`Outlined ${path||'a file'}`,'read url':`Read web page · ${result?.title||args.url||''}`,'write file':`Created ${path||'a file'}`,'replace text':`Edited ${path||'a file'}`,'replace lines':`Edited ${path||'a file'}`,'append text':`Appended to ${path||'a file'}`,'list files':'Listed project files','search':`Searched project for “${args.query||''}”`,'get diff':'Inspected the saved changes'};
      title=names[title]||title;icon=path?'file':'search';
      note=result?.syntax_warning?`⚠ ${result.syntax_warning}`:Array.isArray(result)?`${result.length} results`:result?.total_lines?`${result.total_lines} lines in file`:['write file','replace text','replace lines','append text'].includes(event.title)?'Saved in the task copy':'';
      if(event.title==='read url')note=`${result?.source_url||args.url} · lines ${result?.start_line}–${result?.end_line}${result?.has_more?' · more available':''}`;
      if(d.model)note=[d.model,note].filter(Boolean).join(' · ');
    }else if(event.kind==='check_reused'){icon='tests';note='The same patch and command already passed; no test rerun.'}
    else if(event.kind==='human_decision'){icon='shield';note=d.decision==='defer'?'Edits remain saved. Continue chatting or reopen your decision.':'The reviewed patch is ready for your decision again.'}
    else if(event.kind==='checks'){icon='tests';note=(d.command||[]).join(' ')}
    else if(event.kind==='review'){icon='shield';note=d.feedback||''}
    else if(event.kind==='review_coaching'){icon='shield';note=d.summary||''}
    else if(event.kind==='handoff'){icon='branch';note=`${d.from} → ${d.to}`}
    else if(event.kind==='checkpoint'){icon='shield';note=d.worker_summary||''}
    else if(event.kind==='tool_error'){icon='x';title=d.code==='invalid_tool_arguments'?'Asking the model to correct its tool call':'Action could not finish';note=d.error||''}
    else if(event.kind==='guard'){icon='clock';note=typeof d==='string'?d:d.summary||''}
    else if(event.kind==='routing'){icon='branch';note=[d.model,d.error].filter(Boolean).join(' · ')||d.summary||''}
    else if(event.kind==='permission'){icon='shield';note=(d.command||[]).join(' ')}
    else if(event.kind==='web'){icon='search';title='Requested web page';note=d.url||''}
    else if(event.kind==='commit'){icon='branch';note=d.commit?`${d.commit.slice(0,8)} · ${d.branch} · ${d.message}`:d.error||d.branch||''}
    else if(event.kind==='steer'){icon='compass';title='User course correction';note=typeof d==='string'?d:(d.message||d.detail||'')}
    else return null;
    return {event,title,icon,note,path,failed:event.kind==='tool_error'||event.kind==='checks'&&!d.passed};
  }
  function activity(task) {
    const events=task.events||[],boundary=events.reduce((n,e,i)=>e.kind==='user'?i:n,-1),recent=events.slice(boundary+1);
    const check=[...recent].reverse().find(e=>e.kind==='checks')?.detail;
    const review=[...recent].reverse().find(e=>e.kind==='review')?.detail;
    const checkpoint=review&&(task.checkpoints||[]).find(c=>c.number===review.checkpoint);
    const checkCurrent=Boolean(check?.digest&&check.digest===task.patch_digest&&(check.generation||0)===(task.workspace_generation||0));
    const reviewCurrent=Boolean(checkpoint&&checkpoint.diff===task.patch&&(checkpoint.generation||0)===(task.workspace_generation||0));
    return {request:boundary>=0?events[boundary].detail:task.prompt,
      files:(task.changes||[]).length,
      checks:check?`${check.passed?'Passed':'Failed'}${checkCurrent?'':' · earlier patch'}`:'Not run for this request',
      review:review?`${{APPROVE:'Approved',REQUEST_CHANGES:'Changes requested',TAKE_OVER:'Takeover requested'}[review.decision]||'Decision saved'}${reviewCurrent?'':' · earlier patch'}`:task.status==='reviewing'?'Reviewing now':'Not reviewed for this request',
      check,checkpoint,items:recent.map(activityItem).filter(Boolean).reverse()};
  }
  function canCommit(task) {
    if(task?.branch_run)return false;
    if(task.commit_pending)return true;
    const check=task.checks?.at(-1),review=task.checkpoints?.at(-1);
    return Boolean(task.changes?.length&&['approved','completed','awaiting_reply'].includes(task.status)&&check?.passed&&check.digest===task.patch_digest&&(check.generation||0)===(task.workspace_generation||0)&&(task.status==='completed'||review?.decision==='APPROVE'&&review.diff===task.patch&&(review.generation||0)===(task.workspace_generation||0)));
  }
  function commitDeferred(task) {return task.human_decision?.decision==='defer'&&task.human_decision.digest===task.patch_digest}
  function modelAccess(model={}) {
    const kind=model.access_class||(model.local?'local':model.free?'public_free':Number.isFinite(model.input_rate)&&Number.isFinite(model.output_rate)?'priced':'unknown');
    return ({public_free:'Public free',included:'Included access',local:'Local',priced:'Priced',unknown:'Unknown pricing'})[kind]||'Unknown pricing';
  }
  function includedScope(text) {
    const ids=String(text).split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
    if(ids.some(id=>id.length>200||/\s/.test(id)))throw new Error('Enter one exact model ID per line, without spaces.');
    return [...new Set(ids)];
  }
  function includedChoice(model,settings,selected) {
    return Boolean(selected&&model&&(settings.included_models||[]).includes(model));
  }
  function metadataEvidence(model={}) {
    const e=model.metadata_evidence;
    if(!e)return 'Metadata observation time unavailable';
    const at=typeof e.observed_at==='number'?new Date(e.observed_at*1000):new Date(e.observed_at);
    const stamp=Number.isFinite(at.getTime())?at.toISOString():'time unavailable';
    const changes=Array.isArray(e.changes)?e.changes.slice(0,8).map(x=>String(x).slice(0,80)).join(', '):'';
    return `${e.stale?'Stale metadata':'Observed metadata'} · ${String(e.source||'source unavailable').slice(0,80)} · ${stamp}${changes?' · Changed: '+changes:''}. Catalog metadata does not verify current availability.`;
  }
  function routingTraceView(task={}) {
    const traces=Array.isArray(task.routing_traces)?task.routing_traces.slice(-32):[];
    const reason=value=>String(value||'reason unavailable').replaceAll('_',' ').slice(0,120);
    const rows=traces.map(t=>({id:String(t.id||'trace').slice(0,100),role:String(t.role||'role unavailable'),requested:String(t.requested_route||'unknown'),selected:t.selected_model?String(t.selected_model):null,
      candidates:(t.candidates||[]).slice(0,64).map(c=>`${c.model||'Unknown candidate'}: ${reason(c.reason)}`),
      attempts:(t.attempts||[]).slice(0,64).map(a=>`${a.purpose==='probe'?'Dispatched probe':a.purpose==='cached'?'Cached observation':'Request'} ${a.request_id||'ID unavailable'} · requested ${a.model||'unknown'} · ${reason(a.status)}${Number.isFinite(a.seconds)?' · '+a.seconds.toFixed(2)+'s':''}${a.failure_category?' · '+reason(a.failure_category):''} · served ${a.served_model||'unknown'} (${a.served_model?a.identity_provenance||'provenance unavailable':'identity not exposed'})`),
      notice:[t.candidates_truncated||(t.candidates||[]).length>64?'Candidate evidence is partial; some candidate rows are unavailable in this view.':'',t.attempts_truncated||(t.attempts||[]).length>64?'Attempt evidence is partial; some attempt rows are unavailable in this view.':''].filter(Boolean).join(' '),
      gateway:'Gateway internal attempts unavailable'}));
    const last=rows.at(-1);
    const historyNotice=task.routing_traces_truncated||(task.routing_traces||[]).length>32?'Routing history is partial; earlier traces are unavailable in this view.':'';
    return {rows,...(historyNotice?{historyNotice}:{}),summary:last?(last.selected?`${last.role}: selected ${last.selected}.`:`${last.role}: no route selected. Inspect Models or wait for an eligible route; saved work is retained.`):''};
  }
  function modelHealth(model,at=Date.now()) {
    const h=model.health||{},remaining=Math.ceil(((h.retry_at||0)*1000-at)/60000);
    if(remaining>0)return `${h.cooldown_scope==='provider'?'Provider cooling down':'Cooling down'} · ${h.retry_known===false?'reset time unknown':`${remaining}m`}`;
    const evidence=Object.entries(h.role_evidence||{}).filter(([,e])=>e.samples>0||e.completion_samples>0);
    if(evidence.length)return evidence.map(([role,e])=>{
      const parts=[`${role}: ${e.completed||0} observed completions`];
      if(!e.completed&&!e.completion_samples)parts.push('no prior completion evidence');
      if(e.independently_validated)parts.push(`${e.independently_validated} independently confirmed`);
      if(e.independently_disproved)parts.push(`${e.independently_disproved} independently disproved`);
      if(e.human_integrated)parts.push(`${e.human_integrated} human integrated`);
      if(e.accepted)parts.push(`${e.accepted} human accepted`);
      if(e.samples)parts.push(`${e.samples} activity samples`);
      if(e.invalid_output)parts.push(`${e.invalid_output} invalid outputs`);
      return parts.join(' · ');
    }).join('; ');
    const compatibility=(h.worker_responses||0)+(h.reviewer_responses||0)>0?'Responded in a task':h.tool_check_passed?'Tool check passed':'Not tested yet';
    return compatibility+' · no prior completion evidence';
  }
  function friendlyModel(id) {
    if (!id) return '';
    const isFree = id.endsWith(':free');
    let name = id.replace(/:free$/, '').split('/').pop() || id;
    const map = {
      'north-mini-code': 'North Mini Code',
      'dots-3-note-preview': 'Dots 3 Note',
      'gemma4:31b': 'Gemma 4',
      'gemma4': 'Gemma 4'
    };
    if (map[name.toLowerCase()]) return map[name.toLowerCase()] + (isFree ? ' · free' : '');
    name = name.replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    return name + (isFree ? ' · free' : '');
  }
  function groupActivityItems(events) {
    const reads = new Map(), searches = new Map(), items = [];
    for (const e of events) {
      const d = e.detail || {}, args = d.arguments || {};
      if (e.kind === 'tool') {
        if (e.title === 'read file') {
          const path = args.path || 'file';
          const existing = reads.get(path), lines = d.result?.total_lines;
          if (existing) { existing.count++; if (lines) existing.lines = lines; }
          else { const entry = { type: 'read', path, count: 1, lines, event: e }; reads.set(path, entry); items.push(entry); }
          continue;
        }
        if (e.title === 'outline file') {
          items.push({ type: 'outline', path: args.path || 'file', event: e });
          continue;
        }
        if (e.title === 'search') {
          const query = args.query || '';
          const existing = searches.get(query), results = Array.isArray(d.result) ? d.result.length : 0;
          if (existing) { existing.count++; }
          else { const entry = { type: 'search', query, count: 1, results, event: e }; searches.set(query, entry); items.push(entry); }
          continue;
        }
        if (e.title === 'read url') {
          const res = d.result || {};
          items.push({ type: 'web', url: args.url || res.source_url || '', title: res.title || args.url || 'Web page', range: res.start_line && res.end_line ? `lines ${res.start_line}–${res.end_line}` : '', event: e });
          continue;
        }
        if (['write file', 'replace text', 'replace lines', 'append text'].includes(e.title)) {
          items.push({ type: 'edit', path: args.path || 'file', event: e });
          continue;
        }
        if (e.title !== 'Running verification') items.push({ type: 'tool', title: e.title, event: e });
        continue;
      }
      if (e.kind === 'guard') {
        const text = typeof d === 'string' ? d : '';
        const isStall = e.title.includes('what it found') || text.includes('twice') || text.includes('stopped');
        items.push({ type: 'guard', title: isStall ? 'Worker redirected' : e.title, note: isStall ? 'Repeated read detected; cheapoS redirected worker to continue from existing evidence.' : text, stalled: isStall, event: e });
        continue;
      }
      if (e.kind === 'checks') {
        items.push({ type: 'checks', passed: d.passed, command: d.command || [], exit_code: d.exit_code, duration: d.duration, output: d.output || '', event: e });
        continue;
      }
      if (e.kind === 'check_reused') {
        items.push({ type: 'check_reused', passed: true, note: 'The same patch and command already passed; no test rerun.', event: e });
        continue;
      }
      if (e.kind === 'handoff') {
        items.push({ type: 'handoff', from: friendlyModel(d.from), to: friendlyModel(d.to), role: d.role, title: d.role === 'reviewer' ? 'Sent for independent review' : 'Delegated to worker', event: e });
        continue;
      }
      if (e.kind === 'review') {
        items.push({ type: 'review', decision: d.decision, feedback: d.feedback, title: d.decision === 'APPROVE' ? 'Approved by reviewer' : 'Changes requested by reviewer', event: e });
        continue;
      }
      if (e.kind === 'commit') {
        items.push({ type: 'commit', commit: d.commit, branch: d.branch, message: d.message, event: e });
        continue;
      }
      if (e.kind === 'steer') {
        const text = typeof d === 'string' ? d : (d.message || d.detail || '');
        items.push({ type: 'steer', title: 'User course correction', note: text, event: e });
        continue;
      }
      if (e.kind === 'tool_error') {
        items.push({ type: 'error', title: d.code === 'invalid_tool_arguments' ? 'Model corrected tool call' : 'Action could not finish', note: d.error || '', event: e });
        continue;
      }
    }
    return items;
  }
  function turns(task, at = Date.now()) {
    if (!task) return [];
    const events = task.events || [], userIndices = [];
    events.forEach((e, i) => { if (e.kind === 'user') userIndices.push(i); });
    const segments = [];
    const firstEnd = userIndices.length > 0 ? userIndices[0] : events.length;
    segments.push({ index: 0, userPrompt: task.prompt, events: events.slice(0, firstEnd), isLatest: userIndices.length === 0 });
    userIndices.forEach((userIndex, i) => {
      const nextEnd = i + 1 < userIndices.length ? userIndices[i + 1] : events.length;
      segments.push({ index: i + 1, userPrompt: events[userIndex].detail, events: events.slice(userIndex + 1, nextEnd), isLatest: i === userIndices.length - 1 });
    });
    return segments.map(seg => {
      const turnEvents = seg.events, isLive = seg.isLatest && active.has(task.status);
      const grouped = groupActivityItems(turnEvents);
      const assistantEvent = turnEvents.filter(e => e.kind === 'assistant').at(-1);
      const assistantReply = assistantEvent ? assistantEvent.detail : null;
      const coordinatorModel = task.providers?.coordinator?.model;
      const workerModel = task.providers?.worker?.model;
      const reviewerModel = task.providers?.reviewer?.model;
      const handoffWorker = turnEvents.find(e => e.kind === 'handoff' && e.detail?.role === 'worker')?.detail?.to;
      const handoffReviewer = turnEvents.find(e => e.kind === 'handoff' && e.detail?.role === 'reviewer')?.detail?.to;
      const effectiveWorker = friendlyModel(handoffWorker || workerModel || 'Worker');
      const effectiveReviewer = friendlyModel(handoffReviewer || reviewerModel || 'Reviewer');
      const effectiveCoordinator = friendlyModel(coordinatorModel);
      const latestCheck = turnEvents.filter(e => e.kind === 'checks').at(-1)?.detail;
      const checkPassed = latestCheck?.passed;
      const latestReview = turnEvents.filter(e => e.kind === 'review').at(-1)?.detail;
      const latestCommit = turnEvents.filter(e => e.kind === 'commit' && e.detail?.commit).at(-1)?.detail;
      const editedFiles = [...new Set(turnEvents.filter(e => e.kind === 'tool' && ['write file', 'replace text', 'replace lines', 'append text'].includes(e.title)).map(e => e.detail?.arguments?.path).filter(Boolean))];
      const outlineCount = grouped.filter(g => g.type === 'outline').length;
      const readCount = grouped.filter(g => g.type === 'read').reduce((sum, g) => sum + g.count, 0) + outlineCount;
      const webCount = grouped.filter(g => g.type === 'web').length;
      const searchCount = grouped.filter(g => g.type === 'search').reduce((sum, g) => sum + g.count, 0);
      const totalActions = readCount + webCount + searchCount + editedFiles.length;
      let phase = 'completed', title = 'Work completed', subtitle = '', statusIcon = 'check';
      if (isLive) {
        statusIcon = 'working';
        const p = progress(task, at), elapsed = p?.elapsed || '0s';
        if (task.status === 'waiting_retry') {phase='waiting';title='Waiting for a free route';subtitle=p.detail;} else if (task.status === 'waiting_approval') {
          phase = 'approval'; title = 'Command approval needed'; subtitle = (task.pending_approval?.command || []).join(' '); statusIcon = 'attention';
        } else if (task.check_stream || p?.stage === 'checks') {
          phase = 'verifying'; title = 'Running verification…'; subtitle = (task.check_stream?.command || latestCheck?.command || []).join(' ') + (elapsed ? ` · ${elapsed}` : '');
        } else if (task.status === 'reviewing' || p?.stage === 'reviewer' || (turnEvents.some(e => e.kind === 'handoff' && e.detail?.role === 'reviewer') && !latestReview)) {
          phase = 'reviewing'; title = 'Independent review in progress'; subtitle = `${effectiveReviewer} is checking patch and test evidence · ${elapsed}`;
        } else if (!task.stream && turnEvents.some(e => e.kind === 'routing' || e.kind === 'handoff') && !turnEvents.some(e => e.kind === 'tool') && task.active_role === 'coordinator') {
          phase = 'delegating'; title = 'Delegating task'; subtitle = effectiveCoordinator ? `${effectiveCoordinator} → ${effectiveWorker}` : `Routing to ${effectiveWorker}`;
        } else {
          phase = 'working';
          if (task.stream && task.stream.phase === 'thinking') {
            const tokenEstimate = Math.round((task.stream.thinking || '').length / 4);
            title = `${effectiveWorker} is reasoning`; subtitle = tokenEstimate > 0 ? `${tokenEstimate.toLocaleString()} tokens generated · ${elapsed}` : `Reasoning · ${elapsed}`;
          } else if (task.stream && task.stream.phase === 'tool') {
            title = `${effectiveWorker} is preparing tool`; subtitle = `Preparing ${task.stream.tool || 'action'} · ${elapsed}`;
          } else if (task.web_read) {
            title = 'Reading web page'; subtitle = `${task.web_read.url} · ${elapsed}`;
          } else {
            const seconds = parseInt(elapsed) || 0;
            title = `${effectiveWorker} is working`;
            if (totalActions > 0) {
              const fileDesc = editedFiles.length ? `${editedFiles.length} file edited` : `${readCount} file${readCount === 1 ? '' : 's'} inspected`;
              subtitle = `${fileDesc} · ${elapsed} elapsed`;
            } else if (seconds < 6) subtitle = `Connecting to ${effectiveWorker}… · ${elapsed}`;
            else if (seconds < 16) subtitle = `Inspecting project structure & preparing plan… · ${elapsed}`;
            else subtitle = `Working on implementation… · ${elapsed}`;
          }
        }
      } else {
        if (latestCommit) {
          phase = 'committed'; statusIcon = 'check';
          const commitShort = latestCommit.commit ? latestCommit.commit.slice(0, 8) : '';
          title = editedFiles.length ? `${editedFiles[0]} updated & committed` : 'Changes committed';
          subtitle = [editedFiles.length ? `${editedFiles.length} file${editedFiles.length === 1 ? '' : 's'} changed` : null, latestCheck?.passed ? 'tests passed' : null, 'reviewed', latestCommit.branch ? `${latestCommit.branch} · ${commitShort}` : commitShort].filter(Boolean).join(' · ');
        } else if (seg.isLatest && canCommit(task)) {
          phase = 'ready_to_apply'; statusIcon = 'check'; title = 'Ready to apply';
          subtitle = [editedFiles.length ? `${editedFiles.length} file${editedFiles.length === 1 ? '' : 's'} changed` : null, latestCheck?.passed ? 'tests passed' : null, latestReview?.decision === 'APPROVE' ? `approved by ${effectiveReviewer}` : 'reviewed'].filter(Boolean).join(' · ');
        } else if (task.changes?.length && ['approved', 'completed'].includes(task.status)) {
          phase = 'ready_to_apply'; statusIcon = 'check'; title = 'Ready for your decision';
          subtitle = `${task.changes.length} file${task.changes.length === 1 ? '' : 's'} changed · review complete`;
        } else if (editedFiles.length > 0) {
          phase = 'edited'; statusIcon = checkPassed ? 'check' : 'attention'; title = `${editedFiles[0]} updated`;
          subtitle = `${editedFiles.length} file${editedFiles.length === 1 ? '' : 's'} changed` + (latestCheck ? ` · ${latestCheck.passed ? 'checks passed' : 'checks failed'}` : '');
        } else if (assistantReply) {
          phase = 'answered'; statusIcon = 'check';
          const inspectNotes = [];
          if (readCount) inspectNotes.push(`${readCount} file${readCount === 1 ? '' : 's'} inspected`);
          if (webCount) inspectNotes.push(`${webCount} web source${webCount === 1 ? '' : 's'} read`);
          if (searchCount) inspectNotes.push(`${searchCount} search${searchCount === 1 ? '' : 'es'}`);
          title = inspectNotes.length ? 'Researched repository' : '';
          subtitle = inspectNotes.join(' · ');
        } else if (['budget_paused', 'paused', 'interrupted'].includes(task.status) && seg.isLatest) {
          phase = 'paused'; statusIcon = 'attention'; title = task.error_code === 'worker_turn_limit' ? 'Paused at turn limit' : 'Task paused';
          subtitle = task.error || 'Saved work is available to resume.';
        } else if (task.status === 'error' && seg.isLatest) {
          phase = 'error'; statusIcon = 'failed'; title = 'Task stopped'; subtitle = task.error || 'Encountered an error before finishing.';
        } else {
          phase = 'completed'; statusIcon = 'check'; title = 'Step finished'; subtitle = `${totalActions} action${totalActions === 1 ? '' : 's'} completed`;
        }
      }
      const canCommitNow = seg.isLatest && canCommit(task);
      const thinkingBlocks = turnEvents.filter(e => e.kind === 'generation' && e.detail?.thinking).map(e => e.detail);
      const steerMessages = [];
      const seenGuardTexts = new Set();
      turnEvents.forEach((e, idx) => {
        const isUserSteer = e.kind === 'steer';
        const isGuardSteer = e.kind === 'guard' && e.title === 'Applied User Guidance';
        if (isUserSteer || isGuardSteer) {
          let text = typeof e.detail === 'string' ? e.detail : (e.detail?.message || e.detail?.detail || '');
          text = text.trim();
          if (text.startsWith('"') && text.endsWith('"') && text.length > 2) {
            text = text.slice(1, -1);
          }
          if (text) {
            if (isGuardSteer && seenGuardTexts.has(text)) return;
            if (isGuardSteer) seenGuardTexts.add(text);
            const last = steerMessages.at(-1);
            if (!last || last.text !== text) {
              steerMessages.push({
                text,
                time: e.time,
                id: e.id,
                eventIndex: idx
              });
            }
          }
        }
      });

      const chatItems = [];
      if (steerMessages.length === 0) {
        if (assistantReply) {
          chatItems.push({ kind: 'assistant', text: assistantReply, eventIndex: 999999 });
        }
      } else {
        const firstSteerIdx = steerMessages[0].eventIndex;
        const lastSteerIdx = steerMessages.at(-1).eventIndex;

        const priorAssistant = turnEvents
          .map((e, idx) => ({ e, idx }))
          .filter(({ e, idx }) => e.kind === 'assistant' && idx < firstSteerIdx && typeof e.detail === 'string' && e.detail.trim().length > 0)
          .at(-1);
        if (priorAssistant) {
          chatItems.push({ kind: 'assistant', text: priorAssistant.e.detail, eventIndex: priorAssistant.idx });
        }

        steerMessages.forEach(sm => {
          chatItems.push({ kind: 'steer', text: sm.text, eventIndex: sm.eventIndex });
        });

        const postAssistant = turnEvents
          .map((e, idx) => ({ e, idx }))
          .filter(({ e, idx }) => e.kind === 'assistant' && idx > lastSteerIdx && typeof e.detail === 'string' && e.detail.trim().length > 0)
          .at(-1);
        if (postAssistant) {
          chatItems.push({ kind: 'assistant', text: postAssistant.e.detail, eventIndex: postAssistant.idx });
        }
      }

      const hasMeaningfulWork = totalActions > 0 || editedFiles.length > 0 || latestCheck != null || latestCommit != null || ['paused', 'error', 'ready_to_apply', 'committed'].includes(phase) || steerMessages.length > 0;
      const isStreamingAnswerWithoutTools = isLive && task.stream?.phase === 'answer' && totalActions === 0;
      const hasActivity = isLive ? (!isStreamingAnswerWithoutTools && (turnEvents.length > 0 || isLive)) : hasMeaningfulWork;
      return {
        index: seg.index, userPrompt: seg.userPrompt, isLatest: seg.isLatest, isLive, phase, title, subtitle, statusIcon,
        worker: effectiveWorker, reviewer: effectiveReviewer, coordinator: effectiveCoordinator, hasActivity,
        totalActions, editedFiles, readCount, webCount, searchCount, groupedItems: grouped, steerMessages, chatItems, latestCheck, latestReview, latestCommit,
        canCommit: canCommitNow, assistantReply, thinkingBlocks, events: turnEvents
      };
    });
  }
  function formatTerminalOutput(raw) {
    if (!raw) return '<span class="term-dim">(No output)</span>';
    let safe = String(raw).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const ansiMap = {
      1: 'ansi-bold', 2: 'ansi-dim', 3: 'ansi-italic', 4: 'ansi-underline',
      30: 'ansi-black', 31: 'ansi-red', 32: 'ansi-green', 33: 'ansi-yellow',
      34: 'ansi-blue', 35: 'ansi-magenta', 36: 'ansi-cyan', 37: 'ansi-white',
      90: 'ansi-gray', 91: 'ansi-bright-red', 92: 'ansi-bright-green', 93: 'ansi-bright-yellow',
      94: 'ansi-bright-blue', 95: 'ansi-bright-magenta', 96: 'ansi-bright-cyan', 97: 'ansi-bright-white'
    };
    let openSpans = 0;
    safe = safe.replace(/\x1b\[([0-9;]*)m/g, (match, codes) => {
      if (!codes || codes === '0') {
        const close = '</span>'.repeat(openSpans);
        openSpans = 0;
        return close;
      }
      const classes = codes.split(';').map(c => ansiMap[c]).filter(Boolean);
      if (!classes.length) return '';
      openSpans++;
      return `<span class="${classes.join(' ')}">`;
    });
    if (openSpans > 0) safe += '</span>'.repeat(openSpans);

    const lines = safe.split('\n');
    return lines.map(line => {
      const plain = line.replace(/<[^>]+>/g, '').trim();
      if (!plain) return line;
      if (/^(FAIL(ED)?:|ERROR:|AssertionError:|SyntaxError:|Exception:)/.test(plain) || plain.includes('FAILED (failures=') || plain.includes('FAILED (errors=')) {
        return `<span class="term-line term-error-line">${line}</span>`;
      }
      if (/(\.\.\. ok$|^PASSED$|^OK$|^\d+ passed)/.test(plain)) {
        return `<span class="term-line term-success-line">${line}</span>`;
      }
      if (/^Traceback \(most recent call last\):/.test(plain) || /^File ".*", line \d+/.test(plain)) {
        return `<span class="term-line term-trace-line">${line}</span>`;
      }
      if (/^[-=]{10,}$/.test(plain)) {
        return `<span class="term-line term-divider-line">${line}</span>`;
      }
      return line;
    }).join('\n');
  }
  function sidebarOrder(tasks){return [...tasks].sort((a,b)=>Number(Boolean(b.pinned))-Number(Boolean(a.pinned))||String(b.created_at).localeCompare(String(a.created_at))||a.id.localeCompare(b.id))}
  function permissionChoice(pending){return pending?.profile?{scope:"project_tests_session",label:"Allow project tests for this session"}:{scope:"task_exact",label:"Allow this command for this session"}}
  return {coordinatorStatus,connectionNotice,metadataEvidence,routingTraceView,modelAccess,includedScope,includedChoice,costProvenance,sampleOutcome,setupGuide,workPreset,presetLimits,workPresets,permissionChoice,sidebarOrder,modelHealth,commitDeferred,taskGuide,projectName,workLabel,progress,liveStream,failure,duration,activity,activityItem,canCommit,isActive:status=>active.has(status),friendlyModel,groupActivityItems,turns,formatTerminalOutput};
})();
if(typeof module!=='undefined')module.exports=CheapOSGuide;

/* Ordered conversation: execution is part of a cheapoS response. */
'use strict';
const CheapOSConversation = (() => {
  const guide = CheapOSGuide;
  const last = (events, kind) => events.filter(e => e.kind === kind).at(-1);
  const finalEvent = events => events.findLast(e => !['generation','state','context'].includes(e.kind));
  const committed = event => event?.kind === 'commit' && Boolean(event.detail?.commit);
  function readyForNext(task) {
    return Boolean(task && !task.demo && task.status === 'awaiting_reply' && !task.commit_pending && !task.changes?.length && committed(finalEvent(task.events || [])));
  }
  function eventPhase(event, previous = 'work') {
    if(event.kind==='coordinator_recovery')return event.detail?.state==='result'?(['run_checks','checkpoint'].includes(event.detail?.result?.action)?'checks':'work'):'coordinator';
    if(event.title?.startsWith('Requesting coordinator:')&&previous==='coordinator')return 'coordinator';
    if (event.kind === 'checks' || event.kind === 'check_reused' || event.kind === 'permission' || event.title === 'Running verification') return 'checks';
    if (event.kind === 'review' || event.kind === 'checkpoint' || event.detail?.role === 'reviewer' || event.title?.startsWith('Requesting reviewer:')) return 'review';
    if (event.kind === 'commit') return 'commit';
    if (event.kind === 'planning_inspection' || event.actor?.role === 'planner' || event.detail?.role === 'planner' || event.title?.startsWith('Requesting planner:') || event.detail?.role === 'coordinator' || event.title?.startsWith('Requesting coordinator:')) return 'plan';
    if (event.kind === 'tool' || event.title?.startsWith('Requesting worker:') || event.kind === 'handoff' && event.detail?.role === 'worker') return 'work';
    return previous;
  }
  function currentPhase(task, fallback) {
    if(task.stream?.role==='coordinator'&&task.coordinator_recovery?.some(e=>e.state==='dispatched'))return 'coordinator';
    if (task.check_stream || task.pending_approval) return 'checks';
    if (task.status === 'reviewing' || task.stream?.role === 'reviewer') return 'review';
    if (task.active_role === 'coordinator' || task.active_role === 'planner') return 'plan';
    return fallback || 'work';
  }
  function stepView(step, task, at) {
    const {events, phase, live} = step;
    const check = last(events, 'checks')?.detail;
    const review = last(events, 'review')?.detail;
    const commit = events.findLast(e => e.kind === 'commit' && e.detail?.commit)?.detail;
    const toolEvents = events.filter(e => e.kind === 'tool' && e.detail?.arguments);
    const edits = new Set(toolEvents.filter(e => ['write file','replace text','replace lines','append text'].includes(e.title)).map(e => e.detail.arguments.path));
    const request = events.findLast(e => e.kind === 'model');
    const role = phase === 'coordinator' ? 'coordinator' : phase === 'review' ? 'reviewer' : phase === 'plan' ? 'planner' : 'worker';
    const model = (live && task.stream?.model) || request?.title?.replace(/^Requesting (worker|reviewer|coordinator|planner): /,'') || events.findLast(e => e.detail?.model)?.detail.model || (live?task.providers?.[role]?.model:'') || '';
    const elapsed = live ? guide.progress(task, at)?.elapsed || '0s' : '';
    let title = {work:'Worked on your request',checks:'Ran checks',review:'Requested independent review',plan:'Prepared the next step',commit:'Commit needs attention'}[phase];
    let detail = edits.size ? `${edits.size} file${edits.size === 1 ? '' : 's'} updated` : `${toolEvents.length} action${toolEvents.length === 1 ? '' : 's'}`;
    const inspections=events.filter(e=>e.kind==='planning_inspection');
    if(phase==='plan'&&inspections.length)detail=`${inspections.length} project inspection${inspections.length===1?'':'s'}`;
    let outcome = 'done';
    const finalAction=events.findLast(e=>['tool','tool_error'].includes(e.kind));
    if (phase==='work' && finalAction?.kind==='tool_error') {
      outcome='failed';title='Work needs attention';detail=finalAction.detail?.error||'The last action did not finish.';
    }
    if (phase === 'checks') {
      outcome = check ? check.passed ? 'passed' : 'failed' : events.some(e => e.kind === 'check_reused') ? 'passed' : 'pending';
      title = outcome === 'passed' ? ((check?.command||last(events, 'check_reused')?.detail?.command||[]).join(' ')==='git diff --check'?'Whitespace check passed':'Checks passed') : outcome === 'failed' ? 'Checks found something to fix' : 'Checks pending';
      detail = (check?.command || last(events, 'check_reused')?.detail?.command || []).join(' ');
    }
    if (phase === 'review') {
      outcome = review?.decision === 'APPROVE' ? 'passed' : review?.decision === 'REQUEST_CHANGES' ? 'revision' : 'pending';
      title = outcome === 'passed' ? 'Independent review passed' : outcome === 'revision' ? 'Review requested changes' : 'Review is not finished';
      detail = review?.feedback || 'Checking the changes against your request and test results.';
    }
    if (phase === 'commit') { title = commit ? 'Committed to your project' : title; detail = commit ? `${commit.branch} · ${commit.commit.slice(0,8)}` : ''; outcome = commit ? 'passed' : 'pending'; }
    if (live) {
      title = {work:'Working on your request',checks:'Running checks',review:'Getting an independent review',plan:'Preparing the next step',commit:'Committing your changes'}[phase];
      if (task.pending_approval) title = 'Waiting for your permission';
      else if(task.check_stream?.session_allowed) title = 'Running tests · allowed for this session';
      else if (task.status === 'waiting_retry') title = 'Waiting for a free route';
      else if (task.status === 'stopping') title = 'Pausing work';
      outcome = task.pending_approval || task.status === 'stopping' ? 'pending' : 'live';
      if (task.pending_approval) detail = task.pending_approval.command.join(' ');
      else if (task.check_stream) detail = task.check_stream.command.join(' ');
      else if (task.status === 'waiting_retry') detail = guide.progress(task,at).detail;
      else if (task.stream?.phase === 'thinking') detail = 'Thinking through the next step';
      else if (task.stream?.phase === 'tool') detail = `Preparing ${String(task.stream.tool || 'the next action').replaceAll('_',' ')}`;
      else if (task.stream?.phase === 'answer') detail = 'Writing a response';
      else if (task.web_read) detail = `Reading ${task.web_read.url}`;
      else if (task.stream || request && events.at(-1)===request) {detail = 'Waiting for the model to respond';if(task.branch_run&&!['checks','commit'].includes(phase))title=`Waiting for the ${role}’s response`;}
      if(phase==='review'&&!review&&events.some(e=>e.kind==='review_coaching')&&!task.pending_approval&&!['stopping','waiting_retry'].includes(task.status)){
        title='Reassessing the review';
        if(!task.stream||task.stream.phase==='waiting')detail='I’m asking the reviewer to identify the remaining blocker from the saved evidence.';
      }
    }
    if(phase==='coordinator'){const intervention=last(events,'coordinator_recovery')?.detail||{};title=live?'Coordinator helping':'Coordinator consultation';detail=intervention.summary||'Checking saved evidence to help the worker choose its next step.';if(live&&task.resource_wait)detail=task.resource_wait.reason||'Waiting for the shared local inference slot.';else if(live&&task.stream?.phase==='thinking')detail='Thinking through the saved evidence';else if(live&&task.stream?.phase==='answer')detail='Writing recovery guidance';else if(live)detail='Waiting for the local coordinator to respond';outcome=live?'live':intervention.state==='applied'?'done':'pending';if(!live&&intervention.state==='applied')title='Guidance sent to the worker';if(!live&&intervention.state==='failed'){title='Coordinator reply could not be used';detail=intervention.diagnostic||detail;outcome='failed';}}
    if(phase==='work'&&!live&&!toolEvents.length&&events.some(e=>e.kind==='model')&&task.coordinator_recovery?.length){title='Worker continuation stopped';detail='No further action was recorded in this step.';outcome='pending';}
    const observed=events.findLast(e=>e.kind==='coordinator_recovery'&&e.detail?.state==='result')?.detail;if(observed){detail=observed.summary||detail;if(!live){title=phase==='checks'?(observed.result?.passed?'Check passed after guidance':'Check did not pass after guidance'):'Worker saved an edit after guidance';outcome=phase==='checks'?(observed.result?.passed?'passed':'failed'):'done';}}
    const lastAction = toolEvents.at(-1);
    const activity = lastAction ? guide.activityItem(lastAction)?.title || lastAction.title : '';
    const controller = ['checks','commit'].includes(phase);
    return {...step, title, detail, outcome, model:controller?(phase==='checks'?'Local verification':'Local Git'):model, role:controller?'controller':role, elapsed, activity};
  }
  function response(events, key, task, latest, at) {
    const steps = [];
    let phase = 'work';

    const substantive = events.filter(e => !['generation','state','model','context'].includes(e.kind));
    const final = substantive.at(-1);
    for (const event of events) {
      if (event.kind === 'assistant' || event.kind === 'generation') {
        if (steps.length && event !== final) steps.at(-1).events.push(event);
        continue;
      }
      if (!['tool','model','checks','check_reused','checkpoint','review','review_coaching','coordinator_recovery','handoff','routing','tool_error','guard','permission','commit','web','planning_inspection'].includes(event.kind)) continue;
      if (event.kind === 'guard' && event.title === 'Applied User Guidance') continue;
      phase = eventPhase(event, phase);
      if (steps.at(-1)?.phase !== phase) steps.push({id:`${key}-${event.id ?? events.indexOf(event)}`,phase,events:[],live:false});
      steps.at(-1).events.push(event);
    }
    const live = latest && guide.isActive(task.status);
    const stream = latest ? task.stream : null;
    // A simple streamed chat answer needs no execution row.
    const onlyChat = stream?.phase === 'answer' && !events.some(e => ['tool','checks','handoff','review','review_coaching','coordinator_recovery','tool_error'].includes(e.kind));
    if (live && !onlyChat) {
      phase = currentPhase(task, steps.at(-1)?.phase);
      if (steps.at(-1)?.phase !== phase) steps.push({id:`${key}-live-${phase}`,phase,events:[],live:false});
      steps.at(-1).live = true;
    }
    // A model preparing the next tool is not a separate completed work step.
    // Keep its output with the next action instead of showing “0 actions”.
    for (let i=0; i<steps.length; i++) {
      const step=steps[i];
      if (!step.live && ['work','plan'].includes(step.phase) && !step.events.some(e=>['tool','tool_error','web','planning_inspection'].includes(e.kind)) && steps.length>1 && steps[i-1]?.phase!=='coordinator' && steps[i+1]?.phase!=='coordinator') {
        if (steps[i+1]) steps[i+1].events.unshift(...step.events);
        else steps[i-1].events.push(...step.events);
        steps.splice(i--,1);
      }
    }
    for (let i=1; i<steps.length; i++) {
      if (steps[i-1].phase===steps[i].phase) {
        steps[i-1].events.push(...steps[i].events);
        steps[i-1].live=steps[i].live;
        steps.splice(i--,1);
      }
    }
    let reply = committed(final) && !task.demo ? 'What would you like to work on next?' : final?.kind === 'assistant' && typeof final.detail === 'string' ? final.detail : '';
    const thinkingText = events.findLast(e => e.kind === 'generation' && e.detail?.thinking)?.detail?.thinking;
    if (reply && thinkingText) {
      const trimmedReply = reply.trim(), trimmedThinking = thinkingText.trim();
      if (trimmedReply === trimmedThinking || trimmedThinking.startsWith(trimmedReply)) {
        reply = '';
      } else if (trimmedReply.startsWith(trimmedThinking)) {
        reply = trimmedReply.slice(trimmedThinking.length).trim();
      }
    }
    if (onlyChat || !live && !events.some(e => ['tool','checks','check_reused','review','review_coaching','coordinator_recovery','handoff','tool_error','commit','planning_inspection'].includes(e.kind) || (e.kind === 'generation' && e.detail?.thinking))) steps.length = 0;
    let intro = '';
    if (steps.length) {
      intro = live ? {coordinator:"The worker got stuck. I'm checking the saved work to help it choose the next step.",work:'I’m working through your request.',checks:'I’m checking the changes before sending them for review.',review:'I’m getting a second opinion on the changes and test results.',plan:'I’m choosing the next step for your request.',commit:'I’m committing your approved changes.'}[phase] : 'Here’s what I worked through.';
      if (live && phase === 'work' && last(events, 'review')?.detail?.decision === 'REQUEST_CHANGES') intro = 'The review found something to improve. I’m addressing that feedback.';
      if (latest && task.status==='waiting_retry') intro='I’m waiting for the free route’s cooldown before checking availability again.';
      else if (latest && task.pending_approval) intro = 'I need your permission to run this check.';
      else if (latest && ['paused','budget_paused','interrupted','error','takeover_requested'].includes(task.status)) intro = 'I’ve saved the work so far. I need your attention before continuing.';
      else if (latest && guide.canCommit(task)) intro = task.status === 'completed' ? 'Checks have passed. The changes are ready for your review.' : 'The changes have passed checks and review. They’re ready for your decision.';
      else if (steps.at(-1).phase === 'commit' && steps.at(-1).events.some(e => e.detail?.commit)) intro = 'Your approved changes are committed to the project.';
    }
    return {kind:'assistant',id:key,latest,live,intro,reply:onlyChat ? stream.content || reply : reply,stream:live && !onlyChat ? stream : null,steps:steps.map(s => stepView(s,task,at))};
  }
  function branchBuild(task, at) {
    const run=task.branch_run, items=run.items||[], planning=Boolean(task.planning_request&&!run.authorization_ref);
    const finalOperation=['finalizing','ready_for_merge','merging','merged','left_on_branch'].includes(run.status)||(!run.current_item_id&&items.length&&items.every(i=>['committed','satisfied_without_change'].includes(i.status)));
    const current=planning?'planning':finalOperation?'final':run.current_item_id||'run';
    const entries=[];
    let inherited=task.planning_request?'planning':'run';
    function owner(event) {
      const explicit=event.detail?.item_id||event.detail?.detail?.item_id||event.item_id;
      if(items.some(item=>item.id===explicit))return explicit;
      if(event.actor?.role==='planner'||event.detail?.role==='planner'||event.title?.startsWith('Requesting planner:'))return 'planning';
      if(['branch_final','branch_merged'].includes(event.kind)||(event.branch_run_id===run.id&&event.item_id===null&&inherited!=='planning'))return 'final';
      return inherited;
    }
    function emit(events,key,id,latest) {
      const item=items.find(i=>i.id===id), active=latest&&id===current;
      const receipt=item?.commit_receipt,validReceipt=receipt?.stage==='completed'&&receipt.item_id===item.id&&receipt.run_id===run.id;
      const committed=validReceipt&&(item.status==='committed'&&/^[a-f0-9]{40,64}$/.test(receipt.new_tip||'')||item.status==='satisfied_without_change'&&receipt.outcome==='satisfied_without_change');
      const commitPending=active&&run.status==='running'&&item&&!committed&&(item.status==='committing'||Boolean(item.ready_receipt));
      const streamedMetric=(task.request_metrics||[]).find(r=>r.id===task.stream?.request_id);
      const streamBelongs=active&&events.some(e=>e.kind==='model')&&(!streamedMetric?.branch_item_id||streamedMetric.branch_item_id===id)&&!(item?.status==='working'&&task.stream?.role==='reviewer');
      const branchRunning = active && (['running', 'finalizing', 'merging'].includes(run.status) || Boolean(task.check_stream));
      const view={...task,events,stream:streamBelongs?task.stream:null,check_stream:active?task.check_stream:null,pending_approval:active?task.pending_approval:null,
        status:active?(commitPending&&run.status==='running'?'running':branchRunning&&task.status==='approved'?'running':task.status):'awaiting_reply'};
      let reply=response(events,key,view,active,at);
      reply.operation=id;reply.itemTitle=item?`Item ${items.indexOf(item)+1} of ${items.length} · ${item.title}`:id==='final'?'Final integration':'';
      reply.owner=active;reply.label=active?(id==='planning'?'Planning':commitPending?'Committing':task.status==='reviewing'?'Reviewing':task.check_stream?'Checking':guide.isActive(task.status)?'Working':''):'';
      const question=active&&run.pause_detail?.cause!=='essential_clarification'&&(run.waiting_for_user||task.clarification?.question);
      reply.reply=question||''; // Narration is retained inside its step; explicit questions remain visible.
      if(id==='planning') {
        const busy=active&&guide.isActive(task.status),ready=active&&run.status==='awaiting_authorization';
        const step=stepView({id:`${key}-plan`,phase:'plan',events,live:busy},view,at);
        const request=events.findLast(e=>e.kind==='model');
        step.title=ready?'Your plan is ready':busy?task.stream?.phase==='waiting'||request?'Waiting for the planner’s response':'Selecting a planner':active?'Planning paused':'Plan prepared';
        if(busy&&task.stream&&task.stream.phase!=='waiting')step.title=task.stream.phase==='tool'?'Reading project context':'Preparing your proposal';
        step.detail=ready?'Review the plan before authorizing work.':busy?'You can add guidance while I work.':active?'The saved planning work is retained.':'The proposal is retained in Plan.';
        if(!busy){step.live=false;step.outcome=ready?'done':active?'pending':'done';}
        reply.steps=[step];reply.live=busy;reply.stream=busy?task.stream:null;
        reply.intro=busy?'I’m preparing a plan for your request.':ready?'Your plan is ready to review.':active?'Planning has stopped. The saved details are below.':'I prepared the plan for this work.';
        reply.label=busy?'Planning':'';
      } else {
        if(!reply.steps.length&&(active||events.some(e=>['assistant','generation'].includes(e.kind)))){const live=active&&guide.isActive(view.status);reply.steps=[stepView({id:key+'-work',phase:currentPhase(view,'work'),events,live},view,at)];reply.live=live;reply.stream=live?view.stream:null;}
        if(commitPending) {
          reply.steps=reply.steps.map(step=>stepView({...step,live:false},{...view,stream:null,check_stream:null},at));
          reply.steps.push(stepView({id:`${key}-commit`,phase:'commit',events:[],live:true},{...view,stream:null,check_stream:null,pending_approval:null},at));
          reply.live=true;reply.stream=null;reply.intro='Independent item review is complete. I’m recording this item’s approved result.';
        } else if(committed) {
          reply.steps=reply.steps.map(step=>stepView({...step,live:false},{...view,stream:null,check_stream:null},at));
          const unchanged=item.status==='satisfied_without_change';
          reply.steps.push({id:`${key}-receipt`,receipt:true,phase:'commit',events:[],live:false,role:'controller',model:'Local Git',title:unchanged?'Item already satisfied':'Item committed',detail:unchanged?'Reviewed; no change was needed.':`${item.commit_receipt.new_tip?.slice(0,8)||''} · ${item.title}`,outcome:'passed'});
          reply.live=false;reply.stream=null;reply.intro=unchanged?'This item was reviewed and already satisfied.':'This item’s reviewed changes are committed.';
        }
        if(active&&id==='run'&&run.status==='running'&&!run.current_item_id){
          const first=!(run.items||[]).some(item=>item.commit_receipt?.stage==='completed');
          reply.label=first?'Starting':'Preparing next item';reply.intro=first?'Your plan is approved. I’m preparing the first item.':'I’m preparing the next item in your approved plan.';reply.stream=null;
          reply.steps=[{id:key+'-transition',phase:'work',events:[],live:true,role:'controller',model:'cheapoS controller',title:first?'Starting your approved plan':'Preparing the next item',detail:first?'Waiting for the first item to start.':'Completed item evidence remains with its item above.',outcome:'live',elapsed:guide.progress(task,at)?.elapsed||'0s'}];reply.live=true;
        }
        if(active&&id==='final'&&run.status==='finalizing'){reply.live=true;reply.intro='I’m running final checks on the integrated changes.';}
        if(active&&id==='final'&&run.status==='ready_for_merge'){reply.live=false;reply.intro='Final checks and independent review are complete. Inspect the cumulative changes before merging.';}
        if(active&&id==='final'&&run.status==='merged'){
          const merged=run.merge_receipt?.stage==='completed',record=events.findLast(e=>e.kind==='branch_merged');
          const target=String(run.target_ref||record?.detail?.target_ref||'').replace(/^refs\/heads\//,'');
          const sha=run.merge_receipt?.feature_tip||record?.detail?.sha;
          reply.live=false;reply.stream=null;reply.intro=merged?`The reviewed run has been merged locally${target?' into '+target:''}.`:'The saved integration is awaiting confirmation.';
          reply.steps=reply.steps.filter(step=>step.events.some(e=>['tool','checks','check_reused','review'].includes(e.kind)));
          reply.steps.push({id:key+'-integration',phase:'commit',events:[],live:false,role:'controller',model:'Local Git',title:merged?'Local integration complete':'Confirming local integration',detail:merged?`${target||'Target retained in Plan'} · ${/^[a-f0-9]{40,64}$/.test(sha||'')?sha.slice(0,8):'Commit identity unavailable'}`:'Inspect the saved integration status before continuing.',outcome:merged?'passed':'pending'});
        }
      }
      const phaseCounts={};
      reply.steps=reply.steps.map(step=>({...step,id:`${key}-${step.phase}-${phaseCounts[step.phase]=(phaseCounts[step.phase]||0)+1}`}));
      entries.push(reply);
    }
    const turns=guide.turns(task,at);
    for(const turn of turns) {
      entries.push({kind:'user',id:`user-${turn.index}`,text:turn.userPrompt});
      let batch=[],id=inherited,part=0,attempt=null;
      const flush=(latest=false)=>{emit(batch,`operation-${turn.index}-${id}-${part++}`,id,latest);batch=[];};
      for(const event of turn.events) {
        if(event.kind==='steer') {
          if(batch.length)flush();
          entries.push({kind:'user',id:`steer-${turn.index}-${event.id}`,text:typeof event.detail==='string'?event.detail:event.detail?.message||event.title,steer:true});
          continue;
        }
        const next=owner(event);
        if((next!==id||(attempt&&event.run_id&&attempt!==event.run_id))&&batch.length)flush();
        if(event.run_id)attempt=event.run_id;
        id=next;inherited=next;batch.push(event);
      }
      if(turn.isLatest&&id!==current){if(batch.length)flush();id=current;}
      flush(turn.isLatest);
    }
    for(const entry of entries){if(entry.kind==='assistant'&&entries.findLast(e=>e.kind==='assistant'&&e.operation===entry.operation)!==entry){entry.steps=entry.steps.filter(s=>!s.receipt);if(entry.intro.includes('committed')||entry.intro.includes('already satisfied'))entry.intro='Earlier work on this item.';}}
    return entries;
  }
  function build(task, at = Date.now()) {
    task={...task,stream:guide.liveStream(task)};
    if(task.branch_run)return branchBuild(task,at);
    const entries = [];
    for (const turn of guide.turns(task, at)) {
      entries.push({kind:'user',id:`user-${turn.index}`,text:turn.userPrompt});
      let start = 0, part = 0;
      for (const steer of turn.steerMessages) {
        if (steer.eventIndex > start) entries.push(response(turn.events.slice(start,steer.eventIndex),`reply-${turn.index}-${part++}`,task,false,at));
        entries.push({kind:'user',id:`steer-${turn.index}-${steer.id ?? steer.eventIndex}`,text:steer.text,steer:true});
        start = steer.eventIndex + 1;
      }
      entries.push(response(turn.events.slice(start),`reply-${turn.index}-${part}`,task,turn.isLatest,at));
    }
    return entries;
  }
  return {build,readyForNext};
})();
if (typeof module !== 'undefined') module.exports.conversation = CheapOSConversation;
