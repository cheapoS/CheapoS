"""In-memory structural diagnostics: no inference, Git, network or sleeps."""
import base64
import copy
import json
import unittest
from unittest.mock import patch
from cheapos import structural_telemetry as telemetry, edit_history
from cheapos.engine import Engine, extract_fallback_tool_calls


class StructuralTelemetryTests(unittest.TestCase):
    def task(self):
        return {'request_metrics':[{'id':'request1','role':'worker','dispatched':True}]}

    def test_native_and_xml_preserve_exact_text_without_retaining_source(self):
        source='def SECRET_MARKER():\n\treturn "private credential"\n    # keep spaces\n'
        for xml in (False,True):
            task=self.task()
            args={'path':'example.py','content':source}
            if xml:
                calls,_=extract_fallback_tool_calls('<invoke name="write_file"><parameter name="path">example.py</parameter><parameter name="content">'+source+'</parameter></invoke>',{'write_file'},task)
                call=calls[0]
            else:
                call={'id':'call_native','function':{'name':'write_file','arguments':json.dumps(args)}}
            _,decoded=Engine.parse_call(call,task)
            self.assertEqual(decoded,args)
            diagnosis={};edit_history.syntax_error('example.py',source,diagnosis)
            telemetry.validation(task,'',source,diagnosis)
            rows=task['request_metrics'][0]['structural_telemetry']
            encoded=json.dumps(rows)
            for secret in (source,'SECRET_MARKER','private credential'):
                self.assertNotIn(secret,encoded)
                self.assertNotIn(secret.encode().hex(),encoded)
                self.assertNotIn(base64.b64encode(secret.encode()).decode(),encoded)
            self.assertEqual(rows[-1]['leading_tabs'],1)
            self.assertEqual(rows[-1]['leading_spaces'],4)
            self.assertEqual(rows[-1]['tool_id'],call['id'])
            self.assertEqual(rows[-1]['syntax'],'valid')
            self.assertTrue(all(r['upstream']=='unknown' for r in rows))
            self.assertEqual(task['routing_traces'][0]['attempts'][0]['structural_telemetry'],rows)

    def test_retention_allowlist_and_collector_failure(self):
        task=self.task();record=task['request_metrics'][0]
        for i in range(1000):telemetry.add(record,'argument_decode',text_bytes=i,source='SECRET',syntax='SECRET',headers={'password':'SECRET'})
        self.assertEqual(len(record['structural_telemetry']),telemetry.LIMIT)
        self.assertNotIn('SECRET',json.dumps(record))
        call={'id':'call1','function':{'name':'write_file','arguments':json.dumps({'content':'  exact\n'})}}
        before=copy.deepcopy(call)
        with patch.object(telemetry,'arguments',side_effect=RuntimeError('collector failed')):
            self.assertEqual(Engine.parse_call(call,task)[1]['content'],'  exact\n')
        self.assertEqual(call,before)
        self.assertEqual(Engine.parse_call(call)[1]['content'],'  exact\n')
        with patch.object(telemetry,'add',side_effect=RuntimeError('collector failed')):
            calls,_=extract_fallback_tool_calls('<invoke name="write_file"><parameter name="content">  exact\n</parameter></invoke>',{'write_file'},task)
            self.assertEqual(Engine.parse_call(calls[0])[1]['content'],'  exact\n')

    def test_syntax_categories_use_existing_validation_only(self):
        for path,text,category in [('a.py','def x(:\n','syntax'),('a.json','{"SECRET":','json'),('a.txt','unclosed fragment SECRET','unknown')]:
            result={};edit_history.syntax_error(path,text,result)
            self.assertEqual(result['syntax'],category)
            self.assertNotIn('SECRET',json.dumps(result))

    def test_provider_observes_wire_size_and_ignores_collector_failure(self):
        import io
        from cheapos.providers import ChatProvider
        source='def secret():\n    return "PRIVATE_MARKER"\n'
        call={'id':'call1','function':{'name':'write_file','arguments':json.dumps({'content':source})}}
        raw=json.dumps({'_wire_bytes':999999,'choices':[{'message':{'tool_calls':[call]}}]}).encode()
        for broken in (False,True):
            provider=ChatProvider({'model':'local','base_url':'http://127.0.0.1:11434/v1','pacing_interval':0})
            with patch('cheapos.providers.build_opener') as opener, patch.object(telemetry,'add',side_effect=RuntimeError('unavailable') if broken else telemetry.add):
                opener.return_value.open.return_value=io.BytesIO(raw)
                message,_=provider.complete([],[],100)
                opener.return_value.open.assert_called_once()
            self.assertEqual(message['tool_calls'],[call])
            if not broken:
                row=provider.request_timing['structural_telemetry'][-1]
                self.assertEqual(row['wire_bytes'],len(raw))
                self.assertEqual(row['extraction'],'native')
                self.assertNotIn('PRIVATE_MARKER',json.dumps(provider.request_timing))
