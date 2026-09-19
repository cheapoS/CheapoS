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
        }:null,
        remote_profile:data.club.remote_profile && typeof data.club.remote_profile==='object'?{
          handle:String(data.club.remote_profile.handle||''),
          display_name:String(data.club.remote_profile.display_name||''),
          tokens:Number(data.club.remote_profile.tokens)||0,
          categories:typeof data.club.remote_profile.categories==='object'&&data.club.remote_profile.categories!==null?data.club.remote_profile.categories:{},
          share_models:Boolean(data.club.remote_profile.share_models),
          models:Array.isArray(data.club.remote_profile.models)?data.club.remote_profile.models:[],
          roles:Array.isArray(data.club.remote_profile.roles)?data.club.remote_profile.roles:[],
          work_outcomes:data.club.remote_profile.work_outcomes&&typeof data.club.remote_profile.work_outcomes==='object'?{
            completed_tasks:Number.isFinite(data.club.remote_profile.work_outcomes.completed_tasks)?data.club.remote_profile.work_outcomes.completed_tasks:null,
            human_accepted_jobs:Number.isFinite(data.club.remote_profile.work_outcomes.human_accepted_jobs)?data.club.remote_profile.work_outcomes.human_accepted_jobs:null,
            merged_runs:Number.isFinite(data.club.remote_profile.work_outcomes.merged_runs)?data.club.remote_profile.work_outcomes.merged_runs:null,
            review_approved_jobs:Number.isFinite(data.club.remote_profile.work_outcomes.review_approved_jobs)?data.club.remote_profile.work_outcomes.review_approved_jobs:null,
            acceptance_rate:Number.isFinite(data.club.remote_profile.work_outcomes.acceptance_rate)?data.club.remote_profile.work_outcomes.acceptance_rate:null
          }:null
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
  function renderClub(club={}, viewMode='local'){
    const isLinked=Boolean(club.is_linked),isSyncing=Boolean(club.sync_enabled),op=club.x_identity||{},rp=club.remote_profile;
    return `<section class="club-panel"><div class="club-card-content"><h3>The Cheapskate Club</h3>
      ${isLinked?`<p>Connected to <strong>@${escape(op.handle)}</strong>. One installation connects to one Club account at a time.</p><p>Sharing ${isSyncing?'enabled':'paused'} · Last confirmed upload: ${club.last_synced_at?escape(date(club.last_synced_at)):'None yet'}</p><p>Only new settled request counts, usage category, accounting date, and anonymous event/installation IDs are sent. No prompts, code, paths or provider keys. Existing usage stays with its original account when you disconnect.</p><div class="club-pref-row"><label><input type="checkbox" data-club-models ${club.share_models?'checked':''}/> Share model names for my Club profile</label><button type="button" data-club-preferences>Save model preference</button><span class="club-pref-feedback" data-club-pref-feedback aria-live="polite"></span></div><div class="club-actions-row">${isSyncing?'<button type="button" data-club-sync>Sync now</button><button type="button" data-club-pause>Pause sharing</button>':'<button type="button" data-club-share>Enable sharing for new usage</button>'}<button type="button" data-club-disconnect>Disconnect</button></div>
      ${rp?`<div class="club-reconcile-settings-box"><h4>Usage View Reconciliation</h4><p>Choose whether cheapoS displays machine-local activity or reconciles with your official Cheapskate Club scoreboard.</p><div class="club-view-options"><label><input type="radio" name="club_usage_view_pref" value="local" ${viewMode==='local'?'checked':''}/> <strong>Local installation</strong> (Machine-local activity)</label><label><input type="radio" name="club_usage_view_pref" value="remote" ${viewMode==='remote'?'checked':''}/> <strong>Club scoreboard</strong> (Reconciled with @${escape(rp.handle)}: ${number(rp.tokens)} zero-cost tokens)</label></div><div class="club-reconcile-actions"><button type="button" class="club-apply-btn primary-button" data-apply-view>Apply view to sidebar</button><span class="small" data-apply-status style="color:var(--mint);font-size:0.8125rem;display:none;">✓ Applied to sidebar</span></div></div>`:''}`:`<p>Connect your Club account, then choose whether to share new usage. Your local work never depends on the Club.</p>${club.pairing_pending?'':'<button class="primary-button" type="button" data-club-connect>Connect to Club →</button>'}${club.pairing_pending?`<div class="club-pairing-prompt" style="margin-top:12px;padding:14px;background:rgba(59,130,246,0.08);border:1px solid rgba(59,130,246,0.28);border-radius:8px;"><p style="margin:0 0 8px;font-weight:600;color:var(--text-primary);font-size:0.9375rem;">👉 Step 2: Finish connection on cheapos.lol</p><p style="margin:0 0 12px;font-size:0.875rem;color:var(--text-secondary);line-height:1.4;">Your local session is ready! Click the button below to open <strong>cheapos.lol</strong> in your browser and approve this device:</p><div style="display:flex;flex-direction:column;gap:10px;"><a href="${escape(club.connect_url)}" target="_blank" rel="noopener noreferrer" class="primary-button" style="display:inline-flex;align-items:center;justify-content:center;text-decoration:none;padding:10px 16px;font-weight:600;text-align:center;">Finish connection on cheapos.lol ↗</a><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;"><button type="button" data-club-check>Check connection</button><button type="button" data-club-connect>Refresh approval link</button><span class="small" style="color:var(--text-muted);font-size:0.8125rem;">Waiting for browser approval. Updates automatically.</span></div></div></div>`:''}`}
      ${club.sync_message?`<p role="status">${escape(club.sync_message)}</p>`:''}${club.error?`<p role="status">${escape(club.error)}</p>`:''}<p><a href="${escape(club.leaderboard_url||'https://cheapos.lol')}/account" target="_blank" rel="noopener noreferrer">My Club account ↗</a></p><p data-club-error role="alert"></p></div></section>`;
  }
  function render(data, viewMode='local'){
    const s=safeSummary(data);
    const rp=s.club?.remote_profile;
    const isRemote=viewMode==='remote'&&Boolean(rp);
    const club=s.club||{},isLinked=Boolean(club.is_linked),isSyncing=Boolean(club.sync_enabled),op=club.x_identity||{};
    const clubSection=renderClub(club, viewMode);

    const remoteCats = isRemote ? {
      public_free: { tokens: rp.categories?.public_free || 0, requests: null },
      included: { tokens: rp.categories?.included || 0, requests: null },
      local: { tokens: rp.categories?.local || 0, requests: null }
    } : s.categories;

    const known=Object.values(remoteCats).reduce((n,v)=>n+(v.tokens||0),0);
    const free=remoteCats.public_free?.tokens || 0;
    const includedTokens=remoteCats.included?.tokens || 0;
    const localTokens=remoteCats.local?.tokens || 0;
    const paid=isRemote ? 0 : s.categories.paid.tokens;
    const denom=(free||0)+(paid||0);
    const zeroCostTokens=isRemote ? rp.tokens : (s.total_free_tokens||0);
    const reportedTokens=isRemote ? rp.tokens : s.tokens.reported;
    const zeroCostShare=reportedTokens>0?Math.round((zeroCostTokens/reportedTokens)*100):100;
    const estSavings=isRemote
      ? '$'+(Math.round(zeroCostTokens*0.000003*100)/100).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})
      : (s.estimated_savings!=null?'$'+Number(s.estimated_savings).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}):money(zeroCostTokens*0.000003));

    const rolesEntries = isRemote && rp.roles && rp.roles.length
      ? rp.roles.map(r => [r.name, { tokens: r.tokens, requests: null }])
      : Object.entries(s.roles);

    const modelsList = isRemote && rp.models && rp.models.length
      ? rp.models.map(m => ({ name: m.name, tokens: m.tokens, requests: null }))
      : Object.entries(s.models).map(([name, obj]) => ({ name, tokens: obj.tokens, requests: obj.requests }));

    const bannerHtml = isRemote ? `
      <div class="scoreboard-reconcile-banner">
        <div class="scoreboard-banner-left">
          <span class="scoreboard-pill">🌐 Club Scoreboard</span>
          <span>Official leaderboard score for <strong>@${escape(rp.handle)}</strong>${rp.display_name ? ` (${escape(rp.display_name)})` : ''}</span>
        </div>
        <div class="scoreboard-banner-right">
          <a href="${escape(club.leaderboard_url || 'https://cheapos.lol')}/${escape(rp.handle)}" target="_blank" rel="noopener noreferrer" class="scoreboard-link">
            View on cheapos.lol ↗
          </a>
        </div>
      </div>` : '';

    return `
    <!-- TAB 1: OVERVIEW & SAVINGS -->
    <div class="usage-tab-panel" data-tab-panel="overview">
      ${bannerHtml}
      <div class="usage-meta-bar">
        <span>${isRemote ? `Official verified score for <strong>@${escape(rp.handle)}</strong>` : `Recorded since <strong>${escape(date(s.recorded_since))}</strong> ${s.partial_earlier_history?'· <span class="history-badge">partial earlier history</span>':''}`}</span>
        <span>${isRemote ? `Last synced <strong>${club.last_synced_at?escape(date(club.last_synced_at)):'Live'}</strong>` : `Updated <strong>${escape(date(s.updated_at))}</strong> · <strong>${s.period==='all'?'All time':s.period+' days (UTC)'}</strong>`}</span>
      </div>

      <div class="lifetime-figures">
        <div class="figure-card">
          <span class="figure-label">${isRemote ? 'Verified zero-cost tokens' : 'Reported model tokens'}</span>
          <strong class="figure-val">${number(reportedTokens)}</strong>
          <span class="figure-sub">${isRemote ? 'Live leaderboard score' : 'Total recorded compute'}</span>
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
            <span class="figure-label">${isRemote ? 'Account-included tokens' : 'Paid-model tokens'}</span>
            <span class="pill-badge ${isRemote ? '' : 'amber'}">${isRemote ? 'Included' : 'Metered'}</span>
          </div>
          <strong class="figure-val">${number(isRemote ? includedTokens : paid)}</strong>
          <span class="figure-sub">${isRemote ? 'Included quota' : 'Metered API usage'}</span>
        </div>
        <div class="figure-card">
          <span class="figure-label">${isRemote ? 'Local model compute' : 'Accounted API cost'}</span>
          <strong class="figure-val">${isRemote ? number(localTokens) : money(s.cost.accounted)}</strong>
          <span class="figure-sub">${isRemote ? 'On-device models' : 'Direct provider spend'}</span>
        </div>
        <div class="figure-card highlight-savings">
          <span class="figure-label">Est. commercial savings</span>
          <strong class="figure-val text-savings">${estSavings}</strong>
          <span class="figure-sub">Vs standard commercial rates</span>
        </div>
      </div>

      <div class="savings-highlight-card">
        <div class="savings-highlight-badge">⚡ ${zeroCostShare}% zero-cost compute</div>
        <p class="savings-highlight-main"><strong>${number(zeroCostTokens)} tokens</strong> ${isRemote ? `verified on the Cheapskate Club scoreboard for @${escape(rp.handle)} at $0 out-of-pocket API cost.` : 'consumed at $0 out-of-pocket API cost across public-free, account-included, and local models.'}</p>
        <p class="savings-highlight-note">${isRemote ? `${number(known ? Math.round(100*(free||0)/known) : 100)}% of remote tokens used public-free models. ${rp.models.length} distinct models and ${rp.roles.length} agent roles active.` : (denom?`${number(100*(free||0)/denom)}% of classified free-or-paid remote tokens used public-free models.`:'Free-model share is unavailable: no classified free-or-paid remote tokens.')+' Local, included and unknown are excluded. Charged-free anomalies count as paid usage in this comparison.'}</p>
      </div>

      <div class="lifetime-stack-wrapper">
        <div class="stack-header">
          <h4>Compute distribution</h4>
          <span class="small muted">${isRemote ? 'Verified Club token share' : 'Categorized token share'}</span>
        </div>
        <div class="lifetime-stack" aria-hidden="true">${Object.entries(remoteCats).map(([k,v])=>`<span class="usage-${k}" style="flex:${known?(v.tokens||0)/known:0}" title="${categories[k]||k}: ${number(v.tokens)} tokens"></span>`).join('')}</div>
        <div class="stack-legend">${Object.entries(remoteCats).map(([k,v])=>`
          <div class="stack-legend-item">
            <span class="legend-dot usage-${k}"></span>
            <span class="legend-label">${categories[k]||k}</span>
            <span class="legend-pct">${known?Math.round(((v.tokens||0)/known)*100):0}%</span>
          </div>`).join('')}
        </div>
      </div>

      <div class="completed-work-card">
        <h4>${isRemote ? 'Club Work Outcomes' : 'Completed work outcomes'}</h4>
        ${isRemote ? `
        <div class="completed-work-grid">
          <div class="work-stat">
            <span>🧑‍💻 Completed tasks</span>
            <strong>${rp.work_outcomes?.completed_tasks != null ? number(rp.work_outcomes.completed_tasks) : number((s.completion.human_accepted_jobs||0)+(s.completion.merged_runs||0))}</strong>
          </div>
          <div class="work-stat">
            <span>🛡️ Review-approved</span>
            <strong>${rp.work_outcomes?.review_approved_jobs != null ? number(rp.work_outcomes.review_approved_jobs) : number(s.completion.independent_review_approved_jobs)}</strong>
          </div>
          <div class="work-stat">
            <span>🎯 Acceptance rate</span>
            <strong>${rp.work_outcomes?.acceptance_rate != null ? rp.work_outcomes.acceptance_rate + '%' : (s.completion.independent_review_approved_jobs ? Math.round(((s.completion.human_accepted_jobs||0)+(s.completion.merged_runs||0))/s.completion.independent_review_approved_jobs*1000)/10 + '%' : '—')}</strong>
          </div>
        </div>
        <p class="small muted">Scoreboard data is signed with your local Ed25519 installation key and verified by the Club leaderboard.</p>` : `
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
        <p class="small muted">${s.completion_definitions} Failed work still consumes tokens.</p>`}
      </div>
    </div>

    <!-- TAB 2: BREAKDOWN & HISTORY -->
    <div class="usage-tab-panel" data-tab-panel="breakdown" hidden>
      ${bannerHtml}
      <div class="breakdown-section">
        <h4>${isRemote ? 'Club Scoreboard token breakdown' : 'Reported token access breakdown'}</h4>
        <table class="usage-table">
          <thead>
            <tr>
              <th scope="col">Access category</th>
              <th scope="col" style="text-align:right">Tokens</th>
              ${isRemote ? '' : '<th scope="col" style="text-align:right">Requests</th>'}
              <th scope="col" style="text-align:right">Share</th>
            </tr>
          </thead>
          <tbody>
            ${Object.entries(remoteCats).map(([k,v])=>`
              <tr>
                <th scope="row">
                  <span class="legend-dot usage-${k}" style="display:inline-block;vertical-align:middle;margin-right:6px"></span>
                  ${categories[k]||k}
                </th>
                <td style="text-align:right">${number(v.tokens)}</td>
                ${isRemote ? '' : `<td style="text-align:right">${number(v.requests)}</td>`}
                <td style="text-align:right">${known?Math.round(((v.tokens||0)/known)*100):0}%</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
        ${isRemote ? `<p class="small muted" style="margin-top:10px">Reconciled with live Club profile for @${escape(rp.handle)}. Paid metered tokens are not tracked by the Club.</p>` : `<p class="small muted" style="margin-top:10px">Unknown-usage requests: ${number(s.tokens.unknown_requests)} · Historical accounted tokens: ${number(s.tokens.accounted_historical)} · Charged-free requests: ${number(s.charged_free_requests)}. Missing usage is unknown, not zero.</p>`}
      </div>

      <details class="advanced" open>
        <summary>${isRemote ? 'Club Scoreboard role breakdown' : 'Accounting details and roles'}</summary>
        ${isRemote ? `<p>Role distribution of tokens uploaded and acknowledged by the Club scoreboard.</p>` : `
        <p>Reported input ${number(s.tokens.input)} · output ${number(s.tokens.output)}. Reasoning ${number(s.tokens.reasoning)} and cached ${number(s.tokens.cached)} are reported subsets, not added again; missing subset coverage may be incomplete (reasoning: ${number(s.tokens.unknown_reasoning_requests)} requests; cached: ${number(s.tokens.unknown_cached_requests)} requests).</p>
        <p>Estimated tokens ${number(s.tokens.estimated)} · outstanding reserved tokens ${number(s.tokens.reserved)}; both are separate from reported usage.</p>
        <p>Provider-reported cost ${money(s.cost.provider_reported)} · configured-price estimate ${money(s.cost.configured_estimate)} · historical accounted cost ${money(s.cost.historical_accounted)} · outstanding reservation ${money(s.cost.reserved)}.</p>`}
        <table class="usage-table" style="margin-top:12px">
          <caption>${isRemote ? 'Club Scoreboard role usage' : 'Reported role usage'}</caption>
          <thead>
            <tr>
              <th scope="col">Role</th>
              <th scope="col" style="text-align:right">Tokens</th>
              ${isRemote ? '' : '<th scope="col" style="text-align:right">Requests</th>'}
            </tr>
          </thead>
          <tbody>
            ${rolesEntries.map(([k,v])=>`<tr><th scope="row">${escape(k)}</th><td style="text-align:right">${number(v.tokens)} tokens</td>${isRemote ? '' : `<td style="text-align:right">${number(v.requests)} requests</td>`}</tr>`).join('')}
          </tbody>
        </table>
      </details>

      <details class="advanced" open>
        <summary>${isRemote ? `Club Scoreboard models (${modelsList.length})` : `Models used (${modelsList.length})`}</summary>
        ${modelsList.length ? `<div class="table-scroll-container"><table class="usage-table"><thead><tr><th scope="col">Model</th><th scope="col" style="text-align:right">Tokens</th>${isRemote ? '' : '<th scope="col" style="text-align:right">Requests</th>'}</tr></thead><tbody>${modelsList.map(m => `<tr><th scope="row">${escape(m.name)}</th><td style="text-align:right">${number(m.tokens)} tokens</td>${isRemote ? '' : `<td style="text-align:right">${number(m.requests)} requests</td>`}</tr>`).join('')}</tbody></table></div>` : '<p>No model usage recorded.</p>'}
      </details>

      <details class="advanced" ${isRemote ? '' : 'open'}>
        <summary>Daily recorded history (UTC)</summary>
        ${isRemote ? `<p class="muted">Daily logs are stored locally on this installation. Toggle to <strong>Local</strong> view above to review daily calendar breakdowns.</p>` : `
        <p>Only dated evidence is shown. Missing dates are gaps, not zero usage.${s.history_truncated?' Showing the latest 366 recorded dates; lifetime totals include older dates.':''}</p>
        ${s.history.length?`<div class="table-scroll-container"><table class="usage-table"><thead><tr><th scope="col">Date</th><th scope="col" style="text-align:right">Tokens</th><th scope="col" style="text-align:right">API cost</th></tr></thead><tbody>${s.history.map(r=>`<tr><th scope="row">${escape(r.date)}</th><td style="text-align:right">${number(r.tokens)}</td><td style="text-align:right">${money(r.cost)}</td></tr>`).join('')}</tbody></table></div>`:'<p>No dated usage is available for this period.</p>'}`}
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
      <div class="lifetime-controls-wrapper">
        <div class="usage-view-switch" data-usage-view-switch style="display:none">
          <span class="usage-view-label">Show:</span>
          <div class="usage-view-toggle-group" role="radiogroup" aria-label="Usage view mode">
            <button type="button" class="usage-view-btn active" data-view="local" role="radio" aria-checked="true">💻 Local</button>
            <button type="button" class="usage-view-btn" data-view="remote" role="radio" aria-checked="false">🌐 Club Scoreboard</button>
          </div>
        </div>
        <div class="lifetime-period-wrapper">
          <label>Period <select data-period>
            <option value="all">All time</option>
            <option value="7">Last 7 days</option>
            <option value="30">Last 30 days</option>
          </select></label>
        </div>
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
    </section>
    <div class="modal-footer" data-usage-footer>
      <span data-usage-footer-status>Active view: 💻 <strong>Local installation</strong></span>
      <button type="button" class="primary-button" data-close>Done</button>
    </div>`,'lifetime-modal');

    const q=s=>d.querySelector(s),body=q('[data-usage-body]');let request=0,current=null,pairTimer=null,pairChecking=false,closed=false,activeTab='overview';
    const storage=(typeof localStorage!=='undefined'?localStorage:null);
    let viewMode=(storage?.getItem?.('cheapos_usage_view'))||'local';
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

    function switchView(mode){
      viewMode=mode;
      try{storage?.setItem?.('cheapos_usage_view',mode);}catch{}
      $$('.usage-view-btn',d).forEach(btn=>{
        const active=btn.dataset.view===mode;
        btn.classList.toggle('active',active);
        btn.setAttribute('aria-checked',String(active));
      });
      $$('input[name="club_usage_view_pref"]',d).forEach(r=>{
        r.checked=(r.value===mode);
      });
      const periodWrapper=q('.lifetime-period-wrapper');
      if(periodWrapper){
        if(periodWrapper.style)periodWrapper.style.display=(mode==='remote'?'none':'');
        periodWrapper.hidden=(mode==='remote');
      }
      updateFooterStatus(mode);
      if(current){
        body.innerHTML=render(current,viewMode);
        switchTab(activeTab);
        bindClubActions();
        bindReconcileActions();
      }
      if(typeof renderLifetimeSavingsBadge==='function'&&current){
        renderLifetimeSavingsBadge(current);
      }
    }

    function updateFooterStatus(mode){
      const footerStatus=q('[data-usage-footer-status]');
      if(footerStatus){
        const rp=current?.club?.remote_profile;
        footerStatus.innerHTML=mode==='remote'&&rp?`Active view: 🌐 <strong>Club scoreboard</strong> (@${escape(rp.handle)} · ${number(rp.tokens)} tokens)`:`Active view: 💻 <strong>Local installation</strong> (${number(current?.total_free_tokens||0)} tokens)`;
      }
    }

    function bindReconcileActions(){
      $$('.usage-view-btn',d).forEach(btn=>{
        btn.onclick=()=>switchView(btn.dataset.view);
      });
      $$('input[name="club_usage_view_pref"]',d).forEach(radio=>{
        radio.onchange=()=>{if(radio.checked)switchView(radio.value);};
      });
      const applyBtn=q('[data-apply-view]');
      if(applyBtn){
        applyBtn.onclick=()=>{
          const checked=q('input[name="club_usage_view_pref"]:checked');
          if(checked)switchView(checked.value);
          const status=q('[data-apply-status]');
          if(status){
            status.style.display='inline';
            status.textContent='✓ Applied to sidebar';
            setTimeout(()=>{if(status)status.style.display='none';},2500);
          }
        };
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
      const hasRemote=Boolean(current.club?.remote_profile);
      const switchEl=q('[data-usage-view-switch]');
      if(switchEl){
        if(switchEl.style)switchEl.style.display=(hasRemote?'':'none');
        switchEl.hidden=!hasRemote;
      }
      const scroll=d.scrollTop,panel=q('.club-panel');
      if(panel)panel.outerHTML=renderClub(current.club||{}, viewMode);
      bindClubActions();
      bindReconcileActions();
      schedulePairCheck();
      d.scrollTop=scroll;
    }
    function bindClubActions(){
      const actions=[['connect','/club/pair',{}],['check','/club/check',{}],['share','/club/sync',{enabled:true}],['sync','/club/sync',{}],['pause','/club/sync',{enabled:false}],['disconnect','/club/disconnect',{}],['preferences','/club/sync',{}]];
      for(const [name,path,values] of actions){
        const button=q('[data-club-'+name+']');
        if(button)button.onclick=async()=>{
          const label=button.textContent;
          button.disabled=true;
          if(name==='sync')button.textContent='Syncing…';
          if(name==='preferences'){
            button.textContent='Saving…';
            const feedback=q('[data-club-pref-feedback]');
            if(feedback)feedback.textContent='Saving…';
            const chk=q('[data-club-models]');
            if(chk)chk.disabled=true;
          }
          try{
            const payload=['preferences','share'].includes(name)?{enabled:name==='share'||Boolean(current?.club?.sync_enabled),share_models:Boolean(q('[data-club-models]')?.checked)}:values;
            let status=await api(path,payload);
            if(status.is_linked===undefined)status=await api('/club/status');
            updateClub(status);
            if(name==='connect'&&status.pairing_pending&&status.connect_url){
              try { window.open(status.connect_url, '_blank'); } catch(e){}
            }
            if(name==='preferences'){
              const updatedBtn=q('[data-club-preferences]');
              const feedback=q('[data-club-pref-feedback]');
              if(updatedBtn)updatedBtn.textContent='Saved ✓';
              if(feedback)feedback.textContent='Saved ✓';
              const t=setTimeout(()=>{
                if(updatedBtn&&updatedBtn.isConnected)updatedBtn.textContent='Save model preference';
                if(feedback&&feedback.isConnected)feedback.textContent='';
              },2000);
              if(t&&typeof t.unref==='function')t.unref();
            }
          }catch(error){
            if(closed||!d.isConnected)return;
            const errEl=q('[data-club-error]');
            if(errEl)errEl.textContent=error.message||'Club request failed. Local work is unaffected.';
            const feedback=q('[data-club-pref-feedback]');
            if(feedback)feedback.textContent='';
            button.disabled=false;
            button.textContent=label;
            const chk=q('[data-club-models]');
            if(chk)chk.disabled=false;
          }
        };
      }
      const modelCheckbox=q('[data-club-models]');
      if(modelCheckbox){
        modelCheckbox.onchange=()=>{
          const prefBtn=q('[data-club-preferences]');
          if(prefBtn){
            if(typeof prefBtn.onclick==='function')prefBtn.onclick();
            else if(typeof prefBtn.click==='function')prefBtn.click();
          }
        };
      }
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
        const hasRemote=Boolean(current?.club?.remote_profile);
        const switchEl=q('[data-usage-view-switch]');
        if(switchEl){
          if(switchEl.style)switchEl.style.display=(hasRemote?'':'none');
          switchEl.hidden=!hasRemote;
        }
        if(!storage?.getItem?.('cheapos_usage_view')&&hasRemote&&current?.club?.is_linked){
          viewMode='remote';
        }
        const effectiveView=(viewMode==='remote'&&hasRemote)?'remote':'local';
        const periodWrapper=q('.lifetime-period-wrapper');
        if(periodWrapper){
          if(periodWrapper.style)periodWrapper.style.display=(effectiveView==='remote'?'none':'');
          periodWrapper.hidden=(effectiveView==='remote');
        }
        $$('.usage-view-btn',d).forEach(btn=>{
          const active=btn.dataset.view===effectiveView;
          btn.classList.toggle('active',active);
          btn.setAttribute('aria-checked',String(active));
        });
        body.innerHTML=render(current,effectiveView);
        switchTab(activeTab);
        bindClubActions();
        bindReconcileActions();
        updateFooterStatus(effectiveView);
        $$('[data-close]',d).forEach(b=>b.onclick=()=>d.close());
        if(typeof renderLifetimeSavingsBadge==='function'&&current){
          renderLifetimeSavingsBadge(current);
        }
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
