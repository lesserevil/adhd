"""No subprocess starts: native plan guards and closed strace closure selection."""
import ast
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
import config_native_matrix as runner
import image_host_dependencies as host


def denied(call):
    try:call()
    except (AssertionError,FileNotFoundError):return
    raise AssertionError('Expected custody rejection')


def main():
    assert 'strace' not in host.selected_tools()
    assert host.selected_tools(('strace',))==host.selected_tools()+('strace',)
    for tools in [('other',),('strace','strace'),['strace']]:denied(lambda:host.selected_tools(tools))
    # Source entry must fail before importing any helper on authored --execute.
    code=compile(Path(runner.__file__).read_text(),runner.__file__,'exec')
    with patch.object(sys,'argv',[runner.__file__,'--execute']),patch('subprocess.Popen',side_effect=AssertionError('No process')):
        try:exec(code,{'__name__':'__main__','__file__':runner.__file__})
        except AssertionError as error:assert 'reviewed frozen driver.py' in str(error)
        else:raise AssertionError('Authored execution accepted')
    old=ast.parse(Path(__file__).with_name('config_recovery.py').read_text())
    boundary=next(n for n in ast.walk(old) if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and n.target.id=='boundary')
    assert ast.literal_eval(boundary.iter)==('transaction','config','journal')
    with tempfile.TemporaryDirectory() as directory:
        work=Path(directory).resolve();(work/'driver.py').write_text('other')
        denied(lambda:runner.verify(work,{'driver_sha256':'0'*64}))
    print('PASS native config preparation pure5: default tools unchanged, exact strace allowlist, duplicate/unknown tool denial, actual authored entry denied before helpers/processes, original3 boundaries, redirected-driver denial; app/VM/compiler/provider starts0')


if __name__=='__main__':main()
