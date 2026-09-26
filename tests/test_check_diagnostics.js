const {test}=require('node:test');
const assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../dist/app.js'),'utf8');
const ctx={esc:value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;')};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('function checkDiagnosticsMarkup('),source.indexOf('function rawCheckLink(')),ctx);
test('diagnostic details escape reporter paths, names, messages and working directory',()=>{
  const html=ctx.checkDiagnosticsMarkup({directory:'<cwd>',diagnostics:{items:[{path:'<img src=x>',name:'<rule>',severity:'error',message:'<script>bad</script>',line:2,column:3,raw_evidence:{offset:10,end_offset:30}}]}});
  assert.doesNotMatch(html,/<script>|<img|<cwd>|<rule>/);
  assert.match(html,/&lt;script&gt;bad/);
  assert.match(html,/Original bytes 10–30/);
  assert.match(html,/:2:3/);
});
test('legacy, unparsed and limited diagnostics never imply command success',()=>{
  assert.equal(ctx.checkDiagnosticsMarkup({}), '');
  assert.match(ctx.checkDiagnosticsMarkup({diagnostics:{items:[]}}),/No supported diagnostics recognized/);
  assert.match(ctx.checkDiagnosticsMarkup({diagnostics:{limited:true,items:[]}}),/Partial diagnostic index/);
});
test('both chat command details and Tests view expose diagnostics beside original output',()=>{
  assert.equal(source.split('${checkDiagnosticsMarkup(check)}${rawCheckLink(check)}').length-1,2);
});
