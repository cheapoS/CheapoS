const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const app=fs.readFileSync(path.join(__dirname,'../dist/app.js'),'utf8');
const code=app.slice(app.indexOf('let tokenRefresh=null;'),app.indexOf('function dialog('));
const response=(status,data)=>({status,ok:status===200,headers:{get:()=>null},json:async()=>data});
const expired=()=>response(403,{code:'local_token_expired',error:'Local request token expired. Refresh the app.'});
function fixture(fetch){const state={token:'old',task:{id:'saved'},draft:'keep my draft',view:'changes'},calls=[];
 const context={state,fetch:async(...args)=>{calls.push(args);return fetch(...args);}};vm.createContext(context);vm.runInContext(code,context);return {context,state,calls};}
test('expired token renews the local connection and loads the same review without resetting the page',async()=>{
 const f=fixture(async(url,options)=>url==='/api/bootstrap'?response(200,{app:'CheapOS',token:'new',tasks:[]}):
  options.headers['X-CheapOS-Token']==='old'?expired():response(200,{diff:'+saved change'}));
 const task=f.state.task,result=await f.context.api('/tasks/saved/branch-final-preview',{});
 assert.equal(result.diff,'+saved change');assert.equal(f.calls.length,3);assert.equal(f.state.token,'new');
 assert.equal(f.state.task,task);assert.equal(f.state.draft,'keep my draft');assert.equal(f.state.view,'changes');
 assert.equal(f.calls[0][1].body,f.calls[2][1].body);
});
test('concurrent expired requests share renewal and preserve their original submitted bodies',async()=>{
 let release;const f=fixture(async(url,options)=>url==='/api/bootstrap'?await new Promise(resolve=>release=resolve):
  options.headers['X-CheapOS-Token']==='old'?expired():response(200,{ok:true}));
 const body={approved:true,preview_id:'original'},a=f.context.api('/tasks/one/branch-merge',body),b=f.context.api('/tasks/two/branch-final-preview',{});
 await new Promise(setImmediate);body.preview_id='different';
 assert.equal(f.calls.filter(c=>c[0]==='/api/bootstrap').length,1);
 release(response(200,{app:'CheapOS',token:'new'}));await Promise.all([a,b]);
 const merges=f.calls.filter(c=>c[0].endsWith('/branch-merge'));assert.equal(merges.length,2);assert.equal(merges[0][1].body,merges[1][1].body);
});
test('only explicit pre-dispatch token expiry is retried, and only once',async()=>{
 for(const data of [{error:'Forbidden'},{code:'stale_preview',error:'Preview expired'},{error:'Local request token expired. Refresh the app.'}]){
  const f=fixture(async()=>response(403,data));await assert.rejects(f.context.api('/tasks/x/branch-merge',{}));assert.equal(f.calls.length,1);
 }
 const f=fixture(async url=>url==='/api/bootstrap'?response(200,{app:'CheapOS',token:'new'}):expired());
 await assert.rejects(f.context.api('/tasks/x/branch-merge',{}));assert.equal(f.calls.length,3);
 const offline=fixture(async()=>{throw Error('unknown outcome');});await assert.rejects(offline.context.api('/tasks/x/branch-merge',{}));assert.equal(offline.calls.length,1);
});
test('failed or invalid renewal never replays a mutation and does not discard the draft',async()=>{
 for(const bootstrap of [response(500,{error:'offline'}),response(200,{app:'Other',token:'new'}),response(200,{app:'CheapOS',token:''})]){
  const f=fixture(async url=>url==='/api/bootstrap'?bootstrap:expired());
  await assert.rejects(f.context.api('/tasks/saved/branch-final-preview',{}));assert.equal(f.calls.length,2);assert.equal(f.state.token,'old');assert.equal(f.state.draft,'keep my draft');
 }
});
