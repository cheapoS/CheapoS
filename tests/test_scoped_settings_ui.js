'use strict';
const assert=require('node:assert/strict');
const {createSession,changes,sourceLabel}=require('../dist/settings.js');
(async()=>{
 assert.equal(sourceLabel('task',{scope:'saved',provenance:'unknown'}),'Saved for this chat · source unknown');
 assert.equal(sourceLabel('draft',{scope:'project'}),'From project overrides');
 assert.equal(sourceLabel('project',{scope:'project'}),'Project override');
 const calls=[];let fail=false;
 const api=async(path,body)=>{calls.push({path,body});if(!body)return {revision:3,parent_revision:7,values:{execution:{mode:'remote'},limits:{dollars:0,uncapped_work:false},roles:{reviewer:{strategy:'only',model:'old',connection_id:'gateway'}}}};if(fail)throw Error('offline');return {revision:4,saved:true};};
 const scope={kind:'task',id:'chat-a'},session=createSession(api,scope);await session.load();scope.id='chat-b';session.edit('limits.uncapped_work',true);fail=true;await assert.rejects(session.save(),/offline/);assert.equal(session.dirty,true);const first=calls.at(-1).body.operation_id;fail=false;await session.save();assert.equal(calls.at(-1).path,'/tasks/chat-a/settings');assert.equal(calls.at(-1).body.operation_id,first);assert.equal(session.dirty,false);assert.equal(calls.at(-1).body.expected_revision,3);
 const project=createSession(api,{kind:'project',project:'/repo'});await project.load();project.edit('roles.reviewer.strategy','automatic');await project.save();assert.deepEqual(calls.at(-1).body.patch,{'roles.reviewer':{strategy:'automatic'}});assert.equal(calls.at(-1).body.expected_parent_revision,7);
 project.inherit('roles.reviewer.model');await project.save();assert.deepEqual(calls.at(-1).body.remove,['roles.reviewer']);assert.deepEqual(changes({limits:{dollars:2}},{limits:{dollars:0}}),{'limits.dollars':0});
 console.log('Scoped settings UI contracts passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
