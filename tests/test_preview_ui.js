const test=require('node:test'),assert=require('node:assert/strict');
const preview=require('../dist/preview.js');
test('preview configuration exposes commands, isolation, environment and operator checks',()=>{
 const html=preview.fields({command:'<script>',checklist:'Click hide → hidden'});
 for(const name of ['command','setup','directory','url','environment','checklist'])assert.ok(html.includes('name="'+name+'"'));
 assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
 assert.match(html,/not a security sandbox/);assert.match(html,/expected result/);
});

test('review preview controls send exact revision and preserve operator checklist',async()=>{
 const nodes=new Map(),q=s=>{if(!nodes.has(s))nodes.set(s,{innerHTML:'',textContent:'',insertAdjacentHTML(_,html){this.innerHTML+=html;}});return nodes.get(s);};
 const section={querySelector:q,isConnected:true,open:false};
 const saved={document:global.document,setInterval:global.setInterval,FormData:global.FormData};
 global.document={createElement:()=>section};global.setInterval=()=>0;
 global.FormData=class{*[Symbol.iterator](){yield ['command','python app.py'];}};
 const calls=[];const config={command:'python app.py',checklist:'Click Send → chat appears'};
 const api=async(path,body)=>{calls.push({path,body});return {status:path.endsWith('start')?'running':'stopped',tip:'abc',branch:'feature/test',root:'/tmp/test',url:'http://127.0.0.1:5174',logs:'Ready',config};};
 try{
  preview.mount({append(){}},{id:'task',source:'/repo',branch_run:{plan:{items:[{acceptance_criteria:['Chat still sends']}]}}},api,'abc');
  await new Promise(resolve=>setImmediate(resolve));
  assert.match(q('[data-checklist]').innerHTML,/not automatically verified/);
  assert.match(q('[data-checklist]').innerHTML,/Chat still sends/);
  await q('[data-launch]').onclick();
  assert.equal(calls.at(-1).body.expected_tip,'abc');
  assert.equal(calls.at(-1).body.config.command,'python app.py');
  assert.equal(q('[data-open]').hidden,false);
  await q('[data-stop]').onclick();assert.match(calls.at(-1).path,/preview-stop$/);
 }finally{Object.assign(global,saved);}
});


test('agent browser permission is separate from manual preview and project defaults',async()=>{
 const nodes=new Map(),q=s=>{if(!nodes.has(s))nodes.set(s,{innerHTML:'',textContent:'',insertAdjacentHTML(){}});return nodes.get(s);};
 const section={querySelector:q,isConnected:true,open:false};
 const saved={document:global.document,setInterval:global.setInterval,FormData:global.FormData};
 global.document={createElement:()=>section};global.setInterval=()=>0;
 global.FormData=class{*[Symbol.iterator](){yield ['command','python app.py'];yield ['url','http://127.0.0.1:5174'];}};
 const calls=[];const api=async(path,body)=>{calls.push({path,body});return {status:'stopped',config:{}};};
 try{
  preview.mount({append(){}},{id:'task',source:'/repo',workspace:'/task-copy'},api,'abc');
  await new Promise(resolve=>setImmediate(resolve));
  assert.match(section.innerHTML,/disposable test services/);
  await q('[data-browser-allow]').onclick();
  assert.deepEqual(calls.at(-1),{path:'/tasks/task/browser-permission',body:{enabled:true,directory:'/task-copy',config:{command:'python app.py',url:'http://127.0.0.1:5174'}}});
  await q('[data-browser-revoke]').onclick();
  assert.deepEqual(calls.at(-1),{path:'/tasks/task/browser-permission',body:{enabled:false}});
  assert.equal(calls.filter(c=>c.path.endsWith('preview-start')).length,0);
 }finally{Object.assign(global,saved);}
});
