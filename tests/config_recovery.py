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
from config_image_runtime import ConfigurationFaultRuntime
from image_filesystem_fault import fault_arguments, target_artifact


def configuration_rename_after(trace, target, offset):
    """Only observe renames emitted after the reviewed mutation was armed."""
    assert type(offset) is int and offset >= 0
    if not trace.exists():
        return False
    raw = trace.read_bytes()
    assert len(raw) >= offset, 'Configuration syscall trace was truncated'
    return ('", "' + target + '"').encode() in raw[offset:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--command')
    target.add_argument('--image')
    parser.add_argument('--image-manifest', type=Path)
    fault_arguments(parser, artifact=True)
    parser.add_argument('--report', default='verification/config-recovery.json')
    parser.add_argument('--protocol-version', type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    command = json.loads(args.command) if args.command else None
    if not args.image:
        assert shutil.which('strace'), 'Linux strace is required for syscall-boundary fault injection'
    artifact = target_artifact(args) if args.image else Path(command[-1])
    parent = Path('_build/roadmap/config-recovery').resolve()
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='run-', dir=parent))
    cases = []
    runtimes = []
    for boundary in ('transaction', 'config', 'journal'):
        trace = root / (boundary + '.trace')
        # Delay syscall return so an external observer can kill the process at a
        # real filesystem transition. No application hook or fake persistence.
        if args.image:
            runtime = ConfigurationFaultRuntime(root / boundary, args, boundary)
        else:
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
            initial_revision = runtime.config['config_revision']
            publication = agent.rpc({'op': 'publish', 'text': 'Original survives every commit boundary.'}, token, mid='durable-original')['publication']
            patch = {'port': new_port,
                     'store_path': str(new_store), 'threshold_ppm': 777777}
            if args.protocol_version == 1:
                patch['project_id'] = 'after-crash'
            request = {'op': 'config_update', 'patch': patch, 'expected_revision': initial_revision,
                       'confirm': True, 'message_id': 'crash-change'}
            def mutate():
                try: Client(runtime, admin_token).api(request)
                except Exception as error: failures.append(type(error).__name__)
            # Bootstrap, explicit fixture admission and the initial publication
            # must never satisfy the configuration mutation's boundary witness.
            trace_offset = trace.stat().st_size if trace.exists() else 0
            if args.image:
                runtime.arm_mutation()
            thread = threading.Thread(target=mutate, daemon=True); thread.start()
            target = str(runtime.file) + {'transaction': '.transaction', 'config': '', 'journal': '.journal'}[boundary]
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                if (runtime.observe_boundary() if args.image else configuration_rename_after(trace, target, trace_offset)): break
                time.sleep(.01)
            else: raise AssertionError('Expected configuration rename boundary was not reached: ' + boundary)
            runtime.stop(hard=True); thread.join(timeout=16)
            assert not thread.is_alive(), 'Lost-response client failed to stop'
            if not args.image:
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
                assert runtime.config['config_revision'] == initial_revision + 1
            assert not Path(str(runtime.file) + '.transaction').exists()
            cases.append({'case': 'kill-at-' + boundary + '-rename', 'passed': True,
                          'recovered': 'new' if is_new else 'old',
                          'mutation_trace_offset': trace_offset,
                          'trace_sha256': hashlib.sha256((runtime.sentinel if args.image else trace).read_bytes()).hexdigest()})
            print('PASS', cases[-1]['case'], flush=True)
        finally:
            runtime.stop()
            if args.image:
                runtimes.append(runtime.image_runtime.identity())
    Path(args.report).write_text(json.dumps({'schema': 'adhd/config-recovery@1', 'passed': True,
        'artifact_sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(), 'cases': cases,
        'runtime': runtimes if args.image else None}, indent=2) + '\n')


if __name__ == '__main__': main()
