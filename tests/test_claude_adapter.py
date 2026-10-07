"""CLI boundary tests only; no live Claude calls. Author: Nio (Master)."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
from claude_adapter import respond, PROFILES


class ClaudeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        for name,_ in PROFILES.values():
            (Path(self.tmp.name)/name).write_text('---\nmodel: fixture\n---\nExact role instructions.\n')
        self.env=patch.dict(os.environ,{'COMPRESSION_CLAUDE_PROFILES':self.tmp.name});self.env.start();self.addCleanup(self.env.stop)
        self.req=dict(protocol='compression-v1',role='writer',iteration=1,source_sha256='source-hash')

    def test_profile_and_model_are_used(self):
        payload={'subtype':'success','is_error':False,'structured_output':{'text':'fixture'},'modelUsage':{'mock-model':{}},'total_cost_usd':0}
        response=subprocess.CompletedProcess([],0,json.dumps(payload),'')
        with patch('claude_adapter.subprocess.run',return_value=response) as mock:
            result=respond(self.req)
        args=mock.call_args.args[0]
        self.assertEqual(args[args.index('--model')+1],'sonnet')
        self.assertEqual(args[args.index('--system-prompt')+1],'Exact role instructions.\n')
        self.assertEqual(result['profile'],'compressor.md')
        self.assertEqual(result['text'],'fixture')

    def test_failed_auth_cannot_be_a_draft(self):
        payload={'subtype':'success','is_error':True,'result':'authentication failed'}
        with patch('claude_adapter.subprocess.run',return_value=subprocess.CompletedProcess([],1,json.dumps(payload),'')):
            with self.assertRaises(RuntimeError):respond(self.req)

    def test_missing_structured_output_rejected(self):
        payload={'subtype':'success','is_error':False,'result':'plain text'}
        with patch('claude_adapter.subprocess.run',return_value=subprocess.CompletedProcess([],0,json.dumps(payload),'')):
            with self.assertRaises(ValueError):respond(self.req)

    def test_reviewer_profile_mapping(self):
        for role,model in [('facts','haiku'),('argument','sonnet')]:
            payload={'subtype':'success','is_error':False,'structured_output':{'verdict':'pass','issues':[]}}
            with patch('claude_adapter.subprocess.run',return_value=subprocess.CompletedProcess([],0,json.dumps(payload),'')) as mock:
                result=respond(dict(self.req,role=role,draft_sha256='draft-hash'))
            command=mock.call_args.args[0]
            self.assertEqual(command[command.index('--model')+1],model)
            self.assertEqual(result['draft_sha256'],'draft-hash')

if __name__=='__main__':unittest.main()
