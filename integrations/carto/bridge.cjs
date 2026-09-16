'use strict';
// Pinned Carto adapter. Only operates on cheapoS's disposable source mirror.
const fs=require('node:fs');
const {SQLiteStore}=require('carto-md/src/store/sqlite-store');
const {syncFiles}=require('carto-md/src/store/sync');
const {StoreAdapter}=require('carto-md');
const request=JSON.parse(fs.readFileSync(0,'utf8'));
const store=new SQLiteStore(request.root);
try {
 store.open();
 if(request.action==='index'){
  store.removeStaleFiles(request.files);
  const result=syncFiles(request.root,request.files,{store});
  store.resolveUnresolvedImports();store.computeReverseDeps();
  process.stdout.write(JSON.stringify({indexed:store.getFileCount(),errors:store.getExtractionErrorCount(),...result}));
 } else {
  const adapter=new StoreAdapter();adapter._store=store;adapter._projectRoot=request.root;
  const cap=(items,n=20)=>({items:items.slice(0,n),total:items.length,truncated:items.length>n});
  let result;
  if(request.path){
   const ctx=adapter.getContextForFile(request.path);
   if(ctx?.blastRadius)ctx.blastRadius.dependentFiles=cap(ctx.blastRadius.dependentFiles);
   if(ctx){delete ctx.domainContext;delete ctx.domain;delete ctx.functions;delete ctx.envVars;delete ctx.meta;ctx.symbols=cap(store.db.prepare('SELECT s.name,s.kind,s.line FROM symbols s JOIN files f ON s.file_id=f.id WHERE f.path=?').all(request.path));ctx.neighbors={nodes:cap(ctx.neighbors?.nodes||[]),edges:cap(ctx.neighbors?.edges||[])};ctx.crossDomainDeps=cap(ctx.crossDomainDeps||[]);}
   result={file:request.path,context:ctx};
  } else if(request.query){
   const terms=request.query.toLowerCase().split(/[^a-z0-9_]+/).filter(Boolean).slice(0,12);
   const rows=store.db.prepare('SELECT f.path, s.name FROM files f LEFT JOIN symbols s ON s.file_id=f.id').all();
   const matches=new Map();
   for(const row of rows){const text=(row.path+' '+(row.name||'')).toLowerCase();const score=terms.filter(t=>text.includes(t)).length;if(score)matches.set(row.path,Math.max(matches.get(row.path)||0,score));}
   result={matches:cap([...matches].sort((a,b)=>b[1]-a[1]).map(([path,score])=>({path,score})))};
  } else result={structure:adapter.getStructure(),routes:cap(adapter.getRoutes()),high_impact:adapter.getHighImpactFiles(12)};
  process.stdout.write(JSON.stringify(result));
 }
} catch(error){process.stderr.write(String(error.message));process.exitCode=1;}
finally{store.close();}
