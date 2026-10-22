"""Pure same-state public bootstrap/traced-order and failure-report guards."""
import ast
from pathlib import Path
import tempfile
from config_recovery import start_native_after_public_bootstrap
from config_native_matrix import completed_result


def main():
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);file=root/'config';file.write_bytes(b'original')
        command=['elixir','target'];traced=['strace','-e','inject=rename:delay_exit=2s',*command];events=[]
        class Runtime:
            def __init__(self):self.command=traced;self.file=file;self.root=root
            def start(self):
                events.append(('start',self.command[:],self.file.read_bytes(),id(self)))
                if self.command==command:self.file.write_bytes(b'public admitted actual-state witness')
                else:assert self.file.read_bytes()==b'public admitted actual-state witness'
            def stop(self):events.append(('graceful-stop',self.command[:],self.file.read_bytes(),id(self)))
        runtime=Runtime();start_native_after_public_bootstrap(runtime,command,traced)
        assert [e[0]for e in events]==['start','graceful-stop','start']
        assert [e[1]for e in events]==[command,command,traced] and all(e[3]==id(runtime) for e in events)
        assert events[1][2]==events[2][2] and runtime.file==file
        try:completed_result(root,1)
        except AssertionError as error:assert 'known exit' in str(error)
        else:raise AssertionError('Failed child parsed missing result')
        try:completed_result(root,0)
        except FileNotFoundError:pass
        else:raise AssertionError('Successful child missing report admitted')
        (root/'result.json').write_text('{"passed":true}');assert completed_result(root,0)=={'passed':True}
    source=Path(__file__).with_name('config_recovery.py').read_text();tree=ast.parse(source)
    assert 'inject=rename:delay_exit=2s' in source and 'time.monotonic() + 25' in source and 'thread.join(timeout=16)' in source
    assert 'if args.image:runtime.start()\n            else:start_native_after_public_bootstrap' in source
    assert "trace_offset = trace.stat().st_size" in source and "publication = agent.rpc" in source and source.index('trace_offset = trace.stat().st_size')>source.index('publication = agent.rpc')
    print('PASS native bootstrap pure6: actual helper sameRuntime/state untracedpublicstart→gracefulstop→tracedstart, no baselinepublication beforetrace, unchangedimagebranch/25-16-2bounds/offsetorder, knownnonzero beforemissingreport, successful-report contract; actual app/VM/compiler starts0')


if __name__=='__main__':main()
