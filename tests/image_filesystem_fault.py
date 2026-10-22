"""Test-only source-bound scalar observers and retained exact-image VM custody.

Compiling/auditing is host-only. Each observer still requires its own reviewed
actual-image loader/boundary/PID proof before application fault use.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

from container_fixture import OwnedImage
from image_eventing_fault import SCALAR_SYMBOLS, stop_owned_process
from image_eventing_runtime import EventingFaultImage

OBSERVER = '/adhd-test/filesystem-observer.so'
SOURCES = {
    'multi_fault.c': {'exports': {'rename','renameat','renameat2','link','linkat'},
        'prefix': 'ADHD_CRASH_', 'stages': {'before-prepared','before-decided','before-config','after-snapshot','before-completed','transition-decision','transition-project'}},
    'store_move_fault.c': {'exports': {'rename','link','unlink'}, 'prefix': 'ADHD_MOVE_',
        'stages': {'before-decision','after-decision','after-first-snapshot','after-first-checkpoint','before-config','after-config','before-cleanup'}},
    'storage_write_fault.c': {'exports': {'fsync','rename','pwrite','pwrite64'}, 'prefix': 'ADHD_WRITE_',
        'stages': {'snapshot-data-sync','snapshot-install','checkpoint-write','checkpoint-sync'}},
    'project_recovery_fault.c': {'exports': {'rename','fsync','link','unlink'}, 'prefix': 'ADHD_RECOVERY_FAULT_',
        'stages': {'before-stage-snapshot','after-stage-snapshot','before-decision','after-decision','after-decision-sync','after-install-snapshot','after-install-checkpoint','after-route-selected','after-route-ready','after-completion','before-cleanup','after-cleanup'}},
    'rebind_fault.c': {'exports': {'rename','fsync'}, 'prefix': 'ADHD_REBIND_',
        'stages': {'decision-durable','registry-durable','receipt-durable'}},
}
SCALAR_ABI = SCALAR_SYMBOLS | {'access','readlink','strrchr'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compile_observer(source_name, root):
    """Compile unchanged C; audit every ELF independently, without loading it."""
    assert source_name in SOURCES
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    source = Path(__file__).with_name(source_name)
    library = root / 'observer.so'
    argv = ['cc','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC','-nostdlib',
        '-fno-stack-protector','-U_FORTIFY_SOURCE','-D_FORTIFY_SOURCE=0','-O2',str(source),'-o',str(library)]
    subprocess.run(argv, check=True)
    sections = {key: subprocess.check_output(['readelf','-W',flag,str(library)],text=True)
                for key,flag in [('dynamic','-d'),('versions','-V'),('header','-h'),('symbols','--dyn-syms')]}
    assert 'NEEDED' not in sections['dynamic'] and 'GLIBC_' not in sections['versions']
    assert 'Version needs section' not in sections['versions'] and 'GLIBC_' not in sections['symbols']
    assert re.search(r'Machine:\s+Advanced Micro Devices X86-64',sections['header'])
    assert re.search(r'Class:\s+ELF64',sections['header']) and re.search(r'Type:\s+DYN',sections['header'])
    undefined, exports = set(), set()
    for line in sections['symbols'].splitlines():
        parts=line.split()
        if len(parts)<8:continue
        if parts[6]=='UND':undefined.add(parts[7])
        elif parts[3]=='FUNC' and parts[4]=='GLOBAL':exports.add(parts[7])
    assert undefined and undefined <= SCALAR_ABI and not any('__' in name for name in undefined)
    assert exports == SOURCES[source_name]['exports'], 'Unexpected exported ABI'
    report={'schema':'adhd/image-filesystem-observer-elf@1','passed':True,'scope':'Host compiler/readelf only; object never loaded',
        'source':source_name,'source_sha256':sha(source),'library_sha256':sha(library),'compile_argv':argv,
        'elf_machine':'x86_64','elf_class':'ELF64','undefined_scalar_symbols':sorted(undefined),'exported_symbols':sorted(exports),
        'needed_libraries':[],'glibc_symbol_versions':[],
        'section_sha256':{key:hashlib.sha256(value.encode()).hexdigest() for key,value in sections.items()},
        'compiler_version':subprocess.check_output(['cc','--version'],text=True).splitlines()[0],
        'actual_image_loader_qualified':False,'application_started':False,
        'required_actual_image_abi_cases':sorted(exports)}
    (root/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
    return library, report


def validate_observer(image, library, proof, source_name):
    assert source_name in SOURCES and re.fullmatch('sha256:[a-f0-9]{64}',image)
    library, proof = Path(library).absolute(), Path(proof).absolute()
    assert library.resolve(strict=True)==library and proof.resolve(strict=True)==proof
    info=library.lstat()
    assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==os.getuid()
    report=json.loads(proof.read_text());build=report['observer']
    assert report['schema']=='adhd/image-filesystem-observer-probe@1', 'Generic faults require complete source ABI qualification'
    assert report['passed'] is True and report['application_started'] is False and report['owned_container_absent'] is True
    assert report['image_config_identity']==image and report['exit_code']==137
    assert report['actual_musl_loader']=='/lib/ld-musl-x86_64.so.1'
    assert build['source_sha256']==sha(Path(__file__).with_name(source_name)) and build['library_sha256']==sha(library)
    assert build['needed_libraries']==build['glibc_symbol_versions']==[]
    assert set(build['undefined_scalar_symbols'])<=SCALAR_ABI
    assert report['process_custody']['signal_method']=='ancestor-pidfd-SIGSTOP'
    assert report['process_custody']['kernel_state']=='stopped'
    # A rename-only historical Eventing proof cannot qualify migration's link,
    # linkat or renameat paths, even when the source/library bytes are identical.
    assert set(build['exported_symbols'])==SOURCES[source_name]['exports']
    assert set(report['successful_abi_cases'])==SOURCES[source_name]['exports']
    return library, report


def instrument_argv(base, library, source_name, environment):
    assert base[:2]==['docker','run'] and '--rm' in base
    assert re.fullmatch('sha256:[a-f0-9]{64}',base[-1])
    assert not any(value=='--pid' or value.startswith('--pid=') for value in base)
    assert source_name in SOURCES and ',' not in str(library)
    prefix=SOURCES[source_name]['prefix']
    assert environment[prefix+'STAGE'] in SOURCES[source_name]['stages']
    assert all(key.startswith(prefix) and isinstance(value,str) and '\0' not in value for key,value in environment.items())
    result=list(base);result.remove('--rm')
    result=result[:-1]+['--mount','type=bind,src='+str(library)+',dst='+OBSERVER+',readonly','--env','LD_PRELOAD='+OBSERVER]+[
        item for key,value in sorted(environment.items()) for item in ('--env',key+'='+value)]+result[-1:]
    return result


class RetainedImage(OwnedImage):
    """Reuse reviewed hard-kill/wait137/removal semantics without an observer."""
    stop=EventingFaultImage.stop
    authoritative_absence=staticmethod(EventingFaultImage.authoritative_absence)

    def __init__(self,image,manifest,root):
        assert re.fullmatch('sha256:[a-f0-9]{64}',image)
        super().__init__(image,manifest,root)
        self.armed=False;self.last_exit_code=None

    def identity(self):
        result=super().identity()
        result['cleanup_blocked']=getattr(self,'cleanup_blocked',False)
        return result

    def argv(self,config_file):
        assert not getattr(self,'cleanup_blocked',False), 'Prior owned cleanup remains unconfirmed'
        result=super().argv(config_file);result.remove('--rm');return result


class FilesystemFaultImage(RetainedImage):
    def __init__(self,image,manifest,root,source_name,library,proof,environment):
        super().__init__(image,manifest,root)
        self.source_name=source_name
        self.library,self.proof=validate_observer(image,library,proof,source_name)
        self.library_sha256=sha(self.library);self.proof_sha256=sha(proof)
        self.environment=dict(environment);self.stage=environment[SOURCES[source_name]['prefix']+'STAGE']
        self.config_file=None;self.custody=[];self.armed=True

    def argv(self,config_file):
        assert not getattr(self,'cleanup_blocked',False), 'Prior owned cleanup remains unconfirmed'
        self.config_file=Path(config_file)
        # Call original to retain --rm until the pure instrumentation checks it.
        base=OwnedImage.argv(self,config_file)
        if not self.armed:base.remove('--rm');return base
        assert sha(self.library)==self.library_sha256
        assert self.proof['canonical_manifest_sha256']==hashlib.sha256(self.manifest_bytes).hexdigest()
        assert self.proof['artifact_sha256']==self.manifest['files']['hub.exs']
        return instrument_argv(base,self.library,self.source_name,self.environment)

    def stop_at_observed_boundary(self,trace):
        assert self.armed and trace['stage']==self.stage and trace['pid']==1
        self.observe();row=json.loads(self.docker('inspect',self.name).stdout)[0]
        mount=next(v for v in row['Mounts'] if v['Destination']==OBSERVER)
        assert mount['Source']==str(self.library) and mount['Type']=='bind' and mount['RW'] is False
        assert sha(self.library)==self.library_sha256
        custody=stop_owned_process(row['Id'],self.image_id,trace,OBSERVER,'beam.smp',
            ['/app/hub.exs',json.dumps(['serve',str(self.config_file)])])
        self.custody.append({'container_id':row['Id'],'source':self.source_name,'stage':self.stage,
            'observer_sha256':self.library_sha256,**custody})
        return custody

    def identity(self):
        result=super().identity()
        result.update(observer_source=self.source_name,observer_library_sha256=self.library_sha256,
            observer_loader_proof_sha256=self.proof_sha256,actual_beam_kernel_custody=self.custody,
            observer_disarmed_after_kill=not self.armed)
        return result


def fault_arguments(parser, *, artifact=False):
    parser.add_argument('--image-fault-library',type=Path)
    parser.add_argument('--image-fault-proof',type=Path)
    if artifact:parser.add_argument('--image-artifact',type=Path,help='Hash binding/source identities only; never executed as target')


def target_artifact(args):
    if not args.image:return args.hub
    assert args.image_manifest and args.image_artifact
    manifest=json.loads(args.image_manifest.read_text())
    assert sha(args.image_artifact)==manifest['files']['hub.exs']
    return args.image_artifact


def fault_image(args,root,source,environment):
    assert args.image and args.image_manifest and args.image_fault_library and args.image_fault_proof
    return FilesystemFaultImage(args.image,args.image_manifest,root,source,args.image_fault_library,args.image_fault_proof,environment)
