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
 const preview={blocker:'Target checkout has uncommitted changes',feature_tip:'a'.repeat(40),target_tip:'b'.repeat(40),target_ref:'refs/heads/main',manifest:{files:[{path:'src/main.py',status:'M',added_lines:2,removed_lines:1}]}};
 const html=ui.finalReviewMarkup(task,preview);
 assert.match(html,/1\/2 checks passed/);assert.doesNotMatch(html,/Final review approved/);
 assert.match(html,/Target checkout has uncommitted changes/);assert.match(html,/python3 -m unittest/);assert.match(html,/Fix &lt;issue&gt;/);assert.match(html,/Build &lt;a thing&gt;/);
 assert.match(html,/data-file-search/);assert.match(html,/data-viewed/);assert.match(html,/Approve &amp; merge locally/);
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
 const plan={id:'plan-view',dataset:{task:'a'},innerHTML:'retained review',classList:{toggle(){}},setAttribute(){}},chat={...plan,id:'chat-view',dataset:{},innerHTML:'chat'};
 let renders=0;const state={view:'chat',task:{id:'a'}},context={state,CheapOSBranchUI:{savedPlan:()=>true},$:()=>({hidden:false}),$$:selector=>selector==='.view'?[chat,plan]:[],renderChat(){},bindTerminalCopy(){},branchUI:{renderPlan:()=>renders++}};
 // Optional history-banner lookup must return no existing node.
 context.$=selector=>selector.includes('view-history-notice')?null:{hidden:false};vm.createContext(context);vm.runInContext(snippet,context);
 context.renderView();assert.equal(plan.innerHTML,'retained review');
 state.view='plan';context.renderView();assert.equal(plan.innerHTML,'retained review');assert.equal(renders,1);
 state.view='chat';state.task={id:'b'};context.renderView();assert.equal(plan.innerHTML,'');assert.equal(plan.dataset.task,undefined);
});
