const test=require('node:test'),assert=require('node:assert/strict');
const integration=require('../dist/integration.js');
test('current review readiness supersedes an old combining label without changing the saved operation',()=>{
 const task={status:'approved',branch_run:{status:'ready_for_merge'},integration_preparation:{id:'old',authorized:true,status:'running',stage:'combining',label:'Combining changes',dispatched:true}};
 const before=JSON.stringify(task),html=integration.markup(task,{code:'ready',actions:[],message:'Ready for review'});
 assert.match(html,/Ready for your review/);assert.doesNotMatch(html,/Combining changes/);
 assert.equal(JSON.stringify(task),before);
 delete task.integration_preparation.dispatched;
 assert.match(integration.markup(task,{code:'ready'}),/Combining changes/,'A newly accepted update retains immediate feedback');
 assert.match(integration.markup({...task,integration_preparation:{...task.integration_preparation,dispatched:true}},{code:'review_required'}),/Combining changes/,'Missing verification must not be presented as completed');
});
test('readiness exposes only supported preparation actions and escapes paths',()=>{
 const task={id:'a',branch_run:{}};
 let html=integration.markup(task,{code:'dirty_destination',message:'Waiting for local changes',actions:['inspect_local_changes'],files:['<source>']});
 assert.match(html,/Inspect local changes/);assert.doesNotMatch(html,/data-integration-prepare/);assert.match(html,/&lt;source&gt;/);
 html=integration.markup(task,{code:'target_advanced',actions:['update_resolve'],target_tip:'abc',candidate:'def'});
 assert.match(html,/Update &amp; resolve/);assert.match(html,/Final approval is still required/);assert.match(html,/Keep on branch/);
 html=integration.markup(task,{code:'target_advanced',actions:['update_resolve','inspect_local_changes'],local_changes:['<protocol>.md']});
 assert.match(html,/data-integration-prepare/);assert.match(html,/data-integration-local/);
 assert.match(html,/Local changes will stay untouched/);assert.match(html,/committed changes/);
 assert.match(html,/Unrelated local edits can stay in place when you merge/);assert.match(html,/&lt;protocol&gt;.md/);
 assert.doesNotMatch(html,/until the destination is clean/);
 assert.doesNotMatch(html,/<protocol>/);
});
test('local comparison lists untracked files even when Git diff is empty',()=>{
 const text=integration.comparisonText({files:['PROTOCOL.md','cheapskate-club-protocol.md'],diff:''},true);
 assert.match(text,/Files with local changes:\nPROTOCOL.md\ncheapskate-club-protocol.md/);
 assert.match(text,/New, untracked files do not appear in Git diff/);
 assert.doesNotMatch(text,/No comparison is available/);
 assert.match(integration.comparisonText({files:['tracked.py'],diff:'-old\n+new'},true),/tracked.py[\s\S]*-old\n\+new/);
 assert.equal(integration.comparisonText({diff:''}),'No comparison is available yet.');
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
test('update explains exact check renewal and required permission is actionable in Changes',async()=>{
 const task={id:'permission',branch_run:{check_scope:[{command:['python3','test.py'],directory:'private'}]},integration_preparation:{authorized:true,status:'decision',reason:{code:'command_permission_required',message:'Permission changed'}}};
 const html=integration.markup(task,{actions:['update_resolve']});
 assert.match(html,/Verification included in this update/);assert.match(html,/python3 test.py/);
 assert.match(html,/Review test permissions &amp; continue/);
 const button={disabled:false},error={textContent:''};
 const host={querySelector:s=>s==='[data-integration-permission]'?button:s==='[data-integration-error]'?error:null};
 const calls=[];let finish;
 integration.bind(host,task,null,()=>{throw Error('must use current Resume permission protocol');},()=>{},null,async saved=>{calls.push(saved);await new Promise(resolve=>finish=resolve);});
 const first=button.onclick();await button.onclick();assert.equal(calls.length,1);assert.equal(calls[0],task);
 finish();await first;assert.equal(button.disabled,false);assert.equal(error.textContent,'');
 task.integration_preparation.status='running';assert.doesNotMatch(integration.markup(task),/data-integration-permission/);
 task.integration_preparation.status='cancelled';assert.doesNotMatch(integration.markup(task),/data-integration-permission/);
});

test('deleted publication target names both branches and requires bound explicit preparation',async()=>{
 const task={id:'retarget',integration_preparation:{status:'ready',label:'Ready for your review',reason:{message:'Review the specific decision in this chat.'}}};
 const readiness={publication_id:'saved-publication',previous_base:'old-branch',target_ref:'refs/heads/main',target_tip:'new-tip',candidate:'patch',actions:['update_resolve']};
 const html=integration.markup(task,readiness);
 assert.match(html,/old-branch/);assert.match(html,/<strong>main<\/strong>/);
 assert.match(html,/fresh checks and independent review/);assert.match(html,/separate approval/);
 assert.doesNotMatch(html,/Ready for your review|Review the specific decision/);
 assert.doesNotMatch(integration.markup(task),/Review the specific decision/);
 let sent;
 await integration.prepare(async(url,body)=>{sent={url,body};return task;},task,readiness);
 assert.equal(sent.body.publication_id,'saved-publication');assert.equal(sent.body.target_ref,'refs/heads/main');assert.equal(sent.body.approved,true);
});
