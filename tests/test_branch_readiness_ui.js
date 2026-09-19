const {test}=require('node:test');
const assert=require('node:assert/strict');
const {proposalReadiness}=require('../dist/branch_ui.js');
test('legacy proposals retain Start without invented readiness evidence',()=>{
 assert.deepEqual(proposalReadiness({}),{blocked:false,html:''});
});
test('ready proposal presents checklist, assumptions and scoped authority',()=>{
 const v=proposalReadiness({readiness:{ready:true,checks:[{id:'source',label:'Project context',status:'ready',detail:'Committed snapshot inspected'}],assumptions:['Use existing <pattern>'],policy:'Pause for essential decisions.'}});
 assert.equal(v.blocked,false);assert.match(v.html,/Ready to start unattended/);
 assert.match(v.html,/Committed snapshot inspected/);assert.match(v.html,/Use existing &lt;pattern&gt;/);
 assert.match(v.html,/reads and writes in the task copy/);assert.match(v.html,/Select Allow task commands/);assert.match(v.html,/prepare dependencies and diagnose failures/);
});
test('blocked or inconsistent readiness prevents Start and identifies the blocker',()=>{
 for(const ready of [false,true]){
  const v=proposalReadiness({readiness:{ready,checks:[{label:'Test command',status:'blocked',detail:'Choose the verification command'}]}});
  assert.equal(v.blocked,true);assert.match(v.html,/role="alert">Choose the verification command/);
  assert.doesNotMatch(v.html,/Ready to start unattended/);
 }
 assert.equal(proposalReadiness({readiness:{ready:false,checks:[]}}).blocked,true);
});
