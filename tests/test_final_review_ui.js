const test=require('node:test');
const assert=require('node:assert/strict');
const ui=require('../dist/branch_ui.js');

const patch='diff --git a/main.py b/main.py\nindex aaaa..bbbb 100644\n--- a/main.py\n+++ b/main.py\n@@ -8,2 +8,3 @@ function\n-old\n+new\n+<script>alert("x")</script>\n unchanged\n';
test('unified review shows old/new positions, additions, removals and escaped source',()=>{
 const section=ui.reviewDiffs(patch)[0],html=ui.reviewDiffMarkup(section);
 assert.equal(section.path,'main.py');assert.equal(section.text,patch);
 assert.match(html,/review-diff-line remove/);assert.match(html,/review-diff-line add/);
 assert.match(html,/>8<\/span><span class="review-line-number"><\/span>/);
 assert.match(html,/review-line-number">9<\/span><span class="review-line-number">10<\/span>/);
 assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
 assert.match(ui.reviewDiffMarkup(section,true),/review-raw/);
});
test('Git paths cover spaces, octal UTF-8, deletes, renames and binary files',()=>{
 assert.equal(ui.diffPath('"b/caf\\303\\251.py"'),'café.py');
 assert.equal(ui.diffPath('"b/a\\tfile.py"'),'a\tfile.py');
 assert.equal(ui.diffPath('"b/😀.py"'),'😀.py');
 const renamed=ui.reviewDiffs('diff --git a/old name.txt b/new name.txt\nsimilarity index 100%\nrename from old name.txt\nrename to new name.txt\n')[0];
 assert.equal(renamed.path,'new name.txt');assert.equal(renamed.oldPath,'old name.txt');
 const removed=ui.reviewDiffs('diff --git a/deleted.py b/deleted.py\n--- a/deleted.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-old\n')[0];assert.equal(removed.path,'deleted.py');
 const binary=ui.reviewDiffs('diff --git a/logo.png b/logo.png\nGIT binary patch\nliteral 3\nabc\n')[0];
 assert.equal(binary.binary,true);assert.match(ui.reviewDiffMarkup(binary),/Binary content cannot be displayed/);assert.match(ui.reviewDiffMarkup(binary),/GIT binary patch/);
 assert.equal(ui.reviewDiffs('diff --git a/a b/c.png b/a b/c.png\nGIT binary patch\n')[0].path,'a b/c.png');
 assert.equal(ui.reviewDiffs('diff --git a/old b/new\nrename from a/old name\nrename to a/new name\n')[0].path,'a/new name');
});
test('page boundaries inside a hunk or filename reconstruct the exact diff without duplication',()=>{
 for(const cut of [3,25,100]){
  const full=patch+'diff --git a/café.txt b/café.txt\n--- a/café.txt\n+++ b/café.txt\n@@ -1 +1 @@\n-old\n+😀\n';
  const chars=Array.from(full),state=ui.finalDiffState({manifest:{id:'m'},diff:chars.slice(0,cut).join(''),next_cursor:cut,diff_length:chars.length});
  assert.equal(state.get().complete,false);
  state.append({offset:cut,total:chars.length,manifest_id:'m',diff:chars.slice(cut).join(''),next_cursor:null});
  assert.equal(state.get().text,full);assert.equal(state.get().complete,true);
  const sections=ui.reviewDiffs(state.get().text);assert.equal(sections.length,2);assert.equal(sections[1].path,'café.txt');
 }
});
test('stale, skipped and truncated pages cannot become a complete review',()=>{
 const create=()=>ui.finalDiffState({manifest:{id:'m'},diff:'abc',next_cursor:3,diff_length:6});
 for(const change of [{manifest_id:'other'},{offset:4},{total:7},{next_cursor:3}]){
  const state=create();assert.throws(()=>state.append({offset:3,total:6,manifest_id:'m',diff:'def',next_cursor:null,...change}));assert.equal(state.get().complete,false);
 }
 const state=create();assert.throws(()=>state.append({offset:3,total:6,manifest_id:'m',diff:'d',next_cursor:null}),/complete diff/);assert.equal(state.get().complete,false);
 assert.equal(ui.finalDiffState({diff:'',next_cursor:null,diff_length:0}).get().complete,true);
 assert.equal(ui.finalDiffState({diff_length:0}).get().complete,false);
});
test('review overview surfaces blockers and saved evidence without inventing passing checks',()=>{
 const task={title:'Build <a thing>',branch_run:{feature_ref:'refs/heads/feature/test',readiness:{checks:[{command:['python3','-m','unittest'],record:{passed:true}},{command:['other'],record:{passed:false}}],review:{decision:'REQUEST_CHANGES',feedback:'Fix <issue>'}},items:[{title:'Implement',status:'committed'}]}};
 const preview={blocker:'Target checkout has uncommitted changes',destination:'/projects/main <checkout>',feature_tip:'a'.repeat(40),target_tip:'b'.repeat(40),target_ref:'refs/heads/main',manifest:{files:[{path:'src/main.py',status:'M',added_lines:2,removed_lines:1}]}};
 const html=ui.finalReviewMarkup(task,preview);
 assert.match(html,/1\/2 checks passed/);assert.doesNotMatch(html,/Final review approved/);
 assert.match(html,/Target checkout has uncommitted changes/);assert.match(html,/python3 -m unittest/);assert.match(html,/Fix &lt;issue&gt;/);assert.match(html,/Build &lt;a thing&gt;/);
 assert.match(html,/data-file-search/);assert.match(html,/data-viewed/);assert.match(html,/Approve &amp; merge locally/);
 assert.match(html,/Merge location: <code>\/projects\/main &lt;checkout&gt;<\/code>/);
 assert.deepEqual(ui.reviewFiles({manifest:['file']}),[{path:'file'}]);
});
test('actual preview loader displays progress before awaiting the API and ignores detached results',async()=>{
 const fs=require('node:fs'),vm=require('node:vm'),source=fs.readFileSync(require.resolve('../dist/branch_ui.js'),'utf8');
 const snippet=source.slice(source.indexOf(' async function loadFinal(task,slot)'),source.indexOf(' async function requestRevision'));
 let release,shown;const calls=[],node={isConnected:true,innerHTML:'',setAttribute(){},querySelector:()=>({})};
 const context={document:{createElement:()=>node},api:(url,body)=>{calls.push([url,body]);return new Promise(r=>release=r);}};
 vm.createContext(context);vm.runInContext(snippet,context);
 const pending=context.loadFinal({id:'saved-task'},{replaceChildren:el=>shown=el});
 assert.equal(shown,node);assert.match(node.innerHTML,/Preparing your review/);assert.equal(calls[0][0],'/tasks/saved-task/branch-final-preview');
 node.isConnected=false;release({preview_id:'late'});await pending;
 assert.match(node.innerHTML,/Preparing your review/);assert.equal(calls.length,1);
});
test('app view switching retains this task’s review DOM and discards another task’s preview',()=>{
 const fs=require('node:fs'),vm=require('node:vm'),source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8');
 const snippet=source.slice(source.indexOf('function renderView()'),source.indexOf('function eventDetail('));
 const plan={id:'plan-view',dataset:{task:'a'},innerHTML:'retained review',classList:{toggle(){}},setAttribute(){}},chat={...plan,id:'chat-view',dataset:{},innerHTML:'chat'},changes={...plan,id:'changes-view',dataset:{task:'a'},innerHTML:'retained diff'};
 let renders=0;const state={view:'chat',task:{id:'a'}},context={state,CheapOSBranchUI:{savedPlan:()=>true},$:()=>({hidden:false}),$$:selector=>selector==='.view'?[chat,plan,changes]:[],renderChat(){},bindTerminalCopy(){},branchUI:{renderPlan:()=>renders++}};
 // Optional history-banner lookup must return no existing node.
 context.$=selector=>selector.includes('view-history-notice')?null:{hidden:false};vm.createContext(context);vm.runInContext(snippet,context);
 context.renderView();assert.equal(plan.innerHTML,'retained review');assert.equal(changes.innerHTML,'retained diff');
 state.view='plan';context.renderView();assert.equal(plan.innerHTML,'retained review');assert.equal(changes.innerHTML,'retained diff');assert.equal(renders,1);
 state.view='chat';state.task={id:'b'};context.renderView();assert.equal(plan.innerHTML,'');assert.equal(plan.dataset.task,undefined);assert.equal(changes.innerHTML,'');assert.equal(changes.dataset.task,undefined);
});

test('renderSidebar does not attach task click handler to plan-view container',()=>{
 const fs=require('node:fs'),vm=require('node:vm'),source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8');
 const snippet=source.slice(source.indexOf('function renderSidebar()'),source.indexOf('async function pauseForLifecycle'));
 const list={dataset:{},innerHTML:''};
 const planView={id:'plan-view',dataset:{task:'task-1'},onclick:null};
 const sidebarTaskBtn={dataset:{task:'task-1'},onclick:null};
 const state={preferences:{execution:{}},projects:[],tasks:[{id:'task-1',title:'Test',source:'/repo',status:'running'}],project:null,historyView:'active',task:{id:'task-1'}};
 const context={
   state,
   $:s=>s==='#task-list'?list:s==='#task-total'?{textContent:''}:s==='#connection-indicator'?{textContent:''}:s==='#history-menu'?{innerHTML:'',setAttribute(){},onclick:null}:{},
   $$:(selector,root=document)=>{
     if(root===list){
       if(selector.includes('button.task[data-task]'))return [sidebarTaskBtn];
       return [];
     }
     if(selector.includes('[data-task]'))return [planView,sidebarTaskBtn];
     return [];
   },
   esc:s=>s,date:s=>s,icon:()=>'',taskBusy:()=>false,CheapOSGuide:{connectionNotice:()=>({}),sidebarOrder:t=>t,projectName:()=>'repo'},
   saveSidebarPrefs(){},projectMenu(){},selectTask(){},taskMenu(){},chooseProject(){},findMenuAnchor:()=>null,
   document:{activeElement:null},sidebarMenu:null,sidebarPrefs:{}
 };
 vm.createContext(context);vm.runInContext(snippet,context);
 context.renderSidebar();
 assert.equal(planView.onclick,null);
 assert.notEqual(sidebarTaskBtn.onclick,null);
});


test('diverged preview offers a separate update action without authorizing target merge',()=>{
 const task={branch_run:{feature_ref:'refs/heads/feature/task',target_ref:'refs/heads/main',readiness:{checks:[]}}};
 const preview={files:[],merge_available:false,blocker:'Target has new commits',integration_readiness:{actions:['update_resolve']}};
 assert.match(ui.finalReviewMarkup(task,preview),/data-integration-prepare>Update &amp; resolve/);
 assert.doesNotMatch(ui.finalReviewMarkup(task,{...preview,integration_readiness:{actions:[]}}),/data-integration-prepare/);
});

test('known conflicts offer an agent task instead of repeating the failed update',()=>{
 const task={branch_run:{feature_ref:'feature',target_ref:'main',readiness:{checks:[]}}};
 const html=ui.finalReviewMarkup(task,{files:[],integration_readiness:{code:'conflicts',actions:['update_resolve']}});
 assert.match(html,/data-integration-prepare>Update &amp; resolve/);
 assert.doesNotMatch(html,/data-update-branch/);
});

test('merge publishes the confirmed task without waiting for a slow refresh',async()=>{
 const task={id:'task'},saved={id:'task',status:'completed',branch_run:{status:'merged'}};let published;
 const result=await ui.mergeAndPublish({task,values:{approved:true},api:async()=>saved,onTask:value=>published=value,refresh:()=>new Promise(()=>{})});
 assert.equal(published,saved);assert.equal(result,saved);
});
test('failed merge does not publish completion, and another task response is ignored',async()=>{
 let published=false;
 await assert.rejects(ui.mergeAndPublish({task:{id:'task'},api:async()=>{throw Error('merge failed')},onTask:()=>published=true}));
 assert.equal(published,false);
 await ui.mergeAndPublish({task:{id:'task'},api:async()=>({id:'other',branch_run:{status:'merged'}}),onTask:()=>published=true});
 assert.equal(published,false);
});

test('merge gives immediate feedback and double clicks share one pending request',async()=>{
 let release,calls=0,pending=0,published;
 const options={task:{id:'pending-merge'},values:{preview_id:'preview',approved:true},
  api:()=>{calls++;return new Promise(resolve=>release=resolve);},onPending:()=>pending++,onTask:t=>published=t};
 const first=ui.mergeAndPublish(options),second=ui.mergeAndPublish(options);
 assert.equal(pending,1);assert.equal(first,second);assert.equal(published,undefined);
 await Promise.resolve();assert.equal(calls,1);
 const accepted={id:'pending-merge',branch_run:{status:'merging',target_ref:'refs/heads/main',merge_progress:{label:'Checking reviewed changes'}}};
 release(accepted);await first;assert.equal(published,accepted);
 assert.match(ui.mergeProgressMarkup(accepted),/Checking reviewed changes/);
 assert.equal(ui.projectRun(accepted).merged,false);
});

test('lost merge response reconciles the exact saved approval without another POST',async()=>{
 const calls=[],saved={id:'lost-merge',branch_run:{status:'merging',merge_operation:{id:'operation'},merge_preview_id:'preview'}};
 const result=await ui.mergeAndPublish({task:{id:'lost-merge'},values:{preview_id:'preview',approved:true},api:async(path,body)=>{
  calls.push([path,body]);if(body)throw Error('Connection lost');return saved;
 }});
 assert.equal(result,saved);assert.equal(calls.length,2);assert.equal(calls[1][1],undefined);
 saved.branch_run.merge_preview_id='other';
 await assert.rejects(ui.mergeAndPublish({task:{id:'lost-merge'},values:{preview_id:'preview',approved:true},api:async(path,body)=>{
  if(body)throw Error('Connection lost');return saved;
 }}),/Connection lost/);
});

test('merge progress never presents an accepted approval as a completed merge',()=>{
 const task={branch_run:{status:'merging',target_ref:'refs/heads/<main>',merge_progress:{label:'Confirming merge'}}};
 assert.match(ui.mergeProgressMarkup(task),/Confirming merge/);
 assert.match(ui.mergeProgressMarkup(task),/&lt;main&gt;/);
 task.branch_run.status='paused';assert.equal(ui.mergeProgressMarkup(task),'');
 task.branch_run.status='merged';task.branch_run.merge_receipt={stage:'completed'};
 assert.equal(ui.projectRun(task).merged,true);assert.equal(ui.mergeProgressMarkup(task),'');
});

test('dense replacements expose deleted characters without truncation',()=>{
 const removed='sendChat();'.repeat(50),added='hideSample();';
 const text=`diff --git a/app.js b/app.js\n--- a/app.js\n+++ b/app.js\n@@ -1 +1 @@\n-${removed}\n+${added}\n`;
 const html=ui.reviewDiffMarkup(ui.reviewDiffs(text)[0]);
 assert.match(html,/550 removed characters/);
 assert.match(html,/Long changed lines/);
 assert.match(html,/review-inline-change/);
 assert.equal((html.match(/sendChat/g)||[]).length,50);
 assert.match(ui.reviewDiffMarkup(ui.reviewDiffs(text)[0],true),/sendChat/);
});

function diffElements(){
 const nodes=new Map();
 const node=()=>({value:'',innerHTML:'',textContent:'',hidden:false,disabled:false,scrollTop:0,
  classList:{toggle(){return true;}},setAttribute(){},focus(){},scrollIntoView(){},querySelectorAll(){return [];},querySelector(){return null;}});
 return {isConnected:true,classList:{toggle(){return true;}},querySelector(s){if(!nodes.has(s))nodes.set(s,node());return nodes.get(s);}};
}
const reviewTask={id:'task',branch_run:{status:'ready_for_merge'}};
const reviewPreview={preview_id:'inspected',merge_available:true,manifest:{id:'manifest',files:[{path:'main.py',status:'M'}]},diff:patch,next_cursor:null,diff_length:Array.from(patch).length};
test('Changes mounts a complete first-response diff without requiring another page',()=>{
 const d=diffElements();let calls=0;
 const mounted=ui.mountFinalDiff(d,reviewTask,reviewPreview,()=>{calls++;throw Error('No page should be fetched');});
 assert.match(d.querySelector('.review-diff-viewport').innerHTML,/review-diff-line add/);
 assert.match(d.querySelector('.review-diff-viewport').innerHTML,/new/);
 assert.equal(d.querySelector('[data-merge]').disabled,false);assert.equal(calls,0);
 d.querySelector('[data-viewed]').onclick();assert.equal(mounted.viewed.size,1);
 assert.equal(d.querySelector('[data-review-progress]').textContent,'1 of 1 files reviewed');
 d.querySelector('[data-evidence]').onclick({currentTarget:{setAttribute(){}}});
 assert.equal(d.querySelector('.review-evidence').hidden,false);assert.equal(d.querySelector('.review-workspace').hidden,true);
});
test('paged review keeps merge disabled through failure and a blocker in the recovered page',async()=>{
 const d=diffElements(),cut=40;let rejectPage,resolvePage;
 const mounted=ui.mountFinalDiff(d,reviewTask,{...reviewPreview,diff:patch.slice(0,cut),next_cursor:cut},()=>new Promise((resolve,reject)=>{resolvePage=resolve;rejectPage=reject;}));
 assert.equal(d.querySelector('[data-merge]').disabled,true);
 rejectPage(Error('Temporary connection failure'));await new Promise(setImmediate);
 assert.match(d.querySelector('.branch-error').textContent,/Temporary connection/);assert.equal(d.querySelector('[data-retry-diff]').hidden,false);
 d.querySelector('[data-retry-diff]').onclick();
 resolvePage({offset:cut,total:patch.length,manifest_id:'manifest',diff:patch.slice(cut),next_cursor:null,blocker:'Target changed'});await new Promise(setImmediate);
 assert.equal(mounted.state.get().complete,true);assert.match(d.querySelector('.review-diff-viewport').innerHTML,/review-diff-line add/);
 assert.equal(d.querySelector('[data-merge]').disabled,true);assert.equal(d.querySelector('.review-blocker').textContent,'Target changed');
});
test('Plan never fetches or mounts a diff; every review entry uses Changes and reuses its current preview',()=>{
 const fs=require('node:fs'),vm=require('node:vm'),source=fs.readFileSync(require.resolve('../dist/branch_ui.js'),'utf8');
 const snippet=source.slice(source.indexOf(' function renderPlan(task)'),source.indexOf(' async function loadFinal(task,slot)'));
 const content={},link={},plan={dataset:{},querySelector:s=>s==='[data-plan-content]'?content:link},changes={dataset:{},classList:{remove(){}}};
 let loaded=0,navigated=0;const context={document:{querySelector:s=>s==='#plan-view'?plan:changes},planMarkup:()=>'<article>Approved scope</article>',options:{showChanges:()=>navigated++},loadFinal:(t,p)=>{assert.equal(p,changes);loaded++;}};
 vm.runInNewContext(snippet,context);
 const t={id:'a',branch_run:{status:'ready_for_merge',authorization_ref:'auth',readiness:{id:'r1'},expected_feature_tip:'tip'}};
 context.renderPlan(t);assert.equal(loaded,0);assert.doesNotMatch(plan.innerHTML,/data-review-slot|Jump to results/);
 link.onclick();assert.equal(navigated,1);
 context.renderChanges(t);context.renderPlan(t);context.renderChanges(t);assert.equal(loaded,1);
 t.branch_run.readiness.id='r2';context.renderChanges(t);assert.equal(loaded,2);
});

test('interactive chat sends approval and deferred review to Changes without a second diff',()=>{
 const fs=require('node:fs'),vm=require('node:vm'),source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8');
 const snippet=source.slice(source.indexOf('function commitReviewLink(task)'),source.indexOf('function commitDecisionMarkup(task)'));
 const context={CheapOSGuide:{commitDeferred:task=>Boolean(task.deferred)}};vm.createContext(context);vm.runInContext(snippet,context);
 for(const task of [{},{deferred:true},{commit_pending:true}]){
  const html=context.commitReviewLink(task);assert.match(html,/data-chat-action="changes"/);assert.match(html,/Review changes/);assert.doesNotMatch(html,/<form|<pre|data-commit-action/);
 }
 assert.match(source,/else if\(CheapOSGuide.canCommit\(task\)\)decision=commitReviewLink\(task\)/);
});
