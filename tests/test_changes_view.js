const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('dist/app.js','utf8');
const scope={};vm.runInNewContext(source.slice(source.indexOf('function diffLines('),source.indexOf('function renderChanges(')),scope);
test('folding preserves every added and deleted line with surrounding context',()=>{
 const before=Array.from({length:100},(_,i)=>`line ${i}`).join('\n');
 const rows=scope.diffLines(before,before.replace('line 50','replacement'));
 const folded=scope.reviewRows(rows);
 assert.deepEqual(Array.from(folded.filter(r=>r.type==='add'||r.type==='remove'),r=>r.text),['line 50','replacement']);
 assert.ok(folded.some(r=>r.type==='gap'));
 assert.equal(scope.reviewRows(rows,true),rows);
 assert.equal(folded.reduce((n,r)=>n+(r.type==='gap'?r.count:1),0),rows.length);
});
