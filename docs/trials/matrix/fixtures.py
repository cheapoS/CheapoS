"""Independent baseline projects and acceptance tests for explicit live trials."""
MEDIUM_TEST = '''import unittest
from ledger import parse_expenses
from report import summarize
from decimal import Decimal
class Acceptance(unittest.TestCase):
 def test_csv_quotes_and_exact_money(self):
  rows=parse_expenses('category,amount\\n"food, groceries",0.10\\n"food, groceries",0.20\\nTravel,2.50\\n')
  self.assertEqual(rows,[('food, groceries',Decimal('0.10')),('food, groceries',Decimal('0.20')),('Travel',Decimal('2.50'))])
  self.assertEqual(summarize(rows),'Travel: 2.50\\nfood, groceries: 0.30\\nTOTAL: 2.80\\n')
 def test_empty(self): self.assertEqual(summarize(parse_expenses('category,amount\\n')),'TOTAL: 0.00\\n')
 def test_trim(self): self.assertEqual(parse_expenses('category,amount\\n  food  , 1.20 \\n'),[('food',Decimal('1.20'))])
 def test_bad_header(self):
  with self.assertRaises(ValueError):parse_expenses('name,cost\\nfood,1\\n')
 def test_invalid_rows(self):
  for row in ('food,-1','food,NaN','food,Infinity','food,x',',1','food,1,extra','food,1.001'):
   with self.subTest(row=row),self.assertRaises(ValueError):parse_expenses('category,amount\\n'+row+'\\n')
 def test_determinism_and_no_mutation(self):
  rows=[('b',Decimal('1')),('a',Decimal('2'))];before=list(rows)
  self.assertEqual(summarize(rows),'a: 2.00\\nb: 1.00\\nTOTAL: 3.00\\n');self.assertEqual(rows,before)
'''
HARD_TEST='''import unittest,json,tempfile,threading,urllib.request,urllib.error,subprocess
from pathlib import Path
class APITests(unittest.TestCase):
 def setUp(self):
  from app import create_server
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.db=str(Path(self.temp.name)/'tasks.db')
  self.factory=create_server;self.start()
 def start(self):
  self.server=self.factory(self.db,port=0);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.stop)
  self.url='http://127.0.0.1:'+str(self.server.server_address[1])
 def stop(self):
  if self.server:self.server.shutdown();self.server.server_close();self.thread.join();self.server=None
 def req(self,path,body=None):
  data=None if body is None else json.dumps(body).encode();req=urllib.request.Request(self.url+path,data=data,headers={'Content-Type':'application/json'})
  try:r=urllib.request.urlopen(req,timeout=3)
  except urllib.error.HTTPError as e:r=e
  with r:return r.status,json.loads(r.read())
 def test_create_list_and_restart(self):
  self.assertEqual(self.req('/tasks'),(200,[]));status,item=self.req('/tasks',{'title':' café 東京 '});self.assertEqual(status,201);self.assertEqual(item,{'id':1,'title':'café 東京','done':False})
  self.assertEqual(self.req('/tasks'),(200,[item]));self.stop();self.start();self.assertEqual(self.req('/tasks'),(200,[item]))
 def test_complete_and_missing(self):
  self.req('/tasks',{'title':'A'});self.assertEqual(self.req('/tasks/1/complete',{}),(200,{'id':1,'title':'A','done':True}));self.assertEqual(self.req('/tasks/99/complete',{})[0],404)
 def test_validation_has_no_writes(self):
  for title in ('', '  ', 2, None, 'x'*201):self.assertEqual(self.req('/tasks',{'title':title})[0],400)
  self.assertEqual(self.req('/tasks'),(200,[]));self.assertEqual(self.req('/missing')[0],404)
class UITests(unittest.TestCase):
 def test_real_javascript_client(self):
  script="""const assert=require('node:assert/strict');const {createClient}=require('./ui.js');let calls=[];
(async()=>{const client=createClient(async(url,options={})=>{calls.push([url,options]);return {ok:true,json:async()=>url==='/tasks'&&!options.method?[]:{id:1,title:'A',done:false}}});
assert.deepEqual(await client.list(),[]);assert.equal((await client.add('A')).id,1);assert.equal(calls[1][0],'/tasks');assert.equal(calls[1][1].method,'POST');assert.deepEqual(JSON.parse(calls[1][1].body),{title:'A'});await client.complete(1);assert.equal(calls[2][0],'/tasks/1/complete');assert.equal(calls[2][1].method,'POST');const bad=createClient(async()=>({ok:false,status:400,json:async()=>({error:'Invalid title'})}));await assert.rejects(()=>bad.add(''),/Invalid title/);})().catch(e=>{console.error(e);process.exitCode=1});"""
  result=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=5);self.assertEqual(result.returncode,0,result.stderr)
 def test_page_uses_text_nodes(self):
  html=Path('index.html').read_text();self.assertIn('ui.js',html);self.assertIn('form',html.lower());self.assertIn('aria-live',html)
  source=Path('ui.js').read_text();self.assertNotIn('.innerHTML',source);self.assertIn('textContent',source)
'''
VERY_HARD_TEST='''import unittest,tempfile,sqlite3,json,subprocess,sys
from pathlib import Path
class Base(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'tasks.db'
 def store(self):
  from store import Store
  return Store(self.path)
class StoreTests(Base):
 def test_fresh_and_durable(self):
  s=self.store();self.assertEqual(s.list(),[]);self.assertEqual(s.add(' A '),{'id':1,'title':'A','done':False});s.complete(1);self.assertEqual(self.store().list(),[{'id':1,'title':'A','done':True}])
 def test_legacy_migration(self):
  c=sqlite3.connect(self.path);c.execute('CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT NOT NULL)');c.execute("INSERT INTO tasks VALUES (7,'Legacy')");c.execute('PRAGMA user_version=1');c.commit();c.close()
  self.assertEqual(self.store().list(),[{'id':7,'title':'Legacy','done':False}]);self.assertEqual(self.store().list()[0]['id'],7)
  c=sqlite3.connect(self.path);self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],2);c.close()
 def test_reject_future_schema_unchanged(self):
  c=sqlite3.connect(self.path);c.execute('PRAGMA user_version=99');c.commit();c.close();before=self.path.read_bytes()
  with self.assertRaises(ValueError):self.store()
  self.assertEqual(self.path.read_bytes(),before)
 def test_invalid_and_missing(self):
  s=self.store()
  for title in ('','  ',None):
   with self.assertRaises(ValueError):s.add(title)
  with self.assertRaises(KeyError):s.complete(99)
  self.assertEqual(s.list(),[])
class ExchangeTests(Base):
 def test_import_quoted_unicode_and_export(self):
  s=self.store();self.assertEqual(s.import_csv('title,done\\n"café, 東京",false\\nB,true\\n'),2)
  expected=[{'id':1,'title':'café, 東京','done':False},{'id':2,'title':'B','done':True}]
  self.assertEqual(s.list(),expected);a=s.export_json();self.assertEqual(json.loads(a),expected);self.assertEqual(s.export_json(),a);self.assertEqual(s.list(),expected)
 def test_import_atomic_on_invalid_later_row(self):
  s=self.store();s.add('Keep')
  for data in ('title,done\\nValid,false\\nBad,maybe\\n','title,done\\nValid,false\\n,true\\n','wrong,done\\nX,false\\n'):
   with self.assertRaises(ValueError):s.import_csv(data)
   self.assertEqual(s.list(),[{'id':1,'title':'Keep','done':False}])
class CLITests(Base):
 def cli(self,*args):return subprocess.run([sys.executable,'cli.py','--db',str(self.path),*args],capture_output=True,text=True,timeout=5)
 def test_whole_cli_and_errors(self):
  self.assertEqual(self.cli('add','Task A').returncode,0);self.assertEqual(json.loads(self.cli('list').stdout),[{'id':1,'title':'Task A','done':False}]);self.assertEqual(self.cli('complete','1').returncode,0)
  csv=Path(self.tmp.name)/'input.csv';csv.write_text('title,done\\nTask B,false\\n');self.assertEqual(self.cli('import',str(csv)).returncode,0)
  out=self.cli('export');self.assertEqual(out.returncode,0);self.assertEqual(json.loads(out.stdout),[{'id':1,'title':'Task A','done':True},{'id':2,'title':'Task B','done':False}]);bad=self.cli('complete','999');self.assertNotEqual(bad.returncode,0);self.assertNotIn('Traceback',bad.stderr)
'''

def fixture(level):
 if level=='medium':
  return {'README.md':'# Expense summary\n','ledger.py':"def parse_expenses(text):\n    return [(row.split(',')[0], float(row.split(',')[1])) for row in text.splitlines()[1:]]\n",'report.py':"def summarize(rows):\n    return str(sum(amount for _, amount in rows))\n",'test_acceptance.py':MEDIUM_TEST},[
   ('expenses','Repair CSV money handling and reporting','Fix ledger.py parse_expenses(text) to use real CSV parsing and Decimal. Exact header category,amount. Trim category/amount; category must be nonempty; reject negative, nonfinite, invalid, or more-than-two-decimal-place amounts and wrong row widths with ValueError. Return ordered (category,Decimal) tuples. Fix report.py summarize(rows) to aggregate by category, sort categories lexicographically, emit category: amount lines with two decimals, followed by TOTAL: amount and a final newline. Do not mutate input. Update README with usage.', ['CSV quoted fields, Unicode, exact money and invalid inputs are handled.','Sorted deterministic report and documentation satisfy acceptance checks.'])]
 if level=='hard':
  return {'README.md':'# Persistent task board\n','test_acceptance.py':HARD_TEST},[
   ('api','Build durable task API','Create app.py with create_server(db_path, port=0) returning an HTTPServer bound to 127.0.0.1, not started. SQLite persistent tasks table. GET /tasks returns ordered [{id,title,done}] JSON. POST /tasks {title} trims a 1..200 character string and creates item with status201. POST /tasks/<id>/complete with {} returns updated item200, missing404. Invalid input400 and unknown paths404 return JSON error objects without writes. Handle malformed JSON cleanly. Use only standard library. Document how to start server.', ['HTTP API stores tasks durably and validates input without unintended writes.','Completion and missing routes use correct JSON status codes.'],'APITests'),
   ('ui','Build usable task board and client','Create ui.js as browser-compatible script and CommonJS module exporting createClient(fetchFn). Client methods list(),add(title),complete(id) call relative API paths with JSON POST bodies; non-OK responses reject Error using JSON error message. Create index.html with form to add tasks, list, completion controls and aria-live error/status feedback. Wire UI to client; user labels use textContent, never innerHTML. Serve index.html and ui.js read-only from app.py so this is a usable page. Update README.', ['Client methods and errors satisfy real Node execution tests.','Browser form lists/adds/completes tasks and renders user text safely.','Existing API acceptance checks still pass.'],'UITests')]
 if level=='very-hard':
  return {'README.md':'# Durable task CLI\n','test_acceptance.py':VERY_HARD_TEST},[
   ('store','Implement schema migration and persistent store','Create store.py with Store(path). New SQLite db user_version=2 and tasks(id INTEGER PRIMARY KEY,title TEXT NOT NULL,done INTEGER NOT NULL DEFAULT 0). Migrate existing user_version1 table tasks(id,title) to version2 preserving IDs and titles with done=false. Reopening is idempotent. Reject user_version>2 with ValueError and no database mutations. add(title) trims nonempty str or raises ValueError, returns {id,title,done}; list() returns ordered dicts with boolean done; complete(id) persists true or raises KeyError. Close database handles properly.', ['Fresh and legacy databases preserve data and version correctly.','Future schema refused unchanged; validation and missing IDs behave correctly.'],'StoreTests'),
   ('exchange','Implement atomic CSV import and deterministic JSON export','Add Store.import_csv(text): exact header title,done; quoted Unicode CSV; done accepts exactly true/false; trim nonempty titles; reject malformed header/rows/invalid done with ValueError. Validate all rows and import transactionally: invalid later row leaves database unchanged. Return imported count. Store.export_json() returns deterministic JSON list matching list(), without mutations.', ['Import handles quoted Unicode fields and returns count.','Invalid later rows roll back all new writes.','Export is deterministic and does not change records.'],'ExchangeTests'),
   ('cli','Add and document CLI','Create cli.py --db PATH with subcommands add TITLE, list, complete ID, import FILE, export. list/export print JSON; successful commands exit0; invalid user input or missing IDs exit nonzero with concise stderr, never traceback. Reuse Store. Update README with runnable add/list/complete/import/export examples and migration behavior. Preserve earlier functionality.', ['CLI works end-to-end through real subprocesses and preserves state.','Errors are concise/nonzero and documentation describes all commands.'],'CLITests')]
 raise ValueError(level)
