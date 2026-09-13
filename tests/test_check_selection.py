import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('check_selection', ROOT/'scripts/check.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, path, text=''):
        target = self.root/path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def test_frontend_and_docs_never_select_backend_tests(self):
        self.write('dist/app.js');self.write('tests/test_view.js');self.write('tests/test_backend.py')
        commands, notes, selected = check.plan(self.root, ['dist/styles.css'])
        self.assertEqual(selected, [])
        self.assertIn(['node','--test','tests/test_view.js'], commands)
        self.assertTrue(any('browser' in note for note in notes))
        commands, _, selected = check.plan(self.root, ['docs/notes.md'])
        self.assertEqual(commands, [['git','diff','--check']])
        self.assertEqual(selected, [])
        self.assertEqual(check.plan(self.root, [])[0], [])

    def test_transitive_imports_and_shared_helpers_select_dependents_not_unrelated(self):
        self.write('cheapos/__init__.py')
        self.write('cheapos/leaf.py', 'VALUE=1')
        self.write('cheapos/middle.py', 'from . import leaf')
        self.write('tests/helper.py', 'from cheapos.middle import VALUE')
        self.write('tests/test_affected.py', 'from helper import VALUE')
        self.write('tests/test_unrelated.py', 'import unittest')
        commands, _, selected = check.plan(self.root, ['cheapos/leaf.py'])
        self.assertEqual(selected, ['tests/test_affected.py'])
        self.assertEqual(commands[-1][-2:], ['--pattern','test_affected.py'])
        self.assertEqual(check.plan(self.root, ['tests/helper.py'])[2],selected)

    def test_unknown_deleted_and_broken_import_analysis_fall_back_visibly(self):
        self.write('tests/test_one.py','import unittest')
        self.write('tests/test_two.py','import unittest')
        for changed in ('settings.toml','cheapos/removed.py'):
            _,notes,selected=check.plan(self.root,[changed])
            self.assertEqual(len(selected),2)
            self.assertTrue(notes)
        self.write('cheapos/broken.py','bad syntax !!!')
        self.assertEqual(len(check.plan(self.root,['cheapos/broken.py'])[2]),2)

    def test_changed_test_selects_itself_and_runner_has_explicit_dependency(self):
        self.write('scripts/dev_tests.py')
        self.write('scripts/parallel_tests.py')
        self.write('tests/test_dev_tests.py')
        self.write('tests/test_other.py')
        self.assertEqual(check.plan(self.root,['scripts/parallel_tests.py'])[2],['tests/test_dev_tests.py'])
        self.assertEqual(check.plan(self.root,['tests/test_other.py'])[2],['tests/test_other.py'])
        with self.assertRaises(ValueError):
            check.plan(Path(self.temp.name)/'missing', ['new.py'])

    def test_git_selection_includes_committed_staged_unstaged_and_untracked(self):
        def git(*args):return subprocess.check_output(['git',*args],cwd=self.root,text=True)
        git('init','-q','-b','main');git('config','user.name','Test');git('config','user.email','test@example.invalid')
        self.write('base.py','one');git('add','.');git('commit','-qm','base')
        git('switch','-qc','work')
        self.write('committed.py');git('add','.');git('commit','-qm','change')
        self.write('staged.py');git('add','staged.py')
        self.write('base.py','two');self.write('untracked file.md')
        self.assertEqual(check.git_files(self.root,'main'),['base.py','committed.py','staged.py','untracked file.md'])
        self.assertNotIn('committed.py',check.git_files(self.root))
