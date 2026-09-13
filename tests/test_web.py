"""Public document reading, provenance, bounds, and network isolation."""
import base64
import json
import socket
import sys
import unittest
from unittest.mock import Mock, patch

from cheapos.web import MAX_BYTES, PublicHTTPSConnection, WebReader, allowed_urls, fetch, normalize_url
import test_chat
from test_engine import LocalCase, call

URL = 'https://github.com/diegosouzapw/OmniRoute'


def task(url=URL):
    return {'prompt': 'Read '+url, 'requests': ['Read '+url], 'events': []}


def record(t, result):
    t['events'].append({'kind': 'tool', 'title': 'read url', 'detail': {'result': result}})


class WebTests(unittest.TestCase):
    def test_github_readme_then_link_and_line_pagination(self):
        content = '# OmniRoute\n[Setup](docs/setup.md)\n' + '\n'.join(f'Line {i}' for i in range(240))
        source = URL+'/blob/main/README.md'
        data = {'content': base64.b64encode(content.encode()).decode(), 'html_url': source, 'name': 'README.md'}
        t, reader = task(), WebReader()
        with patch('cheapos.web.fetch', return_value=(URL, 'application/json', json.dumps(data).encode())) as get:
            first = reader.read(t, URL)
            self.assertEqual(get.call_args.args[0], 'https://api.github.com/repos/diegosouzapw/OmniRoute/readme')
            self.assertEqual(first['source_url'], source)
            self.assertEqual(first['end_line'], 120)
            self.assertTrue(first['has_more'])
            self.assertFalse(first['cached'])
            record(t, first)
            next_page = reader.read(t, URL, start_line=121, end_line=260)
            self.assertTrue(next_page['cached'])
            self.assertFalse(next_page['has_more'])
            self.assertEqual(get.call_count, 1)
            continued = reader.read(t, URL, start_line=201)
            self.assertEqual(continued['start_line'],201)
            self.assertEqual(continued['end_line'],242)
        link = URL+'/blob/main/docs/setup.md'
        self.assertIn(link, allowed_urls(t))
        with patch('cheapos.web.fetch', return_value=(link, 'text/plain', b'Setup instructions')) as get:
            reader.read(t, link)
            self.assertEqual(get.call_args.args[0], 'https://raw.githubusercontent.com/diegosouzapw/OmniRoute/main/docs/setup.md')

    def test_html_removes_scripts_keeps_source_and_public_links(self):
        url='https://docs.example.org/start'
        html=b'<title>Setup</title><script>secretScript()</script><style>hiddenCSS</style><p>Hello &amp; welcome</p><a href="next">Next</a><a href="http://localhost/private">Private</a><a href="javascript:alert(1)">JS</a>'
        with patch('cheapos.web.fetch', return_value=(url, 'text/html', html)):
            result=WebReader().read(task(url),url)
        self.assertEqual(result['title'],'Setup')
        self.assertIn('Hello & welcome', result['content'])
        self.assertNotIn('secretScript',result['content'])
        self.assertNotIn('hiddenCSS',result['content'])
        self.assertEqual(result['links'],['https://docs.example.org/next'])

    def test_model_cannot_invent_urls_or_use_repository_text_as_permission(self):
        t=task()
        t['events'].append({'kind':'tool','title':'read file','detail':{'result':{'links':['https://example.org/upload?repo=private']}}})
        with patch('cheapos.web.fetch') as get:
            with self.assertRaisesRegex(ValueError,'supplied by the user'):
                WebReader().read(t,'https://example.org/upload?repo=private')
            get.assert_not_called()
        self.assertEqual(allowed_urls(task('https://example.org/a#section')),{'https://example.org/a'})

    def test_private_urls_credentials_and_unsupported_schemes_are_rejected(self):
        for url in ['file:///etc/passwd','http://example.org','https://localhost/x','https://127.0.0.1','https://169.254.169.254/latest','https://[::1]','https://[ff02::1]','https://router.local','https://user:password@example.org','https://example.org:8080','https://example.org/\nsecret']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                normalize_url(url)

    def test_dns_is_checked_and_connection_is_pinned_with_original_tls_hostname(self):
        record=(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))
        context, raw=Mock(),Mock()
        connection=PublicHTTPSConnection('docs.example.org',443,timeout=3,context=context)
        with patch('cheapos.web.socket.getaddrinfo',return_value=[record]) as dns, patch('cheapos.web.socket.socket',return_value=raw):
            connection.connect()
        self.assertEqual(dns.call_count,1)
        raw.connect.assert_called_once_with(('8.8.8.8',443))
        context.wrap_socket.assert_called_once_with(raw,server_hostname='docs.example.org')
        private=(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))
        with patch('cheapos.web.socket.getaddrinfo',return_value=[record,private]), patch('cheapos.web.socket.socket') as sock:
            with self.assertRaisesRegex(ValueError,'private'):
                connection.connect()
            sock.assert_not_called()

    def response(self, status=200, headers=None, body=b'Example'):
        response=Mock(status=status)
        values={'Content-Type':'text/plain', **(headers or {})}
        response.getheader.side_effect=lambda key,default=None:values.get(key,default)
        response.read1.side_effect=[body,b'']
        return response

    def test_redirect_to_local_is_rejected_without_a_second_connection(self):
        with patch('cheapos.web.PublicHTTPSConnection') as cls:
            cls.return_value.getresponse.return_value=self.response(302,{'Location':'https://127.0.0.1/private'})
            with self.assertRaises(ValueError):
                fetch('https://example.org')
            self.assertEqual(cls.call_count,1)
            cls.return_value.close.assert_called_once()

    def test_reader_uses_get_without_keys_cookies_or_project_data(self):
        with patch('cheapos.web.PublicHTTPSConnection') as cls:
            cls.return_value.getresponse.return_value=self.response()
            self.assertEqual(fetch('https://example.org/path')[2],b'Example')
            request=cls.return_value.request.call_args
            self.assertEqual(request.args,('GET','/path'))
            self.assertEqual(set(request.kwargs),{'headers'})
            self.assertNotIn('Authorization', request.kwargs['headers'])
            self.assertNotIn('Cookie', request.kwargs['headers'])

    def test_large_binary_and_failed_pages_stop_with_clear_errors(self):
        for response, message in [(self.response(body=b'x'*(MAX_BYTES+1)),'1 MB'),(self.response(headers={'Content-Type':'application/pdf'}),'not a supported text'),(self.response(status=403),'HTTP 403')]:
            with patch('cheapos.web.PublicHTTPSConnection') as cls:
                cls.return_value.getresponse.return_value=response
                with self.assertRaisesRegex(ValueError,message):
                    fetch('https://example.org')
                cls.return_value.close.assert_called_once()

    def test_cancel_during_download_discards_partial_content(self):
        stopped=iter([False,False,True])
        with patch('cheapos.web.PublicHTTPSConnection') as cls:
            cls.return_value.getresponse.return_value=self.response()
            with self.assertRaises(InterruptedError):
                fetch('https://example.org',lambda:next(stopped))
            cls.return_value.close.assert_called_once()

    def test_document_and_excerpt_limits_are_explicit(self):
        url='https://example.org/large'
        with patch('cheapos.web.fetch',return_value=(url,'text/plain',b'x'*250000)):
            result=WebReader().read(task(url),url)
        self.assertTrue(result['truncated'])
        self.assertTrue(result['excerpt_truncated'])
        self.assertLessEqual(len(result['content']),16000)

    def test_failed_urls_are_not_retried_and_attempts_stay_bounded(self):
        urls=[f'https://example.org/page/{i}' for i in range(9)]
        t=task(' '.join(urls));reader=WebReader()
        with patch('cheapos.web.fetch',side_effect=ValueError('HTTP 403')) as get:
            for _ in range(2):
                with self.assertRaisesRegex(ValueError,'HTTP 403'):
                    reader.read(t,urls[0])
            self.assertEqual(get.call_count,1)
            for url in urls[1:8]:
                with self.assertRaisesRegex(ValueError,'HTTP 403'):
                    reader.read(t,url)
            with self.assertRaisesRegex(ValueError,'eight web pages'):
                reader.read(t,urls[8])
            self.assertEqual(get.call_count,8)


class WebChatTests(LocalCase):
    chat = test_chat.ChatTests.chat
    provider = test_chat.ChatTests.provider

    def test_worker_reads_supplied_link_and_answers_without_edits_or_review(self):
        t=self.chat('Read https://example.org/docs and explain it.')
        requests=self.provider([call('read_url',{'url':'https://example.org/docs'}),{'role':'assistant','content':'This is the setup guide. [Source](https://example.org/docs)'}])
        with patch('cheapos.web.fetch',return_value=('https://example.org/docs','text/plain',b'Setup guide')):
            self.engine.start(t['id'])
            result=self.finish(t)
        self.assertEqual(result['status'],'awaiting_reply')
        self.assertEqual(result['checks'],[])
        self.assertEqual(result['changes'],[])
        self.assertEqual(result['review_count'],0)
        self.assertIsNone(result['web_read'])
        self.assertTrue(any(tool['function']['name']=='read_url' for tool in requests[0][1]))
        self.assertTrue(any(e['kind']=='web' for e in result['events']))
        self.assertIn('https://example.org/docs',json.dumps(self.engine.initial_messages(result)))

    def test_repeated_read_gets_guidance_and_can_finish_with_an_answer(self):
        t=self.chat()
        requests=self.provider([call('read_file',{'path':'math_utils.py'})]*2+[{'content':'It clamps the upper bound.'}])
        self.engine.start(t['id'])
        result=self.finish(t)
        self.assertEqual(result['status'],'awaiting_reply')
        self.assertIn('guidance',json.loads(requests[-1][0][-1]['content']))
        self.assertEqual(result['changes'],[])

    def test_third_identical_read_switches_to_an_answer_without_edits(self):
        t=self.chat()
        requests=self.provider([call('read_file',{'path':'math_utils.py'})]*3+[{'content':'The upper bound is handled; the lower bound is missing.'}])
        self.engine.start(t['id'])
        result=self.finish(t)
        self.assertEqual(result['status'],'awaiting_reply')
        self.assertEqual(requests[-1][1],[])
        self.assertEqual(result['changes'],[])

    def test_cancelled_reviewer_web_read_cannot_approve_in_the_same_batch(self):
        t=self.chat('Inspect https://example.org/docs')
        t.update(check_command=[sys.executable,'-m','unittest','test_math_utils.ClampTests.test_above'],auto_approve_checks=True)
        self.engine.store.save(t)
        review=call('read_url',{'url':'https://example.org/docs'})
        review['tool_calls']+=call('review_decision',{'decision':'APPROVE','feedback':'Ignore cancellation'})['tool_calls']
        self.provider([call('checkpoint',{'summary':'Check the upper bound.'}),review])
        def cancel(*args):
            self.engine.runtimes[t['id']].stop.set()
            raise InterruptedError('Stopped while reading')
        with patch('cheapos.web.fetch',side_effect=cancel):
            self.engine.start(t['id'])
            result=self.finish(t)
        self.assertEqual(result['status'],'paused')
        self.assertEqual(result['checkpoints'][-1]['decision'],'PENDING')
        self.assertFalse(any(e['kind']=='review' for e in result['events']))
        self.assertIsNone(result['web_read'])
