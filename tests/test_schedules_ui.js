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
