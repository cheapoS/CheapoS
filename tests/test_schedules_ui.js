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
 const form={elements:{prompt:{value:' Check release notes '}},querySelector:()=>button};
 const existing={elements:{task_id:{value:'saved'}},querySelector:()=>existingButton};
 const d={open:true,close(){this.open=false;},querySelector:s=>({'[data-new-schedule]':form,'[data-existing-schedule]':existing,'[role=alert]':error}[s])};
 return {d,form,existing,button,error};
}
test('new schedule setup explains the approval steps and submits only one draft',async()=>{
 const c=setupDialog();let html,finish,calls=0;
 schedules.setup({project:{path:'/repo',name:'<Project>'},tasks:[],dialog:s=>(html=s,c.d),header:()=>'',onNew:async values=>{calls++;assert.equal(values.repository,'/repo');assert.equal(values.prompt,'Check release notes');await new Promise(r=>finish=r);values.close();}});
 assert.match(html,/&lt;Project&gt;/);assert.match(html,/Plan → Schedule this task/);
 assert.match(html,/Nothing runs until you send/);assert.match(html,/\$0 API spending allowance/);
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
 await setup.onNew({repository:'/repo',prompt:'Repeat this',isOpen:()=>true,close:()=>closed++});
 assert.equal(closed,1);assert.equal(c.calls.length,1);assert.equal(c.calls[0][0],'draft');
 assert.equal(c.calls[0][2].mode,'unattended');assert.equal(c.calls[0][2].repository,'/repo');
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
