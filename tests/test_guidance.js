const {test}=require('node:test');
const assert=require('node:assert/strict');
const {taskGuide,projectName,workLabel}=require('../dist/guidance.js');
const task=overrides=>({status:'ready',worker_turns:0,changes:[],checks:[],checkpoints:[],events:[],...overrides});

test('reconciled project context invalidates earlier checks and review even for an identical diff',()=>{
  const {canCommit}=require('../dist/guidance.js');
  const t=task({status:'approved',changes:[{path:'file.py'}],patch:'same patch',patch_digest:'same digest',workspace_generation:1,
    checks:[{passed:true,digest:'same digest'}],checkpoints:[{decision:'APPROVE',diff:'same patch'}]});
  assert.equal(canCommit(t),false);
  t.checks[0].generation=1;
  assert.equal(canCommit(t),false);
  t.checkpoints[0].generation=1;
  assert.equal(canCommit(t),true);
});

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
  assert.equal(modelHealth({}), 'Not tested yet · no prior completion evidence');
  assert.equal(modelHealth({health:{tool_check_passed:true}}), 'Tool check passed · no prior completion evidence');
  assert.equal(modelHealth({health:{worker_responses:2}}), 'Responded in a task · no prior completion evidence');
  assert.equal(modelHealth({health:{retry_at:160}},100000), 'Cooling down · 1m');
  assert.equal(modelHealth({health:{retry_at:160,cooldown_scope:'provider'}},100000), 'Provider cooling down · 1m');
  assert.equal(modelHealth({health:{retry_at:160,tool_check_passed:true}},161000), 'Tool check passed · no prior completion evidence');
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

test('activityItem formats outline file and syntax_warning',()=>{
  const outlineItem=activityItem({kind:'tool',title:'outline file',detail:{arguments:{path:'cheapos/engine.py'},result:{total_lines:200}}});
  assert.equal(outlineItem.title,'Outlined cheapos/engine.py');
  assert.equal(outlineItem.note,'200 lines in file');

  const editWithWarning=activityItem({kind:'tool',title:'write file',detail:{arguments:{path:'broken.py'},result:{syntax_warning:'SyntaxError at line 5: invalid syntax'}}});
  assert.equal(editWithWarning.title,'Created broken.py');
  assert.equal(editWithWarning.note,'⚠ SyntaxError at line 5: invalid syntax');
});

test('automatic syntax restoration and targeted undo are visible without claiming a saved bad edit',()=>{
  const restored={kind:'tool',title:'replace text',detail:{arguments:{path:'app.py'},result:{rolled_back:true,syntax_warning:'invalid indentation'}}};
  assert.match(activityItem(restored).title,/Restored app.py/);
  assert.match(activityItem(restored).note,/automatically/);
  assert.equal(workLabel([restored]),'Work details');
  const undone={kind:'tool',title:'undo edit',detail:{arguments:{path:'app.py'},result:{undone_edit_id:'one'}}};
  assert.equal(activityItem(undone).title,'Undid edit to app.py');
  assert.match(activityItem(undone).note,/verification and review still required/);
  assert.equal(workLabel([undone]),'Made 1 edit');
});

test('groupActivityItems and turns handle outline file events',()=>{
  const events=[
    {kind:'tool',title:'outline file',detail:{arguments:{path:'cheapos/engine.py'},result:{total_lines:1300}}},
    {kind:'tool',title:'read file',detail:{arguments:{path:'cheapos/engine.py'},result:{total_lines:1300}}}
  ];
  const items=groupActivityItems(events);
  assert.equal(items.length,2);
  assert.equal(items[0].type,'outline');
  assert.equal(items[0].path,'cheapos/engine.py');
  assert.equal(items[1].type,'read');

  const t=task({
    prompt:'explain engine',
    status:'running',
    events
  });
  const turnList=turns(t);
  assert.equal(turnList[0].readCount,2);
  assert.equal(turnList[0].totalActions,2);
});

test('formatTerminalOutput parses ANSI escape codes and test runner markers',()=>{
  const {formatTerminalOutput}=require('../dist/guidance.js');
  assert.match(formatTerminalOutput(''), /No output/);

  // ANSI color
  const ansiText = '\x1b[31mFAIL:\x1b[0m test_add';
  const formattedAnsi = formatTerminalOutput(ansiText);
  assert.match(formattedAnsi, /ansi-red/);
  assert.match(formattedAnsi, /term-error-line/);

  // Python unittest success and failure
  const passLine = 'test_basic (tests.test_math.MathTests) ... ok';
  assert.match(formatTerminalOutput(passLine), /term-success-line/);

  const failLine = 'FAIL: test_something (tests.test_math.MathTests)';
  assert.match(formatTerminalOutput(failLine), /term-error-line/);

  const traceLine = 'Traceback (most recent call last):';
  assert.match(formatTerminalOutput(traceLine), /term-trace-line/);

  const divider = '----------------------------------------------------------------------';
  assert.match(formatTerminalOutput(divider), /term-divider-line/);

  // HTML escaping safety
  const unsafe = '<script>alert("xss")</script>';
  const safe = formatTerminalOutput(unsafe);
  assert.ok(!safe.includes('<script>'));
  assert.ok(safe.includes('&lt;script&gt;'));
});

test('activityItem and groupActivityItems format steer events',()=>{
  const item=activityItem({kind:'steer',title:'User Guidance',detail:'Focus on scripts/calc.py'});
  assert.equal(item.title,'User course correction');
  assert.equal(item.icon,'compass');
  assert.equal(item.note,'Focus on scripts/calc.py');

  const grouped=groupActivityItems([
    {kind:'steer',title:'User Guidance',detail:'Do not modify helper.py'}
  ]);
  assert.equal(grouped.length,1);
  assert.equal(grouped[0].type,'steer');
  assert.equal(grouped[0].title,'User course correction');
  assert.equal(grouped[0].note,'Do not modify helper.py');

  const t=task({
    prompt:'build slugify',
    status:'running',
    events:[
      {kind:'steer',title:'User Guidance',detail:"Make sure --separator '_' works cleanly without leaving trailing underscores"}
    ]
  });
  const turnList=turns(t);
  assert.equal(turnList.length,1);
  assert.equal(turnList[0].steerMessages.length,1);
  assert.equal(turnList[0].steerMessages[0].text,"Make sure --separator '_' works cleanly without leaving trailing underscores");
});

test('turns builds chronological chatItems with prior assistant and steer messages',()=>{
  const t=task({
    prompt:'build slugify',
    status:'running',
    events:[
      {kind:'tool',title:'read file'},
      {kind:'assistant',title:'Worker',detail:'I see the duplicate def main line.'},
      {kind:'guard',title:'Applied User Guidance',detail:'yes'},
      {kind:'guard',title:'Applied User Guidance',detail:'why is this not at the bottom?'},
      {kind:'tool',title:'replace lines'},
      {kind:'assistant',title:'Worker',detail:'All tests pass now.'}
    ]
  });
  const turnList=turns(t);
  assert.equal(turnList.length,1);
  const items=turnList[0].chatItems;
  assert.equal(items.length,4);
  assert.equal(items[0].kind,'assistant');
  assert.equal(items[0].text,'I see the duplicate def main line.');
  assert.equal(items[1].kind,'steer');
  assert.equal(items[1].text,'yes');
  assert.equal(items[2].kind,'steer');
  assert.equal(items[2].text,'why is this not at the bottom?');
  assert.equal(items[3].kind,'assistant');
  assert.equal(items[3].text,'All tests pass now.');
});




test('sidebar ordering is pinned first then creation time and stable ID, never live usage',()=>{
  const {sidebarOrder}=require('../dist/guidance.js');
  const tasks=[{id:'b',created_at:'2026-01-02'},{id:'a',created_at:'2026-01-02'},{id:'old',created_at:'2025-01-01',pinned:true}];
  assert.deepEqual(sidebarOrder(tasks).map(t=>t.id),['old','a','b']);
  tasks[0].updated_at='2027';tasks[0].usage={tokens:9999};
  assert.deepEqual(sidebarOrder(tasks).map(t=>t.id),['old','a','b']);
  assert.equal(tasks[0].id,'b');
});


test('permission presentation never labels an exact grant as project-wide',()=>{
  const {permissionChoice}=require('../dist/guidance.js');
  assert.deepEqual(permissionChoice({command:['python','-c','pass']}),{scope:'task_exact',label:'Allow this command for this session'});
  assert.deepEqual(permissionChoice({profile:{runner:'unittest'}}),{scope:'project_tests_session',label:'Allow project tests for this session'});
});

test('exhausted recovery asks for a correction and describes saved evidence',()=>{
 const guide=taskGuide(task({status:'paused',recovery_blocked:0,pause_summary:{saved_files:['a.py'],attempted:['small edits from current files'],blocker:'Missing target version.',next_action:'Provide the target version.'}}));
 assert.equal(guide.primary,'clarify');
 assert.match(guide.description,/1 saved file/);
 assert.match(guide.description,/Missing target version/);
 assert.match(guide.description,/Provide the target version/);
});

test('known cooldown waits are explicit and expose the retry action',()=>{
 const CheapOSGuide=require('../dist/guidance.js');
 const waiting=task({status:'waiting_retry',route_wait:{started_at:1000,retry_at:1010}});
 assert.equal(CheapOSGuide.progress(waiting,1005000).title,'Waiting for an available route');
 assert.match(CheapOSGuide.progress(waiting,1005000).detail,/5s/);
 assert.equal(CheapOSGuide.taskGuide(task({status:'paused',route_unavailable:{can_wait:true,message:'Provider cooling',retry_at:1010}})).primary,'retry-wait');
 assert.notEqual(CheapOSGuide.taskGuide(task({status:'paused',route_unavailable:{can_wait:false}})).primary,'retry-wait');
});

test('work presets keep spending and other custom settings explicit',()=>{
 const {workPreset,presetLimits}=require('../dist/guidance.js');
 const limits={dollars:0,run_minutes:15,worker_turns:40,iterations:5,check_seconds:111,reviewer_tokens:12345};
 assert.equal(workPreset(limits),'custom');
 assert.equal(workPreset({...limits,reviewer_tokens:200000,check_seconds:360,output_tokens:2048,checkpoint_turns:12}),'interactive');
 const extended=presetLimits(limits,'extended');
 assert.equal(extended.run_minutes,45);assert.equal(extended.worker_turns,120);
 assert.equal(extended.dollars,0);assert.equal(extended.check_seconds,111);assert.equal(extended.reviewer_tokens,12345);
 assert.equal(workPreset({...extended,run_minutes:22}),'custom');
 assert.equal(presetLimits({...limits,dollars:2},'extended').dollars,2);
 assert.equal(limits.run_minutes,15);
});

test('hard limit guidance identifies used and remaining allowance',()=>{
 const guide=taskGuide(task({status:'budget_paused',error:'Next request does not fit.',limit_hit:{key:'reviewer_tokens',used:1900,allowed:2000,remaining:100}}));
 assert.match(guide.title,/reviewer-token/);assert.match(guide.description,/1900 of 2000; 100 remaining/);
 assert.equal(guide.primaryLabel,'Review this limit');
 assert.equal(taskGuide(task({status:'paused'})).primary,'resume');
});

test('setup guidance uses typed recovery states and separates gateway identity from local choice',()=>{
  const {setupGuide}=require('../dist/guidance.js');
  for(const status of ['checking','starting','gateway_absent','gateway_stopped','gateway_ready','no_eligible_model','foreign_service','client_key_rejected','offline'])assert.ok(setupGuide({status}).title);
  assert.equal(setupGuide({status:'foreign_service'}).start,false);
  assert.equal(setupGuide({status:'client_key_rejected'}).key,true);
  assert.equal(setupGuide({status:'gateway_absent'}).install,true);
  assert.equal(setupGuide({status:'local_only_ready',gateway:{status:'ready',eligible_free_count:2}}).ready,true);
  assert.equal(setupGuide({status:'no_eligible_model',gateway:{identified:true,dashboard_url:'http://localhost/'}}).dashboard,true);
});

test('sample greeting, missing review and failed checks cannot claim full-loop success',()=>{
 const {sampleOutcome}=require('../dist/guidance.js');
 for(const status of ['ready','awaiting_reply','error','paused'])assert.match(sampleOutcome({status,changes:[],checks:[],checkpoints:[]}),/not been verified/);
 const result={status:'approved',changes:[{path:'x'}],patch:'p',patch_digest:'d',checks:[{passed:true,digest:'d'}],checkpoints:[{decision:'APPROVE',diff:'p'}],providers:{worker:{model:'local'},reviewer:{model:'local'}}};
 assert.match(sampleOutcome(result),/edits, checks and review completed/);
 assert.match(sampleOutcome(result),/same model/);
 result.checks[0].passed=false;assert.match(sampleOutcome(result),/not been verified/);
});

test('cost labels report provenance without hypothetical savings',()=>{
 const {costProvenance}=require('../dist/guidance.js');
 assert.equal(costProvenance({metrics:{cost:{provenance:'provider_reported'}}}),'Provider-reported cost');
 assert.equal(costProvenance({usage:{uncertain_requests:1}}),'Includes uncertain reservations');
 assert.equal(costProvenance({}),'Cost provenance unknown');
});

test('session compute pill omits uncertain reservations to prevent UI breaking',()=>{
 const {costProvenance}=require('../dist/guidance.js');
 const task={metrics:{cost:{provenance:'includes_uncertain_reservations'}},usage:{uncertain_requests:1,cost:0,worker:{tokens:3250308}}};
 const totalTokens=task.usage.worker.tokens;
 const provenance=costProvenance(task);
 const omit=!provenance||provenance.includes('uncertain reservations')||provenance==='Cost provenance unknown';
 const text=`${totalTokens.toLocaleString()} accounted tokens · $0.00${omit?'':` · ${provenance}`}`;
 assert.equal(text,'3,250,308 accounted tokens · $0.00');
 assert.doesNotMatch(text,/Includes uncertain reservations/);
});

test('model evidence exposes role sample counts without quality scores',()=>{
  const label=require('../dist/guidance.js').modelHealth({health:{role_evidence:{worker:{samples:3,valid_calls:8,invalid_output:1,accepted:0}}}});
  assert.match(label,/3 activity samples/);assert.match(label,/1 invalid outputs/);
});

test('exhausted planning recovery offers a fresh chat instead of inert resume',()=>{
 const g=taskGuide(task({status:'paused',planning_request:{},branch_run:{},error:'Two automatic model handoffs were tried for this request.'}));
 assert.equal(g.primary,'new-planning');
 assert.match(g.description,/Resume cannot retry/);
});
