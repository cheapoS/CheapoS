'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const guide=require('../dist/guidance.js'),stamp='2026-09-14T12:00:00Z';
function task(extra={}){return {id:'a',prompt:'Fix parser',status:'running',active_role:'worker',changes:[],checks:[],checkpoints:[],providers:{worker:{model:'remote-worker'},coordinator:{model:'local-helper'}},coordinator_recovery:[{state:'dispatched',selected_model:'local-helper'}],events:[{id:'help',kind:'coordinator_recovery',title:'Coordinator helping',time:stamp,detail:{state:'dispatched',summary:'The worker got stuck. I am checking saved work.'}}],...extra};}
const steps=t=>guide.conversation.build(t).filter(e=>e.kind==='assistant').flatMap(e=>e.steps);
test('coordinator waiting is its own step with actual streamed model/output, not reviewer',()=>{const t=task({stream:{role:'coordinator',phase:'answer',model:'local-helper',content:'Inspect the parser return value.'}});const replies=guide.conversation.build(t).filter(e=>e.kind==='assistant');assert.equal(replies.at(-1).steps.at(-1).title,'Coordinator helping');assert.equal(replies.at(-1).steps.at(-1).role,'coordinator');assert.equal(replies.at(-1).stream.content,'Inspect the parser return value.');const waiting=steps(task()).at(-1);assert.equal(waiting.title,'Coordinator helping');assert.match(waiting.detail,/Waiting/);});
test('applied guidance remains historical before worker continuation, never task success',()=>{const t=task();t.coordinator_recovery[0].state='applied';t.events.push({id:'applied',kind:'coordinator_recovery',time:stamp,detail:{state:'applied',summary:'Inspect the parser return value.'}},{id:'worker',kind:'model',title:'Requesting worker: remote-worker',time:stamp});const list=steps(t);assert.equal(list[0].title,'Guidance sent to the worker');assert.equal(list[0].detail,'Inspect the parser return value.');assert.equal(list.at(-1).role,'worker');});
test('settings legacy Off and installed choices preserve explicit model without changing placement',()=>{const source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8'),code=source.slice(source.indexOf('function coordinatorSettings'),source.indexOf('function executionPreferences'));const c={esc:s=>String(s).replaceAll('<','&lt;')};vm.createContext(c);vm.runInContext(code,c);const off=c.coordinatorSettings({mode:'remote'},['local-a']);assert.match(off,/value="off" selected/);assert.match(off,/local-a/);assert.match(off,/no background thinking/);const on=c.coordinatorSettings({mode:'remote',coordinator_assistance:true,coordinator_model:'saved-helper'},[]);assert.match(on,/value="on" selected/);assert.match(on,/saved-helper · availability not confirmed/);assert.match(on,/Ordinary remote work remains usable/);});
test('paused worker request cannot relabel coordinator identity or count unfinished consultation done',()=>{const t=task({status:'paused'});t.events.push({id:'worker',kind:'model',title:'Requesting worker: remote-worker',time:stamp});const list=steps(t);assert.equal(list[0].role,'coordinator');assert.notEqual(list[0].model,'remote-worker');assert.equal(list[0].outcome,'pending');assert.equal(list.at(-1).title,'Worker continuation stopped');});
test('observed edits and checks after assistance project worker outcomes, not another consultation',()=>{for(const action of ['write_file','run_checks']){const t=task({status:'paused'});t.coordinator_recovery[0].state='applied';t.events.push({id:'result',kind:'coordinator_recovery',time:stamp,detail:{state:'result',summary:'Actual saved result',result:{action,passed:false}}});const list=steps(t);assert.equal(list.at(-1).phase,action==='run_checks'?'checks':'work');assert.notEqual(list.at(-1).role,'coordinator');assert.equal(list.at(-1).detail,'Actual saved result');}});
test('unattended worker stall offers saved-work continuation rather than inventing missing input',()=>{const branch=require('../dist/branch_ui.js');const p=branch.pausePresentation({branch_run:{status:'paused',pause_detail:{version:1,cause:'repeated_work',role:'worker',next_action:'correction'}}});assert.match(p.headline,/Worker could not choose/);assert.equal(p.actionLabel,'Review saved work and continue in chat');});
test('captured task status distinguishes local chat from recovery and new-chat defaults',()=>{
 const t=task({execution:{mode:'delegate',local_model:'gemma',coordinator_assistance:false}});
 assert.equal(guide.coordinatorStatus(t).label,'Off');assert.match(guide.coordinatorStatus(t).pauseNote,/was not attempted/);
 const source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8');
 const c={CheapOSGuide:guide,state:{preferences:{execution:{coordinator_assistance:true}}},esc:String};vm.createContext(c);
 vm.runInContext(source.slice(source.indexOf('function coordinatorTaskNotice'),source.indexOf('function executionPreferences')),c);
 assert.match(c.coordinatorTaskNotice(t,true),/This chat · Coordinator assistance: Off/);
 assert.match(c.coordinatorSettings({coordinator_assistance:true},[]),/Defaults for new chats<\/strong> · On/);
 assert.match(c.coordinatorSettings({},[]),/Restarting restores your saved choice/);
 const ready={...t,coordinator_reassessment:{available:true,model:'gemma'}};
 assert.match(c.coordinatorReassessmentMarkup(ready),/Enable coordinator &amp; reassess/);
 assert.match(c.coordinatorReassessmentMarkup(ready),/No new prompt needed/);
 assert.doesNotMatch(c.coordinatorReassessmentMarkup({...ready,coordinator_reassessment:{available:false,reason:'Already attempted'}}),/data-chat-action/);
 assert.match(c.coordinatorReassessmentMarkup({...ready,execution:{coordinator_assistance:true}}),/Reassess with coordinator/);
});
test('a malformed coordinator reply names the failure and offers its one format repair',()=>{
 const t=task({status:'paused',error:'Coordinator reassessment did not produce an applicable next step.',
 recovery_blocked:0,pause_summary:{},coordinator_reassessment:{available:true,format_repair:true,model:'local-helper'},
 coordinator_recovery:[{state:'failed',diagnostic:'Coordinator must return one JSON object'}]});
 const view=guide.taskGuide(t);assert.equal(view.title,'Coordinator reply could not be read.');assert.match(view.description,/Retry coordinator format/);assert.doesNotMatch(view.description,/Worker could not choose/);
 const c={CheapOSGuide:guide,state:{},esc:String};vm.createContext(c);const source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8');
 vm.runInContext(source.slice(source.indexOf('function coordinatorReassessmentMarkup'),source.indexOf('async function reassessCoordinator')),c);
 assert.match(c.coordinatorReassessmentMarkup(t),/Retry coordinator format/);assert.match(c.coordinatorReassessmentMarkup(t),/original attempt and usage remain counted/);
 const reusable={...t,coordinator_reassessment:{available:true,reuse_saved:true,model:'local-helper'},coordinator_recovery:[{state:'failed',diagnostic:'Advice references a path outside supplied evidence'}]};
 assert.equal(guide.taskGuide(reusable).title,'Saved coordinator guidance is ready.');
 assert.match(c.coordinatorReassessmentMarkup(reusable),/Continue with saved guidance/);
 assert.match(c.coordinatorReassessmentMarkup(reusable),/without another coordinator call/);
 t.events.push({id:'failed',kind:'coordinator_recovery',time:stamp,detail:{state:'failed',diagnostic:'Coordinator must return one JSON object'}});
 assert.equal(steps(t).at(-1).title,'Coordinator reply could not be used');assert.equal(steps(t).at(-1).outcome,'failed');
});
