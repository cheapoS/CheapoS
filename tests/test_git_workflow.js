const test=require('node:test');
const assert=require('node:assert/strict');
const workflow=require('../dist/git_workflow.js');
test('local default and saved project workflow are explicit',()=>{
 assert.equal(workflow.enabled({}),false);
 assert.equal(workflow.enabled({settings_snapshot:{values:{git:{workflow:'pull_request'}}}}),true);
});
test('PR review names the destination and keeps remote merge separate',()=>{
 const html=workflow.content({repo:'org/repo',base:'production',branch:'cheapos/task',id:'preview'});
 assert.match(html,/org\/repo/);assert.match(html,/production/);assert.match(html,/Approve &amp; open pull request|Approve & open pull request/);
 assert.match(html,/destination checkout stays unchanged/);
 assert.doesNotMatch(html,/Approve &amp; merge locally/);
});
test('CI presentation does not claim unprotected branches are protected',()=>{
 const html=workflow.content({url:'https://github.com/org/repo/pull/7',number:7,ci:{state:'pending',message:'No results yet',protected:false,checks:[]}});
 assert.match(html,/No results yet/);assert.match(html,/no GitHub branch protection/);
 assert.equal(workflow.safeURL('javascript:alert(1)'),null);
 assert.equal(workflow.safeURL('https://github.com.evil.test/org/repo/pull/1'),null);
 assert.doesNotMatch(workflow.content({repo:'<script>',base:'main',branch:'x'}),/<script>/);
});
test('merged PR distinguishes local sync and retries pending checkout updates',()=>{
 const p={url:'https://github.com/org/repo/pull/7',number:7,ci:{state:'merged',message:'Merged on GitHub.'},local_sync:{state:'deferred',retryable:true,message:'Local draft preserved <safe>'}};
 assert.match(workflow.content(p),/Local draft preserved &lt;safe&gt;/);
 assert.equal(workflow.needsSync(p),true);
 assert.equal(workflow.needsSync({...p,local_sync:{state:'current',retryable:false}}),false);
 assert.equal(workflow.needsSync({...p,ci:{state:'changed'}}),false);
});
const mergedTask=()=>({status:'awaiting_reply',patch:'reviewed patch',settings_snapshot:{values:{git:{workflow:'pull_request'}}},pull_request:{head:'a'.repeat(40),merged_head:'a'.repeat(40),patch:'reviewed patch',url:'https://github.com/org/repo/pull/7',number:7,base:'main',ci:{state:'merged'},local_sync:{state:'updated',branch:'main',retryable:false}}});
test('merged work shows the recorded pull without asking for another approval',()=>{
 const t=mergedTask();
 assert.equal(workflow.merged(t),true);
 for(const html of [workflow.content(t.pull_request),workflow.completionMarkup(t),workflow.markup(t)]){
  assert.match(html,/Merged · local main up to date/);
  assert.match(html,/cheapoS pulled the merged changes/);
  assert.match(html,/View merged PR #7/);
  assert.doesNotMatch(html,/data-pr-publish|Open pull request|Ready for|Preparing your reviewed|data-pr-refresh/);
 }
 assert.equal(workflow.merged({...t,patch:'new edits'}),true);
 assert.match(workflow.completionMarkup({...t,patch:'new edits'}),/Recover changes into a new task/);
 assert.match(workflow.completionMarkup(t),/Continue in new task/);
 assert.equal(workflow.merged({...t,pull_request:{...t.pull_request,ci:{state:'merged',head:'other'}}}),false);
 assert.equal(workflow.merged({...t,pull_request:{...t.pull_request,ci:{state:'passed'}}}),false);
 const branch={...t,branch_run:{status:'merged',expected_feature_tip:t.pull_request.head}};
 assert.equal(workflow.merged(branch),true);
 assert.equal(workflow.merged({...branch,branch_run:{...branch.branch_run,expected_feature_tip:'new head'}}),true);
 assert.equal(workflow.laterEdits({...branch,branch_run:{...branch.branch_run,expected_feature_tip:'new head'}}),true);
});
test('local sync copy does not claim a pull or an up-to-date branch without evidence',()=>{
 const p=mergedTask().pull_request;
 const current=workflow.content({...p,local_sync:{state:'current',branch:'production'}});
 assert.match(current,/local production up to date/);assert.match(current,/No pull was needed/);assert.doesNotMatch(current,/cheapoS pulled/);
 const ahead=workflow.content({...p,local_sync:{state:'ahead',branch:'main'}});
 assert.match(ahead,/additional local commits/);assert.doesNotMatch(ahead,/up to date/);
 for(const local_sync of [undefined,{state:'deferred',retryable:true,message:'Draft <preserved>'}]){
  const html=workflow.content({...p,local_sync});
  assert.match(html,/local sync pending/);assert.match(html,/data-pr-refresh/);assert.doesNotMatch(html,/up to date|cheapoS pulled/);
 }
 assert.match(workflow.content({...p,local_sync:{state:'destination_changed',retryable:false}}),/local sync needs attention/);
});
test('missing sync receipt remains eligible in Chat and after reload',()=>{
 const task=mergedTask();task.id='missing';task.pull_request.id='receipt';delete task.pull_request.local_sync;
 assert.equal(workflow.needsSync(task.pull_request),true);
 assert.equal(workflow.needsStatus(task),true);
 assert.match(workflow.completionMarkup(task),/data-pr-sync>Retry sync/);
 assert.equal(workflow.needsStatus({...task,archived_at:'saved'}),false);
 assert.equal(workflow.needsStatus({...task,trashed_at:'saved'}),false);
 assert.equal(workflow.needsStatus({...task,settings_snapshot:{}}),false);
});
test('automatic checks coalesce with clicks, back off failures, and stop after sync',async()=>{
 const task=mergedTask();task.id='polling';task.pull_request.id='op';delete task.pull_request.local_sync;
 let clock=1000,calls=0,resolve;
 const original=Date.now;Date.now=()=>clock;
 const api=async path=>{assert.equal(path,'/tasks/polling/pull-request-status');calls++;return new Promise(r=>{resolve=r;});};
 try{
  const first=workflow.checkStatus(task,api);await Promise.resolve();
  // Routine refreshes do not accumulate callbacks while a fetch is in flight.
  assert.equal(await workflow.checkStatus(task,api),null);
  const clicked=workflow.checkStatus(task,api,{force:true});
  resolve({local_sync:{state:'deferred',retryable:true}});
  assert.deepEqual(await first,await clicked);assert.equal(calls,1);
  assert.equal(await workflow.checkStatus(task,api),null);
  clock+=60001;
  await assert.rejects(workflow.checkStatus(task,async()=>{calls++;throw Error('offline');}),/offline/);
  assert.equal(await workflow.checkStatus(task,api),null);assert.equal(calls,2);
  clock+=60001;
  const current={...task.pull_request,local_sync:{state:'current',retryable:false}};
  const resumed=await workflow.checkStatus(task,async()=>{calls++;return current;});
  task.pull_request=resumed;
  clock+=60001;
  assert.equal(await workflow.checkStatus(task,api),null);assert.equal(calls,3);
 }finally{Date.now=original;}
});
test('manual retry acknowledges the click before the network finishes',async()=>{
 const task=mergedTask();task.id='button';task.pull_request.id='op';delete task.pull_request.local_sync;
 const button={textContent:'Retry sync',disabled:false};let resolve,refreshed=false;
 workflow.bindSync({querySelectorAll:()=>[button]},task,()=>new Promise(r=>{resolve=r;}),()=>{refreshed=true;});
 const click=button.onclick();assert.equal(button.disabled,true);assert.match(button.textContent,/Checking GitHub & syncing/);
 await Promise.resolve();resolve({});await click;
 assert.equal(refreshed,true);assert.equal(button.disabled,false);
});
test('new-chat snapshot warning distinguishes pending sync from completed work',()=>{
 assert.equal(workflow.freshnessMarkup({git_sync:{state:'current',retryable:false}}),'');
 const html=workflow.freshnessMarkup({git_sync:{state:'deferred',retryable:true,branch:'production',message:'Draft <preserved>'}});
 assert.match(html,/Started from local production/);assert.match(html,/remote sync was pending/);
 assert.match(html,/original snapshot/);assert.match(html,/Draft &lt;preserved&gt;/);
});
