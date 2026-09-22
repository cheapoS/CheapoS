const {test}=require('node:test');
const assert=require('node:assert/strict');
const {rows}=require('../dist/schedules.js');
test('scheduled tasks disclose blocking work and escape source data',()=>{
 const html=rows({schedules:[{id:'one',name:'<script>bad</script>',repository:'/project',enabled:true,interval_hours:6,next_due:1,last_task_id:'task',waiting:'Waiting for review'}]});
 assert.ok(html.includes('&lt;script&gt;'));
 assert.ok(!html.includes('<script>'));
 assert.match(html,/data-run="one" disabled/);
 assert.ok(html.includes('Waiting for review'));
 assert.ok(html.includes('Open latest task'));
 assert.ok(rows({schedules:[]}).includes('Schedule this task'));
});

const fs=require('node:fs'),vm=require('node:vm');
const schedules=require('../dist/schedules.js');
const settings=require('../dist/settings.js');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function setupDialog(){
 const button={disabled:false},existingButton={disabled:false},error={textContent:''};
 const form={elements:{prompt:{value:' Check release notes '},interval:{value:'12'}},querySelector:()=>button};
 const existing={elements:{task_id:{value:'saved'}},querySelector:()=>existingButton};
 const d={open:true,close(){this.open=false;},querySelector:s=>({'[data-new-schedule]':form,'[data-existing-schedule]':existing,'[role=alert]':error}[s])};
 return {d,form,existing,button,error};
}
test('new schedule setup explains the approval steps and submits only one draft',async()=>{
 const c=setupDialog();let html,finish,calls=0;
 schedules.setup({project:{path:'/repo',name:'<Project>'},tasks:[],dialog:s=>(html=s,c.d),header:()=>'',onNew:async values=>{calls++;assert.equal(values.repository,'/repo');assert.equal(values.prompt,'Check release notes');assert.deepEqual(values.schedule_request,{interval_hours:12});await new Promise(r=>finish=r);values.close();}});
 assert.match(html,/&lt;Project&gt;/);assert.match(html,/Approve &amp; start schedule/);assert.match(html,/<select name="interval">/);
 assert.match(html,/recurring runs wait for your approval/);assert.match(html,/\$0 API spending allowance/);
 const first=c.form.onsubmit({preventDefault(){}});await c.form.onsubmit({preventDefault(){}});
 assert.equal(calls,1);assert.equal(c.button.disabled,true);finish();await first;assert.equal(c.d.open,false);
});
test('setup preserves the prompt after failure and only lists this project’s saved runs',async()=>{
 const c=setupDialog();let html,selected;
 const saved={id:'saved',title:'<Saved>',source:'/repo',branch_run:{status:'merged'}};
 schedules.setup({project:{path:'/repo'},tasks:[saved,{...saved,id:'other',source:'/other',title:'Other project'}, {...saved,id:'trash',trashed_at:'now',title:'Trashed'}, {...saved,id:'draft',branch_run:{status:'draft'},title:'Not approved'}],dialog:s=>(html=s,c.d),header:()=>'',onNew:async()=>{throw Error('Settings changed');},onExisting:async task=>{selected=task;}});
 assert.match(html,/&lt;Saved&gt;/);assert.doesNotMatch(html,/Other project|Trashed|Not approved/);
 await c.form.onsubmit({preventDefault(){}});
 assert.equal(c.error.textContent,'Settings changed');assert.equal(c.button.disabled,false);
 assert.equal(c.form.elements.prompt.value,' Check release notes ');
 await c.existing.onsubmit({preventDefault(){}});assert.equal(selected,saved);
});
function entryContext(){
 const app=fs.readFileSync(require.resolve('../dist/app.js'),'utf8');
 const entry=app.match(/function newScheduledTask\(\)\{[\s\S]*?\n\}(?=\nconst executionLabel)/)[0];
 let setup,projectPicker=0;const calls=[],drafts=new Map();
 const context={state:{projects:[{path:'/repo',name:'Repo'}],project:{path:'/other'},task:{source:'/repo'},tasks:[]},basename:s=>s.split('/').at(-1),openProject:()=>projectPicker++,CheapOSSchedules:{setup:options=>setup=options},dialog(){},modalHeader(){},
  setupDraft:async()=>({record:{values:{limits:{dollars:4},roles:{worker:{strategy:'only',model:'chosen'}}}},overrides:{'limits.work_requests':50}}),setupDrafts:drafts,CheapOSSettings:settings,newTask:(...args)=>calls.push(['draft',...args]),toast(){},api:async path=>{calls.push(['read',path]);return {id:'saved',title:'Saved'};},scheduleTask:task=>calls.push(['schedule',task])};
 vm.createContext(context);vm.runInContext(entry+';this.start=newScheduledTask;',context);
 return {context,calls,drafts,getSetup:()=>setup,getPickers:()=>projectPicker};
}
test('sidebar/home setup uses captured project and a zero-spend draft without dispatch',async()=>{
 const c=entryContext();c.context.start();const setup=c.getSetup();
 assert.equal(setup.project.path,'/repo');let closed=0;
 await setup.onNew({repository:'/repo',prompt:'Repeat this',schedule_request:{interval_hours:12},isOpen:()=>true,close:()=>closed++});
 assert.equal(closed,1);assert.equal(c.calls.length,1);assert.equal(c.calls[0][0],'draft');
 assert.equal(c.calls[0][2].mode,'unattended');assert.equal(c.calls[0][2].repository,'/repo');assert.equal(c.calls[0][2].schedule_request.interval_hours,12);
 assert.equal(c.drafts.get('/repo').values.limits.dollars,0);
 assert.equal(c.drafts.get('/repo').values.roles.worker.model,'chosen');
 assert.equal(c.drafts.get('/repo').overrides['limits.work_requests'],50);
});
test('closing setup during a read creates no draft; missing project opens the picker',async()=>{
 const c=entryContext();let finish,open=true;c.context.setupDraft=()=>new Promise(r=>finish=r);
 c.context.start();const pending=c.getSetup().onNew({repository:'/repo',prompt:'Saved draft',isOpen:()=>open,close(){}});
 open=false;finish({record:{values:{limits:{dollars:2}}},overrides:{}});await pending;
 assert.equal(c.calls.length,0);assert.equal(c.drafts.size,0);
 c.context.state.task=null;c.context.state.project=null;c.context.start();assert.equal(c.getPickers(),1);
});
test('reusing a saved task fetches it before the existing schedule approval form',async()=>{
 const c=entryContext();c.context.start();let finish,open=true;
 c.context.api=path=>{assert.equal(path,'/tasks/saved');return new Promise(r=>finish=r);};
 const pending=c.getSetup().onExisting({id:'saved'},()=>open,()=>{});
 open=false;finish({id:'saved'});await pending;assert.equal(c.calls.length,0);
 open=true;c.context.api=async()=>({id:'saved'});
 await c.getSetup().onExisting({id:'saved'},()=>open,()=>{});
 assert.deepEqual(c.calls,[['schedule',{id:'saved'}]]);
});

test('schedule selection is distinct from recurrence and full-suite consent',()=>{
 const preview={interval_hours:6,approval_digest:'snapshot'};
 const form={elements:{schedule_interval:{value:'6'},schedule_approved:{checked:false},allow_task_commands:{checked:true},schedule_full:{checked:false}}};
 assert.throws(()=>schedules.approval(form,preview),/Approve recurring/);
 form.elements.schedule_approved.checked=true;
 assert.throws(()=>schedules.approval(form,preview,['all tests']),/full-suite/);
 form.elements.schedule_full.checked=true;
 assert.deepEqual(schedules.approval(form,preview,['all tests']),{interval_hours:6,approval_digest:'snapshot',approved:true,full_suite_approved:true});
 form.elements.allow_task_commands.checked=false;
 assert.throws(()=>schedules.approval(form,preview),/Allow task commands/);
 form.elements.schedule_interval.value='0';
 assert.equal(schedules.approval(form,{...preview,error:'Paid plan'},['all tests']),null);
 assert.match(schedules.approvalMarkup(preview),/unmerged PR holds/);
 assert.match(schedules.approvalMarkup({...preview,error:'<bad>'}),/&lt;bad&gt;/);
});
test('chat distinguishes pending frequency from saved recurrence and one-time execution',()=>{
 const task={planning_request:{schedule_request:{interval_hours:12}},branch_run:{}};
 assert.deepEqual(schedules.status(task),{interval_hours:12,label:'Awaiting approval'});
 task.branch_run.authorization_ref='approved';assert.equal(schedules.status(task),null);
 task.schedule_start={interval_hours:12};assert.equal(schedules.status(task).label,'Saving approved schedule');
 task.schedule={id:'recurring',interval_hours:12,enabled:false};assert.equal(schedules.status(task).label,'Schedule disabled');
});
test('combined Start binds schedule consent, deduplicates and reconciles a lost acknowledgement',async()=>{
 const ui=require('../dist/branch_ui.js');let received,writes=0;
 const task={id:'one',schedule:{id:'saved',interval_hours:6},branch_run:{status:'running',authorization_ref:'yes'}};
 const controller=ui.startController({api:async(url,body)=>{if(body){writes++;received=body;throw Error('response lost');}return task;}});
 const choice={interval_hours:6,approval_digest:'snapshot',approved:true};
 await controller.start({task_id:'one',proposal_id:'plan',schedule:choice,allow_task_commands:true});
 assert.deepEqual(received.schedule,choice);assert.equal(controller.get('one').status,'accepted');
 await controller.start({task_id:'one',proposal_id:'plan',schedule:choice});assert.equal(writes,1);
});

test('prefilled scheduled prompt is present when the durable draft is saved',()=>{
 const source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8').match(/function newTask\(prefill='',preset=\{\}\) \{[\s\S]*?\n\}(?=\nfunction scheduleTask)/)[0];
 const input={value:'',focus(){}},saved=[];
 const c={home(){},state:{},basename:s=>s,renderHome(){},restoreDraft(){},saveDraft(){},localStorage:{setItem(){}},$:()=>input,branchUI:{newChat:(mode,schedule)=>saved.push({prompt:input.value,mode,schedule})}};
 vm.createContext(c);vm.runInContext(source+';newTask("Saved description",{repository:"/repo",mode:"unattended",schedule_request:{interval_hours:24}})',c);
 assert.equal(saved[0].prompt,'Saved description');assert.equal(saved[0].schedule.interval_hours,24);
});

test('polling retains schedule controls and displays older schedule receipts without invented intervals',()=>{
 const source=fs.readFileSync(require.resolve('../dist/branch_ui.js'),'utf8').match(/ function syncSchedule\(\)\{[\s\S]*?\n \}(?=\n\n const documentRow)/)[0];
 let writes=0,html='',opened=0;const manage={};
 const row={get innerHTML(){return html.replace('data-manage-schedule','data-manage-schedule=""');},set innerHTML(value){writes++;html=value;},querySelector:s=>s==='[data-manage-schedule]'?manage:null};
 const c={scheduleRow:row,schedules,getState:()=>({task:{schedule:{id:'legacy',name:'Saved schedule'}}}),escape:s=>s,options:{manageSchedules:()=>opened++}};
 vm.createContext(c);vm.runInContext("let scheduleMarkup='';"+source+';syncSchedule();syncSchedule();',c);
 assert.equal(writes,1);assert.doesNotMatch(html,/undefined/);manage.onclick();assert.equal(opened,1);
});
