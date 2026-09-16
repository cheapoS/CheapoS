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
        pairing_pending:Boolean(data.club.pairing_pending),
        error:data.club.error,
        sync_message:data.club.sync_message,
        installation_id:data.club.installation_id,
        installation_name:data.club.installation_name,
        is_linked:Boolean(data.club.is_linked),
        sync_enabled:Boolean(data.club.sync_enabled),
        share_models:Boolean(data.club.share_models),
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
  function renderClub(club={}){
    const isLinked=Boolean(club.is_linked),isSyncing=Boolean(club.sync_enabled),op=club.x_identity||{};
    return `<section class="club-panel"><div class="club-card-content"><h3>The Cheapskate Club</h3>
      ${isLinked?`<p>Connected to <strong>@${escape(op.handle)}</strong>. One installation connects to one Club account at a time.</p><p>Sharing ${isSyncing?'enabled':'paused'} · Last confirmed upload: ${club.last_synced_at?escape(date(club.last_synced_at)):'None yet'}</p><p>Only new settled request counts, usage category, accounting date, and anonymous event/installation IDs are sent. No prompts, code, paths or provider keys. Existing usage stays with its original account when you disconnect.</p><label><input type="checkbox" data-club-models ${club.share_models?'checked':''}/> Share model names for my Club profile</label><button type="button" data-club-preferences>Save model preference</button><div class="club-actions-row">${isSyncing?'<button type="button" data-club-sync>Sync now</button><button type="button" data-club-pause>Pause sharing</button>':'<button type="button" data-club-share>Enable sharing for new usage</button>'}<button type="button" data-club-disconnect>Disconnect</button></div>`:`<p>Connect your Club account, then choose whether to share new usage. Your local work never depends on the Club.</p>${club.pairing_pending?'':'<button class="primary-button" type="button" data-club-connect>Connect to Club →</button>'}${club.pairing_pending?`<p><a href="${escape(club.connect_url)}" target="_blank" rel="noopener noreferrer">Approve connection in the Club ↗</a></p><button type="button" data-club-check>Check connection</button><p>Waiting for browser approval. This updates automatically.</p><button type="button" data-club-connect>Refresh approval link</button>`:''}`}
      ${club.sync_message?`<p role="status">${escape(club.sync_message)}</p>`:''}${club.error?`<p role="status">${escape(club.error)}</p>`:''}<p><a href="${escape(club.leaderboard_url||'https://cheapskate-club.vercel.app')}/account" target="_blank" rel="noopener noreferrer">My Club account ↗</a></p><p data-club-error role="alert"></p></div></section>`;
  }
  function render(data){const s=safeSummary(data),known=Object.values(s.categories).reduce((n,v)=>n+(v.tokens||0),0),free=s.categories.public_free.tokens,paid=s.categories.paid.tokens,denom=(free||0)+(paid||0);
    const zeroCostTokens=s.total_free_tokens||0;
    const zeroCostShare=s.tokens.reported>0?Math.round((zeroCostTokens/s.tokens.reported)*100):100;
    const estSavings=s.estimated_savings!=null?'$'+Number(s.estimated_savings).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}):money(zeroCostTokens*0.000003);
    const cards=[
      ['Reported model tokens',s.tokens.reported,'tokens'],
      ['Total zero-cost tokens',zeroCostTokens,'zero-cost'],
      ['Public-free model tokens',free,'public-free'],
      ['Paid-model tokens',paid,'paid'],
      ['Accounted API cost',s.cost.accounted,'cost'],
      ['Est. commercial savings',s.estimated_savings,'savings']
    ];
    const club=s.club||{},isLinked=Boolean(club.is_linked),isSyncing=Boolean(club.sync_enabled),op=club.x_identity||{},modelsEntries=Object.entries(s.models||{});
    const clubSection=renderClub(s.club||{});

    return `
    <!-- TAB 1: OVERVIEW & SAVINGS -->
    <div class="usage-tab-panel" data-tab-panel="overview">
      <div class="usage-meta-bar">
        <span>Recorded since <strong>${escape(date(s.recorded_since))}</strong> ${s.partial_earlier_history?'· <span class="history-badge">partial earlier history</span>':''}</span>
        <span>Updated <strong>${escape(date(s.updated_at))}</strong> · <strong>${s.period==='all'?'All time':s.period+' days (UTC)'}</strong></span>
      </div>

      <div class="lifetime-figures">
        <div class="figure-card">
          <span class="figure-label">Reported model tokens</span>
          <strong class="figure-val">${number(s.tokens.reported)}</strong>
          <span class="figure-sub">Total recorded compute</span>
        </div>
        <div class="figure-card highlight-zero">
          <div class="figure-label-row">
            <span class="figure-label">Total zero-cost tokens</span>
            <span class="pill-badge mint">${zeroCostShare}% Free</span>
          </div>
          <strong class="figure-val text-mint">${number(zeroCostTokens)}</strong>
          <span class="figure-sub">Public, local &amp; included</span>
        </div>
        <div class="figure-card">
          <div class="figure-label-row">
            <span class="figure-label">Public-free model tokens</span>
            <span class="pill-badge">Free</span>
          </div>
          <strong class="figure-val">${number(free)}</strong>
          <span class="figure-sub">Public gateway pool</span>
        </div>
        <div class="figure-card">
          <div class="figure-label-row">
            <span class="figure-label">Paid-model tokens</span>
            <span class="pill-badge amber">Metered</span>
          </div>
          <strong class="figure-val">${number(paid)}</strong>
          <span class="figure-sub">Metered API usage</span>
        </div>
        <div class="figure-card">
          <span class="figure-label">Accounted API cost</span>
          <strong class="figure-val">${money(s.cost.accounted)}</strong>
          <span class="figure-sub">Direct provider spend</span>
        </div>
        <div class="figure-card highlight-savings">
          <span class="figure-label">Est. commercial savings</span>
          <strong class="figure-val text-savings">${estSavings}</strong>
          <span class="figure-sub">Vs standard commercial rates</span>
        </div>
      </div>

      <div class="savings-highlight-card">
        <div class="savings-highlight-badge">⚡ ${zeroCostShare}% zero-cost compute</div>
        <p class="savings-highlight-main"><strong>${number(zeroCostTokens)} tokens</strong> consumed at $0 out-of-pocket API cost across public-free, account-included, and local models.</p>
        <p class="savings-highlight-note">${denom?`${number(100*(free||0)/denom)}% of classified free-or-paid remote tokens used public-free models.`:'Free-model share is unavailable: no classified free-or-paid remote tokens.'} Local, included and unknown are excluded. Charged-free anomalies count as paid usage in this comparison.</p>
      </div>

      <div class="lifetime-stack-wrapper">
        <div class="stack-header">
          <h4>Compute distribution</h4>
          <span class="small muted">Categorized token share</span>
        </div>
        <div class="lifetime-stack" aria-hidden="true">${Object.entries(s.categories).map(([k,v])=>`<span class="usage-${k}" style="flex:${known?(v.tokens||0)/known:0}" title="${categories[k]}: ${number(v.tokens)} tokens"></span>`).join('')}</div>
        <div class="stack-legend">${Object.entries(s.categories).map(([k,v])=>`
          <div class="stack-legend-item">
            <span class="legend-dot usage-${k}"></span>
            <span class="legend-label">${categories[k]}</span>
            <span class="legend-pct">${known?Math.round(((v.tokens||0)/known)*100):0}%</span>
          </div>`).join('')}
        </div>
      </div>

      <div class="completed-work-card">
        <h4>Completed work outcomes</h4>
        <div class="completed-work-grid">
          <div class="work-stat">
            <span>🧑‍💻 Human-accepted jobs</span>
            <strong>${number(s.completion.human_accepted_jobs)}</strong>
          </div>
          <div class="work-stat">
            <span>🔀 Merged runs</span>
            <strong>${number(s.completion.merged_runs)}</strong>
          </div>
          <div class="work-stat">
            <span>🛡️ Review-approved jobs</span>
            <strong>${number(s.completion.independent_review_approved_jobs)}</strong>
          </div>
        </div>
        <p class="small muted">${s.completion_definitions} Failed work still consumes tokens.</p>
      </div>
    </div>

    <!-- TAB 2: BREAKDOWN & HISTORY -->
    <div class="usage-tab-panel" data-tab-panel="breakdown" hidden>
      <div class="breakdown-section">
        <h4>Reported token access breakdown</h4>
        <table class="usage-table">
          <thead>
            <tr>
              <th scope="col">Access category</th>
              <th scope="col" style="text-align:right">Tokens</th>
              <th scope="col" style="text-align:right">Requests</th>
              <th scope="col" style="text-align:right">Share</th>
            </tr>
          </thead>
          <tbody>
            ${Object.entries(s.categories).map(([k,v])=>`
              <tr>
                <th scope="row">
                  <span class="legend-dot usage-${k}" style="display:inline-block;vertical-align:middle;margin-right:6px"></span>
                  ${categories[k]}
                </th>
                <td style="text-align:right">${number(v.tokens)}</td>
                <td style="text-align:right">${number(v.requests)}</td>
                <td style="text-align:right">${known?Math.round(((v.tokens||0)/known)*100):0}%</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
        <p class="small muted" style="margin-top:10px">Unknown-usage requests: ${number(s.tokens.unknown_requests)} · Historical accounted tokens: ${number(s.tokens.accounted_historical)} · Charged-free requests: ${number(s.charged_free_requests)}. Missing usage is unknown, not zero.</p>
      </div>

      <details class="advanced" open>
        <summary>Accounting details and roles</summary>
        <p>Reported input ${number(s.tokens.input)} · output ${number(s.tokens.output)}. Reasoning ${number(s.tokens.reasoning)} and cached ${number(s.tokens.cached)} are reported subsets, not added again; missing subset coverage may be incomplete (reasoning: ${number(s.tokens.unknown_reasoning_requests)} requests; cached: ${number(s.tokens.unknown_cached_requests)} requests).</p>
        <p>Estimated tokens ${number(s.tokens.estimated)} · outstanding reserved tokens ${number(s.tokens.reserved)}; both are separate from reported usage.</p>
        <p>Provider-reported cost ${money(s.cost.provider_reported)} · configured-price estimate ${money(s.cost.configured_estimate)} · historical accounted cost ${money(s.cost.historical_accounted)} · outstanding reservation ${money(s.cost.reserved)}.</p>
        <table class="usage-table" style="margin-top:12px">
          <caption>Reported role usage</caption>
          <thead>
            <tr>
              <th scope="col">Role</th>
              <th scope="col" style="text-align:right">Tokens</th>
              <th scope="col" style="text-align:right">Requests</th>
            </tr>
          </thead>
          <tbody>
            ${Object.entries(s.roles).map(([k,v])=>`<tr><th scope="row">${escape(k)}</th><td style="text-align:right">${number(v.tokens)} tokens</td><td style="text-align:right">${number(v.requests)} requests</td></tr>`).join('')}
          </tbody>
        </table>
      </details>

      <details class="advanced" open>
        <summary>Daily recorded history (UTC)</summary>
        <p>Only dated evidence is shown. Missing dates are gaps, not zero usage.${s.history_truncated?' Showing the latest 366 recorded dates; lifetime totals include older dates.':''}</p>
        ${s.history.length?`<div class="table-scroll-container"><table class="usage-table"><thead><tr><th scope="col">Date</th><th scope="col" style="text-align:right">Tokens</th><th scope="col" style="text-align:right">API cost</th></tr></thead><tbody>${s.history.map(r=>`<tr><th scope="row">${escape(r.date)}</th><td style="text-align:right">${number(r.tokens)}</td><td style="text-align:right">${money(r.cost)}</td></tr>`).join('')}</tbody></table></div>`:'<p>No dated usage is available for this period.</p>'}
      </details>

      <div class="coverage-card">
        <h4>Coverage and retention</h4>
        <ul>${s.limitations.map(v=>`<li>${escape(v)}</li>`).join('')}</ul>
        <p>Local usage excludes electricity and hardware costs. Included access may have subscription costs outside this accounting. This is installation usage, not your provider account’s entire activity.</p>
        <p>${s.retention}</p>
        <p><strong>Savings comparison not configured.</strong> Free tokens used are not tokens saved; retries and reviews also use tokens.</p>
      </div>
    </div>

    <!-- TAB 3: CHEAPSKATE CLUB -->
    <div class="usage-tab-panel" data-tab-panel="club" hidden>
      ${clubSection}
    </div>`;
  }
  function open({dialog,api,header}){
    const d=dialog(`${header('LOCAL INSTALLATION','Usage & savings')}
    <div class="lifetime-top-bar">
      <div class="settings-tabs usage-tabs" role="tablist">
        <button type="button" class="settings-tab-btn active" data-tab="overview" role="tab" aria-selected="true">
          <span>📊 Overview &amp; Savings</span>
        </button>
        <button type="button" class="settings-tab-btn" data-tab="breakdown" role="tab" aria-selected="false">
          <span>📋 Breakdown &amp; History</span>
        </button>
        <button type="button" class="settings-tab-btn" data-tab="club" role="tab" aria-selected="false">
          <span>🏆 Cheapskate Club</span>
        </button>
        <button type="button" class="settings-tab-btn" data-tab="export" role="tab" aria-selected="false">
          <span>💾 Export</span>
        </button>
      </div>
      <div class="lifetime-period-wrapper">
        <label>Period <select data-period>
          <option value="all">All time</option>
          <option value="7">Last 7 days</option>
          <option value="30">Last 30 days</option>
        </select></label>
      </div>
    </div>
    <div data-usage-body aria-live="polite"></div>
    <section class="usage-export-section" data-tab-panel="export" hidden>
      <div class="export-banner">
        <div>
          <h3>Export summary</h3>
          <p>Local download only. Nothing is uploaded or published.</p>
        </div>
        <button class="outline-button" data-export disabled>Refresh export</button>
      </div>
      <section data-preview hidden>
        <div class="export-controls-bar">
          <label>Format <select data-format>
            <option value="md">Markdown</option>
            <option value="json">JSON</option>
            <option value="leaderboard">Leaderboard Opt-In (JSON)</option>
          </select></label>
          <button class="primary-button" data-download>Download summary</button>
        </div>
        <pre tabindex="0" data-export-text></pre>
      </section>
    </section>`,'lifetime-modal');

    const q=s=>d.querySelector(s),body=q('[data-usage-body]');let request=0,current=null,pairTimer=null,pairChecking=false,closed=false,activeTab='overview';
    const $$=(sel,el=d)=>(typeof el.querySelectorAll==='function'?Array.from(el.querySelectorAll(sel)):[]);

    function switchTab(tabName){
      activeTab=tabName;
      $$('.usage-tabs .settings-tab-btn',d).forEach(btn=>{
        const active=btn.dataset.tab===tabName;
        btn.classList.toggle('active',active);
        btn.setAttribute('aria-selected',String(active));
      });
      $$('.usage-tab-panel',body).forEach(panel=>{
        panel.hidden=panel.dataset.tabPanel!==tabName;
      });
      const exportPanel=q('[data-tab-panel="export"]');
      if(exportPanel)exportPanel.hidden=tabName!=='export';
      if(body)body.hidden=tabName==='export';
      if(tabName==='export'&&current){
        preview();
      }
    }

    $$('.usage-tabs .settings-tab-btn',d).forEach(btn=>{
      btn.onclick=()=>switchTab(btn.dataset.tab);
    });

    async function checkPending(){if(closed||pairChecking||!d.isConnected||!current?.club?.pairing_pending)return;pairChecking=true;try{const status=await api('/club/check',{});if(status.is_linked)updateClub(status);}catch(error){const output=q('[data-club-error]');if(output)output.textContent=error.message||'Unable to check approval; retry shortly.';}finally{pairChecking=false;schedulePairCheck();}}
    function schedulePairCheck(){clearTimeout(pairTimer);if(!closed&&d.isConnected&&current?.club?.pairing_pending)pairTimer=setTimeout(checkPending,3000);}

    function updateClub(status){
      if(closed||!d.isConnected||!current)return;
      current.club=safeSummary({...current,club:status}).club;
      const scroll=d.scrollTop,panel=q('.club-panel');
      if(panel)panel.outerHTML=renderClub(current.club||{});
      bindClubActions();schedulePairCheck();
      d.scrollTop=scroll;
    }
    function bindClubActions(){
      const actions=[['connect','/club/pair',{}],['check','/club/check',{}],['share','/club/sync',{enabled:true}],['sync','/club/sync',{}],['pause','/club/sync',{enabled:false}],['disconnect','/club/disconnect',{}],['preferences','/club/sync',{}]];
      for(const [name,path,values] of actions){const button=q('[data-club-'+name+']');if(button)button.onclick=async()=>{const label=button.textContent;button.disabled=true;if(name==='sync')button.textContent='Syncing…';try{const payload=['preferences','share'].includes(name)?{enabled:name==='share'||Boolean(current.club.sync_enabled),share_models:Boolean(q('[data-club-models]')?.checked)}:values;let status=await api(path,payload);if(status.is_linked===undefined)status=await api('/club/status');updateClub(status);}catch(error){if(closed||!d.isConnected)return;q('[data-club-error]').textContent=error.message||'Club request failed. Local work is unaffected.';button.disabled=false;button.textContent=label;}};}
    }

    async function load(){
      const seq=++request;current=null;
      const expBtn=q('[data-export]');if(expBtn)expBtn.disabled=true;
      const prevSec=q('[data-preview]');if(prevSec)prevSec.hidden=true;
      body.innerHTML='<p role="status">Loading usage…</p>';
      try{
        const data=await api('/lifetime-usage?days='+q('[data-period]').value);
        if(seq!==request||!d.isConnected)return;
        current=safeSummary(data);
        body.innerHTML=render(current);
        switchTab(activeTab);
        bindClubActions();
        schedulePairCheck();
        if(expBtn)expBtn.disabled=false;
      }catch(e){
        if(seq!==request||!d.isConnected)return;
        body.innerHTML=(e.status===404?'<p role="alert">Usage &amp; savings will be available after a later app restart. Your current work can continue.</p>':'<p role="alert">Usage could not be loaded. Your chat is unchanged.</p>')+'<button class="outline-button" data-retry>Retry</button>';
        const retry=q('[data-retry]');if(retry)retry.onclick=load;
      }
    }
    const exported=()=>{if(!current)return '';const fmt=q('[data-format]').value;return fmt==='leaderboard'?leaderboard(current):fmt==='json'?JSON.stringify(current,null,2):markdown(current);};
    function preview(){const p=q('[data-preview]');if(p)p.hidden=false;const t=q('[data-export-text]');if(t)t.textContent=exported();}
    q('[data-period]').onchange=load;
    const exp=q('[data-export]');if(exp)exp.onclick=preview;
    const fmt=q('[data-format]');if(fmt)fmt.onchange=preview;
    const dl=q('[data-download]');
    if(dl)dl.onclick=()=>{if(!current)return;const format=q('[data-format]').value,url=URL.createObjectURL(new Blob([exported()],{type:format==='md'?'text/markdown':'application/json'})),a=document.createElement('a');a.href=url;a.download='cheapoS-usage-summary.'+(format==='md'?'md':'json');a.click();setTimeout(()=>URL.revokeObjectURL(url),0);};
    d.addEventListener('close',()=>{closed=true;request++;clearTimeout(pairTimer);});
    load();
    return d;
  }
  return {render,safeSummary,markdown,open,leaderboard};
})();
if(typeof module!=='undefined')module.exports=CheapOSLifetimeUsage;
