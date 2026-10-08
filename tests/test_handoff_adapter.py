"""File handoff protocol tests, with no model calls. Author: Nio (Master)."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
from handoff_adapter import exchange
from core import save


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.request=dict(protocol='compression-v1',role='writer',iteration=1,source_sha256='source')

    def test_atomic_reply_round_trip(self):
        def worker():
            request=self.root/'01-writer/request.json'
            deadline=time.monotonic()+2
            while not request.exists() and time.monotonic()<deadline:time.sleep(.01)
            value=json.loads(request.read_text());value['text']='candidate'
            save(request.parent/'response.json',value)
        t=threading.Thread(target=worker);t.start()
        try:self.assertEqual(exchange(self.request,self.root,timeout=2,poll=.01)['text'],'candidate')
        finally:t.join(timeout=2)

    def test_timeout_preserves_request(self):
        with self.assertRaises(TimeoutError):exchange(self.request,self.root,timeout=.02,poll=.01)
        self.assertTrue((self.root/'01-writer/request.json').exists())

    def test_reusing_slot_rejected(self):
        (self.root/'01-writer').mkdir()
        with self.assertRaises(FileExistsError):exchange(self.request,self.root,timeout=.02)

    def test_wrong_draft_hash_is_rejected(self):
        request=dict(self.request,role='facts',draft_sha256='expected',source='source')
        def worker():
            path=self.root/'01-facts/request.json'
            deadline=time.monotonic()+2
            while not path.exists() and time.monotonic()<deadline:time.sleep(.01)
            reply=json.loads(path.read_text())
            reply.update(draft_sha256='wrong',verdict='pass',issues=[])
            save(path.parent/'response.json',reply)
        thread=threading.Thread(target=worker);thread.start()
        try:
            with self.assertRaises(ValueError):exchange(request,self.root,timeout=2,poll=.01)
        finally:thread.join(timeout=2)

    def test_late_reply_cannot_complete_new_inbox(self):
        old=self.root/'old';new=self.root/'new'
        with self.assertRaises(TimeoutError):exchange(self.request,old,timeout=.02,poll=.01)
        save(old/'01-writer/response.json',dict(self.request,text='late reply'))
        with self.assertRaises(TimeoutError):exchange(self.request,new,timeout=.02,poll=.01)
        self.assertFalse((new/'01-writer/response.json').exists())

    def test_invalid_identity_rejected(self):
        for role,iteration in [('../escape',1),('writer',True),('writer',0)]:
            with self.assertRaises(ValueError):exchange(dict(self.request,role=role,iteration=iteration),self.root)

if __name__=='__main__':unittest.main()
