const {test}=require('node:test');
const assert=require('node:assert/strict');
const {modelAccess,includedScope,includedChoice}=require('../dist/guidance.js');
test('access labels distinguish authorization from price and capability',()=>{
 assert.equal(modelAccess({access_class:'included',free:false,tool_calling:true}),'Included access');
 assert.equal(modelAccess({free:true}),'Public free');
 assert.equal(modelAccess({local:true}),'Local');
 assert.equal(modelAccess({input_rate:1,output_rate:2}),'Priced');
 assert.equal(modelAccess({tool_calling:true}),'Unknown pricing');
 assert.equal(modelAccess({input_rate:null,output_rate:null}),'Unknown pricing');
});
test('included IDs are explicit and exact, never provider or prefix grants',()=>{
 assert.deepEqual(includedScope('kiro/a\nkiro/b\nkiro/a\n'),['kiro/a','kiro/b']);
 assert.throws(()=>includedScope('kiro/a other'));
 const settings={included_models:['kiro/a']};
 assert.equal(includedChoice('kiro/a',settings,true),true);
 assert.equal(includedChoice('kiro/b',settings,true),false);
 assert.equal(includedChoice('kiro/a-new',settings,true),false);
 assert.equal(includedChoice('kiro/a',settings,false),false);
 assert.equal(includedChoice('kiro/a',{included_models:[]},true),false);
 assert.equal(includedChoice('kiro/a',JSON.parse(JSON.stringify(settings)),true),true);
});
