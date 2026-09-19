'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),ui=require('../dist/lifetime_usage.js');
const fixture=()=>({period:'all',recorded_since:'2026-09-14',updated_at:'2026-09-14',partial_earlier_history:true,tokens:{reported:100,input:60,output:40,accounted_historical:20,estimated:4,reserved:5,reasoning:10,cached:8,unknown_requests:1},categories:{public_free:{tokens:60,requests:2},paid:{tokens:20,requests:1},local:{tokens:10,requests:1},included:{tokens:5,requests:1},unknown:{tokens:5,requests:1}},cost:{accounted:.0003,provider_reported:.0002,configured_estimate:.0001,reserved:.01,historical_accounted:0},roles:{worker:{tokens:80,requests:3}},completion:{human_accepted_jobs:1,merged_runs:1,independent_review_approved_jobs:2},history:[{date:'2026-09-14',tokens:100,cost:.0003}],limitations:['Earlier history is partial.'],charged_free_requests:1});
test('summary distinguishes categories, subcent cost, coverage and honest share',()=>{const html=ui.render(fixture());assert.match(html,/75% of classified free-or-paid remote tokens/);assert.match(html,/\$0.0003/);assert.match(html,/partial earlier history/);assert.match(html,/Unknown access/);assert.match(html,/Historical accounted tokens: 20/);assert.match(html,/Savings comparison not configured/);assert.match(html,/not tokens saved/);});
test('export excludes private fields and preserves reported/reserved separation',()=>{const data=fixture();data.prompt='SECRET';data.project_path='/SECRET';data.categories.paid.model_output='SECRET';data.history[0].task_title='SECRET';const out=JSON.stringify(ui.safeSummary(data));assert.doesNotMatch(out,/SECRET/);assert.equal(JSON.parse(out).tokens.reported,100);assert.equal(JSON.parse(out).tokens.reserved,5);assert.match(ui.markdown(data),/Reported tokens: 100/);assert.match(ui.markdown(data),/completion_definitions/);});
test('missing data remains unknown and untrusted labels escape markup',()=>{const data={limitations:['<script>']};const html=ui.render(data);assert.match(html,/Unknown/);assert.match(html,/share is unavailable/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);});
function controls(){const nodes=new Map();const q=s=>{if(!nodes.has(s))nodes.set(s,{value:s==='[data-period]'?'all':'md',innerHTML:'',textContent:'',hidden:false,disabled:false});return nodes.get(s);};const listeners={};const d={querySelector:q,isConnected:true,addEventListener:(name,fn)=>listeners[name]=fn};return {d,q,listeners};}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
test('open is immediately pending; filters reject stale replies and close leaves chat untouched',async()=>{const c=controls(),pending=[],chat={id:'selected',draft:'keep my draft',scroll:72};let shell='';ui.open({dialog:html=>(shell=html,c.d),header:()=>'',api:path=>new Promise(resolve=>pending.push({path,resolve}))});assert.match(shell,/All time/);assert.match(c.q('[data-usage-body]').innerHTML,/Loading usage/);assert.equal(c.q('[data-export]').disabled,true);c.q('[data-period]').value='7';c.q('[data-period]').onchange();pending[0].resolve(fixture());await tick();assert.match(c.q('[data-usage-body]').innerHTML,/Loading usage/);const data=fixture();data.period='7';pending[1].resolve(data);await tick();assert.match(c.q('[data-usage-body]').innerHTML,/7 days \(UTC\)/);c.q('[data-export]').onclick();assert.equal(c.q('[data-preview]').hidden,false);assert.match(c.q('[data-export-text]').textContent,/Reported tokens: 100/);c.listeners.close();assert.deepEqual(chat,{id:'selected',draft:'keep my draft',scroll:72});assert.equal(pending[1].path,'/lifetime-usage?days=7');});
test('failure offers retry, no raw server error, and successful retry enables export',async()=>{const c=controls();let count=0;ui.open({dialog:()=>c.d,header:()=>'',api:async()=>{if(!count++)throw Error('SECRET path');return fixture();}});await tick();assert.match(c.q('[data-usage-body]').innerHTML,/Retry/);assert.doesNotMatch(c.q('[data-usage-body]').innerHTML,/SECRET/);await c.q('[data-retry]').onclick();assert.equal(c.q('[data-export]').disabled,false);});
test('club renders unlinked, preview, and active states with extended models',async()=>{
  const unlinkedData = fixture();
  assert.match(ui.render(unlinkedData), /The Cheapskate Club/);
  assert.match(ui.render(unlinkedData), /Connect to Club/);

  const linkedData = fixture();
  linkedData.models = {'deepseek-chat': {tokens: 80, requests: 2, category: 'included'}};
  linkedData.club = {
    installation_id: 'inst-1', installation_name: 'Work Laptop',
    is_linked: true, sync_enabled: false,
    x_identity: {handle: 'carlosa8c', name: 'Carlos Cabrera'}
  };
  const linkedHtml = ui.render(linkedData);
  assert.match(linkedHtml, /@carlosa8c/);
  assert.match(linkedHtml, /Only new settled request counts/);
  assert.match(linkedHtml, /Enable sharing for new usage/);
  assert.doesNotMatch(linkedHtml, /verified numerical/);
  assert.match(linkedHtml, /No prompts, code, paths or provider keys/);

  const activeData = fixture();
  activeData.club = {
    installation_id: 'inst-1', is_linked: true, sync_enabled: true,
    x_identity: {handle: 'carlosa8c'}, last_synced_at: '2026-09-15T12:00:00Z'
  };
  const activeHtml = ui.render(activeData);
  assert.match(activeHtml, /Sharing enabled/);
  assert.match(activeHtml, /Sync now/);
  assert.match(activeHtml, /Pause sharing/);

  const exported = JSON.parse(ui.leaderboard(linkedData));
  assert.equal(exported.opt_in_purpose, 'cheapos_community_savings_leaderboard');
  assert.equal(exported.extended_profile.models_used['deepseek-chat'].tokens, 80);
});

test('sync updates only Club panel without collapsing usage or export preview',async()=>{
 const c=controls(),calls=[];let finish;
 const data=fixture();data.club={is_linked:true,sync_enabled:true,x_identity:{handle:'alice'}};
 ui.open({dialog:()=>c.d,header:()=>'',api:async(path)=>{calls.push(path);if(path==='/club/sync')return new Promise(resolve=>finish=resolve);return data;}});
 await tick();const content=c.q('[data-usage-body]').innerHTML;
 c.d.scrollTop=210;c.q('[data-export]').onclick();
 const click=c.q('[data-club-sync]').onclick();
 assert.equal(c.q('[data-club-sync]').textContent,'Syncing…');
 assert.equal(c.q('[data-usage-body]').innerHTML,content);
 finish({...data.club,sync_message:'Up to date.'});await click;
 assert.equal(c.q('[data-usage-body]').innerHTML,content);
 assert.match(c.q('.club-panel').outerHTML,/Up to date/);
 assert.equal(c.d.scrollTop,210);assert.equal(c.q('[data-preview]').hidden,false);
 assert.deepEqual(calls,['/lifetime-usage?days=all','/club/sync']);
});

test('model preference checkbox saves and updates state',async()=>{
  const c=controls(),calls=[];
  const data=fixture();data.club={is_linked:true,sync_enabled:true,share_models:false,x_identity:{handle:'alice'}};
  ui.open({dialog:()=>c.d,header:()=>'',api:async(path,payload)=>{calls.push({path,payload});if(path==='/club/sync')return {...data.club,share_models:payload?.share_models??true};return data;}});
  await tick();
  c.q('[data-club-models]').checked=true;
  await c.q('[data-club-models]').onchange();
  assert.equal(calls.length,2);
  assert.equal(calls[1].path,'/club/sync');
  assert.equal(calls[1].payload.share_models,true);
  assert.equal(calls[1].payload.enabled,true);
});

test('sidebar zero-cost tokens card formats lifetime percentage and token count',()=>{
  const data=fixture();
  data.tokens.reported=123802941;
  data.total_free_tokens=118357086;
  const s=ui.safeSummary(data);
  const zeroCostTokens=s.total_free_tokens;
  const zeroCostShare=Math.round((zeroCostTokens/s.tokens.reported)*100);
  assert.equal(zeroCostShare,96);
  assert.equal(zeroCostTokens.toLocaleString('en-US'),'118,357,086');
});

test('reconciliation switches between local installation and remote club scoreboard',()=>{
  const data=fixture();
  data.tokens.reported=154800000;
  data.club={
    is_linked:true,
    sync_enabled:true,
    x_identity:{handle:'cheaposnumero1',name:'Free token lover'},
    remote_profile:{
      handle:'cheaposnumero1',
      display_name:'Free token lover 0909',
      tokens:80191727,
      categories:{local:232499,included:1601645,public_free:78357583},
      share_models:true,
      models:[{name:'gemini-3.1-flash-lite',tokens:26295820}],
      roles:[{name:'worker',tokens:32486200},{name:'reviewer',tokens:1671606}],
      work_outcomes:{completed_tasks:72,human_accepted_jobs:12,merged_runs:60,review_approved_jobs:79,acceptance_rate:91.1}
    }
  };
  const s=ui.safeSummary(data);
  assert.equal(s.club.remote_profile.work_outcomes.completed_tasks,72);
  assert.equal(s.club.remote_profile.work_outcomes.acceptance_rate,91.1);

  const localHtml=ui.render(data,'local');
  assert.match(localHtml,/154,800,000/);
  assert.doesNotMatch(localHtml,/Club Scoreboard/);

  const remoteHtml=ui.render(data,'remote');
  assert.match(remoteHtml,/80,191,727/);
  assert.match(remoteHtml,/Club Scoreboard/);
  assert.match(remoteHtml,/gemini-3.1-flash-lite/);
  assert.match(remoteHtml,/worker/);
  assert.match(remoteHtml,/cheaposnumero1/);
  assert.match(remoteHtml,/cheapos\.lol/);
  assert.match(remoteHtml,/Completed tasks/);
  assert.match(remoteHtml,/72/);
  assert.match(remoteHtml,/91\.1%/);
  assert.match(remoteHtml,/Apply view to sidebar/);
});
