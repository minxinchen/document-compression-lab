"""Behavioral regressions for source-bound dual review. Author: Nio (Master)."""
import copy
import json
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
from core import CommandBackend, run, save
from demo import SOURCE, adapter


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'input.md'
        self.source.write_text(SOURCE, encoding='utf-8')

    def execute(self, backend=adapter, **kw):
        return run(self.source, self.root / 'run', backend, execution_kind='synthetic', **kw)

    def test_revision_and_artifact_binding(self):
        before = self.source.read_bytes()
        result = self.execute()
        self.assertEqual(result['status'], 'review_pass')
        self.assertEqual(len(result['rounds']), 2)
        self.assertEqual(self.source.read_bytes(), before)
        for r in result['rounds']:
            self.assertEqual(set(r['reviews']), {'facts', 'argument'})
            self.assertTrue(all(v['draft_sha256'] == r['draft_sha256'] for v in r['reviews'].values()))
        writer = json.loads((self.root/'run/round-02/writer-request.json').read_text())
        self.assertEqual({i['reviewer'] for i in writer['feedback']}, {'facts','argument'})

    def test_reviewers_concurrent_and_isolated(self):
        barrier = threading.Barrier(2)
        def backend(req):
            if req['role'] != 'writer':
                self.assertNotIn('feedback', req)
                self.assertNotIn('previous_draft', req)
                barrier.wait(timeout=3)
            return adapter(req)
        self.assertEqual(self.execute(backend)['status'], 'review_pass')

    def test_old_verdict_rejected(self):
        cached = {}
        def backend(req):
            reply = adapter(req)
            if req['role'] == 'argument':
                if 'reply' in cached:
                    return cached['reply']
                cached['reply'] = copy.deepcopy(reply)
            return reply
        result = self.execute(backend)
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error_stage'], 'reviewers')

    def test_iteration_limit_preserves_unresolved(self):
        result = self.execute(max_iterations=1)
        self.assertEqual(result['status'], 'unresolved')
        self.assertTrue((self.root/'run/candidate.md').exists())
        self.assertEqual(result['rounds'][0]['reviews']['facts']['verdict'], 'revise')

    def test_one_pass_does_not_override_other_reviewer(self):
        def backend(req):
            reply = adapter(req)
            if req['role'] == 'argument':
                reply.update(verdict='pass', issues=[])
            return reply
        self.assertEqual(self.execute(backend, max_iterations=1)['status'], 'unresolved')

    def test_ratio_warning_is_separate(self):
        result = self.execute(target=.3, tolerance=.01)
        self.assertEqual(result['status'], 'review_pass_ratio_warning')

    def test_unknown_source_quote_fails_closed(self):
        def backend(req):
            reply = adapter(req)
            if req['role'] == 'facts':
                reply['issues'][0]['source_quote'] = 'not in source'
            return reply
        self.assertEqual(self.execute(backend)['status'], 'error')

    def test_error_and_other_review_are_preserved(self):
        def backend(req):
            if req['role'] == 'facts':
                raise RuntimeError('secret-do-not-log')
            return adapter(req)
        result = self.execute(backend)
        self.assertEqual(result['status'], 'error')
        self.assertIn('verdict', result['rounds'][0]['reviews']['argument'])
        self.assertNotIn('secret-do-not-log', (self.root/'run/run.json').read_text())

    def test_empty_source_and_invalid_parameters(self):
        for kwargs in ({'target':float('nan')}, {'tolerance':-1}, {'max_iterations':0}):
            with self.assertRaises(ValueError):
                self.execute(**kwargs)
        self.source.write_text(' ')
        with self.assertRaises(ValueError):
            self.execute()

    def test_no_overwriting_previous_run(self):
        self.execute()
        saved = (self.root/'run/run.json').read_bytes()
        with self.assertRaises(FileExistsError):
            self.execute()
        self.assertEqual((self.root/'run/run.json').read_bytes(), saved)

    def test_malformed_and_timeout_adapter(self):
        for command in ([sys.executable,'-c','print("not-json")'],
                        [sys.executable,'-c','import time; time.sleep(2)']):
            backend = CommandBackend({r:command for r in ('writer','facts','argument')}, timeout=.1)
            request = dict(protocol='compression-v1',role='writer',iteration=1,source_sha256='x')
            with self.assertRaises((ValueError, subprocess.TimeoutExpired)):
                backend(request)

    def test_feedback_role_cannot_be_spoofed(self):
        def backend(req):
            reply = adapter(req)
            if req['role'] == 'facts' and reply['issues']:
                reply['issues'][0]['reviewer'] = 'argument'
            return reply
        self.execute(backend)
        req = json.loads((self.root/'run/round-02/writer-request.json').read_text())
        self.assertEqual(req['feedback'][0]['reviewer'], 'facts')

    def test_atomic_write_preserves_previous_json_on_replace_failure(self):
        path = self.root/'state.json'
        save(path, {'status':'running'})
        with patch('core.os.replace', side_effect=OSError('disk error')):
            with self.assertRaises(OSError):save(path, {'status':'done'})
        self.assertEqual(json.loads(path.read_text()), {'status':'running'})
        self.assertEqual(list(self.root.glob('.state.json*')), [])

    def test_timeout_kills_descendant(self):
        marker = self.root/'should-not-be-written'
        child = "import time; from pathlib import Path; time.sleep(1); Path(" + repr(str(marker)) + ").touch()"
        parent = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," + repr(child) + "]); time.sleep(3)"
        command = [sys.executable, '-c', parent]
        backend = CommandBackend({r:command for r in ('writer','facts','argument')}, timeout=.3)
        with self.assertRaises(subprocess.TimeoutExpired):backend({'role':'writer'})
        time.sleep(1.1)
        self.assertFalse(marker.exists())

    def test_subprocess_end_to_end(self):
        script = Path(__file__).resolve().parents[1]/'runtime/demo.py'
        result = subprocess.run([sys.executable,str(script),str(self.root/'demo')], capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertEqual(json.loads(result.stdout)['execution_kind'],'synthetic')


if __name__ == '__main__':
    unittest.main()
