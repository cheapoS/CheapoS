const {test}=require('node:test');
const assert=require('node:assert/strict');
const {taskGuide,projectName,workLabel}=require('../dist/guidance.js');
const task=overrides=>({status:'ready',worker_turns:0,changes:[],checks:[],checkpoints:[],events:[],...overrides});

test('a saved task asks for an explicit start',()=>{
  const g=taskGuide(task());
  assert.equal(g.primary,'start');
  assert.equal(g.facts.checks,'Not run yet');
  assert.equal(g.facts.reviewer,'Not reached yet');
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
