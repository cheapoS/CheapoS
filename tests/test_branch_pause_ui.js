const {test}=require('node:test');
const assert=require('node:assert/strict');
const {pausePresentation}=require('../dist/branch_ui.js');
const task=(cause,next_action,extra={})=>({branch_run:{status:'paused',pause_detail:{version:1,cause,next_action,explanation:'Controlled explanation',stage:'reviewing',item_id:'one',role:'reviewer',diagnostic_id:'request-1'},...extra}});
test('quota, restart, clarification and dispute have distinct actions and evidence',()=>{
 const quota=pausePresentation(task('provider_quota','models'));
 assert.equal(quota.action,'models');assert.match(quota.headline,/quota/);assert.equal(quota.saved,'The saved task record is retained.');assert.ok(quota.details.includes('Reset time unavailable'));
 const restart=pausePresentation(task('restart','resume'));assert.equal(restart.action,'resume');
 const clarification=pausePresentation(task('essential_clarification','reply',{waiting_for_user:'Which format?'}));assert.equal(clarification.question,'Which format?');assert.equal(clarification.action,'reply');
 assert.equal(pausePresentation(task('repeated_review_dispute','review_dispute')).action,'review_dispute');
});
test('active or completed work hides stale pauses and legacy has no invented cause',()=>{
 assert.equal(pausePresentation({branch_run:{status:'paused'}}),null);
 for(const status of ['running','finalizing','merged','ready_for_merge'])assert.equal(pausePresentation(task('restart','resume',{status})),null);
 const t=task('restart','resume',{merge_operation:{id:'operation'}});assert.equal(pausePresentation(t).actionLabel,'Finish saved integration');
});
test('all supported blockers use explicit existing actions without claiming commits',()=>{
 for(const [cause,action] of [['missing_setup','environment'],['command_grant','permission'],['exhausted_work','limits'],['branch_drift','inspect'],['authority_changed','authorization'],['malformed_output','correction'],['repeated_work','correction']]){
  const v=pausePresentation(task(cause,action));assert.equal(v.action,action);assert.doesNotMatch(v.saved,/committed|passed/);
 }
});

test('Activity shows escaped claims and counterevidence with bounded dispute history',()=>{
 const fs=require('node:fs'),vm=require('node:vm');
 const source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8');
 const start=source.indexOf('function reviewDisputeMarkup('),end=source.indexOf('function renderActivity()',start);
 const sandbox={esc:value=>String(value??'').replaceAll('<','&lt;')};vm.createContext(sandbox);vm.runInContext(source.slice(start,end),sandbox);
 const finding={id:'a',status:'requested',attempts:3,structural:{criterion:'one:1'},history:[{candidate_id:'old',finding:{location:'a.py:2',expected:'safe',observed:'<script>',support:'code'}}],worker_counterevidence:{disposition:'disproved',evidence:'check 3 passed'}};
 const result=sandbox.reviewDisputeMarkup({branch_run:{dispute_ledger:{findings:{a:finding}}}});
 assert.match(result,/check 3 passed/);assert.match(result,/&lt;script>/);assert.doesNotMatch(result,/<script>/);assert.match(result,/not approval/);
});
