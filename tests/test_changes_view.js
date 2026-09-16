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

test('diffLines on files larger than 1414 lines trims prefix/suffix and does not swap entire file',()=>{
 const before=Array.from({length:2500},(_,i)=>`line ${i}`).join('\n');
 const after=before.replace('line 1370','replacement 1370');
 const rows=scope.diffLines(before,after);
 const added=rows.filter(r=>r.type==='add');
 const removed=rows.filter(r=>r.type==='remove');
 assert.equal(added.length,1);
 assert.equal(removed.length,1);
 assert.equal(added[0].text,'replacement 1370');
 assert.equal(removed[0].text,'line 1370');
 assert.equal(removed[0].old,1371);
 assert.equal(added[0].new,1371);
});

const reviewAction=source.slice(source.indexOf('async function requestCommitReview('),source.indexOf('const commitPreviews='));
test('Finish review dispatches a controller action with immediate feedback',async()=>{
 const calls=[];let release;
 const context={state:{task:{id:'saved'}},api:(url,body)=>{calls.push([url,body]);return new Promise(resolve=>{release=resolve})},
   refresh:async()=>calls.push('refresh'),setView:view=>calls.push(view),toast:()=>assert.fail('unexpected error')};
 vm.runInNewContext(reviewAction,context);
 const button={disabled:false,textContent:'Finish review'};
 const pending=context.requestCommitReview(button);
 assert.equal(button.disabled,true);assert.equal(button.textContent,'Requesting review…');
 assert.deepEqual(JSON.parse(JSON.stringify(calls)),[['/tasks/saved/start',{finish_review:true}]]);
 release();await pending;
 assert.deepEqual(calls.slice(1),['refresh','chat']);
});

test('Finish review failure keeps the action available and explains the error',async()=>{
 const errors=[];
 const context={state:{task:{id:'saved'}},api:async()=>{throw new Error('Re-check the task environment')},
   refresh:()=>assert.fail('must not refresh on rejection'),setView:()=>assert.fail('must not navigate'),toast:message=>errors.push(message)};
 vm.runInNewContext(reviewAction,context);
 const button={disabled:false,textContent:'Finish review'};
 await context.requestCommitReview(button);
 assert.equal(button.disabled,false);assert.equal(button.textContent,'Finish review');
 assert.deepEqual(errors,['Re-check the task environment']);
});
