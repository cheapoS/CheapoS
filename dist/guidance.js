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
      case 'budget_paused': return {...result,tone:'attention',title:task.error_code==='worker_turn_limit'?'This request used its worker turns.':'This task reached a limit.',description:task.error_code==='worker_turn_limit'?`Used ${task.request_worker_turns??task.worker_turns} of ${task.limits.worker_turns} worker turns for this request. Your work is saved. Increase that allowance to continue; spending limits stay the same.`:'CheapOS paused to respect your limits. Inspect what it produced, then review the remaining budget before continuing.',primary:'resume',primaryLabel:task.error_code==='worker_turn_limit'?'Review turn limit':'Review limits & resume'};
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
    const edits=events.filter(e=>e.kind==='tool'&&['write file','replace text','replace lines'].includes(e.title)).length;
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
    const action=completed?({'read file':`Read ${args.path||'a file'}`,'outline file':`Outlined ${args.path||'a file'}`,'read url':`Read ${args.url||'web page'}`,'write file':`Created ${args.path||'a file'}`,'replace text':`Edited ${args.path||'a file'}`,'replace lines':`Edited ${args.path||'a file'}`,'list files':'Listed project files','search':`Searched project for ${args.query||'text'}`}[completed.title]||completed.title):'No tool actions completed yet';
    const files=(task.changes||[]).length,evidence=files?`${files} changed file${files===1?'':'s'} saved`:'No files changed yet';
    let stage='working',title='Preparing the next step',detail='',since=latest?.time||task.updated_at;
    if(task.status==='waiting_approval'){stage='approval';title='Waiting for your approval';detail=(task.pending_approval?.command||[]).join(' ')}
    else if(task.status==='stopping'){stage='stopping';title='Stop requested';detail='Waiting for the current operation to finish. No new tools will start.'}
    else if(task.check_stream){stage='checks';title='Running checks';detail=task.check_stream.command.join(' ');since=task.check_stream.started_at}
    else if(task.web_read){stage='web';title='Opening web page';detail=task.web_read.url;since=task.web_read.started_at}
    else if(latest?.kind==='model'){
      stage='model';const role=latest.title.startsWith('Requesting reviewer:')?'reviewer':latest.title.startsWith('Requesting coordinator:')?'coordinator':'worker';
      title=role==='reviewer'?'Waiting for the reviewer’s response':'Waiting for the model’s response';
      if(task.answer_pending)title='Preparing an answer from gathered evidence';
      detail=latest.title.replace(/^Requesting (worker|reviewer|coordinator): /,'');since=latest.time;
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
      const names={'read file':`Read ${path||'a file'}`,'outline file':`Outlined ${path||'a file'}`,'read url':`Read web page · ${result?.title||args.url||''}`,'write file':`Created ${path||'a file'}`,'replace text':`Edited ${path||'a file'}`,'replace lines':`Edited ${path||'a file'}`,'list files':'Listed project files','search':`Searched project for “${args.query||''}”`,'get diff':'Inspected the saved changes'};
      title=names[title]||title;icon=path?'file':'search';
      note=result?.syntax_warning?`⚠ ${result.syntax_warning}`:Array.isArray(result)?`${result.length} results`:result?.total_lines?`${result.total_lines} lines in file`:['write file','replace text','replace lines'].includes(event.title)?'Saved in the task copy':'';
      if(event.title==='read url')note=`${result?.source_url||args.url} · lines ${result?.start_line}–${result?.end_line}${result?.has_more?' · more available':''}`;
      if(d.model)note=[d.model,note].filter(Boolean).join(' · ');
    }else if(event.kind==='check_reused'){icon='tests';note='The same patch and command already passed; no test rerun.'}
    else if(event.kind==='human_decision'){icon='shield';note=d.decision==='defer'?'Edits remain saved. Continue chatting or reopen your decision.':'The reviewed patch is ready for your decision again.'}
    else if(event.kind==='checks'){icon='tests';note=(d.command||[]).join(' ')}
    else if(event.kind==='review'){icon='shield';note=d.feedback||''}
    else if(event.kind==='handoff'){icon='branch';note=`${d.from} → ${d.to}`}
    else if(event.kind==='checkpoint'){icon='shield';note=d.worker_summary||''}
    else if(event.kind==='tool_error'){icon='x';title=d.code==='invalid_tool_arguments'?'Asking the model to correct its tool call':'Action could not finish';note=d.error||''}
    else if(event.kind==='guard'){icon='clock';note=typeof d==='string'?d:''}
    else if(event.kind==='routing'){icon='branch';note=[d.model,d.error].filter(Boolean).join(' · ')||d.summary||''}
    else if(event.kind==='permission'){icon='shield';note=(d.command||[]).join(' ')}
    else if(event.kind==='web'){icon='search';title='Requested web page';note=d.url||''}
    else if(event.kind==='commit'){icon='branch';note=d.commit?`${d.commit.slice(0,8)} · ${d.branch} · ${d.message}`:d.error||d.branch||''}
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
  function canCommit(task) {
    if(task.commit_pending)return true;
    const check=task.checks?.at(-1),review=task.checkpoints?.at(-1);
    return Boolean(task.changes?.length&&['approved','completed','awaiting_reply'].includes(task.status)&&check?.passed&&check.digest===task.patch_digest&&(task.status==='completed'||review?.decision==='APPROVE'&&review.diff===task.patch));
  }
  function commitDeferred(task) {return task.human_decision?.decision==='defer'&&task.human_decision.digest===task.patch_digest}
  function modelHealth(model,at=Date.now()) {
    const h=model.health||{},remaining=Math.ceil(((h.retry_at||0)*1000-at)/60000);
    if(remaining>0)return `${h.cooldown_scope==='provider'?'Provider cooling down':'Cooling down'} · ${remaining}m`;
    if((h.worker_responses||0)+(h.reviewer_responses||0)>0)return 'Responded in a task';
    return h.tool_check_passed?'Tool check passed':'Not tested yet';
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
        if (['write file', 'replace text', 'replace lines'].includes(e.title)) {
          items.push({ type: 'edit', path: args.path || 'file', event: e });
          continue;
        }
        if (e.title !== 'Running verification') items.push({ type: 'tool', title: e.title, event: e });
        continue;
      }
      if (e.kind === 'guard') {
        const text = typeof d === 'string' ? d : '';
        const isStall = e.title.includes('what it found') || text.includes('twice') || text.includes('stopped');
        items.push({ type: 'guard', title: isStall ? 'Worker redirected' : e.title, note: isStall ? 'Repeated read detected; CheapOS redirected worker to continue from existing evidence.' : text, stalled: isStall, event: e });
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
      const editedFiles = [...new Set(turnEvents.filter(e => e.kind === 'tool' && ['write file', 'replace text', 'replace lines'].includes(e.title)).map(e => e.detail?.arguments?.path).filter(Boolean))];
      const outlineCount = grouped.filter(g => g.type === 'outline').length;
      const readCount = grouped.filter(g => g.type === 'read').reduce((sum, g) => sum + g.count, 0) + outlineCount;
      const webCount = grouped.filter(g => g.type === 'web').length;
      const searchCount = grouped.filter(g => g.type === 'search').reduce((sum, g) => sum + g.count, 0);
      const totalActions = readCount + webCount + searchCount + editedFiles.length;
      let phase = 'completed', title = 'Work completed', subtitle = '', statusIcon = 'check';
      if (isLive) {
        statusIcon = 'working';
        const p = progress(task, at), elapsed = p?.elapsed || '0s';
        if (task.status === 'waiting_approval') {
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
      const hasMeaningfulWork = totalActions > 0 || editedFiles.length > 0 || latestCheck != null || latestCommit != null || ['paused', 'error', 'ready_to_apply', 'committed'].includes(phase);
      const isStreamingAnswerWithoutTools = isLive && task.stream?.phase === 'answer' && totalActions === 0;
      const hasActivity = isLive ? (!isStreamingAnswerWithoutTools && (turnEvents.length > 0 || isLive)) : hasMeaningfulWork;
      return {
        index: seg.index, userPrompt: seg.userPrompt, isLatest: seg.isLatest, isLive, phase, title, subtitle, statusIcon,
        worker: effectiveWorker, reviewer: effectiveReviewer, coordinator: effectiveCoordinator, hasActivity,
        totalActions, editedFiles, readCount, webCount, searchCount, groupedItems: grouped, latestCheck, latestReview, latestCommit,
        canCommit: canCommitNow, assistantReply, thinkingBlocks, events: turnEvents
      };
    });
  }
  return {modelHealth,commitDeferred,taskGuide,projectName,workLabel,progress,failure,duration,activity,activityItem,canCommit,isActive:status=>active.has(status),friendlyModel,groupActivityItems,turns};
})();
if(typeof module!=='undefined')module.exports=CheapOSGuide;
