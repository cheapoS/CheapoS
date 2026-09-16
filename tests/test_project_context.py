import hashlib
import json
from pathlib import Path

from cheapos import project_context
from cheapos.providers import BudgetError
from cheapos.routing import coordinator_messages
from cheapos.workspace import Workspace
try:
    from test_engine import LocalCase
except ImportError:
    from tests.test_engine import LocalCase


class ProjectContextTests(LocalCase):
    def task(self):
        task=self.fixture();root=Path(task['workspace'])
        (root/'README.md').write_text('Small Python clamp library. Use the configured unittest command.\n')
        (root/'pyproject.toml').write_text('[project]\nname="fixture"\n')
        (root/'.env').write_text('PRIVATE_CREDENTIAL=never-include')
        (root/'node_modules').mkdir();(root/'node_modules/README.md').write_text('dependency-private')
        return task

    def test_brief_sources_cache_and_manifest_invalidation(self):
        task=self.task();first=project_context.brief(task)
        self.assertEqual(first,project_context.brief(task))
        self.assertEqual(first['test_command']['argv'],task['check_command'])
        self.assertEqual(first['languages']['Python'],'math_utils.py')
        self.assertNotIn('never-include',json.dumps(first));self.assertNotIn('dependency-private',json.dumps(first))
        (Path(task['workspace'])/'pyproject.toml').write_text('[project]\nname="changed"\n')
        second=project_context.brief(task);self.assertNotEqual(first['identity'],second['identity'])
        self.assertIn('changed',json.dumps(second))
        self.assertLessEqual(len(json.dumps(second).encode()),24000)

    def test_continuation_preserves_all_requirements_and_current_numbered_evidence(self):
        task=self.task();task['requests']=['Keep compatibility','Add bounds tests','Keep docs','Use ValueError','Also reject NaN','Correction: allow NaN']
        task['changes']=[{'path':'math_utils.py'}]
        root=Path(task['workspace']);(root/'math_utils.py').write_text('def current():\n    return 7\n')
        task['events'].append({'kind':'assistant','title':'Worker','detail':'All checks passed'})
        task['events'].append({'kind':'steer','title':'User Guidance','detail':'Preserve the public API'})
        task['compact_edits']=True
        summary=json.loads(self.engine.initial_messages(task)[1]['content']);record=summary['continuation_record']
        self.assertEqual(record['active_requirements'],task['requests']);self.assertEqual(record['current_request'],'Correction: allow NaN')
        self.assertEqual(record['steering'][0]['text'],'Preserve the public API')
        self.assertEqual(record['check'],{});self.assertIn('1: def current()',record['files'][0]['content'])
        self.assertEqual(record['files'][0]['hash'],hashlib.sha256((root/'math_utils.py').read_bytes()).hexdigest())
        self.engine.store.save(task);saved=self.engine.store.get(task['id']);self.assertEqual(saved['continuation_record'],record)
        self.assertLessEqual(len(json.dumps(record).encode()),112000)

    def test_requirements_are_never_silently_dropped_to_fit(self):
        task=self.task();task['requests']=['A'*8000]*7
        with self.assertRaises(BudgetError):project_context.continuation(task)
        self.assertEqual(len(task['requests']),7)

    def test_repeated_question_has_test_command_without_an_extra_read(self):
        task=self.task();first=json.loads(self.engine.initial_messages(task)[1]['content'])
        task['requests'].append('Use the same test command and explain the bounds.')
        task['action_pending']=True
        followup=json.loads(self.engine.initial_messages(task)[1]['content'])
        self.assertEqual(first['project_brief']['test_command'],followup['project_brief']['test_command'])
        self.assertEqual(first['project_brief']['identity'],followup['project_brief']['identity'])
        # Deterministic retrieval fixture: legacy action summaries required a read
        # to recover test instructions; this summary supplies the known command.
        legacy={k:v for k,v in followup.items() if k not in {'project_brief','continuation_record'}}
        needs_read=lambda summary:int(not summary.get('project_brief',{}).get('test_command',{}).get('argv'))
        self.assertEqual((needs_read(legacy),needs_read(followup)),(1,0))
