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
