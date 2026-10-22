"""Prospective sealed optimizer runtime custody. Constructors never start a hub.

Separate from NativeFixture: image startup and cleanup use actual OwnedImage.
No provider client lives here. A refusing local guard is the only model endpoint
allowed during structural preflight. Public APIs, never private state rewriting,
create image originals and verify both runtimes' closed inputs.
"""
import asyncio
import ast
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import threading
import time
from urllib.parse import urlsplit

import httpx

from multi_support import Fixture


class CustodyViolation(AssertionError):pass
class ExperimentFailed(AssertionError):pass
class ProviderUnavailable(RuntimeError):pass
class RuntimeUnavailable(RuntimeError):pass


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def regular(path,*,private=True):
    info=path.lstat()
    if not (stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==os.getuid()):
        raise CustodyViolation('Expected owned unlinked regular input')
    if private and info.st_mode & 0o077:raise CustodyViolation('Private input permissions changed')
    return info


def safe_append(path,*,require_new=False,expected=None):
    """Open only the validated owned inode, never a symlink/replaced log."""
    path=Path(path)
    private=expected is not None or require_new
    try:before=regular(path,private=private)
    except FileNotFoundError:before=None
    if require_new and before is not None:raise CustodyViolation('Log must be newly created')
    if expected is not None and (before is None or (before.st_dev,before.st_ino)!=expected):
        raise CustodyViolation('Log inode replaced')
    flags=os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW|os.O_CLOEXEC
    if before is None:flags|=os.O_CREAT|os.O_EXCL
    fd=os.open(path,flags,0o600)
    try:
        opened=os.fstat(fd);after=regular(path,private=private)
        identity=(opened.st_dev,opened.st_ino)
        if not (stat.S_ISREG(opened.st_mode) and opened.st_nlink==1 and opened.st_uid==os.getuid()):
            raise CustodyViolation('Opened log metadata changed')
        if identity!=(after.st_dev,after.st_ino) or (before is not None and identity!=(before.st_dev,before.st_ino)):
            raise CustodyViolation('Log changed during open')
        return os.fdopen(fd,'ab',buffering=0)
    except BaseException:
        os.close(fd);raise


def log_digest(path,expected):
    before=regular(path)
    if (before.st_dev,before.st_ino)!=expected:raise CustodyViolation('Provider log replaced before hashing')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        info=os.fstat(fd)
        if (info.st_dev,info.st_ino)!=expected:raise CustodyViolation('Provider log changed during hash open')
        result=hashlib.sha256();size=0
        while True:
            block=os.read(fd,65536)
            if not block:break
            size+=len(block)
            if size>268435456:raise CustodyViolation('Provider log exceeds bounded106-exchange allowance')
            result.update(block)
        after=regular(path)
        if (after.st_dev,after.st_ino)!=expected:raise CustodyViolation('Provider log replaced during hashing')
        return result.hexdigest()
    finally:os.close(fd)


def append_held_log(handle,path,expected,raw):
    """Write through the retained owned inode only while its path still binds."""
    current=regular(path);opened=os.fstat(handle.fileno())
    if ((current.st_dev,current.st_ino)!=expected or (opened.st_dev,opened.st_ino)!=expected
            or opened.st_nlink!=1 or opened.st_uid!=os.getuid() or opened.st_mode & 0o077):
        raise CustodyViolation('Provider log binding changed before append')
    if handle.write(raw)!=len(raw):raise OSError('Short provider-log write')
    after=regular(path)
    if (after.st_dev,after.st_ino)!=expected:raise CustodyViolation('Provider log binding changed during append')


def private_seal(root):
    """Hash closed private inputs; logs are observation output, not source state."""
    root=Path(root)
    info=root.lstat()
    assert stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid() and not info.st_mode & 0o077
    result={}
    for current, directories, files in os.walk(root, followlinks=False):
        for name in directories:
            path=Path(current)/name;info=path.lstat()
            assert stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid() and not info.st_mode & 0o077
        for name in sorted(files):
            if name in ('stdout.log','stderr.log'):
                regular(Path(current)/name,private=False)
                continue
            # An interrupted snapshot write in the ORIGINAL accepted fixture
            # can leave a nonauthoritative temporary file with umask modes.
            # Preserve its exact bytes/mode inside the owner-only directory;
            # never select, delete or chmod it as part of qualification.
            temporary=bool(re.fullmatch(r'state\.dets\.snapshot\.tmp-[A-Za-z0-9_-]+',name))
            path=Path(current)/name;info=regular(path,private=not temporary)
            result[str(path.relative_to(root))]={'sha256':sha(path.read_bytes()),'bytes':info.st_size,'mode':stat.S_IMODE(info.st_mode)}
    assert 'hub.json' in result and 'hub.json.stores' in result and 'hub.json.stores.marker' in result
    return dict(sorted(result.items()))


def verify_seal(root, seal):
    assert private_seal(root)==seal, 'Closed fixture changed after its model-free seal'


def python_pins(entries):
    """Pin transitive repository-local Python imports, including inner imports."""
    folder=Path(__file__).parent;pending=list(entries);pins={}
    while pending:
        name=pending.pop()
        if name in pins:
            continue
        path=folder/name;raw=path.read_bytes();pins[name]=sha(raw)
        for node in ast.walk(ast.parse(raw)):
            names=[node.module] if isinstance(node,ast.ImportFrom) else [v.name for v in node.names] if isinstance(node,ast.Import) else []
            for imported in names:
                if imported and '.' not in imported and (folder/(imported+'.py')).is_file():
                    pending.append(imported+'.py')
    return dict(sorted(pins.items()))


def verify_pins(pins):
    assert pins and 'optimization_validation.py' in pins and 'optimization_provider_io.py' in pins
    for name,digest in pins.items():
        assert Path(name).name==name and name.endswith('.py')
        assert sha(Path(__file__).with_name(name).read_bytes())==digest, 'Reviewed Python dependency changed'


def validate_target(target, artifact):
    """Pure file/shape checks: no Docker inspection or startup on check-plan."""
    assert target['kind'] in ('native','image')
    assert re.fullmatch('[a-f0-9]{32}',target['server_id'])
    assert isinstance(target['artifact_sha256'],str) and re.fullmatch('[a-f0-9]{64}',target['artifact_sha256'])
    assert Path(target['fixture_root']).is_absolute() and '..' not in Path(target['fixture_root']).parts
    assert sha(Path(artifact).read_bytes())==target['artifact_sha256']
    parsed=urlsplit(target['broker_rest_url'])
    assert parsed.scheme=='http' and parsed.hostname=='127.0.0.1' and parsed.port and parsed.path in ('','/') and not parsed.username
    if target['kind']=='image':
        assert re.fullmatch('sha256:[a-f0-9]{64}',target['image_config_identity'])
        raw=Path(target['image_manifest']).read_bytes()
        assert sha(raw)==target['canonical_manifest_sha256']
        assert json.loads(raw)['files']['hub.exs']==target['artifact_sha256']


class RefusingModel:
    """Zero upstream calls. Bind the native stored URL without changing config."""
    def __init__(self,url=None):
        host,port='127.0.0.1',0
        if url:
            parsed=urlsplit(url)
            assert parsed.scheme=='http' and ipaddress.ip_address(parsed.hostname).is_loopback and not parsed.username
            host,port=parsed.hostname,parsed.port
        self.posts=[];outer=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_POST(self):
                outer.posts.append({'path':self.path,'length':self.headers.get('Content-Length')})
                self.send_response(503);self.send_header('Content-Length','0');self.end_headers()
        self.server=ThreadingHTTPServer((host,port),Handler);self.server.daemon_threads=True
        self.thread=threading.Thread(target=lambda:self.server.serve_forever(poll_interval=.05),daemon=True);self.thread.start()
        self.url='http://'+host+':'+str(self.server.server_port)+'/v1/systemone'
    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)
        assert not self.thread.is_alive()


class SealedRuntime(Fixture):
    """Owned native VM or Docker container; adopt preserves stored config bytes."""
    def __init__(self,args,target,*,adopt=True):
        root=Path(target['fixture_root'])
        if adopt:
            regular(root/'hub.json')
        else:
            assert not root.exists(), 'Fresh image fixture must never replace an existing installation'
        super().__init__(args,initialize_projects=False)
        assert self.root==root and (self.image_runtime is not None)==(target['kind']=='image')
        self.target=target;self.adopt=adopt;self.log_identities={};self.custody_failures=[]
        if adopt:
            self.config=json.loads(self.file.read_bytes())
            self.tokens=self.config['agents'];self.base='http://127.0.0.1:'+str(self.config['port'])
            assert self.config['server_id']==target['server_id']
            assert self.config['eventing']['rest_url']==target['broker_rest_url']
        if self.image_runtime:
            assert self.image_runtime.requested==target['image_config_identity']
            assert sha(self.image_runtime.manifest_bytes)==target['canonical_manifest_sha256']

    async def start(self):
        if not self.file.exists():
            if self.adopt:raise CustodyViolation('Existing config disappeared; never recreate known installation')
            with self.file.open('x') as output:json.dump(self.config,output)
            self.file.chmod(0o600)
        regular(self.file)
        if sha(self.args.hub.read_bytes())!=self.target['artifact_sha256']:
            raise CustodyViolation('Native/image artifact binding changed')
        self.logs=[]
        for name in ('stdout.log','stderr.log'):
            handle=safe_append(self.root/name);self.logs.append(handle)
            info=os.fstat(handle.fileno());self.log_identities[name]=(info.st_dev,info.st_ino)
        try:command=self.image_runtime.argv(self.file) if self.image_runtime else ['elixir',str(self.args.hub.resolve())]
        except AssertionError as caught:raise CustodyViolation('Image payload/lifecycle identity mismatch') from caught
        if self.image_runtime:
            if self.image_runtime.image_id!=self.target['image_config_identity']:raise CustodyViolation('Image config identity changed')
        self.process=subprocess.Popen(command+[json.dumps(['serve',str(self.file)])],stdout=self.logs[0],stderr=self.logs[1],start_new_session=True)
        deadline=time.monotonic()+150
        async with httpx.AsyncClient(trust_env=False) as client:
            while time.monotonic()<deadline:
                if self.process.poll() is not None:raise RuntimeUnavailable('Owned runtime exited before readiness')
                try:
                    if (await client.get(self.base+'/health',timeout=1)).status_code==200:
                        if self.image_runtime:self.image_runtime.observe()
                        return
                except httpx.HTTPError:pass
                await asyncio.sleep(.1)
        raise RuntimeUnavailable('Declared150s startup bound exceeded')

    async def close(self):
        error=None
        try:
            await super().close()
        except BaseException as caught:
            error=caught
        finally:
            # A failed SDK close must not leave our actual container/VM alive.
            try:
                if self.image_runtime and self.image_runtime.name is not None:
                    self.image_runtime.stop(hard=False)
                    if self.process:self.process.wait(timeout=15)
                elif self.process and self.process.poll() is None:
                    os.killpg(self.process.pid,signal.SIGKILL);self.process.wait(timeout=10)
            finally:
                for log in self.logs:
                    try:log.close()
                    except BaseException as caught:error=error or caught
                self.logs=[]
                try:self.verify_log_custody()
                except BaseException as caught:error=error or caught
        if error:raise error

    def verify_log_custody(self):
        try:
            for name,identity in self.log_identities.items():
                info=regular(self.root/name,private=False)
                if (info.st_dev,info.st_ino)!=identity:raise CustodyViolation('Opened subprocess log was replaced')
        except BaseException as caught:
            self.custody_failures.append(type(caught).__name__);raise

    def hard_stop(self):
        try:super().hard_stop()
        finally:self.verify_log_custody()

    def versions(self):
        assert self.process is not None and self.process.poll() is None
        if self.image_runtime:
            self.image_runtime.observe()
            command=['docker','exec',self.image_runtime.name,'elixir','--version']
        else:command=['elixir','--version']
        result=subprocess.run(command,capture_output=True,timeout=15,check=True)
        assert len(result.stdout)<=8192 and len(result.stderr)<=8192
        return {'command_kind':'actual-container-exec' if self.image_runtime else 'native-toolchain',
            'stdout':result.stdout.decode(),'stderr':result.stderr.decode(),
            'stdout_sha256':sha(result.stdout)}

    def closed_proof(self):
        process_done=self.process is None or self.process.poll() is not None
        result={'process_never_started':self.process is None,'owned_process_exited':process_done}
        result['log_custody_valid']=not self.custody_failures
        if self.image_runtime:
            events=self.image_runtime.events
            result['owned_container_absent']=(self.image_runtime.name is None and
                (not any(v['action']=='started' for v in events) or bool(events[-1].get('observed_absent'))))
            result['payload_probes_verified']=self.image_runtime.verified
        return result

    def bind_evidence(self,evidence,key='runtime'):
        super().bind_evidence(evidence,key)
        if self.image_runtime is None:
            evidence.value[key]={'kind':'native','artifact_sha256':self.target['artifact_sha256']}
        evidence.value[key]['target']=self.target
        if self.process:
            evidence.value[key]['owned_process']={'pid':self.process.pid,'exit_code':self.process.poll()}
        if self.image_runtime and self.image_runtime.verified:
            assert evidence.value[key]['image_config_identity']==self.target['image_config_identity']
            assert evidence.value[key]['canonical_manifest_sha256']==self.target['canonical_manifest_sha256']
