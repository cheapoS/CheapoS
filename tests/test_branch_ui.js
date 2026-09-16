const test=require('node:test');const assert=require('node:assert/strict');const ui=require('../dist/branch_ui.js');
test('explicit requests offer mode; incidental or quoted instructions do not',()=>{
 for(const input of ['Start a branch run for these changes','Please complete this job on a feature branch','Build the utilities on a new feature branch'])assert.equal(ui.intent(input),'offer',input);
 for(const input of ['What is a feature branch?','The branch is feature/parser','Summarize this document','"Start a branch run"','> Start a branch run','`Start a branch run`','Explain how to start a branch run','Do not start a branch run'])assert.equal(ui.intent(input),'interactive',input);
});
function fixture(){const receipt={stage:'completed',item_id:'one',run_id:'run',new_tip:'a'.repeat(40),outcome:'changed'};return {branch_run:{id:'run',status:'running',feature_ref:'refs/heads/feature/job',target_ref:'refs/heads/main',current_item_id:'two',items:[{id:'one',title:'CSV parser',status:'committed',commit_receipt:receipt},{id:'two',title:'CLI',status:'working'}],events:[{id:'event',kind:'item_completed',detail:{item_id:'one',commit:receipt.new_tip}}]}};}
test('durable item receipts project outcomes and deduplicate milestones across polling',()=>{const task=fixture();task.branch_run.events.push(task.branch_run.events[0]);const p=ui.projectRun(task);assert.equal(p.milestones.length,1);assert.equal(p.current,2);assert.equal(p.items[0].commit,'a'.repeat(40));assert.deepEqual(ui.projectRun(task),p);});
test('pending commits and wrong receipt or event SHA never appear completed',()=>{const task=fixture();task.branch_run.items[0].commit_receipt.stage='intent';assert.equal(ui.projectRun(task).items[0].done,false);assert.equal(ui.projectRun(task).milestones.length,0);task.branch_run.items[0].commit_receipt.stage='completed';task.branch_run.items[0].commit_receipt.item_id='other';assert.equal(ui.projectRun(task).items[0].done,false);task.branch_run.items[0].commit_receipt.item_id='one';task.branch_run.events[0].detail.commit='b'.repeat(40);assert.equal(ui.projectRun(task).milestones.length,0);});
test('reviewed no-change has no fake commit; finalizing is not ready or merged',()=>{const task=fixture(),item=task.branch_run.items[0];item.status='satisfied_without_change';item.commit_receipt.outcome='satisfied_without_change';task.branch_run.events[0].detail.commit=null;task.branch_run.status='finalizing';const p=ui.projectRun(task);assert.equal(p.items[0].unchanged,true);assert.equal(p.items[0].commit,null);assert.equal(p.ready,false);assert.equal(p.merged,false);task.branch_run.status='merged';assert.equal(ui.projectRun(task).label,'Confirming integration');task.branch_run.merge_receipt={stage:'completed'};assert.equal(ui.projectRun(task).merged,true);});
test('untrusted titles and diff text can be escaped safely',()=>assert.equal(ui.escape('<script>"&'), '&lt;script&gt;&quot;&amp;'));
test('cumulative diff keeps first and last files and continuation pages',()=>{const text='diff --git a/first b/first\n-old\n+new\ndiff --git a/last b/last\n+last\n';const sections=ui.diffSections(text);assert.equal(sections.length,2);assert.match(sections[0].text,/-old/);assert.match(sections[1].text,/last/);assert.equal(ui.diffSections('+page continuation')[0].title,'Diff continuation');assert.equal(sections.map(s=>s.text).join(''),text);});
test('manual composer limits map to cumulative units without per-request fields',()=>{assert.deepEqual(ui.proposedLimits({dollars:2,run_minutes:45,worker_turns:12,iterations:5,checkpoint_turns:6,output_tokens:1024,reviewer_tokens:50000,check_seconds:120}),{dollars:2,working_seconds:2700,output_tokens:1024,reviewer_tokens:50000,check_seconds:120});assert.equal(ui.proposedLimits().working_seconds,900);assert.throws(()=>ui.proposedLimits({run_minutes:Infinity}));assert.throws(()=>ui.proposedLimits({dollars:NaN}));});
test('paused finalization exposes recheck only after all recorded outcomes completed',()=>{const task=fixture();task.branch_run.status='paused';assert.equal(ui.projectRun(task).canRecheck,false);task.branch_run.items.pop();assert.equal(ui.projectRun(task).canRecheck,true);task.branch_run.items[0].commit_receipt.stage='intent';assert.equal(ui.projectRun(task).canRecheck,false);});
test('resume results distinguish fresh consent from saved merge recovery',()=>{assert.equal(ui.resumeAction({needs_consent:true}),'consent');assert.equal(ui.resumeAction({needs_merge_recovery:true,needs_consent:true}),'merge_recovery');assert.equal(ui.resumeAction({needs_consent:false,task:{}}),'resumed');const task=fixture();task.branch_run.items.pop();task.branch_run.status='paused';task.branch_run.merge_operation={id:'saved'};const p=ui.projectRun(task);assert.equal(p.pendingMerge,true);assert.equal(p.canRecheck,false);});
test('new chat without revision marker never routes into revision submission',()=>{assert.equal(ui.isRevisionTarget(null,undefined),false);assert.equal(ui.isRevisionTarget(undefined,undefined),false);assert.equal(ui.isRevisionTarget({id:'task'},undefined),false);assert.equal(ui.isRevisionTarget({id:'task'},'other'),false);assert.equal(ui.isRevisionTarget({id:'task'},'task'),true);});
test('branch activity keeps Pause available across intermediate approval and finalization',()=>{for(const status of ['running','finalizing','merging'])assert.equal(ui.isBusy({status:'approved',branch_run:{status}}),true);assert.equal(ui.isBusy({status:'approved',branch_run:{status:'ready_for_merge'}}),false);assert.equal(ui.isBusy({status:'reviewing',branch_run:{status:'paused'}}),false);assert.equal(ui.isBusy({status:'reviewing'}),true);assert.equal(ui.isBusy(null),false);});
test('actual event renderer accepts branch review and checkpoint metadata without legacy fields',()=>{const fs=require('node:fs'),vm=require('node:vm');const source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8');const match=source.match(/function eventDetail\(event\) \{[\s\S]*?\n\}(?=\nfunction sourceLink)/);assert.ok(match);const render=vm.runInNewContext('('+match[0]+')',{esc:ui.escape});assert.match(render({kind:'review',detail:{item_id:'one',candidate_id:'candidate'}}),/Review event/);assert.doesNotThrow(()=>render({kind:'review'}));const checkpoint=render({kind:'checkpoint',title:'Reviewing branch item',detail:{item_id:'one',candidate_id:'candidate'}});assert.match(checkpoint,/Reviewing branch item/);assert.doesNotMatch(checkpoint,/undefined|data-checkpoint/);});
test('active duration shows seconds for short runs and minutes with remaining seconds',()=>{assert.equal(ui.duration(12.9),'12s');assert.equal(ui.duration(65),'1m 5s');assert.equal(ui.duration(0),'0s');});
test('saved unattended proposals retain their mode before authorization',()=>{assert.equal(ui.hasRun(null),false);assert.equal(ui.hasRun({id:'ordinary'}),false);assert.equal(ui.hasRun({branch_run:{status:'awaiting_authorization',authorization_ref:null}}),true);assert.equal(ui.hasRun({branch_run:{status:'running',authorization_ref:'approved'}}),true);});
test('saved terminal previews remain readonly after leave or merge',()=>{assert.equal(ui.terminalRun({branch_run:{status:'left_on_branch'}}),true);assert.equal(ui.terminalRun({branch_run:{status:'merged'}}),true);assert.equal(ui.terminalRun({branch_run:{status:'ready_for_merge'}}),false);assert.equal(ui.terminalRun(null),false);});

test("measurement status requires explicit plan opt-in", () => {
 const base={branch_run:{schema_version:1,id:"run",status:"running",items:[],plan:{measurement:true}}};
 assert.equal(ui.projectRun(base).measurement,true);
 base.branch_run.plan.measurement=false;
 assert.equal(ui.projectRun(base).measurement,false);
});

test('planning chats stay busy and accept follow-up before authorization',()=>{
 const task={status:'running',planning_request:{planning_id:'request'},branch_run:{status:'draft',items:[],authorization_ref:null}};
 assert.equal(ui.isBusy(task),true);assert.equal(ui.isPlanning(task),true);assert.equal(ui.projectRun(task).label,'Planning');
 task.status='paused';assert.equal(ui.isBusy(task),false);assert.equal(ui.isPlanning(task),true);
 task.branch_run.status='awaiting_authorization';assert.equal(ui.isBusy(task),false);assert.equal(ui.isPlanning(task),true);
 task.branch_run.authorization_ref='approved';assert.equal(ui.isPlanning(task),false);
 assert.equal(ui.isBusy({status:'running',branch_run:{status:'draft'}}),true);
});

test('saved plan keeps approved scope separate from progress and authorized revisions',()=>{
 const original={items:[{id:'one',title:'Original <scope>',instructions:'Read code',acceptance_criteria:['Works'],required_checks:[{argv:['python3','-m','unittest']}]}],final_checks:[{argv:['check']}],limits:{dollars:0}};
 const task={title:'Job',branch_run:{status:'running',authorization_ref:'auth',authorization:{contract:{plan:original,original_request:'Implement original',feature_ref:'refs/heads/work'}},plan:{items:[{id:'one',title:'Narrated replacement'}]},items:[{id:'one',status:'working'}],current_item_id:'one',amendments:[{origin:'operator',authorization_id:'revision-auth',item:{id:'two',title:'Repair',acceptance_criteria:['Works'],required_checks:[]}}]}};
 const html=ui.planMarkup(task);assert.match(html,/Approved plan/);assert.match(html,/Original &lt;scope&gt;/);assert.doesNotMatch(html,/Narrated replacement/);assert.match(html,/Current item/);assert.match(html,/python3 -m unittest/);assert.match(html,/Authorized revisions/);assert.match(html,/revision-auth/);assert.equal(ui.planMarkup(JSON.parse(JSON.stringify(task))),html);
 task.branch_run.authorization=null;assert.equal(ui.savedPlan(task).incomplete,true);assert.match(ui.planMarkup(task),/Approved plan unavailable/);assert.doesNotMatch(ui.planMarkup(task),/Narrated replacement/);
});
test('ordinary chat and planning placeholders omit Plan until persisted proposal exists',()=>{assert.equal(ui.savedPlan({}),null);const task={branch_run:{status:'draft',plan:{items:[{title:'placeholder'}]}}};assert.equal(ui.savedPlan(task),null);task.branch_run.status='awaiting_authorization';assert.equal(ui.savedPlan(task).approved,false);});

test('Start transitions immediately, binds approval, and deduplicates pending submissions',async()=>{
 let accept,calls=0;const actions=[];const pending=new Promise(r=>accept=r);const controller=ui.startController({api:(url,body)=>{calls++;assert.equal(url,'/tasks/a/branch-start');assert.deepEqual(body,{proposal_id:'inspected',approved:true});return pending;},transition:id=>actions.push(id)});
 const proposal={task_id:'a',proposal_id:'inspected'},promise=controller.start(proposal);proposal.proposal_id='changed';assert.deepEqual(actions,['a']);assert.equal(controller.get('a').status,'pending');controller.start(proposal);assert.equal(calls,1);accept({});await promise;assert.equal(controller.get('a').status,'accepted');
});
test('lost Start responses reconcile saved state without issuing another approval',async()=>{
 const calls=[];const c=ui.startController({api:async(url,body)=>{calls.push([url,body]);if(body)throw Error('response lost');return {branch_run:{authorization_ref:'saved'}};}});await c.start({task_id:'a',proposal_id:'one'});assert.equal(c.get('a').status,'accepted');assert.equal(calls.length,2);assert.equal(calls[1][1],undefined);
 const rejected=ui.startController({api:async(url,body)=>{if(body)throw Error('Proposal expired');return {branch_run:{}};}});await rejected.start({task_id:'b',proposal_id:'two'});assert.equal(rejected.get('b').status,'rejected');assert.equal(rejected.get('b').error,'Proposal expired');assert.equal(rejected.get('a'),undefined);
 const unknown=ui.startController({api:async()=>{throw Error('offline');}});await unknown.start({task_id:'c'});assert.equal(unknown.get('c').status,'unknown');await unknown.start({task_id:'c'});assert.match(unknown.get('c').error,/unknown/);
});

test('saved authorization alone does not falsely acknowledge incomplete startup',async()=>{let calls=0;const c=ui.startController({api:async(url,body)=>{calls++;if(body)throw Error('Worktree creation failed');return {branch_run:{authorization_ref:'saved',status:'awaiting_authorization'}};}});await c.start({task_id:'a',proposal_id:'inspected'});assert.equal(c.get('a').status,'partial');assert.match(c.get('a').error,/Worktree creation failed/);assert.ok(c.get('a').proposal);await c.start({task_id:'a'});assert.equal(calls,2);});
test('technical logs reverse saved append order without mutating it, escape and redact bounded fields',()=>{const events=[1,2,3].map(id=>({id,time:'same',kind:'error',title:'<script>',detail:{error:'api_key=secret-value bad schema',headers:{authorization:'hidden'},output:'<b>failure</b>',request_id:'r'+id}}));const task={events,error:'specific schema failure'};assert.deepEqual(ui.technicalEvents(task).map(e=>e.id),[3,2,1]);assert.deepEqual(events.map(e=>e.id),[1,2,3]);const html=ui.technicalMarkup(task);assert.ok(html.indexOf('raw-3')<html.indexOf('raw-1'));assert.match(html,/specific schema failure/);assert.match(html,/&lt;b&gt;failure/);assert.doesNotMatch(html,/secret-value|hidden|<script>/);assert.match(html,/redacted/);assert.match(ui.technicalMarkup({}),/No technical events/);assert.match(ui.technicalMarkup({events_truncated:true}),/history was truncated/);});
test('specific canonical unknown pause remains prominent and escaped before housekeeping logs',()=>{const task={branch_run:{status:'paused',pause_detail:{version:1,cause:'unknown',explanation:'Planner rejected <bad> schema',next_action:'inspect'}},events:[{id:'latest',title:'Housekeeping',kind:'status'}]};const html=ui.technicalMarkup(task);assert.ok(html.indexOf('Planner rejected &lt;bad&gt; schema')<html.indexOf('Housekeeping'));assert.match(html,/Back to chat actions/);});
test('partial startup retry is explicit and reuses the exact inspected proposal',async()=>{let writes=0;const bodies=[];const c=ui.startController({api:async(url,body)=>{if(body){writes++;bodies.push(body);if(writes===1)throw Error('setup failed');return {};}return {branch_run:{authorization_ref:'saved',status:'awaiting_authorization'}};}});await c.start({task_id:'a',proposal_id:'original'});await c.start({task_id:'a',proposal_id:'different'});assert.equal(writes,1);await c.retry('a');assert.equal(writes,2);assert.deepEqual(bodies,[{proposal_id:'original',approved:true},{proposal_id:'original',approved:true}]);assert.equal(c.get('a').status,'accepted');});

test('direct planning payload supports prompt, document, combined input and explicit overrides',()=>{
 const defaults={base_ref:'refs/heads/trunk',target_ref:'refs/heads/trunk'};
 for(const input of [{prompt:'Build it'},{document:'docs/task.md'},{prompt:'Build',document:'docs/task.md'}]){const p=ui.planningPayload({repository:'/project',planning_id:'same',...input},defaults);assert.equal(p.base_ref,defaults.base_ref);assert.equal(p.planning_id,'same');assert.equal(p.measurement,false);}
 assert.equal(ui.planningPayload({repository:'/p',prompt:'x',base_ref:'refs/heads/custom',measurement:true},defaults).base_ref,'refs/heads/custom');
 assert.throws(()=>ui.planningPayload({prompt:'x'}),/Open a project/);assert.throws(()=>ui.planningPayload({repository:'/p'}),/prompt or.*document/);
});
test('proposal edits invalidate Start and late validation cannot approve newer fields',async()=>{
 let resolve;const v=ui.proposalValidation({proposal_id:'old'},()=>new Promise(r=>resolve=r));assert.equal(v.get().canStart,true);v.edit();assert.equal(v.get().canStart,false);const pending=v.validate({});v.edit();resolve({proposal_id:'stale'});assert.equal(await pending,null);assert.equal(v.get().canStart,false);const next=v.validate({});resolve({proposal_id:'current'});await next;assert.equal(v.get().current.proposal_id,'current');assert.equal(v.get().canStart,true);
 const failed=ui.proposalValidation({proposal_id:'old'},async()=>{throw Error('Feature branch already exists');});failed.edit();await assert.rejects(failed.validate({}),/Feature branch/);assert.equal(failed.get().canStart,false);assert.equal(failed.get().pending,false);
});
test('direct composer submission locks before discovery and sends one planning identity without a dialog',async()=>{
 const fs=require('node:fs'),vm=require('node:vm');const source=fs.readFileSync(require.resolve('../dist/branch_ui.js'),'utf8');const fn=source.match(/ async function submitPlanning\(retry\)\{[\s\S]*?\n \}(?=\n function renderStart)/)[0];let discovery;const calls=[],input={value:'Build it'},errorNode={textContent:'',focus(){}};const state={selection:1,project:{path:'/project'}};
 const context={input,getState:()=>state,settings:()=>({repository:'/project',prompt:'Build it',feature_ref:'refs/heads/new'}),planningPayload:ui.planningPayload,documentRow:{querySelector:()=>errorNode},save(){},key:()=>'/project',options:{openPlanningChat:()=>++state.selection,onDraftChange(){}},renderStart(){},selectTask:async id=>calls.push(['selected',id]),refresh:async()=>{},localStorage:{setItem(){}},api:(url,body)=>{calls.push([url,body]);return url==='/branch-runs/project'?new Promise(r=>discovery=r):Promise.resolve({task_id:'planned'});}};
 vm.createContext(context);vm.runInContext('let busy=false,startState=null,drafts={},storageKey="fixture";'+fn+';this.submit=submitPlanning;',context);
 const one=context.submit();await context.submit();assert.equal(calls.length,1);discovery({base_ref:'refs/heads/main',target_ref:'refs/heads/main'});await one;assert.equal(calls.filter(c=>c[0]==='/branch-runs/plan-start').length,1);assert.ok(calls[1][1].planning_id);assert.equal(calls[1][1].prompt,'Build it');assert.equal(input.value,'');assert.doesNotMatch(fn,/dialog\(/);
 // A lost response preserves the request identity and any newer draft on recovery.
 input.value='Build it';let lostPayload;context.api=async(url,body)=>{if(url.endsWith('/project'))return {base_ref:'refs/heads/main',target_ref:'refs/heads/main'};lostPayload=body;throw Error('Connection lost');};await context.submit();const saved=vm.runInContext('startState.request',context);assert.equal(saved.planning_id,lostPayload.planning_id);assert.equal(input.value,'Build it');input.value='New unsent idea';context.api=async(url,body)=>{assert.equal(body.planning_id,saved.planning_id);input.value='Newer unsent idea';return {task_id:'planned'};};await context.submit(saved);assert.equal(input.value,'Newer unsent idea');
});

test('accepted Start publishes the saved task before clearing pending feedback',async()=>{
 let accept;const saved={id:'a',status:'running',branch_run:{status:'running',authorization_ref:'saved'}};
 const observations=[];let visible={id:'a',status:'awaiting_reply'};
 const c=ui.startController({api:()=>new Promise(r=>accept=r),onTask:t=>{visible=t;},onChange:id=>observations.push([c.get(id).status,visible.status])});
 const pending=c.start({task_id:'a',proposal_id:'inspected'});
 assert.deepEqual(observations,[['pending','awaiting_reply']]);
 accept(saved);await pending;
 assert.equal(visible,saved);assert.deepEqual(observations.at(-1),['accepted','running']);
});
test('Start reconciliation publishes a saved pause without retrying the approval',async()=>{
 let visible,calls=0;const saved={id:'a',status:'paused',error:'Missing test runner',branch_run:{status:'paused',authorization_ref:'saved'}};
 const c=ui.startController({api:async(url,body)=>{calls++;if(body)throw Error('lost response');return saved;},onTask:t=>visible=t});
 await c.start({task_id:'a',proposal_id:'inspected'});assert.equal(visible,saved);assert.equal(calls,2);assert.equal(c.get('a').status,'accepted');
});
function refreshFixture(){
 const fs=require('node:fs'),vm=require('node:vm'),source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8');
 const snippet=source.slice(source.indexOf('let contextRefresh=null;'),source.indexOf('async function resumeBranchRun'));
 const state={task:{id:'a',status:'awaiting_reply',updated_at:'2026-09-14T12:00:00Z'},selection:1};let renderCount=0,gatewayCalls=0,releaseGateway,resolveTask;
 const gateway=new Promise(r=>releaseGateway=r);const replies=[];
 const context={state,console,toast:()=>{},loadStartup:async()=>{},loadReadiness:async()=>{},loadTasks:async()=>{},loadAdmission:async()=>{},loadGateway:()=>{gatewayCalls++;return gateway;},api:()=>replies.length?Promise.resolve(replies.shift()):new Promise(r=>resolveTask=r),renderTask:()=>renderCount++};
 vm.createContext(context);vm.runInContext(snippet,context);
 return {state,context,replies,releaseGateway,resolveTask:t=>resolveTask(t),renderCount:()=>renderCount,gatewayCalls:()=>gatewayCalls};
}
test('task polling and later output continue while one gateway refresh is unresolved',async()=>{
 const f=refreshFixture();
 for(const status of ['running','reviewing','paused']){
  f.replies.push({id:'a',status,updated_at:`2026-09-14T12:00:0${f.renderCount()+1}Z`});
  await f.context.refresh({background:true});assert.equal(f.state.task.status,status);
 }
 assert.equal(f.renderCount(),3);assert.equal(f.gatewayCalls(),1);f.releaseGateway();await f.context.refreshContext();
});
test('late polling cannot undo an accepted Start or overwrite a different selected task',async()=>{
 const f=refreshFixture(),pending=f.context.refresh({background:true});
 const saved={id:'a',status:'running',updated_at:'2026-09-14T12:00:02Z',branch_run:{status:'running'}};
 f.context.receiveStartedTask(saved);f.resolveTask({id:'a',status:'awaiting_reply',updated_at:'2026-09-14T12:00:01Z'});await pending;assert.equal(f.state.task,saved);
 f.context.receiveStartedTask({...saved,status:'paused',updated_at:'2026-09-14T12:00:01Z'});assert.equal(f.state.task,saved);
 const next=f.context.refresh({background:true});f.state.task={id:'b'};f.state.selection++;
 f.resolveTask({...saved,status:'reviewing'});await next;f.context.receiveStartedTask(saved);assert.equal(f.state.task.id,'b');
 f.releaseGateway();await f.context.refreshContext();
});
test('actual startup renderer covers pending, accepted-stale, running and paused states',()=>{
 const fs=require('node:fs'),vm=require('node:vm'),source=fs.readFileSync(require.resolve('../dist/branch_ui.js'),'utf8');
 const snippet=source.slice(source.indexOf(' function render(task)'),source.indexOf(' function renderPlan(task)'));
 let record={status:'pending',started_at:'2026-09-14T12:00:00Z'};const panel={innerHTML:'',querySelector:()=>null};
 const branchResumeStatus=new Map();
 const context={sync:()=>{},getState:()=>({branchResumeStatus}),document:{querySelector:()=>({querySelector:s=>s==='#branch-run-summary'?panel:{}})},projectRun:ui.projectRun,pausePresentation:ui.pausePresentation,starts:{get:()=>record},escape:ui.escape,summaryHTML:'',detailStates:new Map(),options:{}};
 vm.createContext(context);vm.runInContext(snippet,context);
 const t={id:'a',status:'awaiting_reply',branch_run:{id:'run1',status:'awaiting_authorization',items:[]}};
 context.render(t);assert.match(panel.innerHTML,/Starting your approved plan/);assert.match(panel.innerHTML,/data-start-time/);assert.doesNotMatch(panel.innerHTML,/data-proposal/);
 record.status='accepted';context.render(t);assert.match(panel.innerHTML,/Plan accepted. Loading the saved run/);
 t.branch_run.authorization_ref='auth';t.branch_run.status='running';t.status='running';context.render(t);assert.doesNotMatch(panel.innerHTML,/branch-start-status/);
 t.branch_run.status='paused';t.status='paused';context.render(t);assert.doesNotMatch(panel.innerHTML,/data-start-time/);
 t.branch_run.pause_detail={version:1,cause:'unknown',next_action:'inspect',explanation:'Unknown stop',item_id:'one',stage:'working',role:'worker',model:'fixture',diagnostic_id:'request'};
 branchResumeStatus.set('a',{status:'pending'});context.render(t);assert.match(panel.innerHTML,/Continuing saved work/);assert.match(panel.innerHTML,/data-resume disabled/);
 branchResumeStatus.set('a',{status:'error',message:'Exact <failure>'});context.render(t);assert.match(panel.innerHTML,/Exact &lt;failure&gt;/);assert.match(panel.innerHTML,/<button type="button" data-resume >Resume<\/button>/);
 assert.match(panel.innerHTML,/<li>Item: one<\/li>/);assert.match(panel.innerHTML,/<li>Model: fixture<\/li>/);
});
