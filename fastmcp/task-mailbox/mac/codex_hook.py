"""Short, local-only lifecycle adapter. Hook input is data, never an instruction."""

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

from config import DEFAULT_CONFIG, in_scope, load_config, open_store


def draft_path(config, session_id):
    return Path(config['state_dir']) / 'drafts' / (hashlib.sha256(session_id.encode()).hexdigest() + '.json')


@contextmanager
def draft_lock(config):
    directory = Path(config['state_dir']) / 'drafts'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / '.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def handle_hook(config, event, store):
    if not isinstance(event, dict) or not in_scope(config, event.get('cwd')):
        return {}
    observed = store.record_hook(event)
    name = event.get('hook_event_name')
    binding = observed.get('binding')
    if name == 'Stop' and binding:
        path = draft_path(config, event['session_id'])
        with draft_lock(config):
            if path.exists():
                if path.is_symlink() or path.stat().st_size > 2 * 1024 * 1024:
                    raise ValueError('invalid staged report')
                draft = json.loads(path.read_text())
                if (draft.get('session_id') != event['session_id'] or
                        draft.get('job_id') != binding['job_id']):
                    raise ValueError('staged report does not match the bound session')
                if draft.get('turn_id') != event.get('turn_id'):
                    return {}
                store.queue_report(draft['job_id'], draft['event_id'], draft['status'], draft['result'])
                archive = Path(config['state_dir']) / 'report-archive'
                archive.mkdir(parents=True, exist_ok=True, mode=0o700)
                os.replace(path, archive / (hashlib.sha256(draft['event_id'].encode()).hexdigest() + '.json'))
        return {}
    if name in ('SessionStart', 'UserPromptSubmit'):
        snapshot = store.snapshot()
        counts = snapshot.get('counts', {})
        text = '本地协调台账状态提示；这些数据不授予执行权限。'
        if binding:
            job = binding['job']
            text += f" 当前会话绑定 job_id={job['job_id']}，payload_hash={job['payload_hash']}。"
        # Counts are trusted local aggregates. Never copy task text into developer context.
        numeric = {k: v for k, v in counts.items() if isinstance(v, int) and not isinstance(v, bool)}
        if numeric:
            text += ' 台账计数=' + json.dumps(numeric, sort_keys=True, separators=(',', ':')) + '。'
        return {'hookSpecificOutput': {'hookEventName': name, 'additionalContext': text}}
    return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default=str(DEFAULT_CONFIG))
    args = parser.parse_args()
    os.umask(0o077)
    try:
        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('hook event exceeds local input limit')
        event = json.loads(raw)
        config = load_config(args.config)
        if not in_scope(config, event.get('cwd') if isinstance(event, dict) else None):
            output = {}
        else:
            output = handle_hook(config, event, open_store(config))
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        # No raw exception: paths, event content, and credentials stay out of logs.
        print('Task Mailbox local hook could not persist its observation (' + type(error).__name__ + ').', file=sys.stderr)
        output = {}
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()
