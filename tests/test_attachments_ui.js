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
  vm.createContext(c);
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
    projectManagerError: assert.fail, toast: text => notices.push(text),
    formAction: (_, action) => {pending = action();},
    api: async (path, body) => { calls.push({path, body}); return {git: false, name: 'folder-only', path: '/fixture/folder-only'}; }};
  vm.createContext(c);
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
  vm.createContext(c);
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
