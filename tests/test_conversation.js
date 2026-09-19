const {test}=require('node:test');
const assert=require('node:assert/strict');
const {conversation:{build,readyForNext}}=require('../dist/guidance.js');
const stamp='2026-09-13T12:00:00Z';
const event=(id,kind,title,detail)=>({id,kind,title,detail,time:stamp});
const task=overrides=>({prompt:'Fix the script.',status:'awaiting_reply',active_role:'worker',changes:[],checks:[],checkpoints:[],events:[],providers:{worker:{model:'worker-model'},reviewer:{model:'reviewer-model'}},...overrides});
const replies=t=>build(t).filter(e=>e.kind==='assistant');

test('questions have their own replies while work keeps its review controls',()=>{
 for(const status of ['running','reviewing','paused','approved']){
  const t=task({status,discussion:[{id:'q',message:'Why that approach?',status:'answered',answer:'Here is why.'}],
   branch_run:{id:'run',status:'ready_for_merge',authorization_ref:'auth',items:[{id:'one',status:'committed'}],readiness:{manifest:{files:[{path:'app.py'}]}}}});
  const before=JSON.stringify(t),entries=build(t),reply=entries.at(-1);
  assert.equal(reply.reply,'Here is why.');assert.equal(reply.owner,false);
  assert.equal(entries.at(-2).text,'Why that approach?');
  assert.ok(entries.some(e=>e.owner),'The work still owns its approval controls');
  assert.equal(JSON.stringify(t),before);
  assert.deepEqual(build(JSON.parse(before)),entries);
 }
});

test('queued questions acknowledge delivery and never pretend to resume paused work',()=>{
 const t=task({status:'paused',discussion:[{id:'q',message:'Show an example?',status:'queued'}]});
 const reply=build(t).at(-1);assert.equal(reply.label,'Message received');
 assert.match(reply.reply,/answer after the current operation/);assert.equal(reply.owner,false);
 t.discussion[0].status='answering';
 t.stream={purpose:'chat_reply',phase:'waiting',role:'worker',request_id:2};
 t.events=[event(2,'model','Requesting worker',{purpose:'chat_reply'})];
 assert.equal(build(t).at(-1).label,'Replying');
 assert.ok(build(t).slice(0,-2).every(e=>!e.stream),'A chat answer is not a live worker step');
});

test('discussion stays between the work turns where it was sent, including hidden model traffic',()=>{
 const t=task({prompt:'hi',events:[
  event(1,'model','Opening greeting',{purpose:'chat_reply',opening_chat:true}),
  event(2,'assistant','Chat','Hello!'),
  event(3,'model','Answering chat',{purpose:'chat_reply'}),
  event(4,'generation','Chat thinking',{purpose:'chat_reply',thinking:'Private to this reply'}),
  event(5,'user','You','I have a lot on my mind'),
  event(6,'model','Requesting worker'),event(7,'assistant','Worker','Tell me more.')],
  discussion:[{id:'earlier',message:'just chatting',answer:'Happy to chat.',after_event:2,status:'answered'}]});
 const before=JSON.stringify(t),entries=build(t);
 assert.deepEqual(entries.map(e=>e.text||e.reply),['hi','Hello!','just chatting','Happy to chat.','I have a lot on my mind','Tell me more.']);
 assert.equal(JSON.stringify(t),before);
 assert.deepEqual(build(JSON.parse(before)),entries);
 t.discussion.push({id:'later',message:'Why?',after_event:7,status:'queued'});
 const ids=build(t).map(e=>e.id);
 t.discussion[1].status='answered';t.discussion[1].answer='Here is why.';
 assert.deepEqual(build(t).map(e=>e.id),ids,'Receiving the answer must not move its question');
});

test('discussion with a timestamp retains chronology for older receipts without an event anchor',()=>{
 const t=task({events:[{...event(1,'assistant','Worker','First answer'),time:'2026-09-19T12:00:00Z'},
  {...event(2,'user','You','Later direction'),time:'2026-09-19T12:02:00Z'},
  {...event(3,'assistant','Worker','Later answer'),time:'2026-09-19T12:03:00Z'}],
  discussion:[{id:'q',message:'Earlier question',answer:'Earlier reply',status:'answered',time:'2026-09-19T12:01:00Z'}]});
 assert.deepEqual(build(t).map(e=>e.text||e.reply),['Fix the script.','First answer','Earlier question','Earlier reply','Later direction','Later answer']);
});

test('unattended discussion order preserves the final work owner and merge controls',()=>{
 const t=task({status:'approved',events:[event(1,'assistant','Worker','Initial work'),event(2,'user','You','Apply the improvement')],
  branch_run:{id:'run',status:'ready_for_merge',authorization_ref:'auth',current_item_id:null,items:[{id:'one',status:'committed'}],readiness:{manifest:{files:[{path:'app.py'}]}}},
  discussion:[{id:'q',message:'Earlier question',answer:'Earlier reply',status:'answered',after_event:1}]});
 const entries=build(t),question=entries.findIndex(e=>e.id==='discussion-user-q'),direction=entries.findIndex(e=>e.text==='Apply the improvement');
 assert.ok(question<direction);
 assert.equal(entries.filter(e=>e.owner).length,1);
 assert.ok(entries.find(e=>e.owner).id.startsWith('operation-1-'));
 assert.ok(entries.filter(e=>e.discussion).every(e=>!e.owner&&!e.latest));
});

test('opening greeting streams its actual answer without a synthetic coding step',()=>{
 const stream={purpose:'chat_reply',opening_chat:true,phase:'answer',role:'worker',model:'fast-model',request_id:2,content:'Hi! What would you like to work on?'};
 const t=task({prompt:'hi there',status:'running',stream,
  events:[event(2,'model','Requesting worker',{purpose:'chat_reply',opening_chat:true})]});
 const reply=replies(t).at(-1);
 assert.equal(reply.reply,stream.content);
 assert.equal(reply.steps.length,0);
 assert.equal(reply.live,true);
});

test('opening greeting retains separate thinking through streaming and completion',()=>{
 const t=task({prompt:'hi',status:'running',
  stream:{purpose:'chat_reply',opening_chat:true,phase:'thinking',thinking:'Considering greeting',content:''},
  events:[event(2,'model','Requesting worker',{purpose:'chat_reply',opening_chat:true})]});
 let reply=replies(t).at(-1);
 assert.equal(reply.reply,'');assert.equal(reply.thinking,'Considering greeting');assert.equal(reply.steps.length,0);
 t.stream.phase='answer';t.stream.content='Hello!';
 reply=replies(t).at(-1);
 assert.equal(reply.reply,'Hello!');assert.equal(reply.thinking,'Considering greeting');assert.equal(reply.steps.length,0);
 t.stream=null;t.status='awaiting_reply';
 t.events.push(event(3,'generation','Model thinking',{purpose:'chat_reply',opening_chat:true,thinking:'Considering greeting'}),event(4,'assistant','Chat','Hello!'));
 reply=replies(t).at(-1);
 assert.equal(reply.reply,'Hello!');assert.equal(reply.thinking,'Considering greeting');assert.equal(reply.steps.length,0);
 assert.equal(reply.live,false);
});

test('accepted updates show saved preparation stages in both chat modes before agents restart',()=>{
 for(const unattended of [false,true]){
  const t=task({status:'paused',events:[event(1,'tool','read file',{arguments:{path:'README.md'}})],
   integration_preparation:{id:'update-1',authorized:true,status:'running',stage:'accepted'},
   ...(unattended?{branch_run:{id:'run',authorization_ref:'auth',status:'paused',current_item_id:null,items:[{id:'one',title:'Saved work',status:'committed'}]}}:{})});
  for(const [stage,title] of [['accepted','Update request saved'],['checking','Checking latest project'],['combining','Combining changes'],['resolving','Preparing conflict resolution']]){
   t.integration_preparation.stage=stage;
   const before=JSON.stringify(t),entries=build(t),reply=entries.at(-1);
   assert.equal(reply.preparation.title,title);assert.equal(reply.live,true);
   assert.match(reply.intro,/request is saved.*automatically/);
   assert.equal(reply.id,'integration-update-1');assert.equal(reply.stream,null);
   assert.ok(entries.filter(e=>e!==reply&&e.kind==='assistant').every(e=>!e.live&&!e.owner));
   assert.ok(entries.every(e=>!e.intro?.includes('I need your attention before continuing')));
   assert.equal(JSON.stringify(t),before);
   assert.deepEqual(build(JSON.parse(before)),entries,'Refresh restores the saved stage without a new request');
  }
  t.status='running';if(unattended)t.branch_run.status='finalizing';
  assert.ok(!replies(t).some(e=>e.preparation),'Normal activity takes over when execution starts');
 }
});

test('preparation acknowledgement never masks a stop, failed update or permission request',()=>{
 const base=task({status:'paused',integration_preparation:{id:'update',authorized:true,status:'running',stage:'accepted'}});
 const preparation=require('../dist/guidance.js').integrationPreparation;
 for(const status of ['ready','decision','failed','cancelled','waiting'])assert.equal(preparation({...base,integration_preparation:{...base.integration_preparation,status}}),null);
 for(const change of [{status:'stopping'},{status:'error'},{pending_approval:{command:['check']}},{archived_at:stamp},{trashed_at:stamp},{integration_preparation:{...base.integration_preparation,authorized:false}}])assert.equal(preparation({...base,...change}),null);
 assert.equal(preparation(task()),null);
});

test('completed review keeps its action owner despite an old combining update',()=>{
 const t=task({status:'approved',integration_preparation:{id:'update',authorized:true,status:'running',stage:'combining',dispatched:true},
  branch_run:{id:'run',status:'ready_for_merge',authorization_ref:'auth',items:[{id:'one',title:'One',status:'committed'}],
   readiness:{manifest:{files:[{path:'app.js'}]},review:{decision:'APPROVE'}}}});
 const original=JSON.stringify(t),reply=build(t).at(-1);
 assert.equal(reply.operation,'final');assert.equal(reply.owner,true);assert.equal(reply.live,false);
 assert.match(reply.intro,/Final checks and independent review are complete/);
 assert.ok(!reply.preparation);
 assert.equal(require('../dist/branch_ui.js').reviewAction(t).label,'Review changes');
 assert.equal(JSON.stringify(t),original,'Present the saved result without rewriting history');
 assert.deepEqual(build(JSON.parse(original)),build(t),'Old persisted tasks also recover after reload');
 // Starting a NEW update must still acknowledge the click while the previous
 // ready result remains in the task, before the executor has been dispatched.
 delete t.integration_preparation.dispatched;
 assert.equal(build(t).at(-1).preparation.title,'Combining changes');
});

test('live personality varies by task but stays stable through output, polling and reloads',()=>{
 const intros=new Set();
 for(let i=0;i<32;i++){
  const t=task({id:'personality-'+i,status:'running',events:[event(1,'model','Requesting worker: worker-model',{})]});
  const original=JSON.stringify(t),[reply]=replies(t);
  intros.add(reply.intro);
  assert.equal(JSON.stringify(t),original);
  t.stream={request_id:1,role:'worker',phase:'thinking',thinking:'Inspecting the implementation.'};
  t.updated_at='2026-09-13T12:01:00Z';
  t.events.push(event(2,'tool','read file',{arguments:{path:'script.py'}}));
  assert.equal(build(t,Date.parse(t.updated_at)).at(-1).intro,reply.intro);
  assert.equal(replies(JSON.parse(JSON.stringify(t))).at(-1).intro,reply.intro);
  assert.equal(reply.steps[0].title,'Working on your request');
  assert.doesNotMatch(reply.intro,/free tokens|zero dollars|budget is zero|APPROVE|checks passed/i);
 }
 assert.ok(intros.size>=6,'Different tasks should not all get the same stock introduction');
});

test('personality never replaces permissions, stops, route waits or reviewer corrections',()=>{
 const base=task({id:'personality-paused',events:[event(1,'model','Requesting worker: worker-model',{})]});
 for(const status of ['paused','error','budget_paused','interrupted','takeover_requested']){
  // Retain an execution event so the stopped response has a status introduction.
  const [stopped]=replies({...base,status,events:[...base.events,event(2,'tool','read file',{arguments:{path:'script.py'}})]});
  assert.match(stopped.intro,/attention before continuing/);assert.equal(stopped.live,false);
 }
 assert.match(replies({...base,status:'stopping'})[0].intro,/pausing work/);
 assert.match(replies({...base,status:'waiting_retry',route_wait:{}})[0].intro,/No model request is running/);
 assert.match(replies({...base,status:'waiting_approval',pending_approval:{command:['python3','test.py']}})[0].intro,/permission/);
 const recovering={...base,status:'running',events:[event(1,'review','Changes requested',{decision:'REQUEST_CHANGES',feedback:'Fix the assertion.'}),event(2,'model','Requesting worker: worker-model',{})]};
 assert.match(replies(recovering)[0].intro,/addressing that feedback/);
 const probing={...base,status:'running',stream:{request_id:1,purpose:'probe',phase:'waiting'},events:[event(1,'model','Requesting worker: worker-model',{purpose:'probe'})]};
 assert.equal(replies(probing)[0].intro,'I’m working through your request.');
});

test('branch planning and work label route waits without stale model activity',()=>{
 for(const planning of [true,false]){
  const t=task({status:'waiting_retry',active_role:planning?'planner':'worker',
   route_wait:{started_at:1000,retry_at:1060,message:'Checking other authorized routes.'},
   planning_request:planning?{}:null,
   branch_run:{status:'running',authorization_ref:planning?null:'saved',current_item_id:planning?null:'one',
    items:planning?[]:[{id:'one',title:'Fix',status:'working'}]},
   events:[event(1,'model',`Requesting ${planning?'planner':'worker'}: old-model`,{role:planning?'planner':'worker'}),
    event(2,'routing','Waiting for an authorized route; retrying automatically',{})]});
  const reply=build(t,1005000).find(e=>e.kind==='assistant'&&e.owner);
  assert.equal(reply.label,'Waiting');
  assert.equal(reply.stream,null);
  assert.match(reply.steps.at(-1).title,/Waiting.*route/);
  assert.match(reply.steps.at(-1).detail,/No model request is running.*55s/);
  assert.doesNotMatch(reply.intro,/preparing a plan|cooldown/);
 }
});

test('ordinary conversation retains the answer without an execution card',()=>{
 const [reply]=replies(task({events:[event(1,'model','Requesting worker: worker-model',{}),event(2,'assistant','Worker','Hello!')]}));
 assert.equal(reply.reply,'Hello!');assert.deepEqual(reply.steps,[]);
});
test('streamed chat text stays in the current cheapoS reply',()=>{
 const [reply]=replies(task({status:'running',stream:{phase:'answer',content:'Hello',model:'worker-model'},events:[event(1,'model','Requesting worker: worker-model',{})]}));
 assert.equal(reply.reply,'Hello');assert.equal(reply.steps.length,0);assert.equal(reply.live,true);
});
test('worker, checks, and reviewer are chronological steps of one cheapoS reply',()=>{
 const t=task({status:'reviewing',stream:{phase:'thinking',role:'reviewer',model:'reviewer-model',thinking:'Review evidence'},events:[
 event(1,'model','Requesting worker: worker-model',{}),event(2,'assistant','Worker','I will fix the script.'),
 event(3,'tool','replace text',{arguments:{path:'script.py'},result:{updated:true},role:'worker'}),
 event(4,'tool','Running verification',{command:['python3','-m','unittest']}),event(5,'checks','Verification passed',{passed:true,command:['python3','-m','unittest']}),
 event(6,'assistant','Worker','All tests passed. Let me submit the checkpoint.'),
 event(7,'handoff','Sending changes for review',{role:'reviewer',to:'reviewer-model'}),event(8,'model','Requesting reviewer: reviewer-model',{})]});
 const [reply]=replies(t);
 assert.deepEqual(reply.steps.map(s=>s.phase),['work','checks','review']);
 assert.equal(reply.steps[1].title,'Checks passed');
 assert.equal(reply.steps[2].model,'reviewer-model');
 assert.equal(reply.steps[2].live,true);assert.equal(reply.steps[0].live,false);
 assert.equal(reply.reply,'');assert.match(reply.intro,/second opinion/);
 assert.equal(reply.stream.thinking,'Review evidence');
});
test('course correction separates previous work from the next cheapoS response',()=>{
 const t=task({status:'running',events:[event(1,'model','Requesting worker: worker-model',{}),event(2,'tool','read file',{arguments:{path:'before.py'}}),event(3,'steer','User Guidance','Keep the public API unchanged.'),event(4,'guard','Applied User Guidance','Keep the public API unchanged.'),event(5,'tool','replace text',{arguments:{path:'after.py'}})]});
 const entries=build(t);
 assert.deepEqual(entries.map(e=>e.kind),['user','assistant','user','assistant']);
 assert.equal(entries[2].text,'Keep the public API unchanged.');
 assert.equal(entries[1].steps[0].events.find(e=>e.kind==='tool').detail.arguments.path,'before.py');
 assert.equal(entries[3].steps[0].events.find(e=>e.kind==='tool').detail.arguments.path,'after.py');
 assert.equal(entries[1].live,false);assert.equal(entries[3].live,true);
});
test('failed verification and requested revisions never look approved',()=>{
 const [reply]=replies(task({events:[event(1,'checks','Verification failed',{passed:false,exit_code:1}),event(2,'review','Review decision',{decision:'REQUEST_CHANGES',feedback:'Fix an edge case.'})]}));
 assert.equal(reply.steps[0].outcome,'failed');assert.equal(reply.steps[1].outcome,'revision');
 assert.doesNotMatch(reply.intro,/passed/);
});
test('review chunk progress uses controller totals and clears for synthesis',()=>{
 const t=task({status:'reviewing',active_role:'reviewer',events:[
  event(1,'review_request','Requesting final packet review',{chunk_ids:['diff:2'],stage:'chunk',chunk_index:8,chunk_total:12}),
  event(2,'model','Requesting reviewer: reviewer-model',{})]});
 const step=()=>replies(t).at(-1).steps.at(-1);
 assert.equal(step().reviewProgress,'Chunk 8 of 12');
 t.stream={request_id:2,role:'reviewer',phase:'answer',content:'Reviewing the saved change.'};
 assert.equal(step().reviewProgress,'Chunk 8 of 12');
 t.events.push(event(3,'review','Final packet review completed',{chunk_ids:['diff:2'],chunk_index:8,chunk_total:12,decision:'REQUEST_CHANGES',feedback:'Fix this defect.'}));
 t.status='paused';assert.equal(step().reviewProgress,'Chunk 8 of 12');assert.equal(step().outcome,'revision');
 t.events.push(event(4,'review_request','Requesting final packet review',{chunk_ids:['diff:1','diff:2'],stage:'synthesis'}));
 assert.equal(step().reviewProgress,'');
 for(const pair of [[0,12],[13,12],[8,undefined],['8',12]]){
  t.events.push(event(t.events.length+1,'review_request','Requesting review',{chunk_ids:['diff:2'],stage:'chunk',chunk_index:pair[0],chunk_total:pair[1]}));
  assert.equal(step().reviewProgress,'');
 }
});
test('saved item chunk progress uses its earlier paging batch',()=>{
 const t=task({status:'reviewing',events:[
  event(1,'review_paging','Reviewing the large item',{packets:39}),
  event(2,'review_request','Requesting item packet review',{chunk_ids:['item:8'],stage:'chunk'}),
  event(3,'model','Requesting reviewer: reviewer-model',{})]});
 assert.equal(replies(t)[0].steps.at(-1).reviewProgress,'Chunk 8 of 39');
 t.events.push(event(4,'review_paging','Reviewing a revised item',{packets:4}));
 assert.equal(replies(t)[0].steps.at(-1).reviewProgress,'Chunk 8 of 39');
 t.events.push(event(5,'review_request','Requesting item packet review',{chunk_ids:['item:1'],stage:'chunk'}));
 assert.equal(replies(t)[0].steps.at(-1).reviewProgress,'Chunk 1 of 4');
 t.events.push(event(6,'review_request','Requesting item review',{candidate_id:'candidate'}));
 assert.equal(replies(t)[0].steps.at(-1).reviewProgress,'');
});
test('unfinished reviewer and pause retain the worker and passing checks',()=>{
 const [reply]=replies(task({status:'paused',error_code:'checkpoint_turn_limit',error:'Reached checkpoint interval',events:[event(1,'checks','Verification passed',{passed:true}),event(2,'handoff','Sending changes for review',{role:'reviewer'})]}));
 assert.equal(reply.steps[0].outcome,'passed');assert.equal(reply.steps[1].outcome,'pending');
 assert.match(reply.steps[1].title,/not finished/);assert.match(reply.intro,/attention/);
 assert.ok(reply.steps.every(s=>!s.live));
});
test('command permission is an inline check step',()=>{
 const [reply]=replies(task({status:'waiting_approval',pending_approval:{command:['python3','-m','unittest']},events:[event(1,'permission','Permission needed',{})]}));
 assert.equal(reply.steps[0].phase,'checks');assert.equal(reply.steps[0].outcome,'pending');
 assert.equal(reply.steps[0].title,'Waiting for your permission');assert.match(reply.intro,/permission/);
});
test('live IDs remain stable while stream output grows',()=>{
 const t=task({status:'running',events:[event(1,'model','Requesting worker: worker-model',{})],stream:{phase:'thinking',model:'worker-model',thinking:'A'}});
 const first=replies(t)[0];t.stream.thinking+=' longer thought';const next=replies(t)[0];
 assert.equal(first.id,next.id);assert.equal(first.steps[0].id,next.steps[0].id);
});
test('completed or superseded requests cannot keep stale live output in the conversation',()=>{
 const request=event('request','model','Requesting reviewer: reviewer-model',{});
 for(const later of [
  event('output','generation','Model thinking',{request_id:'request',role:'reviewer',thinking:'Saved review thought'}),
  event('read','tool','read file',{role:'reviewer',arguments:{path:'server.py'}}),
  event('next','model','Requesting reviewer: reviewer-model',{})]){
  const t=task({status:'reviewing',events:[request,later],stream:{request_id:'request',role:'reviewer',phase:'thinking',thinking:'Stale live text'}});
  const [reply]=replies(t);assert.equal(reply.stream,null);
  assert.doesNotMatch(reply.steps.at(-1).detail,/Thinking through/);
  if(later.kind!=='model')assert.doesNotMatch(reply.steps.at(-1).detail,/Waiting for the model/);
 }
});
test('transport notices and guidance do not end a current stream but stopping states do',()=>{
 const {liveStream}=require('../dist/guidance.js');
 const stream={request_id:'transport',role:'reviewer',phase:'thinking',thinking:'Current output'};
 const t=task({status:'reviewing',stream,events:[event('request','model','Requesting reviewer: reviewer-model',{}),
  event('transport','transport','Retrying without streaming',{}),event('steer','steer','User guidance','Check the token.')]});
 assert.equal(liveStream(t),stream);
 for(const status of ['paused','approved','completed','error','waiting_retry'])assert.equal(liveStream({...t,status}),null);
 assert.equal(liveStream({...t,pending_approval:{command:['python3','-m','unittest']}}),null);
 assert.equal(liveStream({...t,check_stream:{command:['python3','-m','unittest']}}),null);
 assert.equal(liveStream({...t,status:'stopping'}),stream); // Output remains real until cancellation completes.
});
test('follow-up user messages keep separate execution histories',()=>{
 const t=task({events:[event(1,'tool','read file',{arguments:{path:'first.py'}}),event(2,'assistant','Worker','First answer'),event(3,'user','You','Second question'),event(4,'assistant','Worker','Second answer')]});
 const entries=build(t);assert.equal(entries.length,4);
 assert.equal(entries[1].reply,'First answer');assert.equal(entries[3].reply,'Second answer');
 assert.equal(entries[3].steps.length,0);
});
test('commit acknowledgement belongs to the same reply and names the real commit',()=>{
 const [reply]=replies(task({events:[event(1,'commit','Changes committed',{branch:'main',commit:'1234567890',message:'Fix script'})]}));
 assert.match(reply.intro,/committed/);assert.equal(reply.steps[0].detail,'main · 12345678');
 assert.equal(reply.reply,'What would you like to work on next?');
});
test('a successful commit invites the next request and retains the invitation after reload',()=>{
 const t=task({events:[event(1,'commit','Changes committed',{branch:'main',commit:'1234567890'})]});
 assert.equal(readyForNext(t),true);
 assert.equal(readyForNext(JSON.parse(JSON.stringify(t))),true);
 assert.equal(replies(t).filter(r=>r.reply.includes('work on next')).length,1);
});
test('approval, commit failures, and saved edits never announce readiness for another task',()=>{
 const done=event(1,'commit','Changes committed',{branch:'main',commit:'1234567890'});
 for(const t of [task({status:'approved'}),task({commit_pending:true,events:[done]}),task({changes:[{path:'new.py'}],events:[done]}),task({status:'error',events:[event(1,'commit','Commit needs attention',{error:'Conflict'})]})]){
  assert.equal(readyForNext(t),false);
 }
 assert.equal(replies(task({events:[event(1,'commit','Commit needs attention',{error:'Conflict'})]}))[0].reply,'');
});
test('the next user message starts its own reply without repeating the closing question',()=>{
 const t=task({events:[event(1,'commit','Changes committed',{branch:'main',commit:'1234567890'}),event(2,'user','You','Explain the new script.'),event(3,'assistant','Worker','It formats timestamps.')]});
 assert.equal(readyForNext(t),false);
 const answers=replies(t);
 assert.equal(answers[0].reply,'What would you like to work on next?');
 assert.equal(answers[1].reply,'It formats timestamps.');
});
test('scripted demos do not invite replies into their unavailable composer',()=>{
 const t=task({demo:true,events:[event(1,'commit','Changes committed',{branch:'main',commit:'1234567890'})]});
 assert.equal(readyForNext(t),false);assert.equal(replies(t)[0].reply,'');
});
test('preparation between checks is folded into the next action without losing output',()=>{
 const [reply]=replies(task({events:[event(1,'checks','Verification passed',{passed:true}),event(2,'model','Requesting worker: worker-model',{}),event(3,'assistant','Worker','Ready to submit.'),event(4,'check_reused','Checks already passed',{command:['python3','-m','unittest']}),event(5,'handoff','Sending for review',{role:'reviewer'})]}));
 assert.deepEqual(reply.steps.map(s=>s.phase),['checks','review']);
 assert.ok(reply.steps[0].events.some(e=>e.detail==='Ready to submit.'));
});
test('takeover completion does not claim an independent review passed',()=>{
 const [reply]=replies(task({status:'completed',changes:[{path:'script.py'}],patch:'current',patch_digest:'digest',checks:[{passed:true,digest:'digest'}],events:[event(1,'checks','Verification passed',{passed:true})]}));
 assert.match(reply.intro,/ready for your review/);assert.doesNotMatch(reply.intro,/passed checks and review/);
});
test('a failed final file action is marked as needing attention',()=>{
 const [reply]=replies(task({status:'error',events:[event(1,'model','Requesting worker: worker-model',{}),event(2,'tool_error','Action failed',{error:'File changed'})]}));
 assert.equal(reply.steps[0].outcome,'failed');assert.equal(reply.steps[0].title,'Work needs attention');
});

const branchTask=overrides=>task({id:'branch-task',status:'running',planning_request:{prompt:'Build restart'},branch_run:{id:'run1',status:'draft',items:[{id:'planning',title:'Prepare plan',status:'working'}],current_item_id:'planning'},...overrides});
test('unattended personality follows selection, planning and final review without hiding waiting',()=>{
 const startup=branchTask({branch_run:{id:'run1',authorization_ref:'auth',status:'running',current_item_id:null,items:[],startup:{status:'running',stage:'selecting_worker',label:'Selecting worker',started_at:stamp}}});
 const selecting=replies(startup).at(-1);
 assert.match(selecting.intro,/Your approval is saved/);
 assert.equal(selecting.steps.at(-1).title,'Selecting worker');
 startup.branch_run.startup.stage='preparing_branch';
 assert.equal(replies(startup).at(-1).intro,'Your approval is saved. I’m preparing your run.');
 const planning=branchTask();
 const plan=replies(planning)[0];assert.equal(plan.label,'Planning');assert.equal(plan.steps[0].title,'Selecting a planner');
 planning.status='stopping';assert.match(replies(planning)[0].intro,/pausing planning/);
 const final=branchTask({planning_request:null,status:'reviewing',active_role:'reviewer',branch_run:{id:'run1',authorization_ref:'auth',status:'finalizing',current_item_id:null,items:[]},events:[event(1,'review_request','Requesting final packet review',{}),event(2,'model','Requesting reviewer: reviewer-model',{})].map(e=>({...e,branch_run_id:'run1',item_id:null}))});
 const review=replies(final).at(-1);
 assert.equal(review.steps.at(-1).phase,'review');assert.doesNotMatch(review.intro,/running final checks/);
 assert.equal(review.steps.at(-1).outcome,'live');
 final.status='waiting_retry';final.route_wait={};
 assert.match(replies(final).at(-1).intro,/No model request is running/);
 final.status='paused';assert.match(replies(final).at(-1).intro,/attention/);
});
test('one planning operation retains stable identity through selection stream and proposal readiness',()=>{
 const t=branchTask();let [reply]=replies(t);const id=reply.id,step=reply.steps[0].id;
 assert.equal(reply.label,'Planning');assert.match(reply.steps[0].title,/Selecting a planner/);
 t.events=[{...event(1,'model','Requesting planner: planner-model',{}),branch_run_id:'run1',item_id:null}];
 t.stream={role:'planner',phase:'thinking',thinking:'Inspect current project',model:'planner-model'};
 [reply]=replies(t);assert.equal(reply.id,id);assert.equal(reply.steps[0].id,step);assert.equal(reply.steps[0].role,'planner');assert.equal(reply.stream.thinking,'Inspect current project');
 t.status='ready';t.branch_run.status='awaiting_authorization';delete t.stream;
 [reply]=replies(t);assert.equal(reply.id,id);assert.equal(reply.owner,true);assert.equal(reply.live,false);assert.equal(reply.steps[0].title,'Your plan is ready');
});
test('item results remain scoped across review commit and next item without stale review stream',()=>{
 const items=[{id:'one',title:'Build restart button',status:'reviewing'},{id:'two',title:'Style restart button',status:'pending'},{id:'three',title:'Document restart',status:'pending'}];
 const e=(id,item,kind,title,detail)=>({...event(id,kind,title,detail),item_id:item});
 const t=branchTask({planning_request:null,status:'approved',branch_run:{id:'run1',authorization_ref:'auth',status:'running',items,current_item_id:'one'},events:[
 e(1,'one','tool','replace text',{arguments:{path:'app.js'}}),e(2,'one','checks','Verification passed',{passed:true,command:['git','diff','--check']}),e(3,'one','review','Independent item review passed',{decision:'APPROVE',feedback:'Matches item one'})]});
 items[0].ready_receipt={candidate:{id:'candidate'}};
 let list=replies(t),last=list.at(-1);assert.match(last.itemTitle,/Item 1 of 3/);assert.equal(last.steps.at(-1).phase,'commit');assert.equal(last.steps.at(-1).live,true);assert.equal(last.steps.find(s=>s.phase==='review').title,'Independent review passed');assert.equal(last.steps.find(s=>s.phase==='checks').title,'Whitespace check passed');
 items[0].status='committed';items[0].commit_receipt={stage:'completed',item_id:'one',run_id:'run1',new_tip:'a'.repeat(40)};
 items[1].status='working';t.branch_run.current_item_id='two';t.status='running';t.active_role='worker';
 t.events.push({...e(4,null,'branch_commit','Committed first',{detail:{item_id:'one'}}),branch_run_id:'run1'},e(5,'one','branch_item','Working on style',{item_id:'two'}));
 t.stream={role:'reviewer',phase:'thinking',thinking:'Old review output'};
 list=replies(t);last=list.at(-1);assert.match(last.itemTitle,/Item 2 of 3 · Style/);assert.equal(last.steps.at(-1).phase,'work');assert.equal(last.stream,null);assert.ok(last.steps.every(s=>!['checks','review','commit'].includes(s.phase)));
 assert.equal(list.flatMap(r=>r.steps).filter(s=>s.title==='Item committed').length,1);
 assert.equal(list.find(r=>r.operation==='one').steps.find(s=>s.phase==='review').outcome,'passed');
 assert.equal(list.find(r=>r.operation==='one').steps.find(s=>s.phase==='review').title,'Independent review passed');
});
test('mid-item guidance remains chronological with only one completed receipt and current pause has no spinner',()=>{
 const t=branchTask({planning_request:null,status:'paused',branch_run:{id:'run1',authorization_ref:'auth',status:'paused',current_item_id:'two',waiting_for_user:'Which restart target?',items:[{id:'one',title:'First',status:'committed',commit_receipt:{stage:'completed',item_id:'one',run_id:'run1',new_tip:'a'.repeat(40)}},{id:'two',title:'Second',status:'committing',ready_receipt:{}}]},events:[
 {...event(1,'tool','read file',{arguments:{path:'a'}}),item_id:'one'},event(2,'steer','User Guidance','Keep the UI compact'),{...event(3,'tool','replace text',{arguments:{path:'a'}}),item_id:'one'}]});
 const result=build(t),list=result.filter(e=>e.kind==='assistant');
 assert.equal(list.filter(e=>e.owner).length,1);
 assert.equal(result.find(e=>e.steer).text,'Keep the UI compact');assert.equal(list.flatMap(r=>r.steps).filter(s=>s.title==='Item committed').length,1);
 assert.ok(list.every(r=>!r.live));assert.equal(list.at(-1).reply,'Which restart target?');
});
test('rendered operation contains live details and action slot without routing narration',()=>{
 const vm=require('node:vm'),fs=require('node:fs');
 const source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8').split("\n'use strict';\nconst $ =")[0];
 const context={CheapOSGuide:require('../dist/guidance.js'),esc:x=>String(x??'').replaceAll('<','&lt;'),icon:()=>'',messageText:x=>x,thinkingMarkup:()=>'',eventDetail:()=>''};vm.createContext(context);vm.runInContext(source+'\nthis.view=CheapOSChatView;',context);
 const t=branchTask({stream:{role:'planner',phase:'thinking',thinking:'Actual planner output',model:'planner-model'},events:[event(1,'model','Requesting planner: planner-model',{})],routing_traces:[{role:'unknown',selected_model:'chosen'}]});
 const [entry]=replies(t),html=context.view.message(entry,t,'',true);
 assert.equal((html.match(/<article/g)||[]).length,1);assert.match(html,/data-operation-actions/);assert.match(html,/Actual planner output/);assert.match(html,/workflow-details/);assert.doesNotMatch(html,/unknown: selected/);assert.match(html,/<span>Planner<\/span>/);
});
test('chat answers never inherit work pause, review or permission controls',()=>{
 const vm=require('node:vm'),fs=require('node:fs');
 const source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8').split("\n'use strict';\nconst $ =")[0];
 const context={CheapOSGuide:require('../dist/guidance.js'),esc:x=>String(x??''),icon:()=>'',messageText:x=>x};
 vm.createContext(context);vm.runInContext(source+'\nthis.view=CheapOSChatView;',context);
 const t=task({status:'paused',pending_approval:{id:'command'},discussion:[{id:'q',message:'Why?',status:'answering'}]});
 const reply=build(t).at(-1),html=context.view.message(reply,t,'<button>Resume review</button>');
 assert.match(html,/Replying/);assert.doesNotMatch(html,/Needs you|Resume review|data-operation-actions|Paused/);
 const work=build(t).findLast(e=>e.kind==='assistant'&&!e.discussion);
 assert.match(context.view.message(work,t,'<button>Resume review</button>'),/Resume review/);
});
test('final checks and review with explicit null item ownership cannot join the last item',()=>{
 const t=branchTask({planning_request:null,status:'reviewing',branch_run:{id:'run1',status:'finalizing',authorization_ref:'auth',current_item_id:null,items:[{id:'one',title:'Only item',status:'committed',commit_receipt:{stage:'completed',item_id:'one',run_id:'run1',new_tip:'a'.repeat(40)}}]},events:[
 {...event(1,'tool','replace text',{arguments:{path:'a'}}),branch_run_id:'run1',item_id:'one'},
 {...event(2,'checks','Final verification',{passed:true,command:['python3','-m','unittest']}),branch_run_id:'run1',item_id:null},
 {...event(3,'model','Requesting reviewer: final-reviewer',{}),branch_run_id:'run1',item_id:null}]});
 const list=replies(t);assert.equal(list.at(-1).operation,'final');assert.match(list.at(-1).itemTitle,/Final integration/);assert.equal(list.at(-1).steps.find(s=>s.phase==='checks').outcome,'passed');assert.ok(list.find(e=>e.operation==='one').steps.every(s=>s.phase!=='checks'));assert.equal(list.filter(e=>e.owner).length,1);
});
test('branch streamed narration stays visible inside its owning work details',()=>{
 const t=branchTask({planning_request:null,branch_run:{id:'run1',authorization_ref:'auth',status:'running',current_item_id:'one',items:[{id:'one',title:'Implement restart',status:'working'}]},stream:{role:'worker',phase:'answer',content:'Inspecting the implementation now',model:'worker-model'},events:[{...event(1,'model','Requesting worker: worker-model',{}),item_id:'one'}]});
 const reply=replies(t).at(-1);assert.equal(reply.steps.length,1);assert.equal(reply.steps[0].live,true);assert.equal(reply.stream.content,'Inspecting the implementation now');
});
test('invalid item receipt cannot announce a committed result and missing historical identity stays unavailable',()=>{
 const t=branchTask({planning_request:null,status:'paused',providers:{worker:{model:'new-global-model'}},branch_run:{id:'run1',authorization_ref:'auth',status:'paused',current_item_id:'one',items:[{id:'one',title:'Work',status:'committed',commit_receipt:{stage:'completed',item_id:'one',run_id:'run1',new_tip:'bad'}}]},events:[{...event(1,'tool','read file',{arguments:{path:'a'}}),item_id:'one'}]});
 const reply=replies(t).at(-1);assert.ok(reply.steps.every(s=>s.title!=='Item committed'));assert.equal(reply.steps[0].model,'');
});
test('reused whitespace evidence keeps its precise check description',()=>{
 const [reply]=replies(task({events:[event(1,'check_reused','Reused verification',{command:['git','diff','--check']})]}));
 assert.equal(reply.steps[0]?.title,'Whitespace check passed');
});
test('confirmed integration names actual target and commit while intermediate selection stays item-neutral',()=>{
 const t=branchTask({planning_request:null,status:'completed',branch_run:{id:'run1',authorization_ref:'auth',status:'merged',current_item_id:null,target_ref:'refs/heads/main',merge_receipt:{stage:'completed',feature_tip:'b'.repeat(40)},items:[]},events:[{...event(1,'branch_merged','Merged locally',{target_ref:'refs/heads/main',sha:'b'.repeat(40)}),branch_run_id:'run1',item_id:null}]});
 let reply=replies(t).at(-1);assert.match(reply.intro,/into main/);assert.equal(reply.steps.at(-1).title,'Local integration complete');assert.match(reply.steps.at(-1).detail,/main · bbbbbbbb/);assert.equal(reply.live,false);
 t.branch_run.status='running';t.status='running';t.branch_run.items=[{id:'done',status:'committed',commit_receipt:{stage:'completed'}},{id:'next',title:'Not selected yet',status:'pending'}];t.events=[];
 reply=replies(t).at(-1);assert.equal(reply.operation,'run');assert.equal(reply.steps.at(-1).title,'Preparing the next item');assert.equal(reply.itemTitle,'');
});

test('accepted plan stays visibly active before any worker output and then yields to actual work or pause',()=>{
 const t=branchTask({updated_at:stamp,planning_request:null,branch_run:{id:'run1',authorization_ref:'auth',status:'running',current_item_id:null,items:[{id:'one',title:'Build CSV exporter',status:'pending'}]}});
 const at=Date.parse(stamp)+30000;
 let reply=build(t,at).filter(e=>e.kind==='assistant').at(-1);
 assert.equal(reply.owner,true);assert.equal(reply.live,true);assert.equal(reply.steps.at(-1).title,'Starting your approved plan');assert.equal(reply.steps.at(-1).elapsed,'30s');assert.doesNotMatch(reply.steps.at(-1).detail,/Completed/);
 t.branch_run.current_item_id='one';t.branch_run.items[0].status='working';
 t.events=[{...event(1,'model','Requesting worker: worker-model',{}),item_id:'one'}];
 reply=build(t,at).filter(e=>e.kind==='assistant').at(-1);assert.equal(reply.itemTitle,'Item 1 of 1 · Build CSV exporter');assert.equal(reply.live,true);assert.equal(reply.steps.at(-1).elapsed,'30s');
 t.stream={role:'worker',model:'worker-model',phase:'answer',content:'Reading the CSV parser.'};
 reply=build(t,at).filter(e=>e.kind==='assistant').at(-1);assert.equal(reply.stream.content,'Reading the CSV parser.');
 t.status='paused';t.branch_run.status='paused';t.stream=null;
 reply=build(t,at).filter(e=>e.kind==='assistant').at(-1);assert.equal(reply.live,false);assert.ok(reply.steps.every(s=>!s.live));
});

test('saved startup stages stay in the active chat operation after acknowledgement and refresh',()=>{
 const t=branchTask({updated_at:stamp,branch_run:{id:'run1',authorization_ref:'auth',status:'awaiting_authorization',current_item_id:null,items:[],startup:{status:'running',stage:'verifying_snapshot',label:'Verifying task copy',started_at:stamp}},events:[event(1,'branch_startup','Verifying task copy',{stage:'verifying_snapshot'})]});
 for(const [stage,label] of [['verifying_snapshot','Verifying task copy'],['preparing_branch','Preparing branch'],['selecting_worker','Selecting worker']]){
  Object.assign(t.branch_run.startup,{stage,label});t.updated_at=new Date(Date.parse(stamp)+1000).toISOString();
  const clock=require('../dist/guidance.js').progress(t,Date.parse(stamp)+2000);assert.equal(clock.elapsed,'2s');assert.equal(clock.title,label);
  const reply=build(JSON.parse(JSON.stringify(t)),Date.parse(stamp)+2000).filter(e=>e.kind==='assistant').at(-1);
  assert.equal(reply.operation,'run');assert.equal(reply.live,true);assert.match(reply.intro,/approval is saved/);assert.equal(reply.steps.at(-1).title,label);assert.equal(reply.steps.at(-1).elapsed,'2s');
 }
 t.status='paused';t.branch_run.startup.status='paused';
 assert.equal(replies(t).at(-1).live,false);
});

test('automatic reviewer guidance appears inside the review with inspectable evidence and no false approval',()=>{
 const t=branchTask({planning_request:null,status:'reviewing',branch_run:{id:'run1',authorization_ref:'auth',status:'running',current_item_id:'one',items:[{id:'one',title:'Review report',status:'reviewing'}]},events:[
  {...event(1,'model','Requesting reviewer: reviewer-model',{}),item_id:'one'},
  {...event(2,'review_coaching','Helping the reviewer reach a decision',{role:'reviewer',summary:'I’m asking for a focused reassessment.'}),item_id:'one'}]});
 let reply=replies(t).at(-1);assert.equal(reply.owner,true);assert.equal(reply.steps.at(-1).title,'Reassessing the review');assert.equal(reply.steps.at(-1).role,'reviewer');assert.equal(reply.steps.at(-1).outcome,'live');
 assert.ok(reply.steps.at(-1).events.some(e=>e.kind==='review_coaching'));
 t.status='paused';t.branch_run.status='paused';reply=replies(t).at(-1);assert.equal(reply.live,false);assert.equal(reply.steps.at(-1).outcome,'pending');
});

test('finalizing branch run with approved task status keeps live checks and check_stream',()=>{
 const t=branchTask({planning_request:null,status:'approved',branch_run:{id:'run1',authorization_ref:'auth',status:'finalizing',current_item_id:null,items:[{id:'one',status:'committed',commit_receipt:{stage:'completed'}}]},check_stream:{command:['python3','-m','unittest','discover'],session_allowed:true,output:'running tests...'},events:[
  {...event(1,'tool','Running verification',{command:['python3','-m','unittest','discover']}),branch_run_id:'run1',item_id:null}
 ]});
 const reply=replies(t).at(-1);
 assert.equal(reply.operation,'final');
 assert.equal(reply.live,true);
 assert.equal(reply.label,'Checking');
 assert.equal(reply.steps[0].live,true);
 assert.equal(reply.steps[0].outcome,'live');
 assert.equal(reply.steps[0].phase,'checks');
});

test('assistant reply is not duplicated as a workflow-note in step events',()=>{
 const t=task({status:'awaiting_reply',events:[
  event(1,'tool','read file',{arguments:{path:'server.py'}}),
  event(2,'assistant','cheapoS','Here is the final answer.')
 ]});
 const entries=build(t);
 const reply=entries.find(e=>e.kind==='assistant');
 assert.equal(reply.reply,'Here is the final answer.');
 assert.ok(reply.steps[0].events.every(e=>e.kind!=='assistant'));
});
test('current working approach appears in ordinary chat without tools and distinguishes paused approval',()=>{
 const vm=require('node:vm'),fs=require('node:fs');
 const source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8').split("\n'use strict';\nconst $ =")[0];
 const context={CheapOSGuide:require('../dist/guidance.js'),esc:x=>String(x??'').replaceAll('<','&lt;'),icon:()=>'',messageText:x=>x,thinkingMarkup:()=>'',eventDetail:()=>''};vm.createContext(context);vm.runInContext(source+'\nthis.view=CheapOSChatView;',context);
 for(const [status,pending_approval,label] of [['awaiting_reply',null,'Saved approach'],['paused',null,'Paused'],['awaiting_permission',{command:['test']},'Needs approval']]){
  const t=task({status,pending_approval,working_states:{interactive:{next_action:'Fix <button>'}},events:[event(1,'assistant','Worker','Found the issue.')]});
  const html=context.view.message(replies(t).at(-1),t);
  assert.match(html,new RegExp(label));assert.match(html,/Fix &lt;button>/);assert.match(html,/checks and independent review remain separate/);
 }
});
test('assistant reply matching recorded thinking is not duplicated in reply text',()=>{
 const thought='We need to answer "any other suggestions?" Find another simple improvement.';
 const t=task({status:'awaiting_reply',events:[
  event(1,'model','Requesting worker: groq/openai/gpt-oss-120b',{}),
  event(2,'generation','Model thinking',{thinking:thought}),
  event(3,'assistant','Worker',thought)
 ]});
 const [reply]=replies(t);
 assert.equal(reply.reply,'');
 assert.equal(reply.steps[0].events.find(e=>e.kind==='generation').detail.thinking,thought);
 const vm=require('node:vm'),fs=require('node:fs');
 const source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8').split("\n'use strict';\nconst $ =")[0];
 const context={CheapOSGuide:require('../dist/guidance.js'),esc:x=>String(x??''),icon:()=>'',messageText:x=>x,thinkingMarkup:d=>`<details class="thinking-panel">${d.thinking}</details>`,eventDetail:()=>''};
 vm.createContext(context);vm.runInContext(source+'\nthis.view=CheapOSChatView;',context);
 const html=context.view.message(reply,t);
 assert.match(html,/class="thinking-panel"/);
 assert.doesNotMatch(html,/class="cheapos-answer"/);
});
test('assistant reply with leading thinking strips duplicate thought from answer',()=>{
 const thought='Let me think through this.';
 const t=task({status:'awaiting_reply',events:[
  event(1,'generation','Model thinking',{thinking:thought}),
  event(2,'assistant','Worker',`${thought}\n\nHere is the real answer.`)
 ]});
 const [reply]=replies(t);
 assert.equal(reply.reply,'Here is the real answer.');
});
test('assistant reply distinct from thinking is preserved in reply text',()=>{
 const thought='Let me think through this.';
 const t=task({status:'awaiting_reply',events:[
  event(1,'generation','Model thinking',{thinking:thought}),
  event(2,'assistant','Worker','Here is the distinct answer.')
 ]});
 const [reply]=replies(t);
 assert.equal(reply.reply,'Here is the distinct answer.');
});
