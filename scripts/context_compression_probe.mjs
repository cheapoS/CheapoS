// Offline fidelity/shape probe of the installed gateway's pure SmartCrusher code.
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
const [input,output,modules]=process.argv.slice(2);
const {crushMessages}=await import(pathToFileURL(path.join(modules,'smartcrusher.ts')));
const {decodeTabular}=await import(pathToFileURL(path.join(modules,'tabular.ts')));
const bytes=v=>Buffer.byteLength(JSON.stringify(v));
const captures=JSON.parse(fs.readFileSync(input,'utf8'));
const results=[];
for(const stage of ['raw','concise']){
  let before=0,after=0,changed=0,elapsed=0;
  for(const row of captures){
    const messages=row[stage],start=performance.now();
    const result=crushMessages(messages,8);
    elapsed+=performance.now()-start;
    before+=bytes(messages);after+=bytes(result.messages);changed+=Number(result.changed);
    // Ordinary fixture evidence must stay byte-identical. No model output is executed here.
    assert.deepEqual(result.messages,messages);
  }
  results.push({stage,requests:captures.length,before_bytes:before,after_bytes:after,changed_requests:changed,compression_ms:elapsed,fixture_evidence_unchanged:true,retrieval_calls:0});
}
const rows=Array.from({length:40},(_,i)=>({id:i,status:'ready',label:'repeated fixture label',nested:{count:i,nullable:null}}));
const original=JSON.stringify(rows),start=performance.now();
const compact=crushMessages([{role:'tool',content:original}],8).messages[0].content;
assert.deepEqual(decodeTabular(compact),rows);
const key=createHash('sha256').update(original).digest('hex');
const retained=new Map([[key,original]]);
assert.equal(retained.get(key),original);
const protectedMessages=[{role:'system',content:original},{role:'developer',content:original}];
assert.deepEqual(crushMessages(protectedMessages,8).messages,protectedMessages);
const userChanged=crushMessages([{role:'user',content:original}],8).changed;
const sourceChanged=crushMessages([{role:'tool',content:original}],8).changed;
const toolCall={role:'assistant',content:null,tool_calls:[{function:{name:'replace_text',arguments:JSON.stringify({old_text:original,new_text:'[]'})}}]};
assert.deepEqual(crushMessages([toolCall],8).messages,[toolCall]);
const result={candidate:'installed OmniRoute SmartCrusher; minRows=8',results,
 synthetic:{before_bytes:Buffer.byteLength(original),after_bytes:Buffer.byteLength(compact),compression_and_roundtrip_ms:performance.now()-start,roundtrip_equal:true,original_retrievable:true,original_sha256:key,raw_retrieval_bytes:Buffer.byteLength(original),retrieval_operations:1},
 guard_findings:{system_and_developer_preserved:true,tool_arguments_preserved:true,user_request_bytes_changed:userChanged,json_source_bytes_changed:sourceChanged},
 decision:'defer: no fixture benefit; blanket pass changes protected user/source text; no production retrieval integration'};
fs.writeFileSync(output,JSON.stringify(result,null,2)+'\n');
