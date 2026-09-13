const {test}=require('node:test');
const assert=require('node:assert/strict');
const {taskGuide,projectName,workLabel}=require('../dist/guidance.js');
const task=overrides=>({status:'ready',worker_turns:0,changes:[],checks:[],checkpoints:[],events:[],...overrides});

test('checkpoint pause names the interval instead of the overall worker allowance',()=>{
  const message='The 12-turn checkpoint limit was reached. This request has used 62 of 100 worker turns overall.';
  const guide=taskGuide(task({status:'paused',error_code:'checkpoint_turn_limit',error:message,limits:{worker_turns:100,checkpoint_turns:12}}));
  assert.equal(guide.title,'Checkpoint interval reached.');
  assert.equal(guide.description,message);
  assert.equal(guide.primaryLabel,'Resume');
});

test('commit is offered only for a verified current patch with review or explicit takeover review',()=>{
  const {canCommit}=require('../dist/guidance.js');
  const t=task({status:'approved',changes:[{path:'README.md'}],patch:'current',patch_digest:'digest',checks:[{passed:true,digest:'digest'}],checkpoints:[{decision:'APPROVE',diff:'current'}]});
  assert.equal(canCommit(t),true);
  assert.equal(canCommit({...t,status:'awaiting_reply'}),true);
  assert.equal(canCommit({...t,status:'running'}),false);
  assert.equal(canCommit({...t,patch:'other'}),false);
  assert.equal(canCommit({...t,patch_digest:'other'}),false);
  assert.equal(canCommit({...t,changes:[]}),false);
  assert.equal(canCommit({...t,checkpoints:[]}),false);
  assert.equal(canCommit({...t,status:'completed',checkpoints:[]}),true);
});

test('commit activity identifies the actual branch and commit',()=>{
  const {activityItem}=require('../dist/guidance.js');
  const item=activityItem({kind:'commit',title:'Changes committed to your project',detail:{commit:'abcd1234ffff',branch:'main',message:'Fix clamp'}});
  assert.equal(item.note,'abcd1234 · main · Fix clamp');
});

test('declining keeps the exact patch deferred while a changed patch gets a new decision',()=>{
  const {commitDeferred}=require('../dist/guidance.js');
  const t={patch_digest:'one',human_decision:{decision:'defer',digest:'one'}};
  assert.equal(commitDeferred(t),true);
  assert.equal(commitDeferred({...t,patch_digest:'two'}),false);
  assert.equal(commitDeferred({...t,human_decision:{decision:'review',digest:'one'}}),false);
});

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
test('interrupted responses show saved work and the recovery step',()=>{
  const result=failure(task({status:'error',error_code:'stream_error',answer_pending:true,changes:[{path:'script.py'}]}));
  assert.equal(result.timeout,false);assert.equal(result.title,'The model response ended early.');
  assert.match(result.description,/1 changed file is saved/);assert.match(result.description,/Retry returns to the saved work/);
  assert.equal(failure(task({status:'error',error_code:'output_limit'})).title,'The response reached its output limit.');
  const capped=task({status:'error',error_code:'output_limit',execution:{mode:'delegate'},active_role:'worker'});
  assert.match(failure(capped).description,/smaller next action/);
  assert.doesNotMatch(failure({...capped,pending_review:{}}).description,/smaller next action/);
});
test('tool argument corrections are distinct from unreadable provider responses',()=>{
  const item=activityItem({kind:'tool_error',detail:{code:'invalid_tool_arguments',error:'Invalid arguments'}});
  assert.equal(item.title,'Asking the model to correct its tool call');
  assert.equal(failure(task({status:'error',error_code:'invalid_stream_json'})).title,'The model response could not be read.');
});
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

test('free pool distinguishes untested models, observed responses, and expiring cooldowns',()=>{
  const {modelHealth}=require('../dist/guidance.js');
  assert.equal(modelHealth({}), 'Not tested yet');
  assert.equal(modelHealth({health:{tool_check_passed:true}}), 'Tool check passed');
  assert.equal(modelHealth({health:{worker_responses:2}}), 'Responded in a task');
  assert.equal(modelHealth({health:{retry_at:160}},100000), 'Cooling down · 1m');
  assert.equal(modelHealth({health:{retry_at:160,cooldown_scope:'provider'}},100000), 'Provider cooling down · 1m');
  assert.equal(modelHealth({health:{retry_at:160,tool_check_passed:true}},161000), 'Tool check passed');
});

test('progress names the candidate being probed instead of the failed pinned model',()=>{
  const {progress}=require('../dist/guidance.js');
  const result=progress(task({status:'running',providers:{worker:{model:'old'}},events:[{kind:'model',title:'Requesting worker: replacement',time:new Date().toISOString()}]}));
  assert.equal(result.detail,'replacement');
});

const {turns,friendlyModel,groupActivityItems}=require('../dist/guidance.js');

test('friendlyModel formats model IDs and preserves free badges',()=>{
  assert.equal(friendlyModel('openrouter/cohere/north-mini-code:free'),'North Mini Code · free');
  assert.equal(friendlyModel('openrouter/dots-studio/dots-3-note-preview:free'),'Dots 3 Note · free');
  assert.equal(friendlyModel('gemma4:31b'),'Gemma 4');
  assert.equal(friendlyModel(''),'');
});

test('groupActivityItems groups repeated reads of the same file',()=>{
  const events=[
    {kind:'tool',title:'read file',detail:{arguments:{path:'README.md'},result:{total_lines:145}}},
    {kind:'tool',title:'read file',detail:{arguments:{path:'README.md'},result:{total_lines:145}}},
    {kind:'tool',title:'read file',detail:{arguments:{path:'README.md'},result:{total_lines:145}}},
    {kind:'tool',title:'read file',detail:{arguments:{path:'CONTRIBUTING.md'},result:{total_lines:20}}}
  ];
  const items=groupActivityItems(events);
  assert.equal(items.length,2);
  assert.equal(items[0].type,'read');
  assert.equal(items[0].path,'README.md');
  assert.equal(items[0].count,3);
  assert.equal(items[0].lines,145);
  assert.equal(items[1].path,'CONTRIBUTING.md');
  assert.equal(items[1].count,1);
});

test('groupActivityItems identifies stall guards as helpful worker redirects',()=>{
  const events=[
    {kind:'guard',title:'Asking the worker to use what it found',detail:'The same read returned unchanged information twice.'}
  ];
  const items=groupActivityItems(events);
  assert.equal(items.length,1);
  assert.equal(items[0].stalled,true);
  assert.equal(items[0].title,'Worker redirected');
  assert.match(items[0].note,/Repeated read detected/);
});

test('turns partitions multi-turn chat sessions and computes turn status',()=>{
  const t=task({
    prompt:'First message',
    status:'awaiting_reply',
    events:[
      {kind:'tool',title:'read file',detail:{arguments:{path:'README.md'},result:{total_lines:100}}},
      {kind:'assistant',detail:'Here is the explanation.'},
      {kind:'user',detail:'Second message'},
      {kind:'tool',title:'replace text',detail:{arguments:{path:'README.md'}}},
      {kind:'checks',detail:{passed:true,command:['pytest']}},
      {kind:'commit',detail:{commit:'12345678abcdef',branch:'main',message:'Update README'}}
    ]
  });
  const turnList=turns(t);
  assert.equal(turnList.length,2);
  assert.equal(turnList[0].userPrompt,'First message');
  assert.equal(turnList[0].phase,'answered');
  assert.equal(turnList[0].assistantReply,'Here is the explanation.');
  assert.equal(turnList[0].readCount,1);

  assert.equal(turnList[1].userPrompt,'Second message');
  assert.equal(turnList[1].phase,'committed');
  assert.match(turnList[1].title,/README\.md updated & committed/);
  assert.match(turnList[1].subtitle,/tests passed · reviewed · main · 12345678/);
});

test('turns generates live momentum indicators during slow worker reasoning and checks',()=>{
  const now=Date.parse('2026-09-13T00:00:20Z');
  const t=task({
    prompt:'Fix bug',
    status:'running',
    updated_at:'2026-09-13T00:00:00Z',
    stream:{
      model:'openrouter/cohere/north-mini-code:free',
      phase:'thinking',
      thinking:'A'.repeat(800),
      updated_at:'2026-09-13T00:00:18Z'
    },
    events:[
      {kind:'handoff',title:'Local chat delegated',detail:{to:'openrouter/cohere/north-mini-code:free',role:'worker'}}
    ]
  });
  const turnList=turns(t,now);
  assert.equal(turnList.length,1);
  assert.equal(turnList[0].isLive,true);
  assert.equal(turnList[0].phase,'working');
  assert.match(turnList[0].title,/North Mini Code · free is reasoning/);
  assert.match(turnList[0].subtitle,/200 tokens generated/);
});

test('turns suppresses activity card for completed pure conversational turns (no tool actions)',()=>{
  const t=task({
    prompt:'oh hey one last thing',
    status:'awaiting_reply',
    events:[
      {kind:'assistant',detail:"I'm listening! What's on your mind?"}
    ]
  });
  const turnList=turns(t);
  assert.equal(turnList.length,1);
  assert.equal(turnList[0].phase,'answered');
  assert.equal(turnList[0].assistantReply,"I'm listening! What's on your mind?");
  assert.equal(turnList[0].totalActions,0);
  assert.equal(turnList[0].hasActivity,false);
});

test('turns shows activity card when answered after repository research (tools used)',()=>{
  const t=task({
    prompt:'explain how run.py works',
    status:'awaiting_reply',
    events:[
      {kind:'tool',title:'read file',detail:{arguments:{path:'run.py'},result:{total_lines:80}}},
      {kind:'assistant',detail:'run.py starts the local server.'}
    ]
  });
  const turnList=turns(t);
  assert.equal(turnList.length,1);
  assert.equal(turnList[0].phase,'answered');
  assert.equal(turnList[0].hasActivity,true);
  assert.equal(turnList[0].title,'Researched repository');
  assert.equal(turnList[0].subtitle,'1 file inspected');
});

test('turns suppresses live activity card while actively streaming answer when no tools were used',()=>{
  const t=task({
    prompt:'hello',
    status:'running',
    stream:{phase:'answer',content:'Hello there! How can I help?'},
    events:[]
  });
  const turnList=turns(t);
  assert.equal(turnList.length,1);
  assert.equal(turnList[0].isLive,true);
  assert.equal(turnList[0].hasActivity,false);
});
