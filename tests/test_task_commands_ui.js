const {test}=require('node:test');
const assert=require('node:assert/strict');
const ui=require('../dist/branch_ui.js');
test('Start sends only the operator command choice, including opt-out',async()=>{
 for(const enabled of [undefined,false,true,'true']){
  let body;const c=ui.startController({api:async(_,b)=>{body=b;return {id:'one'};}});
  await c.start({task_id:'one',proposal_id:'approved',allow_task_commands:enabled});
  assert.equal(Object.hasOwn(body,'allow_task_commands'),typeof enabled==='boolean');
  if(typeof enabled==='boolean')assert.equal(body.allow_task_commands,enabled);
 }
});
test('permission allows preparing missing runners but never missing workspace or unknown readiness',()=>{
 const ready={id:'workspace',status:'ready'},missing={id:'command-0',status:'blocked'};
 const p={readiness:{ready:false,checks:[ready,missing]}};
 assert.equal(ui.proposalStartBlocked(p,true),false);
 assert.equal(ui.proposalStartBlocked(p,false),true);
 p.readiness.checks[0].status='blocked';assert.equal(ui.proposalStartBlocked(p,true),true);
 assert.equal(ui.proposalStartBlocked({readiness:{ready:false,checks:[]}},true),true);
});
test('retry after uncertain startup retains the same command permission decision',async()=>{
 const bodies=[];const c=ui.startController({api:async(_,body)=>{
  if(body){bodies.push(body);if(bodies.length===1)throw Error('lost');return {id:'one'};}
  return {branch_run:{authorization_ref:'saved',status:'awaiting_authorization'}};
 }});
 await c.start({task_id:'one',proposal_id:'approved',allow_task_commands:true});
 await c.retry('one');
 assert.deepEqual(bodies,[{proposal_id:'approved',approved:true,allow_task_commands:true},{proposal_id:'approved',approved:true,allow_task_commands:true}]);
});
test('setup output is shown as a command, never as verification',()=>{
 const guide=require('../dist/guidance.js');
 const t={id:'one',status:'running',events:[],changes:[],check_stream:{kind:'command',command:['npm','ci'],started_at:new Date().toISOString()}};
 assert.equal(guide.progress(t).title,'Running task command');
});
