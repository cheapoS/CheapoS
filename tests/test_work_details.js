const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8');
const extract=(start,end)=>source.slice(source.indexOf(start),source.indexOf(end,source.indexOf(start)));
const ctx={CheapOSGuide:require('../dist/guidance.js'),state:{task:null}};
vm.createContext(ctx);
vm.runInContext(source.split("\n'use strict';\nconst $ =")[0]+
  extract('const esc =','const taskBusy=')+
  extract('function eventDetail(','function progressMarkup(')+
  extract('function thinkingMarkup(','function permissionMarkup(')+'\nthis.view=CheapOSChatView;',ctx);
const event=(id,kind,title,detail={})=>({id,kind,title,detail,time:'2026-09-14T17:00:00Z'});
const tool=(id,title,path)=>event(id,'tool',title,{arguments:{path},result:{content:'saved content'}});
const step=(events,more={})=>({id:'work-1',role:'worker',phase:'work',model:'worker-model',outcome:'done',title:'Worked on your request',detail:'Saved work',events,...more});
function render(events,{live=false,stream=null,task={},phase='work'}={}){
 return ctx.view.message({kind:'assistant',id:'reply',steps:[step(events,{live,phase})],live,stream,reply:''},task);
}

test('update preparation is immediately visible in Chat without empty agent output or stale actions',()=>{
 const task={id:'saved',prompt:'Improve the project',status:'paused',events:[],changes:[],
  integration_preparation:{id:'update',authorized:true,status:'running',stage:'checking'}};
 const entry=ctx.CheapOSGuide.conversation.build(task).at(-1);
 const html=ctx.view.message(entry,task);
 assert.match(html,/Your update request is saved/);
 assert.match(html,/role="status" aria-live="polite"/);
 assert.match(html,/spinner/);assert.match(html,/Checking latest project/);
 assert.doesNotMatch(html,/data-operation-actions|Waiting for the first action|Model identity unavailable|data-work-elapsed/);
 entry.preparation.title='<unsafe>';entry.preparation.detail='<details>';
 assert.match(ctx.view.message(entry,task),/&lt;unsafe&gt;/);
 assert.match(ctx.view.message(entry,task),/&lt;details&gt;/);
});

test('finished unattended review renders the action mount instead of stale preparation',()=>{
 const task={status:'approved',prompt:'Improve the project',events:[],changes:[],
  integration_preparation:{id:'update',authorized:true,status:'running',stage:'combining',dispatched:true},
  branch_run:{id:'run',status:'ready_for_merge',readiness:{manifest:{files:[{path:'app.js'}]}},items:[{id:'one',status:'committed'}]}};
 const entry=ctx.CheapOSGuide.conversation.build(task).at(-1),html=ctx.view.message(entry,task);
 assert.match(html,/data-operation-actions/);
 assert.match(html,/Final checks and independent review are complete/);
 assert.doesNotMatch(html,/Combining changes|Preparing update|Your update request is saved/);
});

test('empty model channel markers stay out of saved and live chat without hiding real text',()=>{
 const marker='<|channel>thought\n<channel|>';
 const saved=event('marker','assistant','Worker',marker);
 const html=render([saved,tool('read','read file','example.py')]);
 assert.doesNotMatch(html,/&lt;\|channel|workflow-role/);
 assert.match(html,/example.py/);
 assert.equal(saved.detail,marker);
 for(let i=1;i<=marker.length;i++){
   const live=render([],{live:true,stream:{phase:'answer',content:marker.slice(0,i),role:'worker'}});
   assert.doesNotMatch(live,/workflow-preview|<pre data-thinking/);
 }
 assert.equal(ctx.view.message({kind:'assistant',id:'empty',steps:[],reply:marker},{}),'');
 const actual=render([event('text','assistant','Worker',marker+'Checking the file now.')]);
 assert.match(actual,/Checking the file now/);
 const thought=render([event('think','generation','Model thinking',{thinking:'Checking the file now.'})]);
 assert.match(thought,/thinking-panel/);
 assert.match(thought,/Checking the file now/);
 const user=ctx.view.message({kind:'user',id:'user-0',text:marker},{});
 assert.match(user,/&lt;\|channel/);
});

test('route waiting shows a clock rather than an active-work spinner',()=>{
 const t={status:'waiting_retry'};
 const html=ctx.view.message({kind:'assistant',id:'waiting',steps:[step([],{live:true,outcome:'live'})],live:true,reply:''},t);
 assert.match(html,/#i-clock/);
 assert.doesNotMatch(html,/class="spinner"/);
});

test('large routing history never displaces thinking or edits from chat',()=>{
 const routing=Array.from({length:120},(_,i)=>event('route-'+i,'routing','Checking candidates',{model:'candidate-noise'}));
 const thinking=event('think','generation','Model output',{request_id:'r',model:'worker',thinking:'I will make the focused change.'});
 const task={routing_traces:[{id:'route',role:'worker',candidates:[{model:'image-model',reason:'capability_missing'}],attempts:[{request_id:'private-request-id'}]}]};
 const html=render([thinking,tool('edit','replace text','target.py'),...routing],{task});
 assert.match(html,/I will make the focused change/);assert.match(html,/Edited target.py/);
 assert.doesNotMatch(html,/candidate-noise|image-model|private-request-id|Showing the latest 80/);
 assert.match(html,/data-workflow-logs/);
 assert.match(ctx.view.routingDetails(task),/image-model.*capability missing/);
});
test('probe output is connection activity, not feature-planning thinking',()=>{
 const probe=event('probe','model','Requesting planner',{purpose:'probe'});
 const thinking=event('probe-thought','generation','Model thinking',{request_id:'probe',thinking:'Call routing_ready with the probe marker.'});
 const plan=event('plan-thought','generation','Model thinking',{request_id:'plan',thinking:'Design the golden-task runner.'});
 const task={events:[probe,thinking,plan]};
 const html=render([probe,thinking,plan],{task,phase:'plan'});
 assert.doesNotMatch(html,/routing_ready|probe marker/);
 assert.match(html,/Design the golden-task runner/);
 assert.equal(thinking.detail.thinking,'Call routing_ready with the probe marker.');
 for(const stream of [{request_id:'probe'}, {request_id:'new',purpose:'probe'}]){
   const live=render([],{task,live:true,phase:'plan',stream:{...stream,phase:'thinking',thinking:'Call routing_ready'}});
   assert.match(live,/Checking model connection/);assert.doesNotMatch(live,/routing_ready/);
 }
 const inspection=event('read','planning_inspection','Inspected project context for the plan',{path:'cheapos/benchmark.py',inspection:1,limit:6});
 const ready={status:'ready',active_role:'planner',prompt:'Plan a benchmark',events:[probe,inspection,event('answer','assistant','Plan ready','Your plan is ready.')],providers:{}};
 const reply=ctx.CheapOSGuide.conversation.build(ready).find(e=>e.kind==='assistant');
 assert.equal(reply.steps[0].phase,'plan');assert.equal(reply.steps[0].detail,'1 project inspection');
 assert.match(ctx.view.message(reply,ready),/Read cheapos\/benchmark.py/);
});
test('consecutive exploration collapses without hiding edits or crossing thinking',()=>{
 const html=render([tool('a','read file','first.py'),event('request','model','Requesting worker'),tool('b','search','second.py'),
   tool('edit','replace text','first.py'),tool('c','list files','.'),
   event('think','generation','Output',{request_id:'r',thinking:'Verify the change'}),tool('d','read file','last.py')]);
 assert.match(html,/data-event="explore-a"/);assert.match(html,/Explored the project · 2 actions/);
 assert.equal((html.match(/class="workflow-exploration"/g)||[]).length,3);
 assert.ok(html.indexOf('Edited first.py')>html.indexOf('Read first.py'));
 assert.match(html,/data-event="generation-r" open/);
});
test('planner inspection labels omit a nonexistent limit and keep saved bounded counts',()=>{
 for(const detail of [{inspection:18},{inspection:2,limit:6}]){
  const html=render([event('inspection','planning_inspection','Inspected project context',{path:'app/package.json',...detail})],{phase:'plan'});
  assert.match(html,/evidence saved for the proposal/);
  assert.doesNotMatch(html,/undefined|null/);
  assert.ok(html.includes(detail.limit?'Inspection 2 of 6':'Inspection 18 ·'));
 }
});
test('automatic planning corrections stay in technical logs while chat shows findings and handoff',()=>{
 const events=[event('repair','planning_repair','Correcting project inspection',{attempt:2,error:'Use exact inventory paths and retained findings'}),
   event('read','planning_inspection','Inspected project context',{path:'app/package.json',inspection:3}),
   event('thought','generation','Model thinking',{thinking:'The manifest identifies the relevant check.'}),
   event('handoff','planning_recovery','The planner could not complete planning.',{model:'previous-planner'}),
   event('ready','assistant','Plan ready','The proposal is ready.')];
 const task={events},saved=JSON.stringify(task),html=render(events,{phase:'plan',task});
 assert.doesNotMatch(html,/Correcting project inspection|Use exact inventory paths|"attempt"|previous-planner/);
 assert.match(html,/Read app\/package.json/);
 assert.match(html,/The manifest identifies the relevant check/);
 assert.match(html,/Trying another planner/);
 assert.match(html,/Keeping your request and the findings gathered so far/);
 assert.match(html,/The proposal is ready/);
 assert.match(html,/data-workflow-logs/);
 const logs=require('../dist/branch_ui.js').technicalMarkup(task);
 assert.match(logs,/Correcting project inspection/);
 assert.match(logs,/Use exact inventory paths and retained findings/);
 assert.match(logs,/<dt>attempt<\/dt><dd><pre>2<\/pre>/);
 assert.equal(JSON.stringify(task),saved);
});
test('failure and complete reviewer feedback are readable before another disclosure',()=>{
 const feedback='The UI is still missing. Add the control before resubmitting.';
 const html=render([event('error','tool_error','Action failed',{error:'File hash changed'}),
   event('review','review','Changes requested',{decision:'REQUEST_CHANGES',feedback}),
   event('check','checks','Failed tests',{passed:false,command:['python3','-m','unittest'],output:'FAIL: boundary',exit_code:1,run_id:'check'})]);
 assert.match(html,/class="workflow-failure"/);assert.match(html,/File hash changed/);
 assert.match(html,/data-event="work-event-review" open/);assert.match(html,/Add the control before resubmitting/);
 assert.match(html,/data-event="command-check" open/);assert.match(html,/FAIL: boundary/);
});
test('live output opens immediately and has an escaped preview for collapsed steps',()=>{
 const stream={phase:'thinking',request_id:'live',thinking:'Actual thought <script>unsafe</script>'};
 const html=render([],{live:true,stream});
 assert.match(html,/data-step="work-1" open/);assert.match(html,/class="workflow-preview"/);
 assert.match(html,/Actual thought &lt;script&gt;unsafe&lt;\/script&gt;/);assert.doesNotMatch(html,/<script>/);
 const waiting=render([],{live:true,stream:{phase:'waiting'}});
 assert.doesNotMatch(waiting,/workflow-preview|Waiting for the next chunk|<pre/);assert.match(waiting,/Waiting for the worker’s response/);
});
test('review progress is visible in the step summary before opening Details',()=>{
 const t={status:'reviewing',active_role:'reviewer',prompt:'Review saved work',events:[
  event('paging','review_paging','Reviewing the large item',{packets:39}),
  event('review','review_request','Requesting item packet review',{manifest_id:'technical-manifest-id',chunk_ids:['item:8'],stage:'chunk'}),
  event('model','model','Requesting reviewer: reviewer-model',{})]};
 const reply=ctx.CheapOSGuide.conversation.build(t).find(e=>e.kind==='assistant');
 const html=ctx.view.message(reply,t);
 assert.match(html,/<small[^>]*data-review-progress>Chunk 8 of 39<\/small>/);
 assert.ok(html.indexOf('Chunk 8 of 39')<html.indexOf('class="workflow-details"'));
 assert.doesNotMatch(html,/technical-manifest-id/);
});
test('current reviewer output follows recorded thinking and actions through consecutive requests',()=>{
 const t={status:'reviewing',active_role:'reviewer',prompt:'Check the restart change',changes:[],events:[
  event('r1','model','Requesting reviewer: reviewer-model'),
  event('g1','generation','Model thinking',{request_id:'r1',role:'reviewer',thinking:'Check the restart handler.'}),
  event('read','tool','read file',{role:'reviewer',arguments:{path:'server.py'}}),
  event('r2','model','Requesting reviewer: reviewer-model')],
  stream:{request_id:'r2',role:'reviewer',model:'reviewer-model',phase:'waiting'}};
 const markup=()=>ctx.CheapOSGuide.conversation.build(t).map(e=>ctx.view.message(e,t)).join('');
 let html=markup();
 assert.match(html,/Independent review in progress/);
 assert.equal((html.match(/class="workflow-stream"/g)||[]).length,1);
 assert.ok(html.indexOf('class="workflow-stream"')>html.indexOf('Read server.py'));
 t.stream.phase='thinking';t.stream.thinking='Verify that the request carries its token.';
 html=markup();assert.ok(html.indexOf('data-thinking="workflow-stream-r2"')>html.indexOf('Read server.py'));
 assert.match(html.slice(html.indexOf('data-thinking="workflow-stream-r2"')),/Verify that the request/);
 assert.doesNotMatch(html,/Waiting for the reviewer’s response/);
 t.status='stopping';html=markup();assert.match(html,/Pausing work/);assert.match(html,/class="workflow-stream"/);
 t.status='reviewing';
 t.events.push(event('g2','generation','Model thinking',{request_id:'r2',role:'reviewer',thinking:t.stream.thinking}),
  event('review','review','Review passed',{decision:'APPROVE',feedback:'The handler and tests match.'}));
 t.status='approved';
 html=markup();assert.doesNotMatch(html,/workflow-stream|class="spinner"|data-work-elapsed/);
 assert.match(html,/Independent review passed/);
});
test('live command output follows the earlier completed check',()=>{
 const html=render([event('old','checks','Passed',{passed:true,command:['python3','-m','unittest'],output:'Earlier test passed',run_id:'old'})],
  {live:true,phase:'checks',task:{check_stream:{run_id:'new',command:['python3','-m','unittest'],output:'Checking the changed file'}}});
 assert.ok(html.indexOf('command-new')>html.indexOf('Earlier test passed'));
});
test('only the latest recorded thinking opens by default, and interruptions stay labeled',()=>{
 const html=render([event('a','generation','Output',{request_id:'old',thinking:'First thought'}),
   event('b','generation','Output',{request_id:'new',thinking:'Partial thought',interrupted:true})]);
 assert.doesNotMatch(html,/data-event="generation-old" open/);
 assert.match(html,/data-event="generation-new" open/);assert.match(html,/Thinking · interrupted/);
});
test('technical routing view keeps every retained attempt, newest first with unknown identity',()=>{
 const html=ctx.view.routingDetails({routing_traces:[{id:'old',role:'worker',requested_route:'old-route'},
   {id:'new',role:'reviewer',selected_model:'new-route',attempts:[{request_id:'first'},{request_id:'last'}],attempts_truncated:true}]});
 assert.ok(html.indexOf('new-route')<html.indexOf('old-route'));
 assert.ok(html.indexOf('Request last')<html.indexOf('Request first'));
 assert.match(html,/Attempt evidence is partial/);assert.match(html,/served unknown/);
});
test('earlier recorded thinking panel stays collapsed when a live stream is active',()=>{
 const html=render([event('a','generation','Output',{request_id:'past',thinking:'Past finished thought'})],
   {live:true,stream:{phase:'thinking',request_id:'live',thinking:'Active live thinking'}});
 assert.doesNotMatch(html,/data-event="generation-past" open/);
 assert.match(html,/class="workflow-stream"[^>]*data-phase="thinking"/);
 assert.match(html,/Active live thinking/);
});
test('thinking panels and workflow assistant messages attribute roles clearly in chat',()=>{
 const thinkingEvent=event('gen-1','generation','Model thinking',{request_id:'g1',role:'planner',thinking:'Inspecting the files.'});
 const assistantEvent={id:'msg-1',kind:'assistant',title:'Planner',actor:{role:'planner'},detail:'I planned the following improvement.'};
 const html=render([thinkingEvent,assistantEvent]);
 assert.match(html,/<span class="thinking-role">Planner:<\/span>\s*Thinking/);
 assert.match(html,/<strong class="workflow-role">Planner:<\/strong>\s*I planned the following improvement\./);
});
test('live workflow stream is a collapsible details element with summary and chevron',()=>{
 const html=render([],{live:true,stream:{phase:'thinking',request_id:'live1',thinking:'Stream thinking content'}});
 assert.match(html,/<details class="workflow-stream"[^>]*data-event="workflow-stream-live1"[^>]*open>/);
 assert.match(html,/<summary class="stream-label">/);
 assert.match(html,/Stream thinking content/);
});
