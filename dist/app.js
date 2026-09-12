'use strict';
const $ = (s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon=n=>`<svg aria-hidden="true"><use href="#i-${n}"/></svg>`;
const initialActivity=$('#activity-view').innerHTML, initialInspector=$('.inspector-scroll').innerHTML;
const defaults={mode:'Economy',worker:'OpenRouter Free',reviewer:'Frontier Model',frequency:'After tests pass',budget:4000,iterations:5,permissions:true};
let prefs={...defaults};try{prefs={...defaults,...JSON.parse(localStorage.getItem('cheapos-preferences')||'{}')}}catch{}
if(!['Fast','Standard','Economy','Deep'].includes(prefs.mode))prefs.mode='Economy';
const state={task:'cache',view:'activity',file:0,diff:'unified',run:2,replaying:false,timers:[],testTimer:null,toastTimer:null};
const before=`from copy import deepcopy
from github import Github


class GitHubLoader:
    def __init__(self, token):
        self.client = Github(token)

    def load_repository(self, full_name, ref="main"):
        repository = self.client.get_repo(full_name)
        files = self._read_files(repository, ref)
        return {
            "name": repository.full_name,
            "description": repository.description,
            "files": files,
        }

    def _read_files(self, repository, ref):
        return [
            {"path": item.path, "content": item.decoded_content}
            for item in repository.get_contents("", ref=ref)
            if item.type == "file"
        ]`;
const after=`from collections import OrderedDict
from copy import deepcopy
from threading import RLock
from time import monotonic
from github import Github


class GitHubLoader:
    def __init__(self, token, cache_ttl=300, max_entries=128):
        self.client = Github(token)
        self.cache_ttl = cache_ttl
        self.max_entries = max_entries
        self._cache = OrderedDict()
        self._lock = RLock()

    def load_repository(self, full_name, ref="main"):
        repository = self.client.get_repo(full_name)
        # A new push changes the key, invalidating old metadata.
        key = (repository.full_name, ref, repository.pushed_at)
        now = monotonic()

        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                expires_at, data = cached
                if now < expires_at:
                    self._cache.move_to_end(key)
                    return deepcopy(data)
                del self._cache[key]

        files = self._read_files(repository, ref)
        data = {
            "name": repository.full_name,
            "description": repository.description,
            "files": files,
        }

        with self._lock:
            # Isolate cached data from the caller's edits.
            self._cache[key] = (
                monotonic() + self.cache_ttl,
                deepcopy(data),
            )
            self._cache.move_to_end(key)
            while len(self._cache) > self.max_entries:
                self._cache.popitem(last=False)
        return data

    def clear_cache(self):
        with self._lock:
            self._cache.clear()

    def _read_files(self, repository, ref):
        return [
            {"path": item.path, "content": item.decoded_content}
            for item in repository.get_contents("", ref=ref)
            if item.type == "file"
        ]`;
const testsBefore=`from unittest.mock import patch


def test_load_repository(loader, repository):
    result = loader.load_repository("acme/example")
    assert result["name"] == "acme/example"


def test_load_empty_repository(loader, repository):
    repository.get_contents.return_value = []
    assert loader.load_repository("acme/example")["files"] == []`;
const testsAfter=`from datetime import timedelta
${testsBefore}


def test_cache_hit_skips_file_request(loader, repository):
    first = loader.load_repository("acme/example")
    second = loader.load_repository("acme/example")
    assert first == second
    repository.get_contents.assert_called_once()


def test_cache_returns_isolated_copy(loader, repository):
    first = loader.load_repository("acme/example")
    first["files"].clear()
    second = loader.load_repository("acme/example")
    assert second["files"]


def test_cache_expires_after_ttl(loader, repository):
    with patch("github_loader.monotonic", return_value=100):
        loader.load_repository("acme/example")
    with patch("github_loader.monotonic", return_value=401):
        loader.load_repository("acme/example")
    assert repository.get_contents.call_count == 2


def test_cache_invalidates_after_push(loader, repository):
    loader.load_repository("acme/example")
    repository.pushed_at += timedelta(seconds=1)
    loader.load_repository("acme/example")
    assert repository.get_contents.call_count == 2


def test_cache_separates_refs(loader, repository):
    loader.load_repository("acme/example", ref="main")
    loader.load_repository("acme/example", ref="develop")
    assert repository.get_contents.call_count == 2


def test_cache_respects_capacity(loader, repository):
    loader.max_entries = 2
    for ref in ("main", "develop", "feature"):
        loader.load_repository("acme/example", ref=ref)
    assert len(loader._cache) == 2


def test_clear_cache(loader, repository):
    loader.load_repository("acme/example")
    loader.clear_cache()
    loader.load_repository("acme/example")
    assert repository.get_contents.call_count == 2`;
const files=[{path:'src/loaders/github_loader.py',before,after},{path:'tests/test_github_loader.py',before:testsBefore,after:testsAfter},{path:'README.md',before:'# Trace the Failure\n\nLoad a GitHub repository to explore its stack traces.\n\n## Repository loader\n\nThe loader fetches files from GitHub on each request.',after:'# Trace the Failure\n\nLoad a GitHub repository to explore its stack traces.\n\n## Repository loader\n\nRepository contents are cached in memory for five minutes.\nRepeated requests reuse the cached result, saving API calls.\n\n- A new push invalidates the cached repository.\n- Branches and tags use separate cache entries.\n- The cache holds up to 128 entries, evicting the least recently used.\n- Use `loader.clear_cache()` to force a fresh fetch.'}];
const tests=['load_repository','load_empty_repository','load_nested_files','load_binary_files','preserve_file_paths','decode_utf8_content','handle_missing_repository','handle_permission_error','handle_rate_limit','retry_transient_error','respect_branch_ref','resolve_default_branch','normalize_repository_name','parse_repository_url','reject_invalid_url','preserve_description','cache_hit_skips_file_request','cache_returns_isolated_copy','cache_expires_after_ttl','cache_separates_refs','cache_respects_capacity','clear_cache','cache_is_thread_safe','cache_invalidates_after_push'];
const tasks={
 cache:{title:'A faster repository loader.',label:'Cache GitHub repository loader',project:'trace-the-failure',branch:'feat/repo-cache',prompt:'Add caching to the GitHub repository loader and make sure existing tests still pass.',files,tests,tokens:34821,reviewTokens:2941,cost:'0.04',summary:'Added a bounded repository cache with push-aware invalidation. All 24 tests pass.'},
 trace:{title:'Make every stack trace useful.',label:'Improve stack trace parsing',project:'trace-the-failure',branch:'fix/trace-parsing',prompt:'Handle stack frames with spaces in file paths.',files:[{path:'src/parsers/stack_trace.py',before:'FRAME_PATTERN = r"File (\\S+), line (\\d+)"',after:'FRAME_PATTERN = r\'File "(.+)", line (\\d+)\''}],tests:['parse_python_trace','parse_spaced_path','parse_nested_frame','preserve_frame_order'],tokens:8412,reviewTokens:710,cost:'0.01',summary:'The parser now handles file paths with spaces and keeps the original frame order.'},
 empty:{title:'An explorer that helps you get started.',label:'Add empty states to the explorer',project:'trace-the-failure',branch:'feat/explorer-empty',prompt:'Make the empty repository explorer more helpful.',files:[{path:'src/components/Explorer.tsx',before:'if (!files.length) return null;',after:'if (!files.length) {\n  return <EmptyState title="No files yet" description="Load a repository to start exploring." />;\n}'}],tests:['render_empty_state','render_file_tree','handle_loading'],tokens:6124,reviewTokens:640,cost:'0.01',summary:'An empty explorer now explains how to load a repository, with separate loading and empty states.'},
 retry:{title:'Give rate limits a little breathing room.',label:'Fix retry logic on rate limits',project:'trace-the-failure',branch:'fix/rate-limit',prompt:'Respect Retry-After when the API returns a rate limit.',files:[{path:'src/api/retry.py',before:'delay = 1\ntime.sleep(delay)',after:'delay = max(1, int(response.headers.get("Retry-After", 1)))\ntime.sleep(delay)'}],tests:['retry_after_header','default_retry_delay','stop_after_max_retries','successful_retry'],tokens:11280,reviewTokens:830,cost:'0.02',summary:'Rate-limited requests respect the server’s Retry-After header and the existing retry cap.'},
 readme:{title:'A shorter path to your first trace.',label:'Update the getting started guide',project:'trace-the-failure',branch:'docs/quickstart',prompt:'Add a minimal getting started example to the README.',files:[{path:'README.md',before:'## Getting started\n\nInstall the dependencies.',after:'## Getting started\n\n1. Install dependencies with `pip install -e .`.\n2. Set `GITHUB_TOKEN` in your environment.\n3. Run `trace-the-failure acme/example`.\n\nOpen the explorer to inspect the loaded repository.'}],tests:[],tokens:3920,reviewTokens:430,cost:'0.01',summary:'Added installation, authentication, and first-run steps to the guide.'},
 personal:{title:'A portfolio with a little personality.',label:'Refine the project cards',project:'personal-site',branch:'style/project-cards',prompt:'Give the portfolio project cards more breathing room.',files:[{path:'src/styles/projects.css',before:'.project-card { padding: 16px; }',after:'.project-card {\n  padding: 24px;\n  border: 1px solid var(--border);\n  border-radius: 8px;\n}'}],tests:[],tokens:4100,reviewTokens:380,cost:'0.01',summary:'Adjusted project card spacing and added a restrained border.'}
};
function toast(message){clearTimeout(state.toastTimer);$('#toast').textContent=message;$('#toast').classList.add('visible');state.toastTimer=setTimeout(()=>$('#toast').classList.remove('visible'),3500)}
function diffLines(a,b){
 a=a.split('\n');b=b.split('\n');const dp=Array.from({length:a.length+1},()=>new Uint16Array(b.length+1));
 for(let i=a.length-1;i>=0;i--)for(let j=b.length-1;j>=0;j--)dp[i][j]=a[i]===b[j]?1+dp[i+1][j+1]:Math.max(dp[i+1][j],dp[i][j+1]);
 const rows=[];let i=0,j=0;
 while(i<a.length||j<b.length){if(i<a.length&&j<b.length&&a[i]===b[j])rows.push({type:'context',old:++i,new:++j,text:a[i-1]});else if(j<b.length&&(i===a.length||dp[i][j+1]>dp[i+1][j]))rows.push({type:'add',old:'',new:++j,text:b[j-1]});else rows.push({type:'remove',old:++i,new:'',text:a[i-1]});}return rows;
}
function totals(list){return list.reduce((s,f)=>{diffLines(f.before,f.after).forEach(r=>{if(r.type==='add')s.add++;if(r.type==='remove')s.remove++});return s},{add:0,remove:0})}
function syntax(line){return line.split(/("[^"\n]*"|'[^'\n]*'|#.*$|\b(?:from|import|class|def|return|if|for|in|with|while|del|as|assert|not|is|None|False|True|const|let)\b)/g).map(p=>{const cls=/^#/.test(p)?'syn-comment':/^["']/.test(p)?'syn-string':/^(from|import|class|def|return|if|for|in|with|while|del|as|assert|not|is|None|False|True|const|let)$/.test(p)?'syn-keyword':'';return cls?`<span class="${cls}">${esc(p)}</span>`:esc(p)}).join('')}
function openView(view){if(!['activity','changes','tests'].includes(view))return;state.view=view;$$('.tab').forEach(b=>{b.classList.toggle('active',b.dataset.view===view);if(b.dataset.view===view)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current')});$$('.view').forEach(v=>v.classList.toggle('hidden',v.id!==view+'-view'));if(view==='changes')renderChanges();if(view==='tests')renderTests();$('#view-container').scrollTop=0}
function renderChanges(){
 const task=tasks[state.task];if(!task.files.length){$('#changes-view').innerHTML=`<div class="empty-state">${icon('code')}<h2>No changes yet</h2><p>Your worker’s changes will appear here once a model is connected.</p></div>`;return}
 state.file=Math.min(state.file,task.files.length-1);const f=task.files[state.file],sum=totals(task.files),rows=diffLines(f.before,f.after);
 const line=r=>`<div class="diff-line ${r.type}"><span class="line-number">${r.old}</span><span class="line-number">${r.new}</span><span class="diff-sign">${r.type==='add'?'+':r.type==='remove'?'−':' '}</span><span class="source">${syntax(r.text)||' '}</span></div>`;
 $('#changes-view').innerHTML=`<div class="view-title"><div><h2>Changes ready for review</h2><p>${task.files.length} files changed <span class="inline-add">+${sum.add}</span> <span class="inline-remove">−${sum.remove}</span></p></div><button class="subtle-button" id="copy-patch">${icon('copy')}Copy patch</button></div><div class="file-list">${task.files.map((f,i)=>{const c=totals([f]);return `<button class="file-item ${i===state.file?'selected':''}" data-file="${i}">${icon('file')}<span>${esc(f.path)}</span><span class="inline-add">+${c.add}</span><span class="inline-remove">−${c.remove}</span><span class="file-status">M</span></button>`}).join('')}</div><div class="diff-panel"><div class="diff-toolbar"><span>${icon('file')}${esc(f.path.split('/').pop())}</span><div class="segmented"><button data-diff="unified" class="${state.diff==='unified'?'selected':''}">Unified</button><button data-diff="split" class="${state.diff==='split'?'selected':''}">Split</button></div></div>${state.diff==='unified'?`<div class="diff-code" tabindex="0" aria-label="Unified code diff">${rows.map(line).join('')}</div>`:`<div class="split-diff"><div class="diff-code" tabindex="0" aria-label="Original file"><div class="split-label">Before</div>${rows.filter(r=>r.type!=='add').map(r=>`<div class="diff-line ${r.type}"><span class="line-number">${r.old}</span><span class="source">${syntax(r.text)||' '}</span></div>`).join('')}</div><div class="diff-code" tabindex="0" aria-label="Modified file"><div class="split-label">After</div>${rows.filter(r=>r.type!=='remove').map(r=>`<div class="diff-line ${r.type}"><span class="line-number">${r.new}</span><span class="source">${syntax(r.text)||' '}</span></div>`).join('')}</div></div>`}</div><div class="diff-bottom">${icon('shield')}Sample code diff · your repository is unchanged</div>`;
 $$('[data-file]').forEach(b=>b.onclick=()=>{state.file=Number(b.dataset.file);renderChanges()});$$('[data-diff]').forEach(b=>b.onclick=()=>{state.diff=b.dataset.diff;renderChanges()});
 $('#copy-patch').onclick=async()=>{const patch=task.files.map(f=>`--- a/${f.path}\n+++ b/${f.path}\n@@ -1,${f.before.split('\n').length} +1,${f.after.split('\n').length} @@\n`+diffLines(f.before,f.after).map(r=>(r.type==='add'?'+':r.type==='remove'?'-':' ')+r.text).join('\n')).join('\n');try{await navigator.clipboard.writeText(patch+'\n');toast('Patch copied to clipboard')}catch{toast('Clipboard unavailable in this browser')}};
}
function renderTests(){
 const task=tasks[state.task],cache=state.task==='cache';if(!task.tests.length){$('#tests-view').innerHTML=`<div class="empty-state">${icon('tests')}<h2>${task.custom?'No test run yet':'No code tests needed'}</h2><p>${task.custom?'Connect a model to run tests for this task.':'This sample only changes documentation or presentation.'}</p></div>`;return}
 const failed=cache&&state.run===0,names=cache&&state.run<2?task.tests.slice(0,23):task.tests;
 $('#tests-view').innerHTML=`<div class="view-title"><div><h2>${failed?'One edge case to fix.':'Everything’s green.'}</h2><p>Simulated pytest results · ${cache?'iteration '+(state.run+1):'final run'}</p></div><button class="subtle-button" id="rerun-tests">${icon('play')}Run demo tests</button></div>${cache?`<div class="test-run-picker"><label for="test-run">Test run</label><select id="test-run">${['Run 1 · 22 passed, 1 failed','Run 2 · 23 passed','Run 3 · 24 passed'].map((v,i)=>`<option value="${i}" ${state.run===i?'selected':''}>${v}</option>`).join('')}</select></div>`:''}<div class="test-summary ${failed?'failure':''}">${icon(failed?'x':'check')}<strong>${names.length-(failed?1:0)} passed${failed?' · 1 failed':''}</strong><span>${failed?'2.17':'1.84'}s</span><span>Python 3.12</span></div>${failed?'<div class="test-failure"><strong>test_cache_returns_isolated_copy</strong><p>AssertionError: expected cached files to be preserved after the caller cleared the first result.</p><code>assert second["files"]<br>E assert []</code><p>Resolved in iteration 2: return a deep copy of cached data.</p></div>':''}<div class="test-results">${names.map((name,i)=>`<div class="test-result ${failed&&name==='cache_returns_isolated_copy'?'failed':''}">${icon(failed&&name==='cache_returns_isolated_copy'?'x':'check')}<span>test_${name}</span><time>${((i%6+1)*0.01).toFixed(2)}s</time></div>`).join('')}</div><div class="diff-bottom">${icon('tests')}Demo results illustrate the loop; no commands are executed.</div>`;
 if($('#test-run'))$('#test-run').onchange=e=>{state.run=Number(e.target.value);renderTests()};
 $('#rerun-tests').onclick=()=>{const b=$('#rerun-tests');b.disabled=true;b.innerHTML='<span class="spinner"></span>Running…';state.testTimer=setTimeout(()=>{state.run=2;if(state.view==='tests')renderTests();toast(`Demo run finished: ${task.tests.length} tests passed`)},1200)};
}
function stopReplay(){state.timers.forEach(clearTimeout);state.timers=[];state.replaying=false;$('.eyebrow').classList.remove('running');$('#replay').innerHTML=icon('play');$('#replay').setAttribute('aria-label','Replay demo session')}
function bindActivity(){$$('[data-open-changes]').forEach(b=>b.onclick=()=>openView('changes'));const stat=$$('.activity-detail')[1];if(state.task==='cache'&&stat){const c=totals([files[0]]);stat.innerHTML=`github_loader.py <span class="inline-add">+${c.add}</span> <span class="inline-remove">−${c.remove}</span>`;const footer=$('.requested .review-foot');const button=document.createElement('button');button.className='checkpoint-button';button.textContent='Inspect checkpoint';button.onclick=openCheckpoint;footer.before(button)}}
function openCheckpoint(){dialog(`<div class="modal-header"><div><span class="eyebrow">CHECKPOINT #1</span><h2>Just enough context to review.</h2></div><button class="icon-btn" data-close aria-label="Close checkpoint">${icon('x')}</button></div><p class="modal-description">A compact snapshot replaces the full worker conversation.</p><div class="checkpoint-section"><h3>Original task</h3><p>${esc(tasks.cache.prompt)}</p></div><div class="checkpoint-section"><h3>Files & diff</h3><p>github_loader.py · test_github_loader.py · README.md</p><pre>+ key = (repository.full_name, ref)\n+ cached = self._cache.get(key)\n+ return deepcopy(cached)</pre></div><div class="checkpoint-section"><h3>Verification</h3><p>23 tests passed in 1.84s. Cache hits, expiration, capacity, and copy isolation covered.</p></div><div class="checkpoint-section"><h3>Worker summary</h3><p>Added a bounded, five-minute in-memory cache. Fixed a shared mutable value exposed by the first test run.</p></div><div class="checkpoint-section"><h3>Uncertainty</h3><p>Is TTL-only expiration sufficient when repository metadata changes?</p></div><div class="review-outcomes"><span>Approve</span><span class="selected">Request changes</span><span>Take over</span></div><p class="modal-description">The reviewer chose to request changes. A takeover would pause the worker and let the frontier model finish the task.</p>`,'checkpoint-modal')}
function bindInspector(){['worker-model','reviewer-model'].forEach(id=>{if($('#'+id))$('#'+id).onclick=()=>openSettings()});if($('#journey-expand'))$('#journey-expand').onclick=()=>{const d=$('#journey-details');d.classList.toggle('hidden');$('#journey-expand').setAttribute('aria-expanded',String(!d.classList.contains('hidden')))};if($('#replay-bottom'))$('#replay-bottom').onclick=replay}
function selectTask(id){
 if(!tasks[id])return;stopReplay();clearTimeout(state.testTimer);state.task=id;state.file=0;state.run=2;const task=tasks[id],sum=totals(task.files);
 $('#task-title').textContent=task.title;$('#project-name').textContent=task.project;$('.branch').innerHTML=icon('branch')+esc(task.branch);$('#task-status').textContent=task.custom?'Ready to start':'Completed';$('.eyebrow>span:last-child').textContent=id==='cache'?'Today, 10:42 AM':task.custom?'Just now':'Sample history';$('.task-subtitle').textContent=task.custom?'Your next idea starts here.':'A little patience. A lot less compute cost.';$('#compact-session strong').innerHTML='$'+task.cost+(id==='cache'?'<small> · 81% saved</small>':'');
 $('.tab[data-view="changes"] .count').textContent=task.files.length;$('.test-count').textContent=task.tests.length;$('.diff-tally').innerHTML=`<span>+${sum.add}</span><span>−${sum.remove}</span>`;
 $$('.task').forEach(b=>b.classList.toggle('active',b.dataset.task===id));$$('.project').forEach(b=>b.classList.toggle('active',b.dataset.project===task.project));
 $('#activity-view').innerHTML=id==='cache'?initialActivity:`<div class="user-message"><div class="message-meta"><span class="mini-avatar">C</span><strong>You</strong><time>${task.custom?'Just now':'Sample history'}</time></div><p>${esc(task.prompt)}</p></div><div class="agent-message"><div class="message-meta"><span class="agent-avatar">${icon('code')}</span><strong>Worker</strong><span class="model-label">${task.custom?esc(prefs.worker):'OpenRouter Free'}</span></div><p>${esc(task.summary)}</p></div>${task.custom?`<div class="new-task-notice">${icon('leaf')}<div><strong>${esc(prefs.mode)} is ready when you are.</strong><p>This prototype demonstrates the workspace using sample sessions. Your task stays here for this visit; model execution can be connected in a future build.</p><button class="subtle-button" id="try-demo">${icon('play')}Explore the caching demo</button></div></div>`:`<details class="review-card approved" open><summary><span class="review-symbol">${icon('check')}</span><strong>Reviewer approved</strong><span class="decision approve">Approved</span></summary><div class="review-content"><p>Implementation matches the task. ${task.tests.length?'All '+task.tests.length+' sample tests pass.':'The change is limited to presentation or documentation.'}</p></div></details><div class="completion-note">${icon('file')}<button class="text-link" data-open-changes>Inspect changed files →</button></div>`}<div id="followups"></div>`;
 $('#followups').innerHTML=task.messages||'';
 $('.inspector-scroll').innerHTML=id==='cache'?initialInspector:`<section class="economy-intro"><div class="economy-icon">${icon('leaf')}</div><h2>${task.custom?'A fresh start.':'Small bill. Solid work.'}</h2><p>${task.custom?'Your next coding session starts here.':'A sample session from your workspace.'}</p><div class="mode-badge">${icon('leaf')}${task.custom?esc(prefs.mode):'Economy'} mode</div></section><section class="model-roles"><div class="role-row"><span class="role-icon worker-icon">${icon('code')}</span><span><span class="role-label">WORKER</span><strong>${task.custom?esc(prefs.worker):'OpenRouter Free'}</strong></span></div><div class="role-connection"><span></span><small>codes, tests, iterates</small></div><div class="role-row"><span class="role-icon reviewer-icon">${icon('spark')}</span><span><span class="role-label">REVIEWER</span><strong>${task.custom?esc(prefs.reviewer):'Frontier Model'}</strong></span></div></section><section class="usage"><div class="section-title">${task.custom?'Ready for the first checkpoint':'Sample session usage'}</div><div class="cost-total"><strong>$${task.cost}</strong><span>total session cost</span></div><div class="usage-table"><div><span>Worker</span><span>${task.tokens.toLocaleString()} <small>tokens</small></span></div><div><span>Reviewer</span><span>${task.reviewTokens.toLocaleString()} <small>tokens</small></span></div></div></section>`;
 $('#replay').disabled=id!=='cache';$('#task-input').value='';$('#sidebar').classList.remove('show');bindActivity();bindInspector();if($('#try-demo'))$('#try-demo').onclick=()=>selectTask('cache');openView('activity');
}
function replay(){
 if(state.replaying){selectTask('cache');toast('Replay stopped. Showing the completed session.');return}
 selectTask('cache');state.replaying=true;$('#replay').innerHTML=icon('x');$('#replay').setAttribute('aria-label','Stop replay');
 const blocks=$$('#activity-view > :not(.user-message):not(#followups)');blocks.forEach(b=>b.classList.add('pending-step'));$('#task-status').textContent='Worker is starting';$('.eyebrow').classList.add('running');
 const labels=['Worker is inspecting','Worker is coding and testing','Reviewer requested changes','Worker is revising','Review approved','Completed'],delays=[500,1900,4300,6800,9300,10800],items=$$('.journey-list li');items.forEach(li=>li.classList.add('not-yet'));
 $('.cost-total strong').textContent='$0.00';$('.usage-table').style.opacity='.35';$('.usage-bar').style.opacity='.25';$('.savings').style.visibility='hidden';
 blocks.forEach((b,i)=>state.timers.push(setTimeout(()=>{b.classList.remove('pending-step');b.classList.add('enter-step');$('#task-status').textContent=labels[i]||'Completed';if(i>=1)items.slice(0,2).forEach(li=>li.classList.remove('not-yet'));if(i>=3)items.slice(0,4).forEach(li=>li.classList.remove('not-yet'));if(i===2)$('.cost-total strong').textContent='$0.025';if(i>=4){items.forEach(li=>li.classList.remove('not-yet'));$('.cost-total strong').textContent='$0.04';$('.usage-table').style.opacity='1';$('.usage-bar').style.opacity='1';$('.savings').style.visibility='visible'}if(state.view==='activity')b.scrollIntoView({behavior:'smooth',block:'nearest'})},delays[i]||10800)));
 state.timers.push(setTimeout(()=>{state.replaying=false;$('.eyebrow').classList.remove('running');$('#replay').innerHTML=icon('play');$('#replay').setAttribute('aria-label','Replay demo session');toast('Two checkpoints. One correction. Approved for $0.04.')},11200));toast('Replaying 2m 48s of simulated work in 11 seconds');
}
function dialog(html,cls=''){const prev=document.activeElement,d=document.createElement('dialog');d.className='modal '+cls;d.innerHTML=html;$('#overlay-root').append(d);d.addEventListener('close',()=>{d.remove();prev?.focus()});d.addEventListener('click',e=>{if(e.target===d){const r=d.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)d.close()}});$$('[data-close]',d).forEach(b=>b.onclick=()=>d.close());d.showModal();return d}
function openSettings(modeOnly=false){
 const names=['Fast','Standard','Economy','Deep'],short=['Quick answers','One capable model','Worker + reviewer','Frontier throughout'];
 const d=dialog(`<form id="settings-form"><div class="modal-header"><div><span class="eyebrow">MAKE IT YOURS</span><h2>${modeOnly?'Choose your pace.':'A little control goes a long way.'}</h2></div><button type="button" class="icon-btn" data-close aria-label="Close settings">${icon('x')}</button></div><p class="modal-description">Defaults for your next task. Completed sessions keep their original models and usage.</p><fieldset class="mode-options"><legend class="sr-only">Execution mode</legend>${names.map((n,i)=>`<label class="mode-option ${prefs.mode===n?'chosen':''}"><input type="radio" name="mode" value="${n}" ${prefs.mode===n?'checked':''}><span>${icon(n==='Economy'?'leaf':n==='Deep'?'spark':n==='Fast'?'play':'code')}${n}</span><small>${short[i]}</small></label>`).join('')}</fieldset><div class="mode-explanation" id="mode-explanation"></div><div class="settings-fields ${modeOnly?'hidden':''}"><div class="form-section-title">Models</div><div class="field-grid"><label>Worker model<select name="worker">${['OpenRouter Free','OpenRouter Low-cost','Local · Ollama'].map(v=>`<option ${prefs.worker===v?'selected':''}>${v}</option>`).join('')}</select></label><label>Reviewer model<select name="reviewer">${['Frontier Model','Balanced Model'].map(v=>`<option ${prefs.reviewer===v?'selected':''}>${v}</option>`).join('')}</select></label></div><div class="form-section-title">Review & limits</div><label class="full-field">Review frequency<select name="frequency">${['After tests pass','Every 10 tool actions','At the end of a task'].map(v=>`<option ${prefs.frequency===v?'selected':''}>${v}</option>`).join('')}</select><small>Only a compact checkpoint is sent to the reviewer.</small></label><div class="field-grid"><label>Premium token budget<div class="input-suffix"><input name="budget" type="number" min="500" max="100000" step="500" value="${Number(prefs.budget)||4000}" required><span>tokens</span></div></label><label>Max worker iterations<input name="iterations" type="number" min="1" max="50" value="${Number(prefs.iterations)||5}" required></label></div><div class="permission-setting"><div>${icon('shield')}<span><strong>Auto-approve local tools</strong><small>Allow file reads, edits, and test commands.</small></span></div><label class="switch"><input name="permissions" type="checkbox" ${prefs.permissions?'checked':''} aria-label="Auto-approve local tools"><span></span></label></div></div><div class="modal-footer"><span>Prototype preferences · saved on this device</span><button type="submit" class="primary-button">Save preferences ${icon('check')}</button></div></form>`,'settings-modal');
 const descriptions={Fast:'A lightweight model handles short, simple tasks. Minimal waiting.',Standard:'One capable model takes the task from start to finish.',Economy:'Spend time, save money. A cheap worker iterates; a frontier model reviews only at checkpoints.',Deep:'A frontier model handles the entire task for complex, open-ended work.'};
 const update=()=>{const mode=$('input[name="mode"]:checked',d).value;$('#mode-explanation').textContent=descriptions[mode];$$('.mode-option',d).forEach(l=>l.classList.toggle('chosen',$('input',l).checked))};$$('input[name="mode"]',d).forEach(r=>r.onchange=update);update();
 $('#settings-form').onsubmit=e=>{e.preventDefault();const f=new FormData(e.target);prefs={mode:f.get('mode'),worker:f.get('worker'),reviewer:f.get('reviewer'),frequency:f.get('frequency'),budget:Number(f.get('budget')),iterations:Number(f.get('iterations')),permissions:f.has('permissions')};try{localStorage.setItem('cheapos-preferences',JSON.stringify(prefs))}catch{}updateComposer();d.close();toast(`${prefs.mode} defaults saved for your next task`)};
}
function updateComposer(){$('#mode-select').innerHTML=icon(prefs.mode==='Economy'?'leaf':prefs.mode==='Deep'?'spark':'code')+`<span>${esc(prefs.mode)}</span>`+icon('down');$('.composer-models').textContent=prefs.mode==='Economy'?`${prefs.worker} + review`:prefs.mode==='Deep'?'Frontier model':prefs.mode==='Fast'?'Lightweight model':'Single model';$('.composer-caption span:first-child').innerHTML=icon('shield')+(prefs.permissions?'Local tools allowed':'Ask before tool calls')}
function openSearch(){
 const d=dialog(`<div class="search-box">${icon('search')}<input id="task-search" type="search" placeholder="Find a task or project…" aria-label="Search tasks" autofocus><kbd>ESC</kbd></div><div id="search-results"></div><div class="search-footer">Your local task history <span>↑ ↓ to navigate · Enter to open</span></div>`,'search-modal');
 const render=(q='')=>{const matches=Object.entries(tasks).filter(([,t])=>(t.label+' '+t.project+' '+t.prompt).toLowerCase().includes(q.toLowerCase()));$('#search-results').innerHTML=matches.length?matches.map(([id,t],i)=>`<button class="search-result ${i===0?'focused':''}" data-result="${id}">${icon('chat')}<span><strong>${esc(t.label)}</strong><small>${esc(t.project)}</small></span>${icon('chevron')}</button>`).join(''):'<div class="no-results">No matching tasks. Try “cache” or “trace”.</div>';$$('[data-result]',d).forEach(b=>b.onclick=()=>{selectTask(b.dataset.result);d.close()})};$('#task-search').oninput=e=>render(e.target.value);render();
 d.addEventListener('keydown',e=>{const m=$$('[data-result]',d);let i=m.findIndex(b=>b.classList.contains('focused'));if(['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();m[i]?.classList.remove('focused');i=(i+(e.key==='ArrowDown'?1:-1)+m.length)%m.length;m[i]?.classList.add('focused');m[i]?.scrollIntoView({block:'nearest'})}if(e.key==='Enter'&&m[i]){e.preventDefault();m[i].click()}});
}
function newTask(){
 const d=dialog(`<form id="new-task-form"><div class="modal-header"><div><span class="eyebrow">NEW TASK</span><h2>What are we working on?</h2></div><button type="button" class="icon-btn" data-close aria-label="Close new task">${icon('x')}</button></div><label class="full-field">Project<select name="project"><option>trace-the-failure</option><option>personal-site</option></select></label><label class="full-field">Task<textarea name="prompt" rows="4" placeholder="Describe what you want to build or fix…" required minlength="5" maxlength="2000" autofocus></textarea></label><div class="suggestion-label">Or explore a sample</div><button type="button" class="sample-task" id="sample-cache">${icon('leaf')}Cache the GitHub repository loader ${icon('chevron')}</button><div class="modal-footer"><span>${esc(prefs.mode)} · ${prefs.budget.toLocaleString()} premium tokens max</span><button class="primary-button" type="submit">Create task ${icon('arrow')}</button></div></form>`,'new-task-modal');
 $('#sample-cache').onclick=()=>{d.close();replay()};
 $('#new-task-form').onsubmit=e=>{e.preventDefault();const f=new FormData(e.target),prompt=String(f.get('prompt')).trim();if(prompt.length<5)return;const id='custom-'+Date.now();tasks[id]={title:prompt.length>65?prompt.slice(0,62)+'…':prompt,label:prompt,project:String(f.get('project')),branch:'local workspace',prompt,files:[],tests:[],tokens:0,reviewTokens:0,cost:'0.00',custom:true,summary:`I’m ready to work on this with ${prefs.mode} settings. This is an interactive mockup, so no models or local tools will run.`};const b=document.createElement('button');b.className='task';b.dataset.task=id;b.innerHTML='<span class="task-dot"></span><span>'+esc(prompt)+'</span>';b.onclick=()=>selectTask(id);$('#task-list').prepend(b);d.close();selectTask(id);toast('Task created for this visit')};
}
function submitMessage(){
 const input=$('#task-input'),message=input.value.trim();if(!message)return;input.value='';const task=tasks[state.task],lower=message.toLowerCase();let reply;
 if(/(cost|token|spend|sav)/.test(lower)&&state.task==='cache')reply='This sample used 34,821 free worker tokens and 2,941 premium tokens across two reviews, for $0.04 total. The 81% saving is an illustrative estimate against a frontier-only run, not measured billing.';
 else if(/(test|fail)/.test(lower)&&state.task==='cache')reply='The first run failed because callers could mutate cached data. The worker added defensive copying, then push-aware invalidation after review. The final simulated run passed all 24 tests. Open Tests to compare the three runs.';
 else if(/(cache|review|change)/.test(lower)&&state.task==='cache')reply='The reviewer caught a stale-cache risk after a new push. The worker included pushed_at in the key and added a regression test. Open Changes to inspect the sample patch.';
 else reply='I’ve added your follow-up to this sample conversation. Model execution is not connected in this prototype; you can inspect code changes, adjust task defaults, or replay the caching session to explore the workflow.';
 const html=`<div class="followup-message"><div class="message-meta"><span class="mini-avatar">C</span><strong>You</strong><time>Just now</time></div><p>${esc(message)}</p><div class="message-meta"><span class="agent-avatar">${icon('code')}</span><strong>CheapOS</strong><span class="model-label">Demo response</span></div><p>${esc(reply)}</p></div>`;task.messages=(task.messages||'')+html;$('#followups').insertAdjacentHTML('beforeend',html);openView('activity');$('#followups').lastElementChild.scrollIntoView({behavior:'smooth',block:'end'});
}
$$('.tab').forEach(b=>b.onclick=()=>openView(b.dataset.view));$$('.task').forEach(b=>b.onclick=()=>selectTask(b.dataset.task));$$('.project').forEach(b=>b.onclick=()=>selectTask(b.dataset.project==='personal-site'?'personal':'cache'));
$('#new-task').onclick=newTask;$('#search-trigger').onclick=openSearch;['settings-trigger','composer-settings','session-settings'].forEach(id=>$('#'+id).onclick=()=>openSettings());$('#mode-select').onclick=()=>openSettings(true);$('#replay').onclick=replay;
$('#composer').onsubmit=e=>{e.preventDefault();submitMessage()};$('#task-input').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();submitMessage()}};
$('#toggle-inspector').onclick=()=>{if(matchMedia('(max-width:1000px)').matches)$('#inspector').classList.toggle('show');else $('#inspector').classList.toggle('hidden')};
$('#compact-session').onclick=()=>$('#inspector').classList.toggle('show');
$('#sidebar-toggle').onclick=()=>{if(matchMedia('(max-width:700px)').matches)$('#sidebar').classList.remove('show');else{$('#sidebar').classList.add('collapsed');$('.mobile-menu').style.display='flex'}};
$('#mobile-menu').onclick=()=>{if(matchMedia('(max-width:700px)').matches)$('#sidebar').classList.toggle('show');else{$('#sidebar').classList.remove('collapsed');$('.mobile-menu').style.display='none'}};
document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&['k','n',','].includes(e.key.toLowerCase())){e.preventDefault();if($('dialog[open]'))return;if(e.key.toLowerCase()==='k')openSearch();else if(e.key.toLowerCase()==='n')newTask();else openSettings()}if(e.key==='Escape'){if(state.replaying)selectTask('cache');$('#sidebar').classList.remove('show');$('#inspector').classList.remove('show')}});
selectTask('cache');updateComposer();
if(document.modelContext?.registerTool){
 const lifecycle=new AbortController(),tools=[
  {name:'read_session',title:'Read CheapOS session',description:'Read the displayed sample coding session and its simulated usage.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true,untrustedContentHint:true},execute(input){if(!input||typeof input!=='object'||Object.keys(input).length)throw new Error('Expected an empty object');const t=tasks[state.task];return{task:t.title,view:state.view,simulated:true,files:t.files.map(f=>f.path),tests:t.tests.length,workerTokens:t.tokens,reviewerTokens:t.reviewTokens}}},
  {name:'navigate_session',title:'Open a session view',description:'Navigate the current sample task to Activity, Changes, or Tests.',inputSchema:{type:'object',properties:{view:{type:'string',enum:['activity','changes','tests']}},required:['view'],additionalProperties:false},annotations:{readOnlyHint:false,untrustedContentHint:false},execute(input){if(!input||!['activity','changes','tests'].includes(input.view)||Object.keys(input).some(k=>k!=='view'))throw new Error('Choose activity, changes, or tests');openView(input.view);return{view:state.view}}}
 ];for(const tool of tools){try{Promise.resolve(document.modelContext.registerTool(tool,{signal:lifecycle.signal})).catch(()=>{})}catch{}}window.addEventListener('pagehide',()=>lifecycle.abort(),{once:true});
}
