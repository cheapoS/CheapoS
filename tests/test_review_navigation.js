const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const app=fs.readFileSync('dist/app.js','utf8'),branch=fs.readFileSync('dist/branch_ui.js','utf8');
function fixture(){
 const task={id:'saved',updated_at:'2026-09-18T20:00:00Z',branch_run:{status:'paused'}};
 const panel={dataset:{signature:'old empty view'},innerHTML:'',querySelector:()=>null};
 const state={task,selection:1,view:'chat'},reads=[],rendered=[];
 const context={state,esc:s=>String(s).replaceAll('<','&lt;'),rememberView(){},renderComposer(){},viewMemory:new Map(),
  $:selector=>selector==='#changes-view'?panel:{scrollTo(){},scrollHeight:0},$$:()=>[],
  api:(...args)=>new Promise((resolve,reject)=>reads.push({args,resolve,reject})),
  branchUI:{renderChanges:t=>{rendered.push(t);panel.innerHTML=t.branch_run.readiness?'Current diff':'Review is not ready';}}};
 vm.createContext(context);
 vm.runInContext(app.slice(app.indexOf('function setView(view)'),app.indexOf('function renderTask(')),context);
 vm.runInContext(app.slice(app.indexOf('function renderChanges()'),app.indexOf('async function requestCommitReview(')),context);
 context.renderView=context.renderTask=()=>context.renderChanges();
 return {task,state,panel,reads,rendered,context};
}
test('Review changes fetches current saved work and replaces stale empty state without a reload',async()=>{
 const f=fixture();f.context.setView('changes');
 assert.match(f.panel.innerHTML,/Loading latest changes/);assert.equal(f.panel.dataset.signature,undefined);
 f.context.setView('changes');assert.equal(f.reads.length,1);
 assert.deepEqual(f.reads[0].args,['/tasks/saved']);
 const saved={...f.task,branch_run:{status:'ready_for_merge',readiness:{id:'review'}}};
 f.reads[0].resolve(saved);await new Promise(setImmediate);
 assert.equal(f.state.task,saved);assert.equal(f.panel.innerHTML,'Current diff');
 assert.equal(f.rendered.length,1);
 f.context.setView('chat');f.context.setView('changes');assert.equal(f.reads.length,2);
 f.reads[1].resolve(saved);await new Promise(setImmediate);
});
test('late review read cannot overwrite a newer action or a different selected task',async()=>{
 for(const switchChat of [false,true]){
  const f=fixture();f.context.setView('changes');
  const newer={...f.task,id:switchChat?'other':'saved',updated_at:'2026-09-18T20:01:00Z',branch_run:{status:'running'}};
  f.state.task=newer;if(switchChat)f.state.selection++;
  f.reads[0].resolve({...f.task,branch_run:{readiness:{id:'stale'}}});await new Promise(setImmediate);
  assert.equal(f.state.task,newer);assert.equal(f.rendered.length,switchChat?0:1);
 }
});
test('failed review read exposes loading failure instead of claiming there is nothing to review',async()=>{
 const f=fixture();f.context.setView('changes');f.reads[0].reject(Error('<offline>'));await new Promise(setImmediate);
 assert.match(f.panel.innerHTML,/Could not load saved changes/);assert.match(f.panel.innerHTML,/&lt;offline>/);
 assert.match(f.panel.innerHTML,/data-retry-changes/);assert.equal(f.rendered.length,0);
 await Promise.all([f.context.refreshChanges(),(async()=>{
  assert.equal(f.reads.length,2);f.reads[1].resolve(f.task);
 })()]);
 assert.equal(f.panel.innerHTML,'Review is not ready');
});
test('accepted integration update publishes progress and opens Chat before background refresh completes',async()=>{
 for(const unattended of [false,true])for(const changedSelection of [false,true]){
  const task={id:'saved'},saved={id:'saved',status:'running',integration_preparation:{status:'running'}};
  const state={task:changedSelection?{id:'other'}:task},events=[];let callback,finish;
  const integration={bind:(host,t,readiness,api,onSaved)=>callback=onSaved};
  const context={state,task,slot:{dataset:{}},d:{},preview:{},integrationState:{},api(){},
   integration,CheapOSIntegration:integration,commitPreviews:new Map(),$:()=>({}),
   getState:()=>state,options:{receiveUpdatedTask:t=>{state.task=t;events.push('published');},showChat:()=>events.push('chat')},
   setView:view=>{assert.equal(state.task,saved);events.push(view);},refresh:()=>new Promise(resolve=>{events.push('refresh');finish=resolve;})};
  const text=unattended?branch:app,start=text.indexOf(unattended?'  integration.bind(d,task,preview.integration_readiness':'  const bindIntegration=(host,readiness)=>');
  const end=text.indexOf(unattended?'  const leave=':'  if(CheapOSGitWorkflow.enabled(task))',start);
  assert.ok(start>=0&&end>start);vm.runInNewContext(text.slice(start,end)+(unattended?'':'bindIntegration({},{});'),context);
  const pending=callback(saved);
  assert.deepEqual(events,changedSelection?['refresh']:unattended?['published','chat','refresh']:['chat','refresh']);
  if(changedSelection)assert.equal(state.task.id,'other');
  finish();await pending;
 }
});
