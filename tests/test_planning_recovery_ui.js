const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('dist/app.js','utf8');
const context={esc:s=>String(s).replaceAll('<','&lt;')};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('function operatorRecoveryFields('),source.indexOf('async function operatorRecovery(')),context);
test('planning recovery offers planner actions without execution controls',()=>{
 const html=context.operatorRecoveryFields({planning:true,can_retry:true,can_planner:true,reason:'saved',planners:[{id:'a',label:'<model>'}]});
 assert.match(html,/Retry planning/);assert.match(html,/Use planner/);assert.match(html,/&lt;model>/);
 assert.doesNotMatch(html,/Change worker|Enable development|Choose reviewer/);
});
test('empty planner catalog gives an actionable connection instruction',()=>{
 const html=context.operatorRecoveryFields({planning:true,can_planner:true,planners:[]});
 assert.match(html,/disabled/);assert.match(html,/Check connections in Models/);
});
