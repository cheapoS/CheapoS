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
  assert.match(ui.render(unlinkedData), /Join the Cheapskate Club/);
  assert.match(ui.render(unlinkedData), /Connect X account/);

  const linkedData = fixture();
  linkedData.models = {'deepseek-chat': {tokens: 80, requests: 2, category: 'included'}};
  linkedData.club = {
    installation_id: 'inst-1', installation_name: 'Work Laptop',
    is_linked: true, sync_enabled: false,
    x_identity: {handle: 'carlosa8c', name: 'Carlos Cabrera'}
  };
  const linkedHtml = ui.render(linkedData);
  assert.match(linkedHtml, /@carlosa8c/);
  assert.match(linkedHtml, /Review stats before sharing/);
  assert.match(linkedHtml, /Share my stats/);
  assert.match(linkedHtml, /deepseek-chat/);

  const activeData = fixture();
  activeData.club = {
    installation_id: 'inst-1', is_linked: true, sync_enabled: true,
    x_identity: {handle: 'carlosa8c'}, last_synced_at: '2026-09-15T12:00:00Z'
  };
  const activeHtml = ui.render(activeData);
  assert.match(activeHtml, /Active on Leaderboard/);
  assert.match(activeHtml, /Sync now/);
  assert.match(activeHtml, /Pause sharing/);

  const exported = JSON.parse(ui.leaderboard(linkedData));
  assert.equal(exported.opt_in_purpose, 'cheapos_community_savings_leaderboard');
  assert.equal(exported.extended_profile.models_used['deepseek-chat'].tokens, 80);
});
