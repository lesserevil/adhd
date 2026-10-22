"""Pure closure drift/alias/import/environment guards; no host queries or VMs."""
from pathlib import Path
import tempfile
from unittest.mock import patch
import image_host_dependencies as closure


def denied(call):
    try:call()
    except (AssertionError,FileNotFoundError):return
    raise AssertionError('Dependency drift was accepted')


def main():
    with tempfile.TemporaryDirectory() as directory,patch('subprocess.run',side_effect=AssertionError('No real host query')):
        root=Path(directory).resolve();source=root/'source';source.mkdir();file=source/'module.py';file.write_text('version1')
        alias=source/'alias.py';alias.symlink_to('module.py');internal=source/'nested';internal.mkdir();(source/'directory').symlink_to('nested',target_is_directory=True)
        roots=[source];expected=closure.tree_inventory(source,roots);closure.verify_tree(expected,roots)
        file.write_text('version2');denied(lambda:closure.verify_tree(expected,roots));file.write_text('version1')
        alias.unlink();alias.symlink_to(file);denied(lambda:closure.verify_tree(expected,roots));alias.unlink();alias.symlink_to('module.py')
        added=source/'shadow.py';added.write_text('shadow');denied(lambda:closure.verify_tree(expected,roots));added.unlink()
        outside=root/'outside';outside.mkdir();(source/'escape').symlink_to(outside,target_is_directory=True)
        denied(lambda:closure.tree_inventory(source,roots));(source/'escape').unlink()
        stamp=closure.path_binding(alias);closure.verify_path(stamp);mode=file.stat().st_mode & 0o777
        file.chmod(mode ^ 0o100);denied(lambda:closure.verify_path(stamp));file.chmod(mode)
        missing=closure.presence(source/'absent.py');(source/'absent.py').write_text('shadow')
        assert closure.presence(source/'absent.py')!=missing;(source/'absent.py').unlink()
        (source/'__pycache__').mkdir();(source/'__pycache__/ignored.pyc').write_bytes(b'cache')
        closure.verify_tree(expected,roots) # only excluded with the explicit cache environment below
        env=closure.child_environment({'ERL_FLAGS':'+S 2:2','PYTHONPATH':'evil','LD_PRELOAD':'evil'},
            {'native_path':'/owned/erlang/bin:/owned/elixir/bin:/usr/bin:/bin'},root/'bound',root/'runtime/cache',Path('/private/docker.sock'))
        assert env['PYTHONNOUSERSITE']=='1' and env['PYTHONDONTWRITEBYTECODE']=='1' and env['PYTHONPYCACHEPREFIX']==str(root/'runtime/cache')
        assert env['DOCKER_HOST']=='unix:///private/docker.sock' and 'PYTHONPATH' not in env and 'LD_PRELOAD' not in env and 'GCC_EXEC_PREFIX' not in env and 'ERL_LIBS' not in env
        assert closure.elf_inputs(file) is None
        malformed=root/'bad-elf';malformed.write_bytes(b'\x7fELF'+b'\0'*100);denied(lambda:closure.elf_inputs(malformed))
        actual=closure.elf_inputs('/usr/bin/true');assert actual['interpreter'].startswith('/') and 'libc.so.6' in actual['needed']
        object_file=closure.elf_inputs('/usr/lib/x86_64-linux-gnu/crti.o');assert object_file=={'interpreter':None,'needed':[],'search':[]}
        for command in [['cc','source.c'],['gcc','-shared','source.c'],['ldconfig'],['/usr/bin/true'],['/usr/bin/true','-print-file-name=libc.so']]:denied(lambda:closure.metadata(command))
    print('PASS host dependency pure12: fullSET/content/mode/filealias/directoryescape drift, precedence appearance, explicit isolated-cache policy, sanitized Python/compiler/Elixir/Docker env, actual ELF metadata parse/malformed denial, hostquery no-compile allowlist; real hostqueries/compiler/VM/provider calls0')


if __name__=='__main__':main()
