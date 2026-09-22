const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8');
function fixture(){
  const calls=[],renders=[];
  const ctx={state:{view:'logs',task:{id:'one',updated_at:'1',diagnostics:{revision:'a'}}},
    api:url=>{calls.push(url);return Promise.resolve({routing_traces:[],total:0});},
    renderTask:()=>renders.push(ctx.state.task.id),toast:()=>{}};
  vm.createContext(ctx);
  vm.runInContext(source.slice(source.indexOf('async function loadTaskDiagnostics('),source.indexOf('async function downloadTaskDiagnostics(')),ctx);
  return {ctx,calls,renders};
}
test('diagnostics load on demand, reuse their revision, and page explicitly',async()=>{
  const {ctx,calls}=fixture();
  assert.equal(calls.length,0);
  await ctx.loadTaskDiagnostics(ctx.state.task);
  await ctx.loadTaskDiagnostics(ctx.state.task);
  assert.deepEqual(calls,['/tasks/one/diagnostics?offset=0']);
  await ctx.loadTaskDiagnostics(ctx.state.task,8);
  assert.equal(calls.at(-1),'/tasks/one/diagnostics?offset=8');
  ctx.state.task.diagnostics.revision='b';
  await ctx.loadTaskDiagnostics(ctx.state.task,8);
  assert.equal(calls.length,3);
});
test('failed loads keep an explicit retry and cannot disrupt task state',async()=>{
  const {ctx}=fixture();let requests=0;
  ctx.api=async()=>{requests++;throw new Error('offline');};
  await ctx.loadTaskDiagnostics(ctx.state.task);
  await ctx.loadTaskDiagnostics(ctx.state.task);
  assert.equal(requests,1);
  assert.equal(ctx.state.diagnosticView.error,'offline');
  assert.equal(ctx.state.task.id,'one');
  await ctx.loadTaskDiagnostics(ctx.state.task,0,true);
  assert.equal(requests,2);
});
test('late diagnostic responses cannot overwrite another task or newer page',async()=>{
  const {ctx,renders}=fixture(),pending=[];
  ctx.api=url=>new Promise(resolve=>pending.push({url,resolve}));
  const first=ctx.loadTaskDiagnostics(ctx.state.task);
  ctx.state.task={id:'two',diagnostics:{revision:'b'}};
  const second=ctx.loadTaskDiagnostics(ctx.state.task);
  pending[1].resolve({total:2});await second;
  pending[0].resolve({total:100});await first;
  assert.equal(ctx.state.diagnosticView.id,'two');
  assert.equal(ctx.state.diagnosticView.data.total,2);
  assert.deepEqual(renders,['two']);
});
test('default copied JSON comes from the summary endpoint, not stale UI diagnostics',async()=>{
  const {ctx,calls}=fixture();let copied;
  ctx.navigator={clipboard:{writeText:async value=>{copied=value;}}};
  ctx.state.task.routing_traces=[{private:'debug'}];
  ctx.api=async url=>{calls.push(url);return {kind:'task_summary',steps:[{title:'Read file'}]};};
  vm.runInContext(source.slice(source.indexOf('async function copyTaskJson('),source.indexOf('async function exportTaskJson(')),ctx);
  await ctx.copyTaskJson(ctx.state.task);
  assert.deepEqual(calls,['/tasks/one/export']);
  assert.equal(JSON.parse(copied).kind,'task_summary');
  assert.doesNotMatch(copied,/routing_traces|debug/);
});
