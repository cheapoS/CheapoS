'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync(require.resolve('../dist/app.js'), 'utf8');

function attachment(id) {
  return {id, filename: id + '.png', name: id + '.png', mime_type: 'image/png',
    is_image: true, size: 10, url: '/api/uploads/' + id + '/' + id + '.png'};
}

function fixture(initial = []) {
  const input = {value: 'A draft'}, container = {};
  const state = {task: {id: 'A'}, drafts: new Map(), draftAttachments: new Map(), composerAttachments: initial};
  const uploads = [];
  let buttons = [];
  class FileReader {
    readAsDataURL() { this.result = 'data:image/png;base64,AAAA'; this.onload(); }
  }
  const c = {state, FileReader, esc: String, toast: error => {throw Error(error);},
    $: selector => selector === '#chat-input' ? input : container,
    $$: () => (buttons = state.composerAttachments.map((_, index) => ({dataset: {removeIdx: index}}))),
    branchUI: {restoreDraft() {}}, renderComposer() {},
    api: () => new Promise(resolve => uploads.push(resolve))};
  c.CheapOSGitWorkflow=require('../dist/git_workflow.js');vm.createContext(c);
  vm.runInContext(source.slice(source.indexOf('const draftKey='), source.indexOf('function home()')), c);
  vm.runInContext(source.slice(source.indexOf('function clearOwnedDraft('), source.indexOf('function pendingMessageMarkup(')), c);
  vm.runInContext(source.slice(source.indexOf('function renderComposerAttachments()'), source.indexOf('function renderComposer()')), c);
  return {c, state, input, uploads,
    remove(index) { c.renderComposerAttachments(); buttons[index].onclick({preventDefault() {}, stopPropagation() {}}); },
    switchTo(id) { c.saveDraft(); state.task = {id}; c.restoreDraft(); },
    upload() { return c.uploadFiles([{name: 'image.png', size: 10, type: 'image/png'}]); }};
}

test('upload completion belongs to the original draft after switching chats', async () => {
  const f = fixture(), pending = f.upload();
  await new Promise(resolve => setImmediate(resolve));
  f.switchTo('B');
  f.state.composerAttachments = [attachment('B-file')];
  f.input.value = 'B draft';
  f.c.saveDraft();
  f.uploads.shift()(attachment('A-file'));
  await pending;
  assert.deepEqual(Array.from(f.state.composerAttachments, a => a.id), ['B-file']);
  assert.equal(f.input.value, 'B draft');
  f.switchTo('A');
  assert.deepEqual(Array.from(f.state.composerAttachments, a => a.id), ['A-file']);
  assert.equal(f.input.value, 'A draft');
});

test('removing an attachment during another upload cannot resurrect it', async () => {
  const f = fixture([attachment('removed')]), pending = f.upload();
  await new Promise(resolve => setImmediate(resolve));
  f.remove(0);
  f.uploads.shift()(attachment('new-file'));
  await pending;
  assert.deepEqual(Array.from(f.state.composerAttachments, a => a.id), ['new-file']);
  f.switchTo('B'); f.switchTo('A');
  assert.deepEqual(Array.from(f.state.composerAttachments, a => a.id), ['new-file']);
});

test('late send acknowledgement retains later uploads and another chat draft', async () => {
  const f = fixture([attachment('submitted')]), pending = f.upload();
  await new Promise(resolve => setImmediate(resolve));
  f.switchTo('B');
  f.state.composerAttachments = [attachment('B-file')];
  f.c.saveDraft();
  f.uploads.shift()(attachment('later-upload'));
  await pending;
  f.c.clearOwnedDraft('A', 'A draft', [attachment('submitted')]);
  assert.deepEqual(Array.from(f.state.composerAttachments, a => a.id), ['B-file']);
  f.switchTo('A');
  assert.deepEqual(Array.from(f.state.composerAttachments, a => a.id), ['later-upload']);
});

test('folder-only creation completes without attempting to open a Git project', async () => {
  const form = {}, calls = [], notices = [];
  let pending, closed = 0, callback = 0;
  const nodes = {'#project-manager-modal': {querySelectorAll: () => []}, '#create-project-form': form,
    '#new-project-name': {value: 'folder-only'}, '#new-project-parent': {value: '/fixture'}, '#init-git': {checked: false}};
  const c = {$: selector => nodes[selector], projectManager: {currentPath: '/fixture'},
    projectManagerAfter: () => callback++, closeProjectManager: () => closed++,
    projectManagerError: text => {if(text)assert.fail(text);}, toast: text => notices.push(text),
    formAction: (_, action) => {pending = action();},
    api: async (path, body) => { calls.push({path, body}); return {git: false, name: 'folder-only', path: '/fixture/folder-only'}; }};
  c.CheapOSGitWorkflow=require('../dist/git_workflow.js');vm.createContext(c);
  vm.runInContext(source.slice(source.indexOf('function bindProjectManagerControls()'), source.indexOf('bindProjectManagerControls();')), c);
  c.bindProjectManagerControls();
  form.onsubmit({preventDefault() {}});
  await pending;
  assert.equal(calls.length, 1);
  assert.equal(calls[0].path, '/projects/create');
  assert.equal(calls[0].body.init_git, 0);
  assert.equal(closed, 1);
  assert.equal(callback, 1);
  assert.match(notices[0], /Created directory/);
});

test('task tab bindings and keyboard navigation leave project manager tabs independent', () => {
  function node(view) {
    const classes = new Set();
    return {dataset: {view}, hidden: false, classes, focus() {this.focused = true;},
      classList: {toggle(name, enabled) {enabled ? classes.add(name) : classes.delete(name);}}};
  }
  const taskTabs = [node('chat'), node('changes')], modalTabs = [node('open'), node('create')];
  const nodes = {'#project-manager-modal': {querySelectorAll: () => modalTabs},
    '#project-open': node(), '#project-create': node(), '#new-project-parent': {}, '#new-project-name': node()};
  const selected = [];
  const c = {$: selector => nodes[selector],
    $$: selector => selector === '.tabs .tab' ? taskTabs : [...taskTabs, ...modalTabs],
    projectManager: {currentPath: '/fixture'}, setView: view => selected.push(view)};
  c.CheapOSGitWorkflow=require('../dist/git_workflow.js');vm.createContext(c);
  vm.runInContext(source.slice(source.indexOf('function showProjectView('), source.indexOf('function closeProjectManager(')), c);
  vm.runInContext(source.slice(source.indexOf('function bindProjectManagerControls()'), source.indexOf('bindProjectManagerControls();')), c);
  c.bindProjectManagerControls();
  vm.runInContext(source.split('\n').find(line => line.startsWith('$$(') && line.includes('b.onkeydown')), c);
  modalTabs[1].onclick();
  assert.equal(nodes['#project-open'].classes.has('hidden'), true);
  assert.equal(nodes['#project-create'].classes.has('hidden'), false);
  assert.equal(nodes['#new-project-parent'].value, '/fixture');
  assert.equal(nodes['#new-project-name'].focused, true);
  assert.deepEqual(selected, []);
  taskTabs[0].onkeydown({key: 'End', preventDefault() {}});
  assert.deepEqual(selected, ['changes']);
  assert.equal(taskTabs[1].focused, true);
});

test('attachment-only creation sends captured draft settings with the files', async () => {
  const f = fixture([attachment('screenshot')]), calls = [];
  Object.assign(f.state, {task: null, project: {path: '/fixture'}, selection: 1,
    config: {}, preferences: {}, pendingMessages: new Map(), pendingSends: new Set(), sendErrors: new Map()});
  f.input.value = ''; f.input.focus = () => {};
  const settings = {expected_revision: 2, expected_parent_revision: 3, overrides: {'keep_up_to_date': true}};
  Object.assign(f.c, {sendingHere: () => false, submissionAvailability: () => ({allowed: true}),
    canTakeOver: () => false, branchUI: {interceptSubmit: async () => false},
    setupDraft: async () => ({values: {execution: {mode: 'remote'}}}),
    capturedDraftSetup: async repository => {assert.equal(repository, '/fixture'); return {settings};},
    beginMessageSend() {}, loadTasks: async () => {}, selectTask: async () => {}, startTask: async () => true,
    renderHome() {}, renderChat() {},
    api: async (path, body) => {calls.push({path, body}); return {id: 'created'};}});
  vm.runInContext(source.slice(source.indexOf('async function dispatchChat()'), source.indexOf('async function steerTask(')), f.c);
  await f.c.dispatchChat();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].path, '/tasks');
  assert.equal(calls[0].body.prompt, '');
  assert.deepEqual(calls[0].body.settings, settings);
  assert.deepEqual(Array.from(calls[0].body.attachments, a => a.id), ['screenshot']);
  assert.equal(f.state.composerAttachments.length, 0);
});

test('choosing a project while sending carries attachments without replacing its saved files', async () => {
  const f = fixture([attachment('unassigned')]);
  f.state.task = null;
  f.input.value = 'Inspect this file';
  f.c.saveDraft();
  let afterOpen;
  Object.assign(f.c, {sendingHere: () => false, submissionAvailability: () => ({allowed: true}),
    canTakeOver: () => false, branchUI: {interceptSubmit: async () => false, restoreDraft() {}},
    openProject: callback => {afterOpen = callback;}});
  vm.runInContext(source.slice(source.indexOf('async function dispatchChat()'), source.indexOf('async function steerTask(')), f.c);
  await f.c.dispatchChat();
  f.state.draftAttachments.set('/chosen', [attachment('saved-project-file')]);
  f.state.project = {path: '/chosen'};
  f.c.restoreDraft();
  afterOpen();
  assert.equal(f.input.value, 'Inspect this file');
  assert.deepEqual(Array.from(f.state.composerAttachments, a => a.id), ['saved-project-file', 'unassigned']);
  assert.equal(f.state.draftAttachments.has('new'), false);
  f.c.restoreDraft();
  assert.deepEqual(Array.from(f.state.composerAttachments, a => a.id), ['saved-project-file', 'unassigned']);
});
test('user message text hides attachment metadata notes from the chat body', () => {
  const c = {};
  c.CheapOSGitWorkflow=require('../dist/git_workflow.js');vm.createContext(c);
  vm.runInContext(source.slice(source.indexOf('function stripAttachmentNotes('), source.indexOf('function messageText(')), c);
  assert.equal(typeof c.stripAttachmentNotes, 'function');

  // Plain text with no attachment note is unchanged.
  assert.equal(c.stripAttachmentNotes('explain this image'), 'explain this image');

  // A single image note with a full filesystem path is stripped.
  const imageNote = 'explain this image\n\n### Attached Image: cover-v1.jpg\n[Image file saved at /Users/carlosa8c/Library/Application Support/cheapoS/uploads/abcd/cover-v1.jpg. Use inspect_image tool to analyze visual details.]';
  assert.equal(c.stripAttachmentNotes(imageNote), 'explain this image');

  // An image note without a title line is stripped cleanly.
  assert.equal(c.stripAttachmentNotes('### Attached Image: cover-v1.jpg\n[Image file saved at /path/to/cover-v1.jpg.]'), '');

  // A document note with an embedded code fence is stripped in full.
  const docNote = 'review this\n\n### Attached Document: calc.py\n```py\ndef calculate():\n    return 1\n```';
  assert.equal(c.stripAttachmentNotes(docNote), 'review this');

  // Multiple attached notes after one title line are all stripped.
  const multi = 'look\n\n### Attached Image: a.png\n[Image file saved at /a.png.]\n\n### Attached Document: b.txt\n```\nhi\n```';
  assert.equal(c.stripAttachmentNotes(multi), 'look');
});

function deliveryFixture(status='awaiting_reply') {
  const f=fixture([attachment('screenshot')]), nodes={'#chat-input':f.input,'#chat-form':{},'#chat-steer':{}}, calls=[];
  Object.assign(f.state,{selection:1,project:{path:'/fixture'},preferences:{execution:{mode:'remote'}},
    pendingMessages:new Map(),pendingSends:new Set(),sendErrors:new Map()});
  f.state.task.status=status;f.state.task.requests=['original'];f.input.focus=()=>{};
  Object.assign(f.c,{$:selector=>(nodes[selector]||={}),taskBusy:task=>task.status==='running',
    branchUI:{interceptSubmit:async()=>false,restoreDraft(){}},submissionAvailability:()=>({allowed:true}),
    messageText:String,renderChat(){},renderTask(){},renderHome(){},refresh:async()=>{},refreshContext:async()=>{},
    toast(){},api:(path,body)=>new Promise((resolve,reject)=>calls.push({path,body,resolve,reject}))});
  vm.runInContext(source.split('\n').find(line=>line.startsWith('function sendingHere()')),f.c);
  vm.runInContext(source.slice(source.indexOf('function pendingMessageMarkup()'),source.indexOf('function renderComposerAttachments()')),f.c);
  vm.runInContext(source.slice(source.indexOf('function canTakeOver('),source.indexOf('function checkCommandText(')),f.c);
  vm.runInContext(source.slice(source.indexOf('const submissionEntries='),source.indexOf('async function boostHeadroom(')),f.c);
  let delivery;
  const send=f.c.sendChat;
  f.c.sendChat=()=>{delivery=send();return delivery;};
  for(const line of source.split('\n').filter(line=>line.startsWith("$('#chat-form').onsubmit=")||line.startsWith("$('#chat-input').onkeydown=")||line.startsWith("if($('#chat-steer'))$('#chat-steer').onclick=")))vm.runInContext(line,f.c);
  return {...f,calls,send(method){
    if(method==='enter')f.input.onkeydown({key:'Enter',preventDefault(){}});
    else if(method==='update')nodes['#chat-steer'].onclick();
    else nodes['#chat-form'].onsubmit({preventDefault(){}});
    return delivery;
  }};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));

test('Send, Enter and Send update deliver the same image through chat with immediate pending feedback',async()=>{
  for(const [status,method] of [['awaiting_reply','click'],['awaiting_reply','enter'],['paused','click'],['paused','enter'],['running','update']]){
    const f=deliveryFixture(status), pending=f.send(method);await tick();
    assert.equal(f.calls.length,1);assert.equal(f.calls[0].body.message,'A draft');
    assert.deepEqual(Array.from(f.calls[0].body.attachments,a=>a.id),['screenshot']);
    assert.equal(f.calls[0].path,'/tasks/A/chat-message');
    assert.match(f.c.pendingMessageMarkup(),/<img[^>]*screenshot\.png/);
    assert.match(f.c.pendingMessageMarkup(),/Sending…/);
    f.c.renderComposerAttachments();assert.equal(f.c.$('#composer-attachments').hidden,true);
    await f.send(method);assert.equal(f.calls.length,1);
    f.calls[0].resolve({...f.state.task,status:'running'});await pending;
    assert.equal(f.input.value,'');assert.equal(f.state.composerAttachments.length,0);
    assert.equal(f.c.pendingMessageMarkup(),'');
  }
});

test('failed takeover keeps the text and image draft, including attachment-only messages',async()=>{
  const f=deliveryFixture('paused');f.input.value='';
  const pending=f.send('click');await tick();
  assert.equal(f.calls.length,1);assert.equal(f.calls[0].body.attachments[0].id,'screenshot');
  f.calls[0].reject(Error('Disconnected'));await pending;
  assert.equal(f.state.composerAttachments[0].id,'screenshot');
  assert.equal(f.state.sendErrors.get('A'),'Disconnected');
  assert.equal(f.c.pendingMessageMarkup(),'');
  f.c.renderComposerAttachments();assert.equal(f.c.$('#composer-attachments').hidden,false);
});

test('Send waits for an in-flight upload and includes it without another Enter',async()=>{
  const f=deliveryFixture();f.state.composerAttachments=[];
  const upload=f.upload();await tick();
  const pending=f.send('click');await tick();await f.send('enter');
  assert.equal(f.calls.length,1);assert.equal(f.calls[0].path,'/upload');assert.equal(f.c.sendingHere(),true);
  f.calls[0].resolve(attachment('uploaded'));await upload;await tick();
  assert.equal(f.calls.length,2);assert.equal(f.calls[1].body.attachments[0].id,'uploaded');
  f.calls[1].resolve({...f.state.task,status:'running'});await pending;
  assert.equal(f.state.composerAttachments.length,0);
});

test('failed upload or switching chats while uploading never sends a partial or wrong-chat message',async()=>{
  for(const switchChat of [false,true]){
    const f=deliveryFixture();f.state.composerAttachments=[];
    const upload=f.upload();await tick();const pending=f.send('click');await tick();
    if(switchChat){f.switchTo('B');f.state.selection++;f.input.value='Other draft';f.calls[0].resolve(attachment('uploaded'));}
    else f.calls[0].reject(Error('Upload failed'));
    await upload;await pending;
    assert.equal(f.calls.length,1);assert.equal(f.input.value,switchChat?'Other draft':'A draft');
    if(switchChat){f.switchTo('A');assert.equal(f.state.composerAttachments[0].id,'uploaded');}
  }
});


test('project manager opens on an empty first launch, not an existing or hidden project', () => {
  let opened = 0;
  const state = {projects: [], hiddenProjects: []};
  const c = {state, openProject: () => opened++};
  c.CheapOSGitWorkflow=require('../dist/git_workflow.js');vm.createContext(c);
  vm.runInContext(source.slice(source.indexOf('function openInitialProjectManager()'), source.indexOf('function closeProjectManager()')), c);
  c.openInitialProjectManager();
  assert.equal(opened, 1);
  for (const patch of [{projects: [{}]}, {hiddenProjects: [{}]}, {project: {}}, {task: {}}]) {
    Object.assign(state, {projects: [], hiddenProjects: [], project: null, task: null}, patch);
    c.openInitialProjectManager();
    assert.equal(opened, 1);
  }
});

test('project creation failures stay visible in the open manager', async () => {
  const form = {}, errors = [];
  let pending, closed = 0;
  const nodes = {'#project-manager-modal': {querySelectorAll: () => []}, '#create-project-form': form,
    '#new-project-name': {value: 'bad/name'}, '#new-project-parent': {value: '/fixture'}, '#init-git': {checked: true}};
  const c = {$: selector => nodes[selector], projectManager: {currentPath: '/fixture'},
    closeProjectManager: () => closed++, projectManagerError: text => errors.push(text),
    formAction: (_, action) => {pending = action();}, api: async () => {throw Error('Invalid project name');}};
  c.CheapOSGitWorkflow=require('../dist/git_workflow.js');vm.createContext(c);
  vm.runInContext(source.slice(source.indexOf('function bindProjectManagerControls()'), source.indexOf('bindProjectManagerControls();')), c);
  c.bindProjectManagerControls();
  form.onsubmit({preventDefault() {}});
  await pending;
  assert.equal(closed, 0);
  assert.equal(errors.at(-1), 'Invalid project name');
});
