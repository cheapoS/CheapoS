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
