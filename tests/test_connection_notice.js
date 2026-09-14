const {test}=require('node:test');
const assert=require('node:assert/strict');
const {connectionNotice}=require('../dist/guidance.js');
const local={paths:{local:{models:['gemma4:31b'],selected:'gemma4:31b'}}};
const delegate={mode:'delegate',local_model:'gemma4:31b'};

test('startup shows missing gateway access before any inference, even with an installed local model',()=>{
  const notice=connectionNotice(local,{status:'auth_required'},delegate);
  assert.equal(notice.tone,'attention');
  assert.match(notice.detail,/client API key/);
  assert.match(notice.detail,/Remember/);
});
test('unavailable local model is surfaced while its saved choice is retained',()=>{
  const notice=connectionNotice({paths:{local:{models:[]}}},{status:'ready'},delegate);
  assert.equal(notice.tone,'attention');assert.match(notice.detail,/gemma4:31b/);assert.match(notice.detail,/saved choice is kept/);
  assert.equal(delegate.local_model,'gemma4:31b');
});
test('metadata does not claim model or coding verification and local mode ignores gateway failure',()=>{
  const notice=connectionNotice(local,{status:'auth_required'},{...delegate,mode:'local'});
  assert.equal(notice.tone,'available');assert.match(notice.detail,/Metadata checked/);
  assert.match(notice.detail,/verified when work runs/);
  assert.equal(connectionNotice(undefined,{},delegate).tone,'checking');
  assert.equal(connectionNotice(local,{status:'ready'},delegate).tone,'available');
});
test('locked key store and failed readiness calls expose recovery instead of claiming configured',()=>{
  const locked=connectionNotice(local,{status:'auth_required',key_storage:{error:'Unlock your credential store.'}},delegate);
  assert.match(locked.detail,/Unlock/);
  for(const diagnostic_code of ['readiness_request_failed','readiness_probe_failed']){
    assert.equal(connectionNotice({diagnostic_code},{status:'ready'},delegate).tone,'attention');
  }
});
test('local models are verified before inference, missing roles need setup, and local reviewer absence is visible',()=>{
  assert.equal(connectionNotice(local,{}, {mode:'manual'},{}).tone,'attention');
  assert.match(connectionNotice(local,{}, {mode:'manual'}, {worker:{gateway:'openai'},reviewer:{gateway:'openai'}}).detail,/identity is checked before inference/);
  assert.match(connectionNotice(local,{}, {...delegate,mode:'local',local_reviewer:'missing'}).detail,/reviewer missing/);
});
test('legacy direct remote settings need explicit repair and cannot look ready',()=>{
  const config={worker:{route_error:'Direct connections disabled'},reviewer:{gateway:'omniroute'}};
  const notice=connectionNotice(local,{status:'ready'}, {mode:'manual'},config);
  assert.equal(notice.tone,'attention');assert.match(notice.detail,/Open Models and choose OmniRoute/);
  assert.equal(connectionNotice(local,{status:'ready'}, {...delegate,mode:'local'},config).tone,'available');
});
