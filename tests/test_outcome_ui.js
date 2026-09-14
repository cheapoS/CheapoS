const test=require('node:test');
const assert=require('node:assert/strict');
const {modelHealth}=require('../dist/guidance.js');
test('review envelopes never imply completion or judgment accuracy',()=>{
 const label=modelHealth({health:{role_evidence:{reviewer:{samples:9,reviews_completed:9}}}});
 assert.match(label,/no prior completion evidence/);
 assert.doesNotMatch(label,/accuracy|%|independently confirmed/);
});
test('receipt counts distinguish independent disproof from human integration',()=>{
 const label=modelHealth({health:{role_evidence:{worker:{completion_samples:2,completed:2,independently_validated:1,independently_disproved:1,human_integrated:1,accepted:3}}}});
 for(const value of ['2 observed completions','1 independently confirmed','1 independently disproved','1 human integrated','3 human accepted'])assert.ok(label.includes(value));
 assert.doesNotMatch(label,/accuracy|%/);
});
test('cooldown takes precedence and unknown reset is not an invented countdown',()=>{
 const label=modelHealth({health:{retry_at:200,retry_known:false,cooldown_scope:'provider',role_evidence:{worker:{completed:8,completion_samples:8}}}},100000);
 assert.equal(label,'Provider cooling down · reset time unknown');
});
