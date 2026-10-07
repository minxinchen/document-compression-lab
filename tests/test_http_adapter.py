"""Local HTTP contract tests, not model quality tests. Author: Nio (Master)."""
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
from http_adapter import respond
from core import PROTOCOL, digest, validate_reply
from demo import SOURCE


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.request = dict(protocol=PROTOCOL,role='writer',iteration=1,source=SOURCE,source_sha256=digest(SOURCE))
        self.received=[]
        self.redirect=False
        self.response={'model':'fake-contract-model','choices':[{'finish_reason':'stop','message':{'content':json.dumps({'text':'candidate'})}}]}
        outer=self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                outer.received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                if outer.redirect:
                    self.send_response(302)
                    self.send_header('Location', '/unexpected')
                    self.end_headers()
                    return
                self.send_response(200); self.end_headers()
                self.wfile.write(json.dumps(outer.response).encode())
            def log_message(self,*args): pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        env={'COMPRESSION_API_URL':f'http://127.0.0.1:{self.server.server_port}/v1/chat/completions',
             'COMPRESSION_MODEL_WRITER':'fake-contract-model','COMPRESSION_API_KEY':''}
        self.patch=patch.dict(os.environ,env);self.patch.start();self.addCleanup(self.patch.stop)

    def stop(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def test_request_and_binding(self):
        result=respond(self.request)
        self.assertEqual(result['source_sha256'],digest(SOURCE))
        self.assertEqual(result['text'],'candidate')
        self.assertEqual(self.received[0]['messages'][0]['role'],'system')
        self.assertEqual(self.received[0]['model'],'fake-contract-model')

    def test_truncation_is_not_a_candidate(self):
        self.response['choices'][0]['finish_reason']='length'
        with self.assertRaises(ValueError):respond(self.request)

    def test_plain_text_is_not_json(self):
        self.response['choices'][0]['message']['content']='not json'
        with self.assertRaises(ValueError):respond(self.request)

    def test_review_roles_and_source_quote_validation(self):
        for role in ('facts','argument'):
            req = dict(self.request,role=role,draft='draft',draft_sha256=digest('draft'))
            issue=dict(id='R1',problem='Omitted condition',source_quote='indoors for 7 days',suggestion='Restore it')
            self.response['choices'][0]['message']['content']=json.dumps({'verdict':'revise','issues':[issue]})
            with patch.dict(os.environ,{'COMPRESSION_MODEL_'+role.upper():'fake-reviewer'}):
                result=respond(req)
                self.assertEqual(validate_reply(result,req)['verdict'],'revise')
                issue['source_quote']='nonexistent quote'
                self.response['choices'][0]['message']['content']=json.dumps({'verdict':'revise','issues':[issue]})
                with self.assertRaises(ValueError):validate_reply(respond(req),req)

    def test_redirect_is_not_followed(self):
        self.redirect=True
        with self.assertRaises(ValueError):respond(self.request)
        self.assertEqual(len(self.received),1)

    def test_remote_plain_http_rejected(self):
        with patch.dict(os.environ,{'COMPRESSION_API_URL':'http://example.com/v1/chat/completions'}):
            with self.assertRaises(ValueError):respond(self.request)

if __name__=='__main__':unittest.main()
