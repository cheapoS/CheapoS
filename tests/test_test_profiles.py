import sys
import tempfile
import unittest
from pathlib import Path
from cheapos.test_profiles import match_unittest


class TestProfilesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();(self.root/'tests').mkdir()
        (self.root/'tests/test_one.py').write_text('')
        (self.root/'tests/test_two.py').write_text('')
        (self.root/'outside.py').write_text('')
        self.profile={'schema_version':1,'runner':'unittest','project':'fixture','executable':str(Path(sys.executable).resolve()),'roots':['tests']}
        self.base=[sys.executable,'-B','-m','unittest']

    def test_expected_variants_match(self):
        for args in [['discover','-s','tests'],['discover','-s','tests','-p','test_two*.py','-v'],
                     ['-q','discover','-s','tests','-t','.'],['tests.test_one.TestCase.test_it','-v'],['tests.test_two','-f','-b'],
                     ['tests/test_one.py'],['tests/test_projected.py']]:
            with self.subTest(args=args):self.assertTrue(match_unittest(self.base+args,self.root,self.profile)['matched'])

    def test_unrelated_commands_and_invalid_options_do_not_match(self):
        commands=[[sys.executable,'-c','pass'],[sys.executable,'outside.py'],[sys.executable,'-m','pip'],
                  ['/bin/sh','-m','unittest'],[sys.executable,'-I','-m','unittest'],
                  self.base+['discover','-s','..'],self.base+['discover','-s','tests','-t','..'],
                  self.base+['discover','-s'],self.base+['discover','--unknown'],
                  self.base+['discover','-s','tests','-s','tests'],self.base+['outside'],
                  self.base+['outside.py'],self.base+['../outside.py'],self.base+['tests/test_one.py;echo'],
                  self.base+['tests/test_one.py:TestCase.test_it'],self.base+['tests/test_one.py:'],
                  self.base+['--unknown=tests/test_one.py'],self.base+['tests.missing'],
                  self.base+['tests.test_one',';','echo'],self.base+['tests..test_one'],
                  self.base+['tests.test_one','--locals'],self.base+['discover','-s','tests','-p','../*.py'],
                  self.base+['discover'],self.base+['tests.test_one\x00'],None,[False]]
        for argv in commands:
            with self.subTest(argv=argv):self.assertFalse(match_unittest(argv,self.root,self.profile)['matched'])

    def test_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            Path(other,'test_escape.py').write_text('')
            (self.root/'tests/escape').symlink_to(other,target_is_directory=True)
            (self.root/'tests/test_escape.py').symlink_to(Path(other,'test_escape.py'))
            for args in [['discover','-s','tests/escape'],['tests.test_escape'],['tests/test_escape.py'],['discover','-s','tests']]:
                self.assertFalse(match_unittest(self.base+args,self.root,self.profile)['matched'])

    def test_path_selectors_under_workspace_root(self):
        profile = dict(self.profile, roots=['.'])
        (self.root / 'examples/penny-pinner').mkdir(parents=True)
        (self.root / 'examples/penny-pinner/test_pinner.py').write_text('')
        self.assertTrue(match_unittest(self.base + ['examples/penny-pinner/test_pinner.py', '-v'], self.root, profile)['matched'])
        self.assertTrue(match_unittest(self.base + ['examples/penny-pinner/test_pinner.py'], self.root, profile)['matched'])
        self.assertFalse(match_unittest(self.base + ['examples/penny-pinner/test_pinner.py:TestPinner.test_digest'], self.root, profile)['matched'])
