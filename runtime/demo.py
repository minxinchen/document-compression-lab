"""Deterministic synthetic demonstration; NOT a model or quality benchmark.
Author: Nio (Master).
"""
import json
import sys
from pathlib import Path

SOURCE = ('In a pilot with 12 sensors, cleaning reduced missing readings from 8% to 3%. '
          'The devices were tested indoors for 7 days. There was no outdoor control, '
          'so the result does not establish outdoor reliability. '
          'This report describes a preliminary pilot observation, not a production guarantee.')
DRAFTS = [
    'Cleaning proved reliable: missing readings fell from 8% to 3% in 12 sensors.',
    'In a 7-day indoor pilot with 12 sensors, cleaning reduced missing readings from 8% to 3%. '
    'No outdoor control was used; outdoor reliability remains unestablished. The finding is preliminary.'
]


def adapter(request):
    result = {k: request[k] for k in ('protocol', 'role', 'iteration', 'source_sha256')}
    if request['source'] != SOURCE:
        raise ValueError('synthetic demo accepts only its bundled source')
    if request['role'] == 'writer':
        result['text'] = DRAFTS[min(request['iteration']-1, 1)]
    else:
        result.update(draft_sha256=request['draft_sha256'], verdict='pass', issues=[])
        if request['iteration'] == 1:
            if request['role'] == 'facts':
                issue = dict(id='F1', problem='Missing duration and test environment.',
                             source_quote='indoors for 7 days', suggestion='Restore test conditions.')
            else:
                issue = dict(id='A1', problem='Proved reliable overstates limited evidence.',
                             source_quote='does not establish outdoor reliability',
                             suggestion='Restore limitation and preliminary status.')
            result.update(verdict='revise', issues=[issue])
    return result


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--adapter':
        print(json.dumps(adapter(json.load(sys.stdin))))
    else:
        from core import CommandBackend, run
        output = Path(sys.argv[1]) if len(sys.argv) == 2 else Path('runs/synthetic-demo')
        # source lives in an automatically cleaned temp directory, not beside user data.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source.md'
            source.write_text(SOURCE, encoding='utf-8')
            command = [sys.executable, str(Path(__file__).resolve()), '--adapter']
            state = run(source, output, CommandBackend({r: command for r in ('writer','facts','argument')}),
                        execution_kind='synthetic', backend_label='scripted-two-round-demo')
        print(json.dumps({'status':state['status'], 'rounds':len(state['rounds']),
                          'execution_kind':state['execution_kind'], 'output':str(output)}))
        raise SystemExit(0 if state['status']=='review_pass' else 2)
