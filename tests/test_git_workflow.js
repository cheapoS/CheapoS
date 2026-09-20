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
 assert.equal(workflow.merged({...t,patch:'new edits'}),false);
 assert.doesNotMatch(workflow.markup({...t,patch:'new edits'}),/Merged ·/);
 assert.equal(workflow.completionMarkup({...t,patch:'new edits'}),'');
 assert.equal(workflow.merged({...t,pull_request:{...t.pull_request,merged_head:'other'}}),false);
 assert.equal(workflow.merged({...t,pull_request:{...t.pull_request,ci:{state:'passed'}}}),false);
 const branch={...t,branch_run:{status:'merged',expected_feature_tip:t.pull_request.head}};
 assert.equal(workflow.merged(branch),true);
 assert.equal(workflow.merged({...branch,branch_run:{...branch.branch_run,expected_feature_tip:'new head'}}),false);
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
