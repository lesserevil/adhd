"""Minimal real Python interpreters prove bytecode-read isolation; no apps/VMs."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import py_compile
import subprocess
import sys
import tempfile
from unittest.mock import patch


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary).resolve();source=root/'source';source.mkdir();module=source/'vector.py'
        module.write_text("VALUE='source'\n");alternate=root/'alternate.py';alternate.write_text("VALUE='cached'\n")
        assert module.stat().st_size==alternate.stat().st_size
        os.utime(alternate,ns=(module.stat().st_atime_ns,module.stat().st_mtime_ns))
        cache=Path(importlib.util.cache_from_source(str(module)));cache.parent.mkdir()
        py_compile.compile(str(alternate),cfile=str(cache),dfile=str(module),doraise=True)
        expression='import sys;sys.path.insert(0,'+repr(str(source))+');import vector;print(vector.VALUE);print(sys.pycache_prefix)'
        base=[sys.executable,'-I','-S','-B'];calls=[]
        def run(argv):
            result=subprocess.run(argv,capture_output=True,text=True,env={**os.environ,'PYTHONPYCACHEPREFIX':str(root/'ignored-env')},timeout=15)
            calls.append({'exit_code':result.returncode,'stdout':result.stdout.strip(),'stderr_type':'assertion' if 'AssertionError' in result.stderr else None})
            return result
        control=run(base+['-c',expression]);assert control.returncode==0 and control.stdout.splitlines()[0]=='cached','Control must prove -B reads existing unbound cache'
        prefix=root/'fresh-cache';prefix.mkdir(mode=0o700)
        isolated=run(base+['-X','pycache_prefix='+str(prefix),'-c',expression])
        assert isolated.returncode==0 and isolated.stdout.splitlines()==['source',str(prefix)] and not list(prefix.iterdir())
        # Execute only the actual builtin-only staged guard prefix, never the
        # driver/fixtures/imports after its first argparse statement.
        code=Path(__file__).with_name('image_recovery_remaining_matrix.py').read_text().split('\nimport argparse\n',1)[0]
        work=root/'staged';work.mkdir();parent=work/'parent-cache';parent.mkdir(mode=0o700)
        guard='exec('+repr(code)+',{"__file__":'+repr(str(work/'driver.py'))+',"__name__":"review_only"})'
        success=run(base+['-X','pycache_prefix='+str(parent),'-c',guard]);assert success.returncode==0
        for flags in [base, [sys.executable,'-I','-S','-X','pycache_prefix='+str(parent)],base+['-X','pycache_prefix='+str(prefix)]]:
            assert run(flags+['-c',guard]).returncode!=0
        (parent/'stale.pyc').write_bytes(b'cache');assert run(base+['-X','pycache_prefix='+str(parent),'-c',guard]).returncode!=0
        assert calls[0]['stdout'].startswith('cached') and calls[1]['stdout'].startswith('source')
        print(json.dumps({'passed':True,'minimal_python_interpreters':len(calls),'unbound_cache_control_loaded':True,
            'fresh_cli_prefix_source_loaded':True,'parent_guard_correct_flags_pass':True,'missing_B_or_X_wrong_prefix_stale_cache_denied':True,
            'test_bytecode_fixture_created':True,'applications_external_compilers_elixir_vms_containers_providers':0},sort_keys=True))


if __name__=='__main__':main()
