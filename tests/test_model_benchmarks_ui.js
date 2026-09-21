const {test}=require('node:test');
const assert=require('node:assert/strict');
const {modelBenchmarks,sortModelCatalog}=require('../dist/guidance.js');
const model=(id,coding,agentic)=>({id,benchmarks:{source:'Artificial Analysis',catalog:'OpenRouter',refreshed_at:'2026-09-21T12:00:00Z',coding,agentic}});

test('catalog sorting keeps unknown models, zero scores, ties and original data',()=>{
  const models=[{id:'new'},model('a',10,80),model('b',80,10),model('zero',0,0),model('tie',80,null)];
  const ids=rows=>rows.map(m=>m.id);
  assert.deepEqual(ids(sortModelCatalog(models,'coding')),['b','tie','a','zero','new']);
  assert.deepEqual(ids(sortModelCatalog(models,'agentic')),['a','b','zero','new','tie']);
  assert.deepEqual(ids(sortModelCatalog(models)),['new','a','b','zero','tie']);
  assert.notEqual(sortModelCatalog(models),models);
  assert.deepEqual(ids(models),['new','a','b','zero','tie']);
});

test('benchmark presentation separates missing scores from zero and identifies catalog refresh',()=>{
  const view=modelBenchmarks(model('zero',0,null));
  assert.equal(view.scores,'Coding: 0 · Agentic: Unknown · Intelligence: Unknown');
  assert.match(view.source,/Artificial Analysis · via OpenRouter · Catalog refreshed:/);
  assert.doesNotMatch(view.source,/unknown|Invalid Date/);
  assert.equal(modelBenchmarks({}).source,'No benchmark scores reported');
  assert.match(modelBenchmarks({...model('old',50,20),metadata_evidence:{stale:true}}).source,/Stale metadata/);
  const unknownDate=model('no-date',50,20);delete unknownDate.benchmarks.refreshed_at;
  assert.match(modelBenchmarks(unknownDate).source,/refreshed: unknown/);
  for(const bad of [null,true,'99',Infinity,NaN,-1]){
    assert.match(modelBenchmarks(model('bad',bad,0)).scores,/Coding: Unknown/);
    assert.equal(sortModelCatalog([model('bad',bad),model('zero',0)],'coding')[0].id,'zero');
  }
});
