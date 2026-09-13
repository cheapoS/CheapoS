const {test}=require('node:test');
const assert=require('node:assert/strict');
const {routingTraceView,metadataEvidence}=require('../dist/guidance.js');
test('trace preserves ordered skips and dispatches without inventing served identity',()=>{
 const t={routing_traces:[{id:'r1',role:'worker',requested_route:'automatic',candidates:[{model:'a',reason:'quota_exhausted'},{model:'b',reason:'eligible'}],attempts:[{request_id:'p1',model:'b',purpose:'probe',status:'passed',seconds:1},{request_id:'w1',model:'b',purpose:'work',status:'completed',served_model:'actual-b',identity_provenance:'gateway_header'}],selected_model:'b'}]};
 const v=routingTraceView(t);
 assert.match(v.summary,/selected b/);assert.match(v.rows[0].candidates[0],/a: quota exhausted/);
 assert.match(v.rows[0].attempts[0],/Dispatched probe.*served unknown/);
 assert.match(v.rows[0].attempts[1],/served actual-b \(gateway_header\)/);
 assert.equal(v.rows[0].gateway,'Gateway internal attempts unavailable');
});
test('old records remain empty; unavailable routing has actionable honest message',()=>{
 assert.deepEqual(routingTraceView({}),{rows:[],summary:''});
 assert.match(routingTraceView({routing_traces:[{role:'reviewer'}]}).summary,/no route selected.*saved work is retained/);
});
test('metadata distinguishes observation provenance, stale and unavailable dates',()=>{
 assert.match(metadataEvidence({}),/unavailable/);
 const result=metadataEvidence({metadata_evidence:{source:'catalog',observed_at:'2026-09-13T12:00:00Z',changes:['context_length'],stale:true}});
 assert.match(result,/Stale metadata.*catalog.*2026-09-13.*context_length/);
 assert.match(result,/does not verify current availability/);
});
test('routing details stay inside reply disclosure with stable key and escaped labels',()=>{
 const vm=require('node:vm'),fs=require('node:fs');
 const source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8').split("\n'use strict';\nconst $ =")[0];
 const context={CheapOSGuide:require('../dist/guidance.js'),esc:x=>String(x??'').replaceAll('<','&lt;'),icon:()=>'',messageText:x=>x};
 vm.createContext(context);vm.runInContext(source+'\nthis.view=CheapOSChatView;',context);
 const t={routing_traces:[{id:'trace',role:'worker',requested_route:'<alias>',selected_model:'b'}]};
 const e={kind:'assistant',id:'reply-1',steps:[],reply:'',live:false};
 const html=context.view.message(e,t,'',true);
 assert.match(html,/data-event="routing-reply-1"/);assert.match(html,/<summary>Details<\/summary>/);
 assert.match(html,/&lt;alias>/);assert.doesNotMatch(html,/<alias>/);
 assert.equal(context.view.message(e,t,'',false),'');
});
