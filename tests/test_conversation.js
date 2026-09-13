const {test}=require('node:test');
const assert=require('node:assert/strict');
const {conversation:{build,readyForNext}}=require('../dist/guidance.js');
const stamp='2026-09-13T12:00:00Z';
const event=(id,kind,title,detail)=>({id,kind,title,detail,time:stamp});
const task=overrides=>({prompt:'Fix the script.',status:'awaiting_reply',active_role:'worker',changes:[],checks:[],checkpoints:[],events:[],providers:{worker:{model:'worker-model'},reviewer:{model:'reviewer-model'}},...overrides});
const replies=t=>build(t).filter(e=>e.kind==='assistant');

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
