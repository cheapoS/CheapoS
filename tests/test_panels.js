const {test}=require('node:test');
const assert=require('node:assert/strict');
const {limits,settledWidth}=require('../dist/panels.js');
test('desktop caps match reference proportions and leave room for the conversation',()=>{
 for(const viewport of [701,1024,1440,2048,3840]){
  const left=limits('left',viewport),right=limits('right',viewport);
  assert.ok(left.max<=viewport*.285);assert.ok(right.max<=viewport*.25);
  assert.ok(viewport-left.max-right.max>=viewport*.465);
  assert.equal(settledWidth(10000,'left',viewport),left.max);
  assert.equal(settledWidth(10000,'right',viewport),right.max);
 }
});
test('outer-edge drag collapses and narrow drags settle to a usable size',()=>{
 for(const side of ['left','right']){
  assert.equal(settledWidth(-200,side,1440),0);
  assert.equal(settledWidth(56,side,1440),0);
  assert.equal(settledWidth(57,side,1440),limits(side,1440).min);
  assert.equal(settledWidth(270,side,1440),270);
 }
});
test('mobile panels retain a gutter and small windows never exceed available width',()=>{
 for(const viewport of [280,375,700])for(const side of ['left','right']){
  assert.ok(limits(side,viewport).max<=viewport-32);
  assert.ok(settledWidth(500,side,viewport)<=viewport-32);
 }
});
