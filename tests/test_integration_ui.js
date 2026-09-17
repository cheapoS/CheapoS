const test=require('node:test'),assert=require('node:assert/strict');
const integration=require('../dist/integration.js');
test('readiness exposes only supported preparation actions and escapes paths',()=>{
 const task={id:'a',branch_run:{}};
 let html=integration.markup(task,{code:'dirty_destination',message:'Waiting for local changes',actions:['inspect_local_changes'],files:['<source>']});
 assert.match(html,/Inspect local changes/);assert.doesNotMatch(html,/data-integration-prepare/);assert.match(html,/&lt;source&gt;/);
 html=integration.markup(task,{code:'target_advanced',actions:['update_resolve'],target_tip:'abc',candidate:'def'});
 assert.match(html,/Update &amp; resolve/);assert.match(html,/Final approval is still required/);assert.match(html,/Keep on branch/);
});
test('duplicate clicks share one server-owned operation and never dispatch start in the browser',async()=>{
 const calls=[];let resolve;
 const api=(url,body)=>{calls.push({url,body});return new Promise(r=>resolve=r);};
 const task={id:'duplicates'},r={target_tip:'abc',candidate:'def'};
 const one=integration.prepare(api,task,r),two=integration.prepare(api,task,r);
 assert.equal(one,two);assert.equal(calls.length,1);assert.match(calls[0].url,/integration-prepare$/);
 assert.equal(calls[0].body.approved,true);resolve({id:task.id});await one;
 assert.equal(calls.length,1);
});
test('lost acknowledgement reads the same task instead of creating another operation',async()=>{
 const calls=[];let id;
 const api=async(url,body)=>{calls.push(url);if(body){id=body.operation_id;throw Error('response lost');}return {id:'lost',integration_preparation:{id}};};
 const result=await integration.prepare(api,{id:'lost'},{target_tip:'a',candidate:'b'});
 assert.equal(result.integration_preparation.id,id);assert.deepEqual(calls,['/tasks/lost/integration-prepare','/tasks/lost']);
});
