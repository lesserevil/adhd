#!/usr/bin/env python3
"""Black-box process-kill recovery at real configuration file rename boundaries."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
from foundation_acceptance import Runtime, Client, free_port


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--command', required=True)
    parser.add_argument('--report', default='verification/config-recovery.json')
    parser.add_argument('--protocol-version', type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    command = json.loads(args.command)
    assert shutil.which('strace'), 'Linux strace is required for syscall-boundary fault injection'
    parent = Path('_build/roadmap/config-recovery').resolve()
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='run-', dir=parent))
    cases = []
    for boundary in ('transaction', 'config', 'journal'):
        trace = root / (boundary + '.trace')
        # Delay syscall return so an external observer can kill the process at a
        # real filesystem transition. No application hook or fake persistence.
        traced = ['strace', '-f', '-e', 'trace=rename', '-e',
                  'inject=rename:delay_exit=2s', '-o', str(trace)] + command
        runtime = Runtime(root / boundary, traced)
        old_port, new_port = free_port(), free_port()
        token, admin_token = 'independent-agent-credential-0001', 'independent-administrator-credential-0001'
        old_store, new_store = runtime.root / 'old.dets', runtime.root / 'new.dets'
        original = {'project_id': 'before-crash', 'port': old_port,
                    'store_path': str(old_store), 'agents': {'writer': token},
                    'admin_token': admin_token,
                    'matcher': {'url': 'http://127.0.0.1:1/v1/systemone', 'model': 'Nemotron-Deciffusion-8B-v2.1'}}
        runtime.file.write_text(json.dumps(original)); runtime.file.chmod(0o600)
        failures = []
        try:
            runtime.start()
            agent = Client(runtime)
            publication = agent.rpc({'op': 'publish', 'text': 'Original survives every commit boundary.'}, token, mid='durable-original')['publication']
            patch = {'port': new_port,
                     'store_path': str(new_store), 'threshold_ppm': 777777}
            if args.protocol_version == 1:
                patch['project_id'] = 'after-crash'
            request = {'op': 'config_update', 'patch': patch, 'expected_revision': 1,
                       'confirm': True, 'message_id': 'crash-change'}
            def mutate():
                try: Client(runtime, admin_token).api(request)
                except Exception as error: failures.append(type(error).__name__)
            thread = threading.Thread(target=mutate, daemon=True); thread.start()
            target = str(runtime.file) + {'transaction': '.transaction', 'config': '', 'journal': '.journal'}[boundary]
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                if trace.exists() and ('", "' + target + '"') in trace.read_text(): break
                time.sleep(.01)
            else: raise AssertionError('Expected configuration rename boundary was not reached: ' + boundary)
            runtime.stop(hard=True); thread.join(timeout=16)
            assert not thread.is_alive(), 'Lost-response client failed to stop'
            runtime.command = command
            runtime.start()
            config = runtime.config
            is_new = config['port'] == new_port
            # Profile 2 project IDs are immutable. Display-name changes have
            # their own project transaction tests; this transaction moves the
            # listener and all stores without changing the default identity.
            assert config['project_id'] == ('after-crash' if is_new and args.protocol_version == 1 else 'before-crash')
            assert config['port'] == (new_port if is_new else old_port)
            assert config['store_path'] == str(new_store if is_new else old_store)
            assert config.get('threshold_ppm', 900000) == (777777 if is_new else 900000)
            client = Client(runtime, admin_token)
            assert Client(runtime).rpc({'op': 'publish', 'text': 'Original survives every commit boundary.'}, token, mid='durable-original')['publication'] == publication
            fetched = Client(runtime).rpc({'op': 'get', 'publication_id': publication['id']}, token)['publication']
            assert fetched['text'] == publication['text'] and fetched['project_id'] == config['project_id']
            if is_new:
                assert client.api(request)['applied'] is True
                assert runtime.config['config_revision'] == 2
            assert not Path(str(runtime.file) + '.transaction').exists()
            cases.append({'case': 'kill-at-' + boundary + '-rename', 'passed': True,
                          'recovered': 'new' if is_new else 'old'})
            print('PASS', cases[-1]['case'], flush=True)
        finally: runtime.stop()
    Path(args.report).write_text(json.dumps({'schema': 'adhd/config-recovery@1', 'passed': True,
        'artifact_sha256': hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest(), 'cases': cases}, indent=2) + '\n')


if __name__ == '__main__': main()
