"""Pure observer gate/argv/native-assertion checks; no observer loading or Docker."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from container_fixture import OwnedImage
from image_filesystem_fault import SOURCES, FilesystemFaultImage, RetainedImage, instrument_argv, validate_observer, sha

IMAGE='sha256:'+'a'*64


def denied(call):
    try:call()
    except (AssertionError,KeyError,ValueError):return
    raise AssertionError('Invalid source/runtime proof admitted')


class Native(ast.NodeTransformer):
    def visit_Attribute(self,node):
        if isinstance(node.value,ast.Name) and node.value.id=='args' and node.attr=='image':return ast.Constant(False)
        return self.generic_visit(node)
    def visit_IfExp(self,node):
        node=self.generic_visit(node)
        if isinstance(node.test,ast.Constant):return node.body if node.test.value else node.orelse
        return node


def native_assertions(before,after):
    # This is a preparation guard, not proof of all native runtime behavior.
    original=ast.parse(before);current=Native().visit(ast.parse(after))
    observed={ast.dump(n,include_attributes=False) for n in ast.walk(current) if isinstance(n,ast.Assert)}
    expected={ast.dump(n,include_attributes=False) for n in ast.walk(original) if isinstance(n,ast.Assert)}
    assert expected<=observed, 'An original native assertion changed or disappeared'
    return len(expected)


def main():
    starts=[]
    def forbidden(*args,**kwargs):starts.append('attempt');raise AssertionError('No process allowed')
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory).resolve();lib=root/'observer.so';lib.write_bytes(b'synthetic unexecutable unit fixture')
        manifest=root/'manifest.json';manifest.write_text(json.dumps({'schema':'adhd/container-inputs@1','files':{'hub.exs':'b'*64}}))
        proof=root/'proof.json'
        source='store_move_fault.c'
        def write_proof(**changes):
            report={'schema':'adhd/image-filesystem-observer-probe@1','passed':True,'application_started':False,
                'owned_container_absent':True,'image_config_identity':IMAGE,'exit_code':137,
                'actual_musl_loader':'/lib/ld-musl-x86_64.so.1','artifact_sha256':'b'*64,
                'canonical_manifest_sha256':sha(manifest),
                'observer':{'source_sha256':sha(Path(__file__).with_name(source)),'library_sha256':sha(lib),
                    'needed_libraries':[],'glibc_symbol_versions':[],'undefined_scalar_symbols':['dlsym'],
                    'exported_symbols':sorted(SOURCES[source]['exports'])},
                'process_custody':{'signal_method':'ancestor-pidfd-SIGSTOP','kernel_state':'stopped'},
                'successful_abi_cases':sorted(SOURCES[source]['exports'])}
            report.update(changes);proof.write_text(json.dumps(report));return report
        env={'ADHD_MOVE_STAGE':'after-decision','ADHD_MOVE_CONFIG':str(root/'hub.json'),
             'ADHD_MOVE_TARGET':str(root/'moved.dets'),'ADHD_MOVE_SENTINEL':str(root/'sentinel.json')}
        base=['docker','run','--rm','--read-only','--name','synthetic-owned-name',IMAGE]
        with patch('subprocess.Popen',forbidden),patch('subprocess.run',forbidden),patch('subprocess.check_output',forbidden):
            good=write_proof();validate_observer(IMAGE,lib,proof,source)
            denied(lambda:validate_observer(IMAGE,lib,proof,'storage_write_fault.c'))
            write_proof(schema='adhd/image-filesystem-observer-elf@1');denied(lambda:validate_observer(IMAGE,lib,proof,source))
            write_proof(successful_abi_cases=['rename']);denied(lambda:validate_observer(IMAGE,lib,proof,source))
            bad=copy.deepcopy(good);bad['observer']['undefined_scalar_symbols']=['stat'];proof.write_text(json.dumps(bad));denied(lambda:validate_observer(IMAGE,lib,proof,source))
            write_proof(image_config_identity='sha256:'+'c'*64);denied(lambda:validate_observer(IMAGE,lib,proof,source))
            source='multi_fault.c'
            write_proof(schema='adhd/image-observer-loader-probe@1',successful_abi_cases=['rename'])
            denied(lambda:validate_observer(IMAGE,lib,proof,source))
            write_proof(successful_abi_cases=['rename'])
            denied(lambda:validate_observer(IMAGE,lib,proof,source))
            write_proof();validate_observer(IMAGE,lib,proof,source)
            source='store_move_fault.c'
            write_proof();obj=FilesystemFaultImage(IMAGE,manifest,root,source,lib,proof,env)
            with patch.object(OwnedImage,'argv',return_value=base):
                instrumented=obj.argv(root/'hub.json')
                assert '--rm' not in instrumented and 'LD_PRELOAD=/adhd-test/filesystem-observer.so' in instrumented
                assert any('dst=/adhd-test/filesystem-observer.so,readonly' in value for value in instrumented)
                obj.armed=False
                cold=obj.argv(root/'hub.json');assert '--rm' not in cold and not any('LD_PRELOAD=' in value for value in cold)
            for changed in (base[:-1]+['--pid=host',IMAGE],):
                denied(lambda:instrument_argv(changed,lib,source,env))
            denied(lambda:instrument_argv(base,lib,source,{**env,'LD_PRELOAD':'other'}))
        # Exercise real lifecycle logic using a recording Docker transport only.
        owned=RetainedImage(IMAGE,manifest,root)
        owned.image_id=IMAGE;owned.verified=True;owned.name='synthetic-name';owned.container_id='f'*64
        calls=[];state={'running':True,'exists':True}
        def docker(*args,check=True):
            calls.append(args)
            if args[0]=='inspect':
                if not state['exists']:return SimpleNamespace(returncode=1,stdout=b'',stderr=('No such container: '+args[1]).encode())
                row={'Id':'f'*64,'Image':IMAGE,'State':{'Running':state['running'],'ExitCode':137,'Pid':1000}}
                return SimpleNamespace(returncode=0,stdout=json.dumps([row]).encode(),stderr=b'')
            if args[0]=='kill':state['running']=False
            if args[0]=='rm':state['exists']=False
            return SimpleNamespace(returncode=0,stdout=b'137\n' if args[0]=='wait' else b'',stderr=b'')
        owned.docker=docker
        with patch('subprocess.Popen',forbidden),patch('subprocess.run',forbidden):owned.stop(hard=True)
        assert ('kill','--signal','KILL','f'*64) in calls and ('wait','f'*64) in calls and ('rm','f'*64) in calls
        assert owned.name is None and owned.last_exit_code==137 and owned.events[-1]['observed_absent']
    assert not starts
    print('PASS image filesystem11: source binding, build-only denial, complete ABI cases, scalar whitelist, image binding, readonly observer, retained container, disarmed cold replacement, PID/env denial, exact-ID kill/wait137/remove custody, full multi-source ABI closure; process attempts0')


if __name__=='__main__':main()
