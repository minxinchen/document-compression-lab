"""Author: Nio (Master). Python 3.10+; no third-party dependencies."""
import argparse
import json
from pathlib import Path
from core import CommandBackend, run


def main():
    p = argparse.ArgumentParser(description='Compress with two independently bound reviews.')
    p.add_argument('source', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--target', type=float, default=.65)
    p.add_argument('--tolerance', type=float, default=.03)
    p.add_argument('--max-iterations', type=int, default=5)
    args = p.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding='utf-8'))
        backend = CommandBackend(config['commands'], config.get('timeout_seconds', 180))
        state = run(args.source, args.out, backend, target=args.target, tolerance=args.tolerance,
                    max_iterations=args.max_iterations,
                    execution_kind=config.get('execution_kind', 'live'),
                    backend_label=config.get('label', 'configured-command'))
    except (ValueError, OSError, KeyError) as exc:
        p.exit(2, f'Input/configuration error: {type(exc).__name__}\n')
    print(json.dumps({'status': state['status'], 'execution_kind': state['execution_kind'],
                      'rounds': len(state['rounds']), 'output': str(args.out)}, ensure_ascii=False))
    return 0 if state['status'] == 'review_pass' else 3 if state['status'] == 'review_pass_ratio_warning' else 2


if __name__ == '__main__':
    raise SystemExit(main())
