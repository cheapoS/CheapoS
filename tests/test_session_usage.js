const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8');
const ctx={esc:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;')};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('function tokenUsageLabel('),source.indexOf('function renderInspector(')),ctx);
const task=()=>({id:'task',token_accounting:{reported:133422,reserved:99644,accounted:233066,coverage:'complete',
  requests:[{model:'fixture/model',role:'planner',purpose:'planning',status:'failed',error_code:'gateway_cooldown',
    prompt_tokens:86454,output_tokens:8192,tokens:94646,prompt_bytes:85430,buffer_tokens:1024}]}});
test('role rows show a total while accounting details retain reported and reserved evidence',()=>{
  const t=task();
  t.token_accounting.roles={planner:{reported:90699,reserved:49184,accounted:139883,consistent:true}};
  assert.equal(ctx.tokenUsageLabel(t,'planner'),'139,883 tokens');
  assert.equal(ctx.tokenUsageLabel(t),'133,422 reported + 99,644 reserved tokens');
  const html=ctx.tokenReservationDetails(t);
  assert.match(html,/133,422 reported · 99,644 reserved/);
  assert.match(html,/86,454 prompt estimate \+ 8,192 output estimate/);
  assert.match(html,/85,430 bytes \+ 1,024 buffer/);
  assert.match(html,/not confirmed consumption or money held/);
  assert.match(html,/data-event="token-reservations-task"/);
});
test('missing history is never presented as zero actual usage',()=>{
  const t=task();t.token_accounting.coverage='partial';t.token_accounting.unclassified=10;
  assert.match(ctx.tokenUsageLabel(t),/233,066 accounted tokens · breakdown partial/);
  assert.match(ctx.tokenReservationDetails(t),/10 unclassified/);
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
