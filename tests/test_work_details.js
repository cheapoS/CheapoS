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
