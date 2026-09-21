const test=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const storage=require('../dist/storage.js');
test('Storage shows totals and escaped eligibility without inventing cleanup actions',()=>{
 const data={task_bytes:2048,workspace_bytes:1024,eligible_bytes:0,tasks:[{title:'<img src=x>',workspace_bytes:1024,reason:'Open PR; files retained'}]};
 assert.match(storage.summary(data),/2.0 KiB/);assert.match(storage.summary(data),/0 B/);
 assert.match(storage.rows(data),/&lt;img src=x&gt;/);assert.doesNotMatch(storage.rows(data),/<img/);
 assert.match(storage.rows(data),/Open PR; files retained/);
});
test('Storage lives in installation settings and is loaded by the app',()=>{
 assert.match(fs.readFileSync('dist/settings.js','utf8'),/storage:'This installation'/);
 assert.match(fs.readFileSync('dist/index.html','utf8'),/src="\.\/storage.js"/);
 assert.match(fs.readFileSync('dist/app.js','utf8'),/storage:host=>CheapOSStorage.open/);
});
