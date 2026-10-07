"""Source-bound compression orchestration. Author: Nio (Master)."""
import copy
import hashlib
import json
import math
import os
import signal
import tempfile
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROTOCOL = 'compression-v1'
ROLES = ('facts', 'argument')


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def save(path, value):
    path = Path(path)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.' + path.name, delete=False) as stream:
            tmp = Path(stream.name)
            stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if tmp is not None and tmp.exists():
            tmp.unlink()


def parameters(target, tolerance, max_iterations):
    if not (math.isfinite(target) and math.isfinite(tolerance)
            and 0 < target < 1 and 0 <= tolerance < target and target + tolerance <= 1):
        raise ValueError('invalid target/tolerance')
    if type(max_iterations) is not int or not 1 <= max_iterations <= 20:
        raise ValueError('max_iterations must be an integer in 1..20')


def validate_reply(reply, request):
    if not isinstance(reply, dict):
        raise ValueError('response must be an object')
    for key in ('protocol', 'role', 'iteration', 'source_sha256'):
        if reply.get(key) != request[key]:
            raise ValueError('response binding mismatch: ' + key)
    if type(reply.get('iteration')) is not int:
        raise ValueError('iteration must be integer')
    if request['role'] == 'writer':
        if not isinstance(reply.get('text'), str) or not reply['text'].strip():
            raise ValueError('writer text must be nonempty')
        return reply
    if reply.get('draft_sha256') != request['draft_sha256']:
        raise ValueError('review belongs to another draft')
    issues = reply.get('issues')
    verdict = reply.get('verdict')
    if verdict not in ('pass', 'revise') or not isinstance(issues, list):
        raise ValueError('review requires pass/revise and issues array')
    if (verdict == 'pass' and issues) or (verdict == 'revise' and not issues):
        raise ValueError('verdict contradicts issues')
    for issue in issues:
        if not isinstance(issue, dict) or any(not isinstance(issue.get(k), str) or not issue[k].strip()
                                              for k in ('id', 'problem', 'source_quote', 'suggestion')):
            raise ValueError('incomplete issue')
        if issue['source_quote'] not in request['source']:
            raise ValueError('issue source_quote not found in source')
    ids = [i['id'] for i in issues]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate issue id')
    return reply


class CommandBackend:
    """Trusted local executable: one JSON request on stdin, one JSON reply on stdout."""
    def __init__(self, commands, timeout=180):
        if set(commands) != {'writer', *ROLES}:
            raise ValueError('commands require writer, facts, argument')
        if any(not isinstance(v, list) or not v or any(not isinstance(s, str) for s in v)
               for v in commands.values()):
            raise ValueError('each command must be a nonempty argv array')
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('timeout must be positive')
        self.commands, self.timeout = commands, timeout

    def __call__(self, request):
        started = time.monotonic()
        process = subprocess.Popen(self.commands[request['role']], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding='utf-8', start_new_session=True)
        try:
            stdout, _stderr = process.communicate(json.dumps(request), timeout=self.timeout)
        finally:
            # POSIX process group: also clean descendant CLIs on timeout or interruption.
            # Adapters must not daemonize or escape the group; this is not a sandbox.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
        # stderr may contain credentials; never persist it.
        if process.returncode:
            raise RuntimeError('adapter exited nonzero: ' + str(process.returncode))
        reply = json.loads(stdout)
        validate_reply(reply, request)
        reply['elapsed_seconds'] = round(time.monotonic() - started, 3)
        return reply


def run(source_path, output, backend, *, target=.65, tolerance=.03, max_iterations=5,
        execution_kind='live', backend_label='configured-command'):
    parameters(target, tolerance, max_iterations)
    source_path, output = Path(source_path), Path(output)
    source = source_path.read_bytes().decode('utf-8')
    if not source.strip():
        raise ValueError('source is empty')
    # A fresh directory is mandatory; never overwrite a prior run or source.
    output.mkdir(parents=True, exist_ok=False)
    (output / 'source.md').write_bytes(source.encode('utf-8'))
    state = dict(protocol=PROTOCOL, execution_kind=execution_kind, backend=backend_label,
                 source_sha256=digest(source), source_chars=len(source), target=target,
                 tolerance=tolerance, max_iterations=max_iterations, status='running', rounds=[])
    save(output / 'run.json', state)
    previous, feedback = None, []
    stage = 'writer'
    try:
        for iteration in range(1, max_iterations + 1):
            base = dict(protocol=PROTOCOL, iteration=iteration, source=source,
                        source_sha256=digest(source), target=target, tolerance=tolerance)
            folder = output / f'round-{iteration:02d}'
            folder.mkdir()
            request = dict(base, role='writer', previous_draft=previous, feedback=feedback)
            stage = 'writer'
            save(folder / 'writer-request.json', request)
            writer = validate_reply(backend(copy.deepcopy(request)), request)
            save(folder / 'writer-response.json', writer)
            draft = writer['text']
            (folder / 'draft.md').write_bytes(draft.encode('utf-8'))
            sha = digest(draft)
            ratio = len(draft) / len(source)
            record = dict(iteration=iteration, draft_sha256=sha, draft_chars=len(draft),
                          ratio=ratio, within_tolerance=abs(ratio-target) <= tolerance + 1e-12,
                          reviews={})
            state['rounds'].append(record)
            save(output / 'run.json', state)
            # Each reviewer receives the same immutable candidate, never the other's result
            # or writer rationale/previous reviews. Separate processes run concurrently.
            stage = 'reviewers'
            requests = {role: dict(base, role=role, draft=draft, draft_sha256=sha) for role in ROLES}
            for role, req in requests.items():
                save(folder / f'{role}-request.json', req)
            errors = []
            with ThreadPoolExecutor(max_workers=2) as pool:
                jobs = {role: pool.submit(backend, copy.deepcopy(req)) for role, req in requests.items()}
                for role, job in jobs.items():
                    try:
                        reply = validate_reply(job.result(), requests[role])
                        record['reviews'][role] = reply
                        save(folder / f'{role}-response.json', reply)
                    except Exception as exc:
                        errors.append(type(exc).__name__)
                        record['reviews'][role] = {'status': 'error', 'error_type': type(exc).__name__}
            save(output / 'run.json', state)
            if errors:
                raise ValueError('reviewer failure')
            if all(record['reviews'][r]['verdict'] == 'pass' for r in ROLES):
                state['status'] = 'review_pass' if record['within_tolerance'] else 'review_pass_ratio_warning'
                break
            previous = draft
            feedback = [{**issue, 'reviewer': role} for role in ROLES
                        for issue in record['reviews'][role]['issues']]
        else:
            state['status'] = 'unresolved'
        # Candidate can be unresolved; filename deliberately avoids "approved".
        (output / 'candidate.md').write_bytes(draft.encode('utf-8'))
        state['candidate_sha256'] = digest(draft)
    except Exception as exc:
        state.update(status='error', error_stage=stage, error_type=type(exc).__name__)
    save(output / 'run.json', state)
    return state
