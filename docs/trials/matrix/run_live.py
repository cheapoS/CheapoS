"""Operator driver for explicit live trials. Never imported by automated tests."""
import argparse, hashlib, json, shutil, sys, time
from pathlib import Path
REPO=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(REPO))
from cheapos.engine import Engine
from cheapos.workspace import git
from cheapos import branch_completion

ROOT=Path('/tmp/cheapos-matrix-20260913')
CONFIG=Path.home()/'Library/Application Support/cheapoS'
EASY_TEST='''import unittest
from labels import normalize_label
class Labels(unittest.TestCase):
 def test_spaces(self): self.assertEqual(normalize_label('  hello\\t world\\n'), 'hello world')
 def test_unicode(self): self.assertEqual(normalize_label('  café  東京  '), 'café 東京')
 def test_empty(self): self.assertEqual(normalize_label(' \\t\\n'), '')
 def test_type(self):
  for value in (None, 1, [], b'hello'):
   with self.subTest(value=value), self.assertRaises(TypeError): normalize_label(value)
'''

def fixture(level):
 if level=='easy':
  files={'README.md':'# Label formatter\n\nStandard-library Python utility.\n','test_acceptance.py':EASY_TEST}
  instructions='Create labels.py with normalize_label(text). Require str (TypeError otherwise), trim surrounding whitespace and collapse internal whitespace sequences to one ASCII space while preserving Unicode. Amend README.md with a runnable usage example. Preserve the supplied tests. Standard library only.'
  items=[('labels','Implement and document normalization',instructions,['normalize_label meets the complete whitespace, Unicode and type contract.','README.md includes runnable examples.','Supplied acceptance tests are unchanged and pass.'])]
 else:
  import importlib.util
  spec=importlib.util.spec_from_file_location('trial_fixtures',str(Path(__file__).with_name('fixtures.py')));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  return module.fixture(level)
 return files,items

def main():
 ap=argparse.ArgumentParser();ap.add_argument('level',choices=['easy','medium','hard','very-hard']);ap.add_argument('attempt',type=int);ap.add_argument('--live',action='store_true',help='Explicitly authorize live provider requests');ap.add_argument('--root',type=Path,default=ROOT);ap.add_argument('--config-dir',type=Path,default=CONFIG);args=ap.parse_args()
 if not args.live:ap.error('Live requests require --live; do not run this driver as an automated regression test')
 root=args.root/(args.level+'-'+str(args.attempt));root.mkdir(parents=True,exist_ok=False)
 source=root/'project';source.mkdir();state=root/'state';state.mkdir()
 for name in ('config.json','preferences.json','gateway.json'):
  shutil.copyfile(args.config_dir/name,state/name);(state/name).chmod(0o600)
 files,items=fixture(args.level)
 for name,content in files.items():
  p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)
 git(source,'init','-qb','main');git(source,'config','user.name','cheapoS Trial');git(source,'config','user.email','trial@example.invalid');git(source,'add','.');git(source,'commit','-qm','Independent trial specification and acceptance baseline')
 baseline=git(source,'rev-parse','HEAD').strip();command=sys.executable+' -B -m unittest -v test_acceptance'
 plan={'measurement':True,'items':[],'limits':{'dollars':0},'final_checks':[command]}
 for n,item in enumerate(items):
  identity,title,instructions,criteria=item[:4]
  item_command=command+('.'+item[4] if len(item)>4 else '')
  plan['items'].append({'id':identity,'title':title,'instructions':instructions+' Run '+item_command+' and submit checkpoint when complete. Do not edit test_acceptance.py.','acceptance_criteria':criteria,'dependencies':[] if n==0 else [items[n-1][0]],'required_checks':[item_command]})
 prompt='Complete the proposed '+args.level+' qualification. Preserve independent tests. Only the requested files and standard-library dependencies. No merge or push.'
 (root/'plan.json').write_text(json.dumps(plan,indent=2))
 app_commit=git(REPO,'rev-parse','HEAD').strip()
 app_hash=lambda:hashlib.sha256(b''.join(p.read_bytes() for p in sorted((REPO/'cheapos').glob('*.py')))).hexdigest()
 app_before=app_hash()
 engine=Engine(state);started=time.monotonic();task_id=None
 try:
  proposal=engine.branch.prepare({'repository':str(source),'prompt':prompt,'base_ref':'refs/heads/main','target_ref':'refs/heads/main','feature_ref':'refs/heads/feature/trial','plan':plan})
  task_id=proposal['task_id'];(root/'task-id').write_text(task_id)
  engine.branch.authorize(task_id,{'proposal_id':proposal['proposal_id'],'approved':True})
  rt=engine.runtimes[task_id];last=None
  while rt.thread.is_alive():
   rt.thread.join(5);d=engine.store.get(task_id)
   snapshot=(d['status'],d['worker_turns'],len(d['checks']),len(d['request_metrics']))
   if snapshot!=last:print(args.level,args.attempt,snapshot,[(e['kind'],e['title']) for e in d['events'][-2:]],flush=True);last=snapshot
  d=engine.store.get(task_id);run=d['branch_run']
  independent={'app_code_unchanged':app_before==app_hash(),'source_main_unchanged':git(source,'rev-parse','main').strip()==baseline,'source_clean':git(source,'status','--porcelain')=='','tests_unchanged':(Path(d['workspace'])/'test_acceptance.py').read_bytes()==(source/'test_acceptance.py').read_bytes()}
  if run['status']=='ready_for_merge':
   preview=branch_completion.preview(engine.branch,task_id);independent['merge_available']=preview['merge_available']
   independent['commits_verified']=all(i['commit_receipt']['stage']=='completed' and i['commit_receipt']['run_id']==task_id and i['commit_receipt']['item_id']==i['id'] and git(source,'cat-file','-t',i['commit_receipt']['new_tip']).strip()=='commit' for i in run['items'])
  summary={'app_commit':app_commit,'app_code_hash':app_before,'level':args.level,'attempt':args.attempt,'run_id':task_id,'status':run['status'],'error':d.get('error'),'error_code':d.get('error_code'),'measurement':run['plan'].get('measurement'),'operator_prepared_plan':True,'interventions_after_start':0,'models':{r:c.get('model') if c else None for r,c in d['providers'].items()},'models_used':{role:sorted({q['model'] for q in d['request_metrics'] if q.get('role')==role}) for role in ('worker','reviewer')},'handoffs':len([e for e in d['events'] if e['kind']=='handoff' and e['title'].startswith('Switching')]),'review_revisions':len([e for e in d['events'] if e['kind']=='review' and isinstance(e.get('detail'),dict) and e['detail'].get('decision')=='REQUEST_CHANGES']),'request_count':len(d['request_metrics']),'usage':d['usage'],'consumption':run['consumption'],'run_metrics':d.get('run_metrics',[]),'checks':[{'passed':c.get('passed'),'duration':c.get('duration'),'allowed_seconds':c.get('allowed_seconds'),'output':c.get('output')} for c in d['checks']],'commits':[i.get('commit_receipt',{}).get('new_tip') for i in run['items'] if i.get('commit_receipt')],'independent':independent,'driver_seconds':time.monotonic()-started}
  summary['autonomous_execution_success']=run['status']=='ready_for_merge' and all(independent.values())
  (root/'result.json').write_text(json.dumps(summary,indent=2));print('RESULT',json.dumps({k:summary[k] for k in ('level','attempt','status','error','request_count','commits','independent')}),flush=True)
 finally: engine.shutdown()
if __name__=='__main__':main()
