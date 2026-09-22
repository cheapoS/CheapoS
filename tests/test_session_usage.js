const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8');
const ctx={esc:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;')};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('function tokenUsageLabel('),source.indexOf('function renderInspector(')),ctx);
const task=()=>({id:'task',token_accounting:{reported:133422,reserved:99644,accounted:233066,coverage:'complete',
  requests:[{model:'fixture/model',role:'planner',purpose:'planning',status:'failed',error_code:'gateway_cooldown',
    prompt_tokens:86454,output_tokens:8192,tokens:94646,prompt_bytes:85430,buffer_tokens:1024}]}});
test('header and role rows show totals while the plain accounting dropdown retains the breakdown',()=>{
  const t=task();
  t.token_accounting.roles={planner:{reported:90699,reserved:49184,accounted:139883,consistent:true}};
  assert.equal(ctx.tokenUsageLabel(t,'planner'),'139,883 tokens');
  assert.equal(ctx.tokenUsageLabel(t),'233,066 tokens');
  const html=ctx.tokenReservationDetails(t);
  assert.match(html,/<summary>Token accounting<\/summary>/);
  assert.match(html,/133,422 reported · 99,644 reserved/);
  assert.match(html,/86,454 prompt estimate \+ 8,192 output estimate/);
  assert.match(html,/85,430 bytes \+ 1,024 buffer/);
  assert.match(html,/not confirmed consumption or money held/);
  assert.match(html,/data-event="token-reservations-task"/);
});
test('missing history is never presented as zero actual usage',()=>{
  const t=task();t.token_accounting.coverage='partial';t.token_accounting.unclassified=10;
  assert.equal(ctx.tokenUsageLabel(t),'233,066 tokens');
  assert.match(ctx.tokenReservationDetails(t),/Historical request evidence is incomplete/);
  assert.match(ctx.tokenReservationDetails(t),/10 unclassified/);
  assert.equal(ctx.tokenUsageLabel({metrics:{tokens:{accounted_total:123}}}),'123 tokens');
  assert.equal(ctx.tokenUsageLabel({usage:{worker:{tokens:123}}},'worker'),'123 tokens');
  t.token_accounting.roles={planner:{reported:10,reserved:20,unclassified:100,accounted:130,consistent:false}};
  assert.equal(ctx.tokenUsageLabel(t,'planner'),'130 tokens');
});
test('untrusted metadata is escaped and pending requests are labeled honestly',()=>{
  const t=task(),r=t.token_accounting.requests[0];r.model='<script>';r.status='pending';r.prompt_bytes=null;
  const html=ctx.tokenReservationDetails(t);
  assert.doesNotMatch(html,/<script>/);assert.match(html,/&lt;script>/);assert.match(html,/awaiting usage/);
  assert.doesNotMatch(html,/85,430 bytes/);
});

test('session action headline is additive, formatted and identifies partial history',()=>{
  ctx.icon=()=>'';
  for(const [total,label] of [[0,'0 actions'],[1,'1 action'],[12345,'12,345 actions']]){
    const html=ctx.sessionJourney({metrics:{actions:{total,counts:{worker:total,reviewer:0,planner:0,coordinator:0,tools:0},coverage:'complete',details:'Counted once.'}},checks:[],checkpoints:[]});
    assert.ok(html.includes('This session · '+label));assert.ok(html.includes('Coordinator calls'));assert.ok(!html.includes(' · known'));
  }
  assert.ok(ctx.sessionJourney({metrics:{actions:{total:2,counts:{tools:2},coverage:'partial',details:'Older history incomplete'}}}).includes('2 actions · known'));
});

function overviewTask(overrides={}){
  ctx.CheapOSBranchUI=require('../dist/branch_ui.js');
  ctx.CheapOSGitWorkflow={merged:t=>t.merged===true};
  ctx.taskBusy=t=>['running','reviewing','waiting_approval'].includes(t.status);
  ctx.labels={approved:'Reviewer approved',running:'Working',reviewing:'Reviewing',paused:'Paused'};
  return {status:'approved',changes:[{path:'example.js'}],checks:[{passed:false},{passed:true}],checkpoints:[{decision:'APPROVE'}],...overrides};
}
test('session overview shows latest check outcome without treating historical failures as current',()=>{
  const html=ctx.sessionOverview(overviewTask());
  assert.match(html,/<dt>Latest check<\/dt><dd>Passed/);
  assert.doesNotMatch(html,/1\/2 passed/);
  assert.match(html,/<dt>Independent review<\/dt><dd>Approved/);
  assert.match(html,/id="session-changes">Review changes/);
  const failed=ctx.sessionOverview(overviewTask({checks:[{passed:true},{passed:false}]}));
  assert.match(failed,/<dt>Latest check<\/dt><dd>Failed/);
});
test('session overview does not advertise previous approval while new work or review is running',()=>{
  for(const [status,review] of [['running','Pending'],['reviewing','In progress']]){
    const html=ctx.sessionOverview(overviewTask({status,branch_run:{status:'running',readiness:{review:{decision:'APPROVE'}}}}));
    assert.match(html,new RegExp('<dt>Independent review</dt><dd>'+review));
    assert.match(html,/<dt>Changed files<\/dt><dd>1/);
    assert.match(html,/id="session-changes">View changes/);
  }
  assert.match(ctx.sessionOverview(overviewTask({merged:true,status:'completed'})),/id="session-changes">View changes/);
});
test('plain conversation has no empty review or check actions',()=>{
  const html=ctx.sessionOverview(overviewTask({status:'paused',changes:[],checks:[],checkpoints:[]}));
  assert.doesNotMatch(html,/id="session-changes"|id="session-tests"/);
  assert.match(html,/<dt>Independent review<\/dt><dd>Not requested/);
  assert.match(html,/session-status attention/);
});

test('session calls separate planning from connection checks without inflating actions',()=>{
  ctx.icon=()=>'';
  const html=ctx.sessionJourney({metrics:{actions:{total:141,counts:{planner:130,tools:11},coverage:'complete'},
    request_breakdown:{planner:{requests:22,probes:108,unclassified:0}}}});
  assert.match(html,/141 actions/);
  assert.match(html,/22 task requests · 108 connection checks/);
  assert.match(html,/<strong>130<\/strong>/);
  const partial=ctx.sessionJourney({metrics:{actions:{total:3,counts:{planner:3},coverage:'partial'},
    request_breakdown:{planner:{requests:1,probes:1,unclassified:1}}}});
  assert.match(partial,/1 unclassified/);
});
