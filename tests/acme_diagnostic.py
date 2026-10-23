#!/usr/bin/env python3
"""Authorized passive diagnostic; original acceptance main/bounds unchanged."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import acme_acceptance
import acme_rebind_acceptance
from acme_runtime import NativeDiagnostic, PublicClient, regular


class StatusRecorder:
    def __init__(self, path):
        self.path = Path(path)
        self.fd = os.open(self.path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
        self.used = 0
        self.started = time.monotonic()
        self.failed = False

    def record(self, event):
        try:
            self._record(event)
        except BaseException:
            self.failed = True

    def _record(self, event):
        # No request, response, URL, header, state or arbitrary exception text.
        raw = json.dumps(event, separators=(',', ':')).encode()+b'\n'
        if self.used + len(raw) > 1_048_576 or time.monotonic()-self.started > 600:
            self.failed = True
            return
        view = memoryview(raw)
        while view:
            written = os.write(self.fd, view)
            if written <= 0: raise OSError("diagnostic write failed")
            view = view[written:]
        self.used += len(raw)

    def invoke(self, original, client, path, data=None, **kwargs):
        if path != '/admin/api' or not isinstance(data, dict) or data.get('op') != 'tls_status':
            return original(client, path, data, **kwargs)
        started = time.monotonic()
        self.record({'event':'start','at_monotonic':started})
        try:
            result = original(client, path, data, **kwargs)
        except BaseException as error:
            self.record({'event':'end','at_monotonic':time.monotonic(),
                         'elapsed':time.monotonic()-started,'exception_type':type(error).__name__})
            raise
        self.record({'event':'end','at_monotonic':time.monotonic(),
                     'elapsed':time.monotonic()-started,'status':result[0]})
        return result

    def close(self):
        os.fsync(self.fd)
        os.close(self.fd)


def main():
    work = Path(sys.argv[sys.argv.index('--work')+1]).resolve()
    assert not work.exists()
    observer = Path(__file__).with_name('acme_passive_observer.exs').resolve()
    regular(observer)
    digest = hashlib.sha256(observer.read_bytes()).hexdigest()
    recorder = StatusRecorder(work.with_name(work.name+'.requests.jsonl'))
    original_request = PublicClient.request
    traces = []

    class ObservedNative(NativeDiagnostic):
        def start(self):
            path = self.root / ('passive-'+str(len(self.identities))+'.jsonl')
            assert not path.exists()
            self.diagnostic_prefix = 'Code.require_file('+json.dumps(str(observer))+'); ACMEPassiveObserver.start('+json.dumps(str(path))+'); '
            self.diagnostic_binding = {'observer_sha256':digest,'trace_path':str(path),'scope':'passive process-info; no app function replacement'}
            traces.append(str(path))
            return super().start()

    def observed_request(client, path, data=None, **kwargs):
        return recorder.invoke(original_request, client, path, data, **kwargs)
    acme_acceptance.NativeDiagnostic = ObservedNative
    acme_rebind_acceptance.NativeDiagnostic = ObservedNative
    PublicClient.request = observed_request
    primary = None
    try:
        acme_acceptance.main()
    except BaseException as error:
        primary = error
        raise
    finally:
        PublicClient.request = original_request
        try:
            recorder.close()
            summary={'schema':'adhd/acme-passive-diagnostic@1','scope':'Diagnostic only; repeating success does not resolve prior07 timeout',
                     'observer_sha256':digest,'recorder_bound_failed':recorder.failed,'traces':[]}
            for name in traces:
                path=Path(name)
                if path.exists():
                    regular(path)
                    summary['traces'].append({'path':name,'bytes':path.stat().st_size,
                      'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
            work.with_name(work.name+'.diagnostic.json').write_text(json.dumps(summary,indent=2)+'\n')
        except BaseException as error:
            if primary: primary.add_note('Diagnostic finalization: '+type(error).__name__)
            else: raise


if __name__=='__main__':main()
