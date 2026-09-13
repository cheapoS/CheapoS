import json
import tempfile
import unittest
from pathlib import Path
from cheapos import check_output as output
from cheapos.storage import Store

class OutputTests(unittest.TestCase):
    def log(self, count=40):
        return ''.join(f'test_{i} (fixture.Tests.test_{i}) ... ok\n' for i in range(count))+'\nRan 40 tests in 0.01s\n\nOK\n'

    def test_only_pass_rows_collapse_and_failures_unknowns_survive(self):
        failure='FAIL: test_bad (fixture.Tests)\nTraceback (most recent call last):\n  File "x", line 1\nAssertionError: expected 3\nstrange important line\n'
        raw='\x1b[32m'+self.log()+'\x1b[0m'+failure
        summary,count=output.summarize(raw)
        self.assertEqual(count,40);self.assertIn(failure,summary);self.assertIn('Ran 40 tests',summary)
        self.assertLess(len(summary),len(raw))
        for text in ('unrecognized\nok\n','Ran 0 tests in 0.00s\nOK\n',failure+'Ran 1 test in 0.01s\nFAILED (failures=1)\n'):
            self.assertEqual(output.summarize(text),(text,0))

    def test_bounded_raw_survives_reload_and_rejects_paths(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root);task={'id':'t','status':'paused','checks':[]}
            data=(self.log()+'FAIL exact\n').encode()+b'\xff'
            for i in range(9):
                run=f'{i:032x}';meta=output.retain(root,'t',run,data,False)
                task['checks'].append({'run_id':run,'raw_output':meta})
            store.save(task);store=Store(root)
            self.assertEqual(output.raw(store,'t',run),data)
            self.assertIn('FAIL exact',output.read(store,'t',run)['output'])
            with self.assertRaisesRegex(ValueError,'expired'):output.raw(store,'t','0'*32)
            with self.assertRaises(ValueError):output.raw(store,'t','../../task.json')
            with self.assertRaises(ValueError):output.read(store,'t',run,-1)
            meta=output.retain(root,'t',run,b'x'*(output.RAW_LIMIT+10),False)
            self.assertTrue(meta['truncated']);self.assertEqual(meta['bytes'],output.RAW_LIMIT)
            self.assertEqual(len(list((Path(root)/'tasks/t/check-output').glob('*.log'))),8)

    def test_optional_payload_preserves_controller_fields_tools_and_raw(self):
        raw=self.log();check={'run_id':'a'*32,'raw_output':{'bytes':len(raw)},'command':['python','-m','unittest'],'exit_code':1,'passed':False,'reason':'cancelled','duration':1,'output':raw,'truncated':False}
        task={'check_output_filter':'unittest','checks':[check],'requests':['original instruction']}
        config={'base_url':'http://127.0.0.1:11434/v1'}
        original=[{'role':'user','content':json.dumps({'checks':check,'source':'exact code','request':'original instruction'})},
                  {'role':'assistant','tool_calls':[{'function':{'arguments':json.dumps(check)}}]}]
        result,info=output.messages(task,original,config)
        got=json.loads(result[0]['content'])['checks']
        for key in check:
            if key!='output':self.assertEqual(got[key],check[key])
        self.assertEqual(result[1],original[1]);self.assertEqual(check['output'],raw)
        self.assertEqual(info['layer'],'cheapos-unittest-v1')
        for cfg in ({'base_url':config['base_url'],'gateway':'omniroute'},{'base_url':'https://remote.invalid'}):
            self.assertEqual(output.messages(task,original,cfg)[0],original)
        check['truncated']=True
        self.assertEqual(output.messages(task,original,config)[0],original)
        task['check_output_filter']='off'
        self.assertEqual(output.messages(task,original,config)[0],original)
