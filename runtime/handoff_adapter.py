"""File handoff for a human-supervised agent session; not an agent launcher.
Author: Nio (Master). Workers atomically write response.json beside request.json.
"""
import argparse
import json
import math
from pathlib import Path
import sys
import time
from core import save, validate_reply


def exchange(request, inbox, timeout=900, poll=.2):
    if request.get('role') not in ('writer','facts','argument') or type(request.get('iteration')) is not int or request['iteration'] < 1:
        raise ValueError('invalid request identity')
    if not math.isfinite(timeout) or timeout<=0 or not math.isfinite(poll) or poll<=0:
        raise ValueError('invalid wait settings')
    slot=Path(inbox)/f"{request['iteration']:02d}-{request['role']}"
    slot.mkdir(parents=True,exist_ok=False)
    save(slot/'request.json',request)
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        response=slot/'response.json'
        if response.exists():
            return validate_reply(json.loads(response.read_text(encoding='utf-8')),request)
        time.sleep(min(poll,max(0,deadline-time.monotonic())))
    raise TimeoutError('agent response deadline exceeded')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--inbox',type=Path,required=True)
    parser.add_argument('--timeout',type=float,default=900)
    args=parser.parse_args()
    try:print(json.dumps(exchange(json.load(sys.stdin),args.inbox,args.timeout),ensure_ascii=False))
    except Exception as exc:
        print(type(exc).__name__,file=sys.stderr);raise SystemExit(2)
