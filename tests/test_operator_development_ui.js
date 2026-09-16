'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8'),c={esc:s=>String(s).replaceAll('<','&lt;')};vm.createContext(c);vm.runInContext(source.slice(source.indexOf('function developmentSettings'),source.indexOf('function executionPreferences')),c);
test('operator development is explicit opt-in with truthful preserved safeguards',()=>{assert.doesNotMatch(c.developmentSettings({}),/name="development_mode" checked/);assert.match(c.developmentSettings({development_mode:true}),/name="development_mode" checked/);assert.match(c.developmentSettings({}),/Spending authorization, permissions, independent review/);assert.match(c.developmentSettings({}),/recovery-attempt caps/);});
test('correction acknowledgment distinguishes interruption, running, consent, and actual blocker',()=>{assert.equal(c.operatorContinuationMarkup({}),'');for(const status of ['interrupting','blocked','needs_consent']){const html=c.operatorContinuationMarkup({status:'running',operator_continue:{status,reason:'Exact <blocker>'}});assert.match(html,/Exact &lt;blocker>/);assert.equal(html.includes('data-chat-action="resume"'),status==='needs_consent');}assert.match(c.operatorContinuationMarkup({status:'running',operator_continue:{status:'interrupting'}}),/stopping the previous approach/);});
vm.runInContext(source.slice(source.indexOf('function operatorRecoveryFields'),source.indexOf('async function operatorRecovery')),c);
test('recovery controls follow server capabilities and revision approval is explicit',()=>{const none=c.operatorRecoveryFields({reason:'Wait for pause'});assert.doesNotMatch(none,/data-recovery=/);const html=c.operatorRecoveryFields({can_enable:true,can_retry:true,can_model:true,can_revise:true,models:[{id:'allowed',label:'Allowed model'}]});assert.match(html,/Enable development mode for this task/);assert.match(html,/value="allowed"/);assert.match(html,/Approve item revision &amp; continue/);assert.match(html,/Other accepted criteria, checks, spending and permissions remain in force/);});
vm.runInContext(source.slice(source.indexOf('function canTakeOver'),source.indexOf('async function takeOverTask')),c);
test('failed saved tasks offer takeover but routine replies and genuine questions do not',()=>{for(const status of ['paused','error','blocked','budget_paused'])assert.equal(c.canTakeOver({status}),true);assert.equal(c.canTakeOver({status:'awaiting_reply'}),false);assert.equal(c.canTakeOver({status:'paused',pause_summary:{question:'Choose format'}}),false);assert.equal(c.canTakeOver({status:'paused',branch_run:{authorization_ref:null}}),false);assert.equal(c.canTakeOver({status:'paused',branch_run:{authorization_ref:'approved'}}),true);});

test("completed tasks do not retain a continuing notice",()=>{assert.equal(c.operatorContinuationMarkup({status:"approved",operator_continue:{status:"running"}}),"");});

test('ordinary continuation stays quiet across chat updates',()=>{for(const status of ['running','reviewing','verifying','queued','starting','approved']){assert.equal(c.operatorContinuationMarkup({status,operator_continue:{status:'running',reason:'Continuing from saved files with your direction.'}}),'');}});

test('sidebar hide wiring preserves chat submission and cancellation',()=>{
  const nodes=new Map(), get=key=>{if(!nodes.has(key))nodes.set(key,{});return nodes.get(key);};
  let sent=0,hidden=0,confirmed=false,menuAnchor=null,menuLabel=null,menuActions=null;
  get('#demo-row').classList={add:name=>{assert.equal(name,'hidden');hidden++;}};
  const storage=new Map();
  const fakeLocalStorage={setItem:(k,v)=>storage.set(k,v),getItem:k=>storage.get(k)};
  const form={};
  let dialogHtml='';
  const noop=()=>{}, context={
    $: (sel, root) => (sel === 'form' ? form : get(sel)),
    modalHeader:(k,t)=>`<h2>${t}</h2>`,
    dialog:html=>{
      dialogHtml=html;
      return {close:()=>{}};
    },
    localStorage:fakeLocalStorage,
    compactMenu:(anchor,label,actions)=>{
      menuAnchor=anchor;menuLabel=label;menuActions=actions;
      if(confirmed&&actions[0]?.run){
        actions[0].run();
        if(form.onsubmit) form.onsubmit({preventDefault:()=>{}});
      }
    },
    sendChat:()=>sent++,openProject:noop,home:noop,newTask:noop,openSearch:noop,openConnections:noop,sampleDialog:noop,chatLimits:noop,executionPreferences:noop,saveDraft:noop,renderComposer:noop,steerTask:noop,stopFromComposer:noop
  };
  vm.createContext(context);
  const updatedSource=fs.readFileSync(require.resolve('../dist/app.js'),'utf8');
  vm.runInContext(updatedSource.slice(updatedSource.indexOf("$('#home-trigger').onclick="),updatedSource.indexOf('function toggleInspector')),context);
  let prevented=0;
  get('#chat-form').onsubmit({preventDefault:()=>prevented++});
  get('#chat-input').onkeydown({key:'Enter',preventDefault:()=>prevented++});
  assert.equal(sent,2);assert.equal(prevented,2);
  for(const selector of ['#new-task','#settings-trigger','#demo-trigger','#chat-stop'])assert.equal(typeof get(selector).onclick,'function');
  get('#hide-demo').onclick();assert.equal(hidden,0);
  assert.equal(menuLabel,'Demo options');
  assert.equal(typeof menuActions[0].run,'function');
  assert.equal(menuActions[0].action,undefined);
  confirmed=true;get('#hide-demo').onclick();assert.equal(hidden,1);
  assert.equal(storage.get('cheapos-demo-hidden'),'true');
  assert.match(dialogHtml,/Hide Try a sample task\?/);
  assert.match(dialogHtml,/This will remove the demo from the sidebar until you re-enable it in settings\./);
  assert.match(dialogHtml,/Cancel/);
  assert.match(dialogHtml,/Yes, hide/);
  get('#chat-form').onsubmit({preventDefault:()=>{}});assert.equal(sent,3);
});

test('findMenuAnchor includes #hide-demo',()=>{
  const selectorMatch=source.match(/const findMenuAnchor=key=>\$\$\('([^']+)'\)/);
  assert.ok(selectorMatch);
  assert.ok(selectorMatch[1].includes('#hide-demo'));
});