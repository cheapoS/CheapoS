const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8');
const marker='// Restart modal wiring';
assert.ok(source.includes(marker));
const code=source.slice(source.indexOf(marker),source.indexOf('\n})();',source.indexOf(marker))+6);
function fixture(responses={}){
 const calls=[],toasts=[],timers=new Map(),nodes=new Map();let now=0,id=0,reloads=0;
 const node=selector=>{if(!nodes.has(selector))nodes.set(selector,{close(){},showModal(){},addEventListener(){},disabled:false});return nodes.get(selector);};
 const response=(data={},status=200)=>({ok:status>=200&&status<300,status,json:async()=>data});
 const fetch=async(path,options={})=>{
  calls.push({path,options});
  if(responses[path])return responses[path](options,calls.filter(c=>c.path===path).length,response);
  return response(path==='/api/connection'?{app:'CheapOS',token:'new'}:{status:'restarting'});
 };
 const ctx={fetch,AbortController,state:{token:'old'},toast:m=>toasts.push(m),console,
  $:node,document:{getElementById:id=>node('#'+id)},window:{location:{reload(){reloads++;}}},
  Date:{now:()=>now},setTimeout:(fn,ms)=>{timers.set(++id,{fn,at:now+ms});return id;},clearTimeout:id=>timers.delete(id)};
 vm.runInNewContext(code,ctx);
 async function click(selector='#restart-webapp'){
  let done=false,error;
  Promise.resolve(node(selector).onclick()).then(()=>done=true,e=>{error=e;done=true;});
  for(let i=0;i<1500&&!done;i++){
   for(let j=0;j<12;j++)await Promise.resolve();
   if(done)break;
   if(timers.size){const [key,t]=[...timers].sort((a,b)=>a[1].at-b[1].at)[0];timers.delete(key);now=t.at;t.fn();}
  }
  assert.equal(done,true,'operation must settle without a real-time wait');if(error)throw error;
 }
 return {calls,toasts,click,get reloads(){return reloads},get now(){return now},response};
}
function validPost(call){
 assert.equal(call.options.method,'POST');
 assert.equal(call.options.headers['Content-Type'],'application/json');
 assert.equal(call.options.headers['X-CheapOS-Token'],'old');
 assert.deepEqual(JSON.parse(call.options.body),{});
}
test('restart waits for a new backend token, not a successful old response',async()=>{
 const f=fixture({'/api/connection':(_,n,r)=>r({app:'CheapOS',token:n<3?'old':'new'})});await f.click();
 validPost(f.calls.find(c=>c.path==='/api/restart'));
 assert.equal(f.calls[0].path,'/api/restart');assert.equal(f.reloads,1);
 assert.equal(f.calls.filter(c=>c.path==='/api/connection').length,3);assert.equal(f.now,1500);
});
test('reconnect never waits for the full bootstrap payload',async()=>{
 const f=fixture({'/api/bootstrap':()=>{throw Error('Task restoration is busy');}});
 await f.click();assert.equal(f.reloads,1);
 assert.equal(f.calls.filter(c=>c.path==='/api/bootstrap').length,0);
 assert.equal(f.calls.filter(c=>c.path==='/api/connection').length,1);
});
test('rejected restart does not poll or reload',async()=>{
 const f=fixture({'/api/restart':(_,n,r)=>r({error:'Denied'},403)});await f.click();
 assert.equal(f.calls.length,1);assert.equal(f.reloads,0);assert.match(f.toasts.at(-1),/403|Denied/);
});
test('wrong app, missing token, and old boot never reload before the restart deadline',async()=>{
 const f=fixture({'/api/connection':(_,n,r)=>r(n%3===0?{app:'CheapOS',token:'old'}:n%3===1?{app:'Other',token:'new'}:{app:'CheapOS'})});await f.click();
 assert.equal(f.reloads,0);assert.equal(f.calls.filter(c=>c.path==='/api/connection').length,120);
 assert.equal(f.now,60000);assert.match(f.toasts.at(-1),/failed|did not/i);
});
test('a hung restart request is aborted and finishes visibly',async()=>{
 const f=fixture({'/api/restart':options=>new Promise((_,reject)=>options.signal?.addEventListener('abort',()=>reject(new Error('Timed out'))))});await f.click();
 assert.equal(f.reloads,0);assert.ok(f.now>0&&f.now<=10000);assert.match(f.toasts.at(-1),/failed|timed out/i);
});
test('combined action authenticates gateway refresh before restarting',async()=>{
 const f=fixture();await f.click('#restart-webapp-omni');
 assert.deepEqual(f.calls.slice(0,2).map(c=>c.path),['/api/gateway/refresh','/api/restart']);
 validPost(f.calls[0]);validPost(f.calls[1]);assert.equal(f.reloads,1);
});
test('failed gateway refresh is visible and does not claim success',async()=>{
 const f=fixture({'/api/gateway/refresh':(_,n,r)=>r({error:'Denied'},403)});await f.click('#restart-webapp-omni');
 assert.equal(f.calls.length,1);assert.equal(f.reloads,0);assert.match(f.toasts.at(-1),/403|Denied/);
 const g=fixture({'/api/gateway/refresh':(_,n,r)=>r({error:'Denied'},403)});await g.click('#restart-omni');
 assert.doesNotMatch(g.toasts.at(-1),/restarted|refreshed/i);assert.match(g.toasts.at(-1),/403|Denied/);
});

test('a backend taking twenty seconds to restart still reconnects automatically',async()=>{
 const f=fixture({'/api/connection':(_,n,r)=>{if(n<40)throw Error('Network unavailable');return r({app:'CheapOS',token:'new'});}});
 await f.click();assert.equal(f.reloads,1);assert.equal(f.now,20000);
 assert.ok(f.toasts.some(m=>/Waiting for the server/.test(m)));assert.doesNotMatch(f.toasts.join(' '),/failed/i);
});
test('initial connection failure is retried and overlapping bootstraps are coalesced',async()=>{
 const start=source.indexOf('async function bootstrap()'),end=source.indexOf("$$('.tabs .tab')",start);
 let calls=0,release,homes=0,refreshes=0;const timers=[];
 const node={innerHTML:''},state={online:false,preferences:{},restarting:false};
 const ctx={state,console:{error(){}},$:()=>node,setTimeout:fn=>timers.push(fn),
  api:async()=>{calls++;if(calls===1)throw Error('Network error');return new Promise(resolve=>release=resolve);},
  localStorage:{getItem:()=>null,setItem(){}},loadAdmission:async()=>{},renderSidebar(){},updateLifetimeSavingsBadge(){},
  home(){homes++;},loadReadiness:async()=>{},openInitialProjectManager(){},renderInspector(){},refresh:async()=>{refreshes++;}};
 vm.createContext(ctx);vm.runInContext(source.slice(start,end),ctx);
 await ctx.bootstrap();assert.equal(state.online,false);assert.match(node.innerHTML,/reconnect automatically/);
 const retry=ctx.poll();await ctx.bootstrap();assert.equal(calls,2);
 release({token:'new',tasks:[],projects:[],startup:{}});await retry;
 assert.equal(state.online,true);assert.equal(homes,1);assert.equal(state.bootstrapping,false);
 state.restarting=true;await ctx.poll();assert.equal(refreshes,0);assert.equal(calls,2);
 state.restarting=false;await ctx.poll();assert.equal(refreshes,1);
});
