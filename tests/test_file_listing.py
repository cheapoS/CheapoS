"""Folder arguments work through the same constrained tools used by both models."""
from unittest.mock import Mock

from cheapos.engine import READ_TOOLS
from cheapos.workspace import Workspace
from test_engine import LocalCase, call


class FileListingTests(LocalCase):
    def test_root_and_nested_directory_paths_return_project_relative_names(self):
        workspace = Workspace(self.fixture()['workspace'])
        workspace.write_file('scripts/report.py', 'report\n')
        workspace.write_file('scripts/nested/helper.py', 'helper\n')
        workspace.write_file('scripts_extra/other.py', 'other\n')
        (workspace.root / 'scripts/empty').mkdir()
        (workspace.root / 'scripts/.env').write_text('secret')
        (workspace.root / 'scripts/link.py').symlink_to(workspace.root / 'math_utils.py')
        expected = ['scripts/nested/helper.py', 'scripts/report.py']
        self.assertEqual(workspace.list_files('scripts'), expected)
        self.assertEqual(workspace.list_files('./scripts/'), expected)
        self.assertEqual(workspace.list_files('scripts/nested'), expected[:1])
        self.assertEqual(workspace.list_files('scripts/empty'), [])
        for root in ('.', './', '././'):
            self.assertEqual(workspace.list_files(root), workspace.list_files())
        self.assertIn('scripts_extra/other.py', workspace.list_files())

    def test_directory_arguments_cannot_escape_or_list_protected_paths(self):
        workspace = Workspace(self.fixture()['workspace'])
        (workspace.root / 'external').symlink_to(self.root, target_is_directory=True)
        for path in ('..', '../outside', str(self.root), '.git', '.env', 'external', 'external/nested', 'nested/../..', '', None, 3, 'bad\x00path', 'bad\\path'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                workspace.list_files(path)
        for path in ('missing', 'math_utils.py'):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'Directory not found'):
                workspace.list_files(path)

    def test_worker_and_reviewer_can_list_folders_and_finish_the_loop(self):
        task = self.fixture(paid=True)
        task['conversational'] = True
        self.engine.store.save(task)
        replies = [
            call('list_files', {'path':'.'}),
            call('replace_text', {'path':'math_utils.py','old_text':'return min(value, upper)','new_text':'return max(lower, min(value, upper))'}),
            call('run_checks'),
            call('checkpoint', {'summary':'Fixed both bounds','uncertainties':''}),
            call('list_files', {'path':'./'}),
            call('review_decision', {'decision':'APPROVE','feedback':'Both bounds are correct.'}),
        ]
        provider = Mock()
        provider.complete.side_effect = [(reply, {'prompt_tokens':10,'completion_tokens':5,'cost':0}) for reply in replies]
        self.engine.provider_factory = lambda *args: provider
        self.engine.start(task['id'])
        result = self.finish(task)
        self.assertEqual(result['status'], 'approved', result['error'])
        self.assertEqual(provider.complete.call_count, len(replies))
        self.assertFalse([e for e in result['events'] if e['kind']=='tool_error'])
        listings = [e['detail'] for e in result['events'] if e['kind']=='tool' and e['title']=='list files']
        self.assertEqual([item['role'] for item in listings], ['worker', 'reviewer'])
        self.assertTrue(all('math_utils.py' in item['result'] for item in listings))
        schema = next(t['function']['parameters'] for t in READ_TOOLS if t['function']['name']=='list_files')
        self.assertEqual(schema['properties']['path']['type'], 'string')
        self.assertNotIn('path', schema['required'])
