'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8');
function fixture(){const input={value:'original'},state={task:{id:'b',status:'ready'},tasks:[{id:'a',title:'Unattended job'}],startup:{},admission:{interactive:{allowed:true},unattended:{allowed:false,reason:'Unattended slot full.'},active:[{task_id:'a',mode:'unattended'}]},pendingSends:new Set(),startErrors:new Map(),drafts:new Map()};let renders=0;const c={state,branchUI:{getMode:()=> 'interactive'},taskBusy:t=>t.status==='running',draftKey:()=>state.task?.id||'new',$:()=>input,renderComposer:()=>{},renderTask:()=>renders++,refresh:async()=>{},api:async()=>{},document:{}};vm.createContext(c);vm.runInContext(source.slice(source.indexOf('function submissionAvailability'),source.indexOf('function renderComposer')),c);vm.runInContext(source.slice(source.indexOf('async function startTask('),source.indexOf('async function resumeTask')),c);return {c,state,input,renders:()=>renders};}
test('server admission allows independent Interactive but blocks occupied Unattended and never guidance',()=>{const {c,state}=fixture();assert.equal(c.submissionAvailability().allowed,true);assert.equal(c.submissionAvailability(null,'unattended').allowed,false);assert.match(c.submissionAvailability(null,'unattended').reason,/Unattended job/);state.task.status='running';assert.equal(c.submissionAvailability(state.task,'unattended').allowed,true);state.admission=null;state.task.status='ready';assert.equal(c.submissionAvailability().allowed,true);assert.equal(c.submissionAvailability(null).allowed,false);});
test('owned draft clearing cannot change another selected chat or newer text',()=>{const {c,state,input}=fixture();state.drafts.set('a','original');c.clearOwnedDraft('a','original');assert.equal(input.value,'original');assert.equal(state.drafts.has('a'),false);state.drafts.set('b','newer');input.value='newer';c.clearOwnedDraft('b','original');assert.equal(input.value,'newer');assert.equal(state.drafts.get('b'),'newer');});
test('rejected start persists specific same-task explanation; lost response reconciles without new task',async()=>{const {c,state}=fixture();let calls=[];c.api=async(path,body)=>{calls.push(path);if(body)throw Error('Capacity occupied');return {...state.task,start_error:'Capacity occupied'};};assert.equal(await c.startTask('b'),false);assert.equal(state.startErrors.get('b'),'Capacity occupied');assert.deepEqual(calls,['/tasks/b/start','/tasks/b']);calls=[];c.api=async(path,body)=>{calls.push(path);if(body)throw Error('Response lost');return {id:'b',status:'running'};};assert.equal(await c.startTask('b'),true);assert.equal(state.task.status,'running');assert.deepEqual(calls,['/tasks/b/start','/tasks/b']);});
test('late start reconciliation never overwrites another chat',async()=>{const {c,state}=fixture();let resolve;c.api=(path,body)=>body?Promise.reject(Error('lost')):new Promise(r=>resolve=r);const pending=c.startTask('b');await new Promise(r=>setImmediate(r));state.task={id:'c',status:'ready'};resolve({id:'b',status:'running'});await pending;assert.equal(state.task.id,'c');});
test('old server 404 retains legacy single-task capacity while other errors fail closed',async()=>{const {c,state}=fixture();c.api=async()=>{throw Object.assign(Error('not found'),{status:404});};await c.loadAdmission();assert.equal(state.admission.legacy,true);state.tasks[0].status='running';assert.equal(c.submissionAvailability(null).allowed,false);assert.match(c.submissionAvailability(null).reason,/later app restart/);state.tasks[0].status='paused';assert.equal(c.submissionAvailability(null).allowed,true);c.api=async()=>{throw Object.assign(Error('unavailable'),{status:503});};await c.loadAdmission();assert.equal(c.submissionAvailability(null).allowed,false);});

function sendFixture(){
 const f=fixture(),{c,state,input}=f;state.task={id:'b',status:'awaiting_reply',requests:['original']};state.project={path:'/fixture'};state.preferences={execution:{mode:'remote'}};state.selection=1;
 Object.assign(c,{messageText:s=>String(s).replaceAll('<','&lt;'),saveDraft:()=>state.drafts.set('b',input.value),renderChat:()=>{},renderHome:()=>{},toast:()=>{},refreshContext:()=>new Promise(()=>{})});
 c.branchUI.interceptSubmit=async()=>false;input.focus=()=>{};
 vm.runInContext(source.slice(source.indexOf('function canTakeOver'),source.indexOf('function operatorRecoveryFields')),c);
 vm.runInContext(source.slice(source.indexOf('const submissionEntries='),source.indexOf('async function steerTask(')),c);
 return f;
}
test('Enter and Send share immediate pending feedback and duplicate protection while delivery waits',async()=>{
 const {c,state,input}=sendFixture();input.value='Finish <trash>';let accept,calls=0;
 c.api=()=>{calls++;return new Promise(r=>accept=r);};
 const sending=c.sendChat();await new Promise(r=>setImmediate(r));
 assert.equal(c.sendingHere(),true);assert.match(c.pendingMessageMarkup(),/Sending…/);
 assert.match(c.pendingMessageMarkup(),/Finish &lt;trash>/);assert.equal(state.drafts.get('b'),input.value);
 await c.sendChat();assert.equal(calls,1);
 accept({...state.task,status:'running',requests:['original',input.value]});await sending;
 assert.equal(state.task.status,'running');assert.equal(input.value,'');assert.equal(c.sendingHere(),false);assert.equal(c.pendingMessageMarkup(),'');
 // refreshContext never resolves: accepted delivery must not await gateway/sidebar work.
});
test('delivery rejection restores editable draft and late delivery cannot overwrite another chat',async()=>{
 const {c,state,input}=sendFixture();input.value='Continue';c.api=async()=>{throw Error('No turns remain');};
 await c.sendChat();assert.equal(input.value,'Continue');assert.equal(state.sendErrors.get('b'),'No turns remain');assert.equal(c.sendingHere(),false);
 let accept;c.api=()=>new Promise(r=>accept=r);const pending=c.sendChat();await new Promise(r=>setImmediate(r));
 state.task={id:'c',status:'paused',requests:[]};state.selection++;input.value='Other draft';
 accept({id:'b',status:'running',requests:['original','Continue']});await pending;
 assert.equal(state.task.id,'c');assert.equal(input.value,'Other draft');assert.equal(c.pendingMessageMarkup(),'');
});

function branchSendFixture(){
 const f=sendFixture(),{c,state}=f;
 c.CheapOSBranchUI=require('../dist/branch_ui.js');
 state.admission.unattended={allowed:true};
 state.task={id:'b',status:'paused',pause_summary:{question:'Which behavior do you need?'},branch_run:{status:'paused',authorization_ref:'accepted',guidance:[]}};
 vm.runInContext(source.slice(source.indexOf('async function steerTask('),source.indexOf('async function boostHeadroom(')),c);
 vm.runInContext(source.slice(source.indexOf('async function resumeBranchRun('),source.indexOf('async function bootstrap(')),c);
 return f;
}
test('ordinary branch question reply saves once, then resumes the same run with immediate feedback',async()=>{
 for(const message of ['try again','continue','Run the focused tests and submit checkpoint']){
  const {c,state,input}=branchSendFixture();input.value=message;const calls=[];let finishResume;
  c.api=async(path,body)=>{calls.push([path,body]);if(path.endsWith('/chat-message'))return {...state.task,branch_run:{...state.task.branch_run,guidance:[{message:body.message}]}};return new Promise(r=>finishResume=r);};
  const pending=c.sendChat();await new Promise(r=>setImmediate(r));
  assert.equal(input.value,'');assert.equal(state.task.branch_run.guidance[0].message,message);
  assert.equal(state.branchResumeStatus.get('b').status,'pending');assert.equal(c.sendingHere(),true);
  await c.sendChat();assert.equal(calls.length,2);
  assert.equal(calls[0][0],'/tasks/b/chat-message');assert.equal(calls[1][0],'/tasks/b/branch-resume');assert.equal(Object.keys(calls[1][1]).length,0);
  finishResume({needs_consent:false});await pending;
  assert.equal(state.branchResumeStatus.has('b'),false);assert.equal(c.sendingHere(),false);
 }
});
test('failed branch continuation keeps delivered guidance and exposes exact error without resending it',async()=>{
 const {c,state,input}=branchSendFixture();input.value='Continue';let saves=0;
 c.api=async(path,body)=>{if(path.endsWith('/chat-message')){saves++;return state.task;}throw Error('Branch changed since the saved operation');};
 await c.sendChat();assert.equal(input.value,'');assert.equal(saves,1);
 assert.equal(state.branchResumeStatus.get('b').message,'Branch changed since the saved operation');
 assert.equal(state.sendErrors.has('b'),false);assert.equal(c.sendingHere(),false);
});
test('guidance to active branch does not restart it, and unsaved guidance never resumes',async()=>{
 const {c,state,input}=branchSendFixture();state.task.status='running';state.task.branch_run.status='running';input.value='Keep the existing behavior';let paths=[];
 c.api=async path=>{paths.push(path);return state.task;};await c.steerTask();assert.deepEqual(paths,['/tasks/b/branch-message']);
 state.task.status='paused';state.task.branch_run.status='paused';input.value='Try again';paths=[];
 c.api=async path=>{paths.push(path);throw Error('Guidance could not be saved');};await c.steerTask();
 assert.deepEqual(paths,['/tasks/b/branch-message']);assert.equal(input.value,'Try again');assert.equal(state.sendErrors.get('b'),'Guidance could not be saved');
});
test('branch continuation opens scoped consent instead of approving commands automatically',async()=>{
 const {c,state,input}=branchSendFixture();input.value='continue';const paths=[];let form,html;
 Object.assign(c,{esc:String,modalHeader:()=>'',dialog:s=>{html=s;return {};},$:selector=>selector==='form'?(form={}):input});
 c.api=async path=>{paths.push(path);return path.endsWith('/chat-message')?state.task:{needs_consent:true,proposal_id:'exact',scopes:[{command:['python3','-m','unittest'],directory:'/fixture'}]};};
 await c.sendChat();assert.match(html,/Allow tests & resume/);assert.equal(typeof form.onsubmit,'function');assert.equal(paths.length,2);assert.equal(c.sendingHere(),false);
});


test('renewing test permissions closes the modal before the server responds and prevents duplicate submission',async()=>{
 const {c,state,input}=branchSendFixture();let form,closed=false,accept,calls=0;
 Object.assign(c,{esc:String,modalHeader:()=>'',dialog:()=>({close:()=>closed=true}),$:selector=>selector==='form'?(form={}):input});
 await c.resumeBranchRun(state.task,{needs_consent:true,proposal_id:'inspected',scopes:[]});
 c.api=async(path,body)=>{calls++;assert.equal(closed,true);assert.equal(body.proposal_id,'inspected');assert.equal(body.approved,true);return new Promise(r=>accept=r);};
 form.onsubmit({preventDefault(){}});
 assert.equal(closed,true);assert.equal(state.branchResumeStatus.get('b').status,'pending');
 form.onsubmit({preventDefault(){}});assert.equal(calls,1);
 accept({needs_consent:false});await new Promise(r=>setImmediate(r));
 assert.equal(state.branchResumeStatus.has('b'),false);
});

function permissionFixture(){
 const state={task:{id:'b',pending_approval:{id:'check-1',command:['python3','-m','unittest']}}};
 const c={state,api:async()=>{},renderChat:()=>{},toast:()=>{},loadTaskPermissions:()=>new Promise(()=>{}),refresh:async()=>{},esc:String,CheapOSGuide:{permissionChoice:()=>({scope:'once',label:'Run once'})}};
 vm.createContext(c);vm.runInContext(source.slice(source.indexOf('function permissionMarkup('),source.indexOf('function bindPermissions(')),c);return c;
}
test('command approval renders immediately, survives polling, and does not await permissions refresh',async()=>{
 const c=permissionFixture();let accept,calls=0;c.api=()=>{calls++;return new Promise(r=>accept=r);};
 const pending=c.submitPermission(c.state.task,'once');assert.match(c.permissionMarkup(c.state.task),/Sending your decision/);
 assert.doesNotMatch(c.permissionMarkup(c.state.task),/data-permission=/);
 await c.submitPermission(c.state.task,'once');assert.equal(calls,1);
 accept({accepted:true});await pending;assert.match(c.permissionMarkup(c.state.task),/Permission accepted/);
 // A fresh command must not inherit the previous confirmation.
 c.state.task.pending_approval.id='check-2';assert.match(c.permissionMarkup(c.state.task),/Can I run this check/);
});
test('rejected command approval is actionable and a late response cannot replace another chat',async()=>{
 const c=permissionFixture();c.api=async()=>{throw Error('Command scope changed');};
 await c.submitPermission(c.state.task,'once');assert.match(c.permissionMarkup(c.state.task),/Command scope changed/);assert.match(c.permissionMarkup(c.state.task),/data-permission=/);
 let accept,renders=0;c.renderChat=()=>renders++;c.api=()=>new Promise(r=>accept=r);
 const pending=c.submitPermission(c.state.task,'decline');assert.equal(renders,1);c.state.task={id:'other'};
 accept({accepted:true});await pending;assert.equal(renders,1);assert.equal(c.state.task.id,'other');
});

function workLimitFixture(){
 const c={CheapOSGuide:require('../dist/guidance.js')};vm.createContext(c);
 vm.runInContext(source.slice(source.indexOf('const numberField='),source.indexOf('function newTask(')),c);return c;
}
test('work limits expose explicit infinity and remove the 200-turn HTML maximum',()=>{
 const c=workLimitFixture(),limits={dollars:0,reviewer_tokens:200000,iterations:5,worker_turns:1200,output_tokens:2048,run_minutes:15};
 c.limits=limits;const markup=vm.runInContext('limitFields(limits)',c);
 assert.match(markup,/Uncapped work · ∞/);
 const worker=markup.match(/<input name="worker_turns"[^>]*>/)[0];
 assert.match(worker,/value="1200"/);assert.doesNotMatch(worker,/max=/);
 c.form=new Map(Object.entries({...limits,uncapped_work:'on'}));
 const parsed=vm.runInContext('readLimits(form)',c);assert.equal(parsed.uncapped_work,true);assert.equal(parsed.worker_turns,1200);assert.equal(parsed.dollars,0);
 c.form.delete('uncapped_work');assert.equal(vm.runInContext('readLimits(form)',c).uncapped_work,false);
});
test('saved branch mode takes precedence over local limits and legacy measurement is visible',()=>{
 const c=workLimitFixture();assert.equal(c.workLimits({limits:{uncapped_work:true},branch_run:{plan:{}}}).uncapped_work,false);
 assert.equal(c.workLimits({limits:{},branch_run:{plan:{uncapped_work:true}}}).uncapped_work,true);
 assert.equal(c.workLimits({limits:{},branch_run:{plan:{measurement:true}}}).uncapped_work,true);
 assert.equal(c.workLimits(null,{uncapped_work:true}).uncapped_work,true);
});
test('paused-task Send keeps normal authority and later-chat drafts intact',async()=>{const {c,state,input}=sendFixture();state.task.status='paused';input.value='Use the saved evidence';let accept,calls=[];c.api=(path,body)=>{calls.push([path,body]);return new Promise(r=>accept=r);};const pending=c.sendChat();await new Promise(r=>setImmediate(r));await c.sendChat();assert.equal(calls.length,1);assert.equal(calls[0][0],'/tasks/b/chat-message');assert.equal(calls[0][1].action,undefined);assert.equal(calls[0][1].approved,undefined);state.task={id:'other'};state.selection++;input.value='Other draft';accept({id:'b',status:'running'});await pending;assert.equal(state.task.id,'other');assert.equal(input.value,'Other draft');});
