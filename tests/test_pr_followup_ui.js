'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8');
function fixture(){
 const input={value:'Fix the missed styling',focus(){}},button={disabled:false,textContent:'Continue',after(node){this.notice=node;}};
 const state={task:{id:'old',pull_request:{head:'a',ci:{state:'merged'}}},selection:1,composerAttachments:[{id:'image'}]};
 const saved=[],cleared=[],selected=[],calls=[];
 const c={state,CheapOSGitWorkflow:require('../dist/git_workflow.js'),$:()=>input,saveDraft:()=>saved.push(input.value),draftKey:()=>state.task.id,
  document:{createElement:()=>({setAttribute(){}})},loadTasks:async()=>{},renderComposer(){},
  selectTask:async id=>{selected.push(id);state.task={id};input.value='';state.composerAttachments=[];},
  clearOwnedDraft:(...args)=>cleared.push(args),api:(...args)=>new Promise((resolve,reject)=>calls.push({args,resolve,reject}))};
 vm.createContext(c);vm.runInContext(source.slice(source.indexOf('const followupRequests='),source.indexOf('const CheapOSChatView')),c);
 return {c,state,input,button,saved,cleared,selected,calls};
}
test('follow-up acknowledges immediately, deduplicates clicks and moves the unsent draft only on success',async()=>{
 const f=fixture(),run=f.c.continueMergedTask(f.button);
 assert.equal(f.button.disabled,true);assert.match(f.button.textContent,/Preparing/);
 assert.match(f.button.notice.textContent,/original task stays intact/);
 await f.c.continueMergedTask(f.button);assert.equal(f.calls.length,1);
 f.calls[0].resolve({id:'child'});await run;
 assert.deepEqual(f.selected,['child']);assert.equal(f.input.value,'Fix the missed styling');
 assert.equal(f.state.composerAttachments[0].id,'image');assert.equal(f.cleared[0][0],'old');
});
test('failed creation preserves the original draft and a late result never hijacks another chat',async()=>{
 const f=fixture(),run=f.c.continueMergedTask(f.button);
 f.calls[0].reject(Error('offline'));await run;
 assert.equal(f.input.value,'Fix the missed styling');assert.equal(f.cleared.length,0);
 assert.equal(f.button.disabled,false);assert.match(f.button.notice.textContent,/offline/);
 const retry=f.c.continueMergedTask(f.button);f.state.selection=2;f.state.task={id:'elsewhere'};
 f.calls[1].resolve({id:'child'});await retry;assert.deepEqual(f.selected,[]);
});

// Reclamation proved there were no later files; the saved diff is history.
test('reclaimed task offers a fresh follow-up without claiming later edits',()=>{
 const task={pull_request:{head:'tip',ci:{state:'merged'},patch:'old'},patch:'saved history',workspace_cleanup:{state:'reclaimed'}};
 const ui=require('../dist/git_workflow.js');
 assert.equal(ui.laterEdits(task),false);
 assert.match(ui.followupButton(task),/Continue in new task/);
});
