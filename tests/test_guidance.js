const {test}=require('node:test');
const assert=require('node:assert/strict');
const {taskGuide,projectName,workLabel}=require('../dist/guidance.js');
const task=overrides=>({status:'ready',worker_turns:0,changes:[],checks:[],checkpoints:[],events:[],...overrides});

test('live checks keep their command and elapsed time while output updates',()=>{
  const {progress}=require('../dist/guidance.js');
  const t=task({status:'running',updated_at:'2026-09-13T00:00:09Z',check_stream:{command:['python3','-m','unittest'],started_at:'2026-09-13T00:00:00Z',updated_at:'2026-09-13T00:00:09Z',output:'test_bounds ... ok'}});
  const p=progress(t,Date.parse('2026-09-13T00:00:10Z'));
  assert.equal(p.stage,'checks');assert.equal(p.elapsed,'10s');
  assert.equal(p.detail,'python3 -m unittest');assert.match(p.hint,/output is shown below/);
  assert.equal(progress({...t,status:'stopping'}).stage,'stopping');
});

test('a saved task asks for an explicit start',()=>{
  const g=taskGuide(task());
  assert.equal(g.primary,'start');
  assert.equal(g.facts.checks,'Not run yet');
  assert.equal(g.facts.reviewer,'Not reached yet');
});
test('a worker-turn stop identifies the request allowance separately from spending',()=>{
  const g=taskGuide(task({status:'budget_paused',error_code:'worker_turn_limit',worker_turns:85,request_worker_turns:40,limits:{worker_turns:40}}));
  assert.equal(g.title,'This request used its worker turns.');
  assert.match(g.description,/40 of 40/);
  assert.match(g.description,/spending limits stay the same/);
  assert.equal(g.primaryLabel,'Review turn limit');
});
test('a reviewer failure preserves the passing check without implying approval',()=>{
  const g=taskGuide(task({status:'error',worker_turns:12,changes:[{},{}],checks:[{passed:true}],checkpoints:[{decision:'PENDING'}],events:[{kind:'model',title:'Requesting reviewer: fixture'}]}));
  assert.equal(g.title,'The reviewer didn’t finish.');
  assert.equal(g.primary,'connections');
  assert.equal(g.facts.worker,'2 files changed');
  assert.equal(g.facts.checks,'Latest check passed');
  assert.equal(g.facts.reviewer,'No decision returned');
  assert.equal(g.facts.you,'Review comes last');
  assert.equal(g.retry,true);
});
test('an old pending checkpoint does not misidentify a later worker failure',()=>{
  const g=taskGuide(task({status:'error',checkpoints:[{decision:'PENDING'}],events:[{kind:'model',title:'Requesting reviewer: old'},{kind:'model',title:'Requesting worker: new'}]}));
  assert.equal(g.title,'This task stopped before it finished.');
});
test('passing checks alone never offer a completed or approved result',()=>{
  for(const status of ['running','reviewing','paused','budget_paused']){
    const g=taskGuide(task({status,changes:[{}],checks:[{passed:true}],checkpoints:[{decision:'PENDING'}]}));
    assert.notEqual(g.tone,'success');
    assert.equal(g.facts.reviewer,'Awaiting a decision');
  }
});
test('the latest failing check replaces an earlier pass in the overview',()=>{
  assert.equal(taskGuide(task({checks:[{passed:true},{passed:false}]})).facts.checks,'Latest check failed');
});
test('command approval and takeover remain explicit user actions',()=>{
  const waiting=taskGuide(task({status:'waiting_approval'}));
  assert.equal(waiting.primary,'approve');
  assert.equal(waiting.secondary,'decline');
  const takeover=taskGuide(task({status:'takeover_requested',checkpoints:[{decision:'TAKE_OVER'}]}));
  assert.equal(takeover.primary,'resume');
  assert.match(takeover.primaryLabel,/takeover/);
  assert.equal(takeover.facts.reviewer,'Takeover requested');
});
test('finished takeover is distinguished from independent reviewer approval',()=>{
  const completed=taskGuide(task({status:'completed',checkpoints:[{decision:'TAKE_OVER'}]}));
  assert.equal(completed.primary,'changes');
  assert.equal(completed.tone,'attention');
  assert.match(completed.description,/not an independent reviewer approval/);
  const approved=taskGuide(task({status:'approved',checkpoints:[{decision:'APPROVE'}]}));
  assert.equal(approved.tone,'success');
  assert.equal(approved.primary,'changes');
  assert.equal(approved.secondary,'export');
});
test('sample-project IDs are given a readable label without renaming real projects',()=>{
  assert.equal(projectName({source:'/project/.cheapos/examples/a123ff',demo:false}),'Sample Python project');
  assert.equal(projectName({source:'/projects/my-app',demo:false}),'my-app');
  assert.equal(projectName({source:'/projects/my-app',demo:true}),'Local demo');
});

test('collapsed work labels describe observed actions only', () => {
  assert.equal(workLabel([{kind:'tool',title:'read file'},{kind:'model',title:'Requesting worker'},{kind:'checks',title:'Verification failed'}]), 'Explored the project (1) · Ran 1 check');
  assert.equal(workLabel([{kind:'tool_error',title:'replace text'}]), 'Work details');
});

const {progress,failure}=require('../dist/guidance.js');
const when=Date.parse('2026-09-12T23:00:00Z');
const request={id:2,kind:'model',title:'Requesting worker: gemma4:31b',time:new Date(when).toISOString(),detail:{timeout_seconds:180}};
test('a long wait is visible but is not labelled a timeout while running',()=>{
  const p=progress(task({status:'running',events:[{kind:'tool',title:'read file',detail:{arguments:{path:'README.md'}}},request]}),when+70000);
  assert.equal(p.title,'Waiting for the model’s response');assert.equal(p.elapsed,'1m 10s');assert.equal(p.action,'Read README.md');assert.equal(p.evidence,'No files changed yet');assert.equal(p.slow,true);
  assert.equal(progress(task({status:'error'})),null);
});
test('checks and stopping have distinct execution states',()=>{
  assert.equal(progress(task({status:'running',events:[request,{kind:'tool',title:'Running verification',time:request.time,detail:{command:['python3','-m','unittest']}}]}),when).stage,'checks');
  assert.equal(progress(task({status:'stopping',events:[request]}),when).title,'Stop requested');
});
test('live reasoning and answer chunks replace the generic wait',()=>{
  const base=task({status:'running',events:[request],stream:{model:'gemma4:31b',phase:'thinking',updated_at:new Date(when+60000).toISOString()}});
  assert.equal(progress(base,when+60000).title,'Receiving the model’s thinking');
  assert.equal(progress(base,when+60000).slow,false);
  assert.equal(progress(base,when+91000).slow,true);
  base.stream.phase='answer';assert.equal(progress(base,when+60000).title,'Receiving the model’s answer');
});
test('only evidence of a timeout produces the timeout explanation',()=>{
  const failed=task({status:'error',error:'Model request did not complete.',events:[request,{kind:'error',time:new Date(when+180000).toISOString()}]});
  assert.equal(failure(failed).timeout,true);assert.match(failure(failed).description,/No files were changed/);
  failed.events[1].time=new Date(when+179980).toISOString();assert.equal(failure(failed).timeout,true);
  failed.events[1].time=new Date(when+2000).toISOString();assert.equal(failure(failed).timeout,false);
  failed.error_code='model_timeout';assert.equal(failure(failed).timeout,true);
});

const {activity,activityItem}=require('../dist/guidance.js');
test('route failures expose the model and reason',()=>{
  const item=activityItem({kind:'routing',title:'Free model check failed',detail:{model:'free-model',error:'Output limit reached'}});
  assert.equal(item.note,'free-model · Output limit reached');
});
test('Activity separates this request from an earlier approved turn',()=>{
  const a=activity(task({prompt:'First',patch:'new',events:[{kind:'checks',detail:{passed:true,digest:'old'}},{kind:'review',detail:{checkpoint:1,decision:'APPROVE'}},{kind:'user',detail:'Now change another file'}],checkpoints:[{number:1,decision:'APPROVE',diff:'old'}]}));
  assert.equal(a.request,'Now change another file');assert.equal(a.checks,'Not run for this request');assert.equal(a.review,'Not reviewed for this request');
});
test('Activity never presents an earlier patch check as current approval',()=>{
  const a=activity(task({patch:'updated',patch_digest:'new',events:[{kind:'checks',title:'Verification passed',detail:{passed:true,digest:'old'}}]}));
  assert.equal(a.checks,'Passed · earlier patch');assert.equal(a.review,'Not reviewed for this request');
});
test('Activity names real file actions and excludes preparation from completed work',()=>{
  assert.equal(activityItem({kind:'tool',title:'read file',detail:{arguments:{path:'README.md'},result:{total_lines:80}}}).title,'Read README.md');
  assert.equal(activityItem({kind:'model',title:'Requesting worker: X'}),null);
  assert.equal(activityItem({kind:'tool',title:'Running verification'}),null);
  assert.equal(activityItem({kind:'tool_error',title:'Failed',detail:{error:'No match'}}).failed,true);
});

test('web reading is distinct from repository search and shows its source',()=>{
  assert.equal(activityItem({kind:'tool',title:'search',detail:{arguments:{query:'OmniRoute'},result:[]}}).title,'Searched project for “OmniRoute”');
  const item=activityItem({kind:'tool',title:'read url',detail:{arguments:{url:'https://example.org'},result:{title:'Guide',source_url:'https://example.org/guide',start_line:1,end_line:120,has_more:true}}});
  assert.equal(item.title,'Read web page · Guide');assert.match(item.note,/https:\/\/example.org\/guide/);assert.match(item.note,/more available/);
  const p=progress(task({status:'running',web_read:{url:'https://example.org/guide',started_at:'2026-09-13T00:00:00Z'}}),Date.parse('2026-09-13T00:00:05Z'));
  assert.equal(p.stage,'web');assert.equal(p.elapsed,'5s');assert.equal(p.title,'Opening web page');
});
test('Activity shows handoffs and verified review evidence newest first',()=>{
  const a=activity(task({patch:'p',patch_digest:'digest',events:[{kind:'handoff',title:'Delegated',detail:{from:'Local',to:'Remote'}},{kind:'checks',title:'Passed',detail:{passed:true,digest:'digest'}},{kind:'review',title:'Approved',detail:{checkpoint:1,decision:'APPROVE'}}],checkpoints:[{number:1,diff:'p'}]}));
  assert.equal(a.checks,'Passed');assert.equal(a.review,'Approved');assert.equal(a.items[0].title,'Approved');assert.equal(a.items[2].note,'Local → Remote');
});
