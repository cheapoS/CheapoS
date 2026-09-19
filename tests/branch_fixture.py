"""Disposable, deterministic CSV → Markdown CLI job for UI/controller proof.

This provider is synthetic. It executes actual tools/checks and never calls a
network model. The independently asserted expected behavior lives in the tests.
"""
import json
import shlex
import sys
import tempfile
import time
from pathlib import Path
from cheapos.engine import Engine
from cheapos.server import LocalServer
from cheapos.workspace import git

COMMAND=shlex.join([sys.executable,'-m','unittest','discover'])
PROMPT='Build a CSV reader, Markdown table renderer, and a documented CLI. Preserve quoted CSV fields and report malformed row widths. Test each part.'
PLAN=[
 {'id':'csv','title':'Read CSV records','instructions':'Implement read_csv(text) in csv_reader.py returning headers and rows. Preserve quoted fields and reject inconsistent row widths. Add real unittest coverage.','dependencies':[],'acceptance_criteria':['Quoted CSV fields are preserved and inconsistent row widths are rejected.'],'required_checks':[COMMAND]},
 {'id':'markdown','title':'Render Markdown tables','instructions':'Implement render_table(headers,rows) in markdown_table.py, escaping pipes. Include headers, separator and all rows, with tests.','dependencies':['csv'],'acceptance_criteria':['Markdown tables include headers, separator and escaped pipe characters.'],'required_checks':[COMMAND]},
 {'id':'cli','title':'Wire and document the CLI','instructions':'Implement csvmd.py accepting a CSV filename and printing Markdown using both modules. Document usage in README.md and add subprocess tests.','dependencies':['markdown'],'acceptance_criteria':['The documented CLI reads a file and prints the correct Markdown table.'],'required_checks':[COMMAND]}
]
CSV='''import csv
import io

def read_csv(text):
    records = list(csv.reader(io.StringIO(text)))
    if not records:
        return [], []
    headers, rows = records[0], records[1:]
    if any(len(row) != len(headers) for row in rows):
        raise ValueError('Inconsistent row width')
    return headers, rows
'''
CSV_BAD=CSV.replace('csv.reader(io.StringIO(text))',"(line.split(',') for line in text.splitlines())")
CSV_TEST='''import unittest
from csv_reader import read_csv
class CSVTests(unittest.TestCase):
    def test_quoted(self):
        self.assertEqual(read_csv('name,note\\nAda,"x,y"\\n'), (['name','note'],[['Ada','x,y']]))
    def test_width(self):
        with self.assertRaises(ValueError): read_csv('a,b\\n1\\n')
    def test_empty(self): self.assertEqual(read_csv(''), ([],[]))
'''
MARKDOWN='''def render_table(headers, rows):
    def line(row): return '| ' + ' | '.join(str(cell).replace('|', '\\\\|') for cell in row) + ' |'
    if not headers: return ''
    return '\\n'.join([line(headers), line(['---'] * len(headers))] + [line(row) for row in rows]) + '\\n'
'''
MARKDOWN_TEST='''import unittest
from markdown_table import render_table
class MarkdownTests(unittest.TestCase):
    def test_table(self):
        self.assertEqual(render_table(['a'],[['x|y']]), '| a |\\n| --- |\\n| x\\\\|y |\\n')
'''
CLI='''import argparse
from pathlib import Path
from csv_reader import read_csv
from markdown_table import render_table

def main():
    parser = argparse.ArgumentParser(description='Convert CSV to Markdown')
    parser.add_argument('file')
    args = parser.parse_args()
    print(render_table(*read_csv(Path(args.file).read_text())), end='')

if __name__ == '__main__': main()
'''
CLI_TEST='''import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
class CLITests(unittest.TestCase):
    def test_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.csv'
            source.write_text('name,score\\nAda,9\\n')
            result = subprocess.run([sys.executable,'csvmd.py',str(source)], capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,'| name | score |\\n| --- | --- |\\n| Ada | 9 |\\n')
'''
README='# CSV to Markdown\n\nRun `python3 csvmd.py input.csv` to print a Markdown table. Quoted CSV fields and pipe escaping are supported.\n'

def call(name,args):
    return {'role':'assistant','content':None,'tool_calls':[{'id':'fixture-call','type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}

class ScriptedProvider:
    def __init__(self,delay=0):
        self.steps={};self.reviewer_revision=False;self.delay=delay;self.calls=[]
    def complete(self,messages,tools,max_tokens):
        if self.delay:time.sleep(self.delay)
        names=[t['function']['name'] for t in tools]
        if 'propose_branch_plan' in names:
            packet=json.loads(messages[1]['content'])
            result=call('propose_branch_plan',{'status':'plan','clarification':'','plan':{'items':PLAN,'limits':packet['displayed_limits'],'final_checks':[COMMAND]}})
        elif 'final_review_decision' in names:
            packet=json.loads(messages[1]['content'])
            result=call('final_review_decision',{**{k:packet[k] for k in ('manifest_id','chunk_ids','criteria_ids')},'decision':'APPROVE','feedback':'All supplied changes and criteria are covered by the passing actual suite.'})
        elif 'review_decision' in names:
            packet=json.loads(messages[1]['content']);item=packet['item']
            if item['id']=='markdown' and not self.reviewer_revision:
                self.reviewer_revision=True
                result=call('review_decision',{'decision':'REQUEST_CHANGES','feedback':'Add an explicit empty-table test for the renderer before approval.', 'candidate_id':packet['candidate_id'], 'defects':[{'criterion':item['acceptance_criteria'][0], 'location':'test_markdown.py:1', 'expected':'Empty-table regression coverage', 'observed':'No empty-table assertion', 'kind':'static', 'support':'The supplied tests omit the documented empty-table path.', 'reproduction':''}]})
            else:
                result=call('review_decision',{'decision':'APPROVE','feedback':'Implementation and actual tests satisfy the supplied criteria.','candidate_id':packet['candidate_id'],'criteria_outcomes':{c:{'passed':True,'evidence':'Read implementation and passing behavioral test'} for c in item['acceptance_criteria']}})
        else:
            packets=[]
            for message in messages:
                try:packets.append(json.loads(message.get('content') or 'null'))
                except (ValueError,TypeError):pass
            item=next(p['active_item'] for p in reversed(packets) if isinstance(p,dict) and 'active_item' in p)
            identity=item['id'];step=self.steps.get(identity,0);self.steps[identity]=step+1
            scripts={
              'csv':[('csv_reader.py',CSV_BAD),('test_csv_reader.py',CSV_TEST),None,('csv_reader.py',CSV)],
              'markdown':[('markdown_table.py',MARKDOWN),('test_markdown_table.py',MARKDOWN_TEST),None,('test_markdown_table.py',MARKDOWN_TEST+"    def test_empty(self): self.assertEqual(render_table([],[]),'')\n")],
              'cli':[('csvmd.py',CLI),('test_cli.py',CLI_TEST),('README.md',README)]}
            actions=scripts.get(identity,[('README.md',README+'\nExample input:\n\n```csv\nname,score\nAda,9\n```\n\nExample output:\n\n```markdown\n| name | score |\n| --- | --- |\n| Ada | 9 |\n```\n')])
            action=actions[step] if step<len(actions) else None
            if identity=='csv' and step==3:
                result=call('replace_text',{'path':'csv_reader.py','old_text':CSV_BAD,'new_text':CSV})
            elif identity=='markdown' and step==3:
                result=call('replace_text',{'path':'test_markdown_table.py','old_text':MARKDOWN_TEST,'new_text':action[1]})
            elif identity=='cli' and step==2:
                result=call('read_file',{'path':'README.md'})
                self.steps[identity]=3
            elif identity=='cli' and step==3:
                result=call('replace_text',{'path':'README.md','old_text':'# CSV conversion project\n','new_text':README})
            elif identity not in scripts and step==0:
                result=call('read_file',{'path':'README.md'})
            elif identity not in scripts and step==1:
                result=call('replace_text',{'path':'README.md','old_text':README,'new_text':actions[0][1]})
            else:
                result=call('write_file',{'path':action[0],'content':action[1]}) if action else call('checkpoint',{'summary':'Implemented the item and its behavioral coverage','uncertainties':''})
        self.calls.append(names)
        return result,{'prompt_tokens':25,'completion_tokens':15,'cost':0}

class Fixture:
    def __init__(self,delay=0):
        self.tmp=tempfile.TemporaryDirectory(prefix='cheapos-branch-proof-');self.root=Path(self.tmp.name).resolve()
        self.source=self.root/'project';self.source.mkdir()
        git(self.source,'init','-qb','main');git(self.source,'config','user.name','Fixture');git(self.source,'config','user.email','fixture@example.invalid')
        (self.source/'SPEC.md').write_text(PROMPT+'\n')
        (self.source/'README.md').write_text('# CSV conversion project\n')
        git(self.source,'add','.');git(self.source,'commit','-qm','Baseline specification')
        self.engine=Engine(self.root/'state',fixture_delay=0)
        config={'base_url':'https://fixture.invalid/v1','model':'fixture-worker','key_env':'CHEAPOS_FIXTURE_UNUSED','input_rate':0,'output_rate':0}
        self.engine.config={'worker':config,'reviewer':dict(config,model='fixture-reviewer')}
        self.engine.save_preferences({'execution':{'mode':'manual'}})
        self.engine.startup.busy=lambda:False
        self.provider=ScriptedProvider(delay);self.engine.provider_factory=lambda *args:self.provider
    def close(self):self.engine.shutdown();self.tmp.cleanup()
    def values(self,feature='feature/csv-cli'):
        return {'repository':str(self.source),'prompt':PROMPT,'base_ref':'refs/heads/main','target_ref':'refs/heads/main','feature_ref':'refs/heads/'+feature,'plan':{'items':PLAN,'limits':{'dollars':0},'final_checks':[COMMAND]}}
