import hashlib
import json
import os
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
    def _add_rules_file(self, root, content):
        # Ensure .cheapos directory exists
        (root / '.cheapos').mkdir(parents=True, exist_ok=True)
        (root / '.cheapos' / 'rules.md').write_text(content)

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

    def test_rules_file_included(self):
        task = self.task()
        root = Path(task['workspace'])
        self._add_rules_file(root, "Rule content line1\nLine2\n")
        brief = project_context.brief(task)
        src = next((s for s in brief['sources'] if s.get('path') == '.cheapos/rules.md'), None)
        self.assertIsNotNone(src, "Rules file should be included in sources")
        self.assertIn('Rule content', src['excerpt'])
        self.assertFalse(src.get('partial', False))

    def test_rules_file_excerpt_limit(self):
        task = self.task()
        root = Path(task['workspace'])
        long_content = "A" * 2000
        self._add_rules_file(root, long_content)
        brief = project_context.brief(task)
        src = next((s for s in brief['sources'] if s.get('path') == '.cheapos/rules.md'), None)
        self.assertIsNotNone(src, "Rules file should be included when present")
        self.assertTrue(src.get('partial', False), "Long rules file should be marked as partial")
        self.assertEqual(len(src['excerpt']), 1000)

    def test_rules_file_unreadable(self):
        task = self.task()
        root = Path(task['workspace'])
        self._add_rules_file(root, "secret content")
        rules_path = root / '.cheapos' / 'rules.md'
        # remove read permissions
        os.chmod(rules_path, 0)
        try:
            brief = project_context.brief(task)
            self.assertTrue(all(s.get('path') != '.cheapos/rules.md' for s in brief['sources']),
                            "Unreadable rules file should be skipped")
        finally:
            # restore permissions for cleanup
            os.chmod(rules_path, 0o644)

    def test_rules_file_absent(self):
        task = self.task()
        brief = project_context.brief(task)
        self.assertTrue(all(s.get('path') != '.cheapos/rules.md' for s in brief['sources']),
                        "When rules file absent, it should not appear in sources")

    def test_sources_limit(self):
        task = self.task()
        root = Path(task['workspace'])
        # add rules file
        self._add_rules_file(root, "rule content")
        # add all GUIDANCE files to potentially exceed limit
        from cheapos import project_context as pc
        for fname in pc.GUIDANCE:
            (root / fname).write_text(f"content of {fname}\n")
        brief = project_context.brief(task)
        self.assertLessEqual(len(brief['sources']), 12)
        # rules file should be present if readable
        self.assertTrue(any(s.get('path') == '.cheapos/rules.md' for s in brief['sources']))

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
