const {test}=require('node:test');
const assert=require('node:assert/strict');
const {pausePresentation}=require('../dist/branch_ui.js');
const ui=require('../dist/branch_ui.js');
const task=(cause,next_action,extra={})=>({branch_run:{status:'paused',pause_detail:{version:1,cause,next_action,explanation:'Controlled explanation',stage:'reviewing',item_id:'one',role:'reviewer',diagnostic_id:'request-1'},...extra}});
test('quota, restart, clarification and dispute have distinct actions and evidence',()=>{
 const quota=pausePresentation(task('provider_quota','models'));
 assert.equal(quota.action,'models');assert.match(quota.headline,/quota/);assert.equal(quota.saved,'The saved task record is retained.');assert.ok(quota.details.includes('Reset time unavailable'));
 const restart=pausePresentation(task('restart','resume'));assert.equal(restart.action,'resume');
 const clarification=pausePresentation(task('essential_clarification','reply',{waiting_for_user:'Which format?'}));assert.equal(clarification.question,'Which format?');assert.equal(clarification.action,'reply');
 assert.equal(pausePresentation(task('repeated_review_dispute','review_dispute')).action,'resume');
});
test('active or completed work hides stale pauses and legacy has no invented cause',()=>{
 assert.equal(pausePresentation({branch_run:{status:'paused'}}),null);
 for(const status of ['running','finalizing','merged','ready_for_merge'])assert.equal(pausePresentation(task('restart','resume',{status})),null);
 const t=task('restart','resume',{merge_operation:{id:'operation'}});assert.equal(pausePresentation(t).actionLabel,'Finish saved integration');
});
test('all supported blockers use explicit existing actions without claiming commits',()=>{
 for(const [cause,action] of [['missing_setup','resume'],['command_grant','permission'],['exhausted_work','limits'],['branch_drift','inspect'],['authority_changed','authorization'],['malformed_output','correction'],['repeated_work','correction']]){
  const v=pausePresentation(task(cause,action));assert.equal(v.action,action);assert.doesNotMatch(v.saved,/committed|passed/);
 }
});

test('ordinary saved failures lead with Resume; required decisions remain explicit',()=>{
 for(const action of ['models','inspect','correction','resume']){
  const t=task('provider_connection',action,{authorization_ref:'auth'}),html=ui.pauseMarkup(t);
  assert.match(html.split('<details')[0],/class="primary-button"[^>]+>Resume saved work/);
  assert.match(html,/<details[^>]*>[\s\S]*View technical logs[\s\S]*<\/details>/);
  assert.match(ui.pauseMarkup(t,{status:'pending'}),/class="primary-button"[^>]+disabled/);
 }
 for(const action of ['permission','limits','reply','authorization','reviewer']){
  const html=ui.pauseMarkup(task('command_grant',action,{authorization_ref:'auth'}));
  assert.doesNotMatch(html,/data-resume/);
  assert.match(html,/class="primary-button" data-pause-action/);
 }
 assert.doesNotMatch(ui.pauseMarkup(task('provider_connection','models')),/data-resume/);
 const pending=task('command_grant','permission',{authorization_ref:'auth'});pending.pending_approval={};
 assert.doesNotMatch(ui.pauseMarkup(pending),/data-resume/);
});

test('paused completed items resume without an empty review CTA; ready evidence opens Changes',async()=>{
 const fs=require('node:fs'),vm=require('node:vm'),source=fs.readFileSync(require.resolve('../dist/branch_ui.js'),'utf8');
 const t=task('provider_connection','resume',{id:'run',authorization_ref:'auth',items:[{id:'one',status:'committed',commit_receipt:{stage:'completed',run_id:'run',item_id:'one',new_tip:'a'.repeat(40)}}]});t.id='saved';t.status='paused';
 let resumed=0,reviewed=0;const nodes=new Map();
 const panel={innerHTML:'',querySelector(selector){if(!this.innerHTML.includes(selector.slice(1,-1)))return null;if(!nodes.has(selector))nodes.set(selector,{});return nodes.get(selector);}};
 const view={querySelector:s=>s==='#branch-run-summary'?panel:{}};
 const context={...ui,sync(){},document:{querySelector:()=>view},starts:{get:()=>null},getState:()=>({}),detailStates:new Map(),summaryHTML:'',options:{resume:async saved=>{assert.equal(saved,t);resumed++;}},guarded:async(button,fn)=>fn(),showFinal:saved=>{assert.equal(saved,t);reviewed++;}};
 vm.createContext(context);vm.runInContext(source.slice(source.indexOf(' function render(task)'),source.indexOf(' function renderPlan(task)')),context);
 context.render(t);assert.equal(ui.projectRun(t).canRecheck,true);assert.equal(panel.querySelector('[data-preview]'),null);
 await panel.querySelector('[data-pause-action]').onclick();assert.equal(resumed,1);
 t.branch_run.pause_detail.cause='repeated_review_dispute';t.branch_run.pause_detail.next_action='review_dispute';
 context.render(t);assert.doesNotMatch(panel.innerHTML,/Inspect review disagreement|needs a decision/);
 await panel.querySelector('[data-pause-action]').onclick();assert.equal(resumed,2);
 delete t.branch_run.pause_detail;context.render(t);assert.equal(panel.querySelector('[data-recheck-run]'),null);
 await panel.querySelector('[data-resume]').onclick();assert.equal(resumed,3);
 t.branch_run.status='ready_for_merge';t.branch_run.readiness={manifest:{files:[{path:'actual.py'}]}};
 context.render(t);assert.match(panel.innerHTML,/>Review changes<\/button>/);
 await panel.querySelector('[data-preview]').onclick();assert.equal(reviewed,1);
 t.branch_run.readiness.manifest.files=[];context.render(t);
 assert.match(panel.innerHTML,/>Review results<\/button>/);assert.doesNotMatch(panel.innerHTML,/>Review changes<\/button>/);
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

test('paused planning uses the same retry as Advanced without authorizing implementation',async()=>{
 const fs=require('node:fs'),vm=require('node:vm'),app=fs.readFileSync(require.resolve('../dist/app.js'),'utf8');
 const planning=task('missing_setup','environment');planning.id='saved';planning.planning_request={prompt:'Improve project'};
 assert.equal(ui.pausePresentation(planning).action,'resume');
 assert.match(ui.pauseMarkup(planning),/>Resume saved work<\/button>/);
 assert.doesNotMatch(ui.pauseMarkup(planning),/Inspect task environment/);
 for(const action of ['models','inspect','correction','reviewer']){
  planning.branch_run.pause_detail.next_action=action;
  assert.equal(ui.pausePresentation(planning).action,'resume');
 }
 for(const action of ['permission','limits','reply','authorization']){
  planning.branch_run.pause_detail.next_action=action;
  assert.equal(ui.pausePresentation(planning).action,action);
 }
 const calls=[],ctx={state:{task:planning},CheapOSBranchUI:ui,renderChat(){},refresh:async()=>{},
  api:async(...args)=>{calls.push(args);return {task:planning};}};
 vm.createContext(ctx);vm.runInContext(app.slice(app.indexOf('async function resumeBranchRun('),app.indexOf('async function bootstrap()')),ctx);
 await ctx.resumeBranchRun(planning);
 assert.equal(calls[0][0],'/tasks/saved/operator-recovery');
 assert.deepEqual(JSON.parse(JSON.stringify(calls[0][1])),{action:'retry'});
 planning.branch_run.authorization_ref='accepted';
 await ctx.resumeBranchRun(planning);
 assert.equal(calls[1][0],'/tasks/saved/branch-resume');
 assert.deepEqual(JSON.parse(JSON.stringify(calls[1][1])),{});
});
