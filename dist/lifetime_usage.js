/* Local installation statistics. No task state changes or provider calls. */
'use strict';
const CheapOSLifetimeUsage = (() => {
  const categories={public_free:'Public-free remote',local:'Local',included:'Included account access',paid:'Paid / metered',unknown:'Unknown access'};
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number=value=>Number.isFinite(value)?value.toLocaleString('en-US',{maximumFractionDigits:6}):'Unknown';
  const date=value=>value&&Number.isFinite(Date.parse(value))?new Date(value).toLocaleString(): 'Unknown';
  const money=value=>Number.isFinite(value)?'$'+value.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:8}):'Unknown';
  function safeSummary(data){
    // Whitelist fields so future endpoint additions cannot leak into exports.
    const numeric=(obj,keys)=>Object.fromEntries(keys.map(k=>[k,Number.isFinite(obj?.[k])?obj[k]:null]));
    const safeModels = typeof data.models === 'object' && data.models !== null
      ? Object.fromEntries(Object.entries(data.models).slice(0, 50).map(([k, v]) => [
          String(k).slice(0, 100),
          {tokens: Number.isFinite(v?.tokens) ? v.tokens : 0, requests: Number.isFinite(v?.requests) ? v.requests : 0, category: typeof v?.category === 'string' ? v.category : 'unknown'}
        ]))
      : {};
    return {schema_version:1,app_version:typeof data.app_version==='string'?data.app_version:'Unknown',scope:'Local installation',period:['7','30'].includes(String(data.period))?String(data.period):'all',recorded_since:data.recorded_since,updated_at:data.updated_at,partial_earlier_history:data.partial_earlier_history===true,history_truncated:data.history_truncated===true,
      tokens:numeric(data.tokens,['reported','accounted_historical','estimated','reserved','input','output','reasoning','cached','unknown_requests','unknown_reasoning_requests','unknown_cached_requests']),
      categories:Object.fromEntries(Object.keys(categories).map(k=>[k,numeric(data.categories?.[k],['tokens','requests'])])),
      roles:Object.fromEntries(['coordinator','planner','worker','reviewer','unknown'].map(k=>[k,numeric(data.roles?.[k],['tokens','requests'])])),
      models:safeModels,
      cost:numeric(data.cost,['provider_reported','configured_estimate','reserved','historical_accounted','accounted']),charged_free_requests:Number(data.charged_free_requests)||0,
      completion:numeric(data.completion,['human_accepted_jobs','merged_runs','independent_review_approved_jobs']),history:(data.history||[]).map(row=>({date:row.date,...numeric(row,['tokens','cost'])})),
      limitations:Array.isArray(data.limitations)?data.limitations.map(String):[],savings_comparison:'Savings comparison not configured',completion_definitions:'Human-accepted jobs and merged runs are separate outcomes; independent review is not human acceptance. Item commits are not additional jobs.',retention:'Deidentified usage totals remain after chat deletion. No prompts, paths, task titles or model output are retained in this export.',
      total_free_tokens:Number.isFinite(data.total_free_tokens)?data.total_free_tokens:((data.categories?.public_free?.tokens||0)+(data.categories?.included?.tokens||0)+(data.categories?.local?.tokens||0)),
      estimated_savings:Number.isFinite(data.estimated_savings)?data.estimated_savings:Math.round(((data.categories?.public_free?.tokens||0)+(data.categories?.included?.tokens||0)+(data.categories?.local?.tokens||0))*0.000003*100)/100,
      club:data.club && typeof data.club==='object'?{
        installation_id:data.club.installation_id,
        installation_name:data.club.installation_name,
        is_linked:Boolean(data.club.is_linked),
        sync_enabled:Boolean(data.club.sync_enabled),
        last_synced_at:data.club.last_synced_at,
        leaderboard_url:data.club.leaderboard_url,
        connect_url:data.club.connect_url,
        x_identity:data.club.x_identity?{
          handle:data.club.x_identity.handle,
          name:data.club.x_identity.name,
          avatar_url:data.club.x_identity.avatar_url
        }:null
      }:null
    };
  }
  function leaderboard(s){
    const zeroCostTokens=s.total_free_tokens||0;
    const zeroCostShare=s.tokens.reported>0?Math.round((zeroCostTokens/s.tokens.reported)*100):100;
    return JSON.stringify({
      schema_version:1,
      opt_in_purpose:'cheapos_community_savings_leaderboard',
      app_version:s.app_version,
      recorded_period:s.period==='all'?'all_time':s.period+'_days',
      metrics:{
        total_reported_tokens:s.tokens.reported,
        zero_cost_free_tokens:zeroCostTokens,
        zero_cost_percentage:zeroCostShare,
        paid_metered_tokens:s.categories.paid?.tokens||0,
        accounted_api_spend_usd:s.cost.accounted||0,
        estimated_commercial_savings_usd:s.estimated_savings!=null?s.estimated_savings:Math.round(zeroCostTokens*0.0003)/100
      },
      breakdown_tokens:{
        public_free_remote:s.categories.public_free?.tokens||0,
        account_included_quota:s.categories.included?.tokens||0,
        local_hardware:s.categories.local?.tokens||0
      },
      extended_profile:{
        models_used:s.models||{},
        roles:s.roles||{},
        recorded_since:s.recorded_since,
        completed_work:{
          human_accepted_jobs:s.completion.human_accepted_jobs,
          merged_runs:s.completion.merged_runs,
          review_approved_jobs:s.completion.independent_review_approved_jobs
        }
      },
      verified_at:s.updated_at
    },null,2);
  }
  function markdown(data){const s=safeSummary(data);return '# cheapoS · Usage & savings\n\n'+`Local installation · ${s.period==='all'?'All time':s.period+' days'} · app ${s.app_version}\nRecorded since ${s.recorded_since||'unknown'} · updated ${s.updated_at||'unknown'}${s.partial_earlier_history?' · partial earlier history':''}\n\n`+`Reported tokens: ${number(s.tokens.reported)}\nTotal zero-cost tokens: ${number(s.total_free_tokens)}\nHistorical accounted tokens: ${number(s.tokens.accounted_historical)}\nAccounted API cost: ${money(s.cost.accounted)}\nEstimated savings: ${money(s.estimated_savings)}\n\n`+Object.entries(s.categories).map(([k,v])=>`${categories[k]}: ${number(v.tokens)} tokens (${number(v.requests)} requests)`).join('\n')+'\n\n## Exact accounting and coverage\n\n```json\n'+JSON.stringify(s,null,2)+'\n```\n';}
  function render(data){const s=safeSummary(data),known=Object.values(s.categories).reduce((n,v)=>n+(v.tokens||0),0),free=s.categories.public_free.tokens,paid=s.categories.paid.tokens,denom=(free||0)+(paid||0);
    const zeroCostTokens=s.total_free_tokens||0;
    const zeroCostShare=s.tokens.reported>0?Math.round((zeroCostTokens/s.tokens.reported)*100):100;
    const estSavings=s.estimated_savings!=null?'$'+Number(s.estimated_savings).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}):money(zeroCostTokens*0.000003);
    const cards=[['Reported model tokens',s.tokens.reported],['Total zero-cost tokens',zeroCostTokens],['Public-free model tokens',free],['Paid-model tokens',paid]];
    const club=s.club||{},isLinked=Boolean(club.is_linked),isSyncing=Boolean(club.sync_enabled),op=club.x_identity||{},modelsEntries=Object.entries(s.models||{});

    let clubSection='';
    if(!isLinked){
      clubSection=`<section class="club-panel"><div class="club-card-content"><div class="club-badge-row"><span class="club-badge">Leaderboard</span><strong>Join the Cheapskate Club</strong></div><p>Connect your X account to claim your savings on the public scoreboard. You control what gets shared — no passwords or separate signups required.</p><div class="club-actions-row"><a class="primary-button club-btn" href="${escape(club.connect_url||'https://cheapskate.club/join')}" target="_blank" rel="noopener noreferrer">Connect X account →</a><button class="text-link" type="button" data-club-manual>Manual token link</button></div></div></section>`;
    }else if(!isSyncing){
      clubSection=`<section class="club-panel club-linked"><div class="club-card-content"><div class="club-profile-header">${op.avatar_url?`<img class="club-avatar" src="${escape(op.avatar_url)}" alt="">`:''}<div class="club-profile-text"><strong>${escape(op.name||op.handle)}</strong><span class="small muted">@${escape(op.handle)} · Linked to ${escape(club.installation_name||'this Mac')}</span></div></div><h3>Review stats before sharing</h3><p class="small muted">Only verified numerical token counters and model names will be published. Your prompts, code, and paths NEVER leave your computer.</p><div class="club-preview-figures"><div><span>Zero-Cost Tokens</span><strong>${number(zeroCostTokens)} (${zeroCostShare}%)</strong></div><div><span>Est. Savings</span><strong>${estSavings}</strong></div><div><span>API Spend</span><strong>${money(s.cost.accounted)}</strong></div></div>${modelsEntries.length?`<details class="club-models-preview"><summary>Extended Profile · Models used (${modelsEntries.length})</summary><table><thead><tr><th scope="col">Model</th><th scope="col">Tokens</th><th scope="col">Category</th></tr></thead><tbody>${modelsEntries.slice(0,8).map(([name,m])=>`<tr><th scope="row">${escape(name)}</th><td>${number(m.tokens)}</td><td>${escape(categories[m.category]||m.category)}</td></tr>`).join('')}</tbody></table></details>`:''}<div class="club-actions-row"><button class="primary-button" type="button" data-club-share>Share my stats</button><button class="outline-button" type="button" data-club-disconnect>Disconnect</button></div></div></section>`;
    }else{
      clubSection=`<section class="club-panel club-active"><div class="club-card-content"><div class="club-profile-header">${op.avatar_url?`<img class="club-avatar" src="${escape(op.avatar_url)}" alt="">`:''}<div class="club-profile-text"><span class="club-status-pill">🏆 Active on Leaderboard</span><strong>@${escape(op.handle)}</strong><span class="small muted">Last synced: ${club.last_synced_at?escape(date(club.last_synced_at)):'Just now'}</span></div></div><div class="club-actions-row"><a class="outline-button" href="${escape(club.leaderboard_url||'https://cheapskate.club')}/@${escape(op.handle)}" target="_blank" rel="noopener noreferrer">View public profile ↗</a><button class="outline-button" type="button" data-club-sync>Sync now</button><button class="outline-button" type="button" data-club-pause>Pause sharing</button><button class="text-link" type="button" data-club-disconnect>Disconnect this installation</button></div></div></section>`;
    }

    return `<p class="small muted">Recorded since ${escape(date(s.recorded_since))} ${s.partial_earlier_history?'· partial earlier history':''}<br>Updated ${escape(date(s.updated_at))} · ${s.period==='all'?'All time':s.period+' days (UTC)'}</p><div class="lifetime-figures">${cards.map(([label,value])=>`<div><span>${label}</span><strong>${number(value)}</strong></div>`).join('')}<div><span>Accounted API cost</span><strong>${money(s.cost.accounted)}</strong></div><div><span>Est. commercial savings</span><strong>${estSavings}</strong></div></div>
    <p>${denom?`${number(100*(free||0)/denom)}% of classified free-or-paid remote tokens used public-free models.`:'Free-model share is unavailable: no classified free-or-paid remote tokens.'} Local, included and unknown are excluded. Charged-free anomalies count as paid usage in this comparison.</p>
    <p class="savings-highlight"><strong>${zeroCostShare}% zero-cost compute:</strong> ${number(zeroCostTokens)} tokens consumed at $0 out-of-pocket API cost across public-free, account-included, and local models.</p>
    ${clubSection}
    <div class="lifetime-stack" aria-hidden="true">${Object.entries(s.categories).map(([k,v])=>`<span class="usage-${k}" style="flex:${known?(v.tokens||0)/known:0}"></span>`).join('')}</div><table><caption>Reported token access breakdown</caption><thead><tr><th scope="col">Access</th><th scope="col">Tokens</th><th scope="col">Requests</th></tr></thead><tbody>${Object.entries(s.categories).map(([k,v])=>`<tr><th scope="row">${categories[k]}</th><td>${number(v.tokens)}</td><td>${number(v.requests)}</td></tr>`).join('')}</tbody></table>
    <p>Unknown-usage requests: ${number(s.tokens.unknown_requests)} · Historical accounted tokens: ${number(s.tokens.accounted_historical)} · Charged-free requests: ${number(s.charged_free_requests)}. Missing usage is unknown, not zero.</p>
    <details><summary>Accounting details and roles</summary><p>Reported input ${number(s.tokens.input)} · output ${number(s.tokens.output)}. Reasoning ${number(s.tokens.reasoning)} and cached ${number(s.tokens.cached)} are reported subsets, not added again; missing subset coverage may be incomplete (reasoning: ${number(s.tokens.unknown_reasoning_requests)} requests; cached: ${number(s.tokens.unknown_cached_requests)} requests).</p><p>Estimated tokens ${number(s.tokens.estimated)} · outstanding reserved tokens ${number(s.tokens.reserved)}; both are separate from reported usage.</p><p>Provider-reported cost ${money(s.cost.provider_reported)} · configured-price estimate ${money(s.cost.configured_estimate)} · historical accounted cost ${money(s.cost.historical_accounted)} · outstanding reservation ${money(s.cost.reserved)}.</p><table><caption>Reported role usage</caption><tbody>${Object.entries(s.roles).map(([k,v])=>`<tr><th scope="row">${escape(k)}</th><td>${number(v.tokens)} tokens</td><td>${number(v.requests)} requests</td></tr>`).join('')}</tbody></table></details>
    <h3>Completed work</h3><p>Human-accepted jobs: ${number(s.completion.human_accepted_jobs)} · merged runs: ${number(s.completion.merged_runs)} · independently review-approved jobs: ${number(s.completion.independent_review_approved_jobs)}</p><p>${s.completion_definitions} Failed work still consumes tokens.</p>
    <details><summary>Daily recorded history (UTC)</summary><p>Only dated evidence is shown. Missing dates are gaps, not zero usage.${s.history_truncated?' Showing the latest 366 recorded dates; lifetime totals include older dates.':''}</p>${s.history.length?`<table><thead><tr><th scope="col">Date</th><th scope="col">Tokens</th><th scope="col">API cost</th></tr></thead><tbody>${s.history.map(r=>`<tr><th scope="row">${escape(r.date)}</th><td>${number(r.tokens)}</td><td>${money(r.cost)}</td></tr>`).join('')}</tbody></table>`:'<p>No dated usage is available for this period.</p>'}</details>
    <h3>Coverage and retention</h3><ul>${s.limitations.map(v=>`<li>${escape(v)}</li>`).join('')}</ul><p>Local usage excludes electricity and hardware costs. Included access may have subscription costs outside this accounting. This is installation usage, not your provider account’s entire activity.</p><p>${s.retention}</p><p><strong>Savings comparison not configured.</strong> Free tokens used are not tokens saved; retries and reviews also use tokens.</p>`;
  }
  function open({dialog,api,header}){
    const d=dialog(`${header('LOCAL INSTALLATION','Usage & savings')}<label>Period <select data-period><option value="all">All time</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option></select></label><div data-usage-body aria-live="polite"></div><button class="outline-button" data-export disabled>Export summary</button><section data-preview hidden><h3>Export preview</h3><p>Local download only. Nothing is uploaded or published.</p><label>Format <select data-format><option value="md">Markdown</option><option value="json">JSON</option><option value="leaderboard">Leaderboard Opt-In (JSON)</option></select></label><pre tabindex="0" data-export-text></pre><button class="primary-button" data-download>Download summary</button></section>`,'lifetime-modal');
    const q=s=>d.querySelector(s),body=q('[data-usage-body]');let request=0,current=null;
    function bindClubActions(){
      const shareBtn=q('[data-club-share]');if(shareBtn)shareBtn.onclick=async()=>{shareBtn.disabled=true;try{await api('/club/sync',{enabled:true});}catch{}await load();};
      const syncBtn=q('[data-club-sync]');if(syncBtn)syncBtn.onclick=async()=>{syncBtn.disabled=true;try{await api('/club/sync',{period:q('[data-period]').value});}catch{}await load();};
      const pauseBtn=q('[data-club-pause]');if(pauseBtn)pauseBtn.onclick=async()=>{pauseBtn.disabled=true;try{await api('/club/sync',{enabled:false});}catch{}await load();};
      const discBtn=q('[data-club-disconnect]');if(discBtn)discBtn.onclick=async()=>{discBtn.disabled=true;try{await api('/club/disconnect',{});}catch{}await load();};
      const manualBtn=q('[data-club-manual]');if(manualBtn)manualBtn.onclick=async()=>{const handle=prompt('Enter X handle (e.g. @yourname):');if(!handle)return;const sync_secret=prompt('Enter pairing sync secret:');if(!sync_secret)return;try{await api('/club/link',{handle,sync_secret});}catch(e){alert(e.message||'Link failed');}await load();};
    }
    async function load(){const seq=++request;current=null;q('[data-export]').disabled=true;q('[data-preview]').hidden=true;body.innerHTML='<p role="status">Loading usage…</p>';try{const data=await api('/lifetime-usage?days='+q('[data-period]').value);if(seq!==request||!d.isConnected)return;current=safeSummary(data);body.innerHTML=render(current);bindClubActions();q('[data-export]').disabled=false;}catch(e){if(seq!==request||!d.isConnected)return;body.innerHTML=(e.status===404?'<p role="alert">Usage &amp; savings will be available after a later app restart. Your current work can continue.</p>':'<p role="alert">Usage could not be loaded. Your chat is unchanged.</p>')+'<button class="outline-button" data-retry>Retry</button>';q('[data-retry]').onclick=load;}}
    const exported=()=>{const fmt=q('[data-format]').value;return fmt==='leaderboard'?leaderboard(current):fmt==='json'?JSON.stringify(current,null,2):markdown(current);};
    function preview(){q('[data-preview]').hidden=false;q('[data-export-text]').textContent=exported();}
    q('[data-period]').onchange=load;q('[data-export]').onclick=preview;q('[data-format]').onchange=preview;
    q('[data-download]').onclick=()=>{if(!current)return;const format=q('[data-format]').value,url=URL.createObjectURL(new Blob([exported()],{type:format==='md'?'text/markdown':'application/json'})),a=document.createElement('a');a.href=url;a.download='cheapoS-usage-summary.'+(format==='md'?'md':'json');a.click();setTimeout(()=>URL.revokeObjectURL(url),0);};
    d.addEventListener('close',()=>{request++;});load();return d;
  }
  return {render,safeSummary,markdown,open,leaderboard};
})();
if(typeof module!=='undefined')module.exports=CheapOSLifetimeUsage;
