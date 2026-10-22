"""Read-only host dependency closure for the reviewed recovery image harness.

No generated application, VM, compiler job or service is run. The only optional
host introspection commands are ldconfig -p and GCC -print-* metadata queries.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys
import sysconfig


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def path_binding(path):
    path=Path(path).absolute();real=path.resolve(strict=True);links={}
    for part in [path,*path.parents]:
        if part.is_symlink():links[str(part)]=os.readlink(part)
    info=real.stat();assert stat.S_ISREG(info.st_mode)
    return {'path':str(path),'realpath':str(real),'links':links,'sha256':sha(real),'mode':stat.S_IMODE(info.st_mode)}


def verify_path(row):
    assert path_binding(row['path'])==row,'Host dependency file/alias changed: '+row['path']


def tree_inventory(root,closed_roots):
    root=Path(root).absolute();assert root.resolve(strict=True)==root and root.is_dir() and not root.is_symlink()
    result={'root':str(root),'files':{},'directories':[],'links':{}}
    for directory,children,files in os.walk(root,followlinks=False):
        # Custom PYTHONPYCACHEPREFIX + -B means these caches are never read/written.
        children[:]=[name for name in children if name!='__pycache__']
        for name in sorted(children+files):
            path=Path(directory)/name;relative=str(path.relative_to(root));info=path.lstat()
            if path.is_symlink():
                real=path.resolve(strict=True)
                if real.is_dir():assert any(real.is_relative_to(p) for p in closed_roots),'Directory alias escapes closed roots: '+str(path)
                else:assert real.is_file()
                result['links'][relative]={'text':os.readlink(path),'realpath':str(real),'directory':real.is_dir(),
                    'file':path_binding(path) if real.is_file() else None}
            elif stat.S_ISDIR(info.st_mode):result['directories'].append(relative)
            else:
                assert stat.S_ISREG(info.st_mode),'Special host dependency: '+str(path)
                result['files'][relative]={'sha256':sha(path),'mode':stat.S_IMODE(info.st_mode)}
    result['directories'].sort();return result


def verify_tree(row,closed_roots):
    assert tree_inventory(row['root'],closed_roots)==row,'Host dependency tree SET/hash/alias changed: '+row['root']


def presence(path):
    path=Path(path).absolute()
    try:path.lstat()
    except FileNotFoundError:
        parent=path.parent
        while not parent.exists():
            assert not parent.is_symlink();parent=parent.parent
        assert parent.is_dir()
        return {'path':str(path),'present':False,'existing_parent':str(parent),'parent_realpath':str(parent.resolve(strict=True)),
            'parent_links':{str(p):os.readlink(p) for p in [parent,*parent.parents] if p.is_symlink()}}
    return {'path':str(path),'present':True,'file':path_binding(path)}


def elf_inputs(path):
    """ELF64 little-endian x86_64 PT_INTERP/DT_NEEDED, no binary execution."""
    raw=Path(path).read_bytes()
    if raw[:4]!=b'\x7fELF':return None
    assert raw[4:7]==b'\x02\x01\x01' and len(raw)>=64
    header=struct.unpack_from('<16sHHIQQQIHHHHHH',raw)
    assert header[2]==62 and header[1] in (1,2,3) and header[10]<=4096
    if header[10]==0:
        assert header[1]==1
        return {'interpreter':None,'needed':[],'search':[]}
    assert header[9]==56
    segments=[];interpreter=None;dynamic=None
    for index in range(header[10]):
        offset=header[5]+index*56;assert offset+56<=len(raw)
        kind,flags,start,address,physical,size,memory,alignment=struct.unpack_from('<IIQQQQQQ',raw,offset)
        assert start+size<=len(raw)
        if kind==1:segments.append((address,start,size))
        elif kind==2:dynamic=(start,size)
        elif kind==3:interpreter=raw[start:start+size].rstrip(b'\0').decode()
    result={'interpreter':interpreter,'needed':[],'search':[]}
    if dynamic is None:return result
    table=[]
    for offset in range(dynamic[0],sum(dynamic),16):
        assert offset+16<=len(raw);tag,value=struct.unpack_from('<qQ',raw,offset)
        if tag==0:break
        table.append((tag,value))
    strings=next((value for tag,value in table if tag==5),None)
    if strings is None:assert not any(tag==1 for tag,_ in table);return result
    ranges=[offset+(strings-address) for address,offset,size in segments if address<=strings<address+size];assert len(ranges)==1
    base=ranges[0]
    def string(value):
        start=base+value;assert 0<=start<len(raw);end=raw.index(b'\0',start);return raw[start:end].decode()
    result['needed']=[string(value) for tag,value in table if tag==1]
    result['search']=[part for tag,value in table if tag in (15,29) for part in string(value).split(':') if part]
    return result


def metadata(argv):
    # No compiler output, executable or source argv is accepted here.
    assert (str(Path(argv[0]).absolute()) in ('/sbin/ldconfig','/usr/sbin/ldconfig') and argv[1:]==['-p']) or (
        len(argv)==2 and str(Path(argv[0]).absolute()) in ('/usr/bin/cc','/usr/bin/gcc') and argv[1] in (
            '-print-search-dirs',*[('-print-file-name='+name) for name in ('libc.so','libc_nonshared.a','libdl.a','crti.o','crtn.o')],
            *[('-print-prog-name='+name) for name in ('cc1','collect2','as','ld')]))
    value=subprocess.run(argv,capture_output=True,text=True,check=True,timeout=15,
        env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
    return value.stdout.strip()


def capture(python,native_path):
    python=Path(python).absolute();assert python.resolve()==Path(sys.executable).resolve()
    venv=python.parent.parent;configuration=venv/'pyvenv.cfg'
    assert configuration.is_file() and re.search(r'^include-system-site-packages\s*=\s*false\s*$',configuration.read_text(),re.M|re.I)
    stdlib=Path(sysconfig.get_path('stdlib')).resolve(strict=True)
    native_dirs=[Path(p).resolve(strict=True) for p in native_path.split(':')[:2]]
    native_roots=[p.parent for p in native_dirs]
    compiler=Path('/usr/bin/cc');compiler_real=compiler.resolve(strict=True)
    match=re.fullmatch(r'(.+)-gcc-(\d+)',compiler_real.name);assert match
    gcc=Path('/usr/lib/gcc')/match[1]/match[2];assert gcc.is_dir()
    roots=[venv,stdlib,*native_roots,gcc,Path('/usr/include'),Path('/usr/local/include'),Path('/usr/lib/x86_64-linux-gnu/ldscripts')]
    roots=list(dict.fromkeys(p.resolve(strict=True) for p in roots))
    # Header roots contain a known system Clang include alias. Close that exact
    # target too rather than following an unrecorded external directory.
    for alias in Path('/usr/include/clang').glob('*/include'):
        if alias.is_symlink():
            target=alias.resolve(strict=True);assert target.is_relative_to('/usr/lib') and 'clang' in target.parts and target.name=='include'
            if target not in roots:roots.append(target)
    # The actual selected venv has no .pth execution/import path injection.
    assert not list(venv.rglob('*.pth')),'Unreviewed venv .pth import hook'
    trees=[tree_inventory(p,roots) for p in roots]
    path=':'.join(str(p) for p in native_dirs)+':/usr/bin:/bin'
    tools={}
    for name in ('docker','cc','gcc','as','ld','env','sh','dirname','basename','readlink','cat','which'):
        selected=shutil.which(name,path=path);assert selected;tools[name]=path_binding(selected)
    ldconfig=Path('/sbin/ldconfig');tools['ldconfig']=path_binding(ldconfig)
    raw_cache=metadata([str(ldconfig),'-p']);cache={}
    for line in raw_cache.splitlines():
        match=re.match(r'\s*(\S+) \([^)]*x86-64[^)]*\) => (\S+)$',line)
        if match:cache.setdefault(match[1],[]).append(match[2])
    files={};probes={};query_outputs={}
    searches=metadata([str(compiler),'-print-search-dirs']);query_outputs['search_dirs']=searches
    libraries=next(line.split('=',1)[1] for line in searches.splitlines() if line.startswith('libraries: =')).split(':')
    assert libraries and all(Path(p).is_absolute() for p in libraries if p)
    for directory in libraries:
        if not directory:continue
        for name in ('libc.so','libc.a','libdl.so','libdl.a','libgcc.so','libgcc.a','libgcc_s.so'):
            option=Path(directory)/name;probes[str(option)]=presence(option)
    for name in ('libc.so','libc_nonshared.a','libdl.a','crti.o','crtn.o'):
        value=metadata([str(compiler),'-print-file-name='+name]);assert Path(value).is_absolute() and Path(value).is_file()
        query_outputs[name]=value;files[value]=path_binding(value)
    for name in ('cc1','collect2','as','ld'):
        value=metadata([str(compiler),'-print-prog-name='+name]);value=shutil.which(value,path=path) if not Path(value).is_absolute() else value
        assert value;query_outputs[name]=value;files[value]=path_binding(value)
    files[str(python)]=path_binding(python);files['/etc/ld.so.cache']=path_binding('/etc/ld.so.cache')
    for row in tools.values():files[row['path']]=row
    candidates=set(Path(row['realpath']) for row in files.values())
    for row in trees:
        base=Path(row['root']);candidates.update(base/name for name in row['files'])
        candidates.update(Path(v['realpath']) for v in row['links'].values() if not v['directory'])
    queue=list(candidates);seen=set();elfs={}
    while queue:
        filename=queue.pop();filename=filename.resolve(strict=True)
        if filename in seen:continue
        seen.add(filename)
        # Magic check avoids loading entire archives/large data to parse ELF.
        with filename.open('rb') as stream:magic=stream.read(4)
        if magic!=b'\x7fELF':continue
        parsed=elf_inputs(filename);elfs[str(filename)]=parsed
        dependencies=[]
        if parsed['interpreter']:dependencies.append(Path(parsed['interpreter']))
        search=[]
        for item in parsed['search']:
            item=item.replace('${ORIGIN}',str(filename.parent)).replace('$ORIGIN',str(filename.parent))
            assert '$' not in item and Path(item).is_absolute();search.append(Path(item))
        for needed in parsed['needed']:
            assert '/' not in needed
            options=[p/needed for p in search]+[Path(p) for p in cache.get(needed,[])]+[
                Path(p)/needed for p in ('/lib/x86_64-linux-gnu','/usr/lib/x86_64-linux-gnu','/lib64','/usr/lib64','/lib','/usr/lib')]
            chosen=None
            for option in options:
                stamp=presence(option);probes[str(option)]=stamp
                if stamp['present']:chosen=option;break
            assert chosen is not None,'Unresolved actual ELF dependency: '+needed
            dependencies.append(chosen)
        for dependency in dependencies:
            files[str(dependency)]=path_binding(dependency);queue.append(dependency)
    # Bind import-precedence absence too, rather than permitting a new zip to
    # shadow the full hashed stdlib directory on a future interpreter startup.
    zip_path=stdlib.parent/('python'+str(sys.version_info.major)+str(sys.version_info.minor)+'.zip')
    probes[str(zip_path)]=presence(zip_path)
    preload=presence('/etc/ld.so.preload');assert not preload['present'],'Unreviewed global loader preloads'
    probes[preload['path']]=preload
    return {'schema':'adhd/image-host-dependencies@1','roots':[str(p) for p in roots],'trees':trees,'files':files,'probes':probes,
        'elf_inputs':elfs,'tools':tools,'compiler_queries':query_outputs,'ldconfig_output_sha256':hashlib.sha256(raw_cache.encode()).hexdigest(),
        'python_executable':str(python),'native_path':path,'cache_exclusion':'__pycache__ directories only; -B + owned PYTHONPYCACHEPREFIX prevents cache reads/writes.',
        'pth_policy':'No .pth import hooks in selected venv; include-system-site-packages false.'}


def verify(value):
    roots=[Path(p) for p in value['roots']]
    for row in value['trees']:verify_tree(row,roots)
    for row in value['files'].values():verify_path(row)
    for row in value['probes'].values():assert presence(row['path'])==row,'Host precedence/input presence changed: '+row['path']
    return True


def child_environment(original,closure,bound,cache,socket):
    # Build a small explicit environment instead of inheriting path/code/provider
    # injections such as PYTHONPATH, LD_PRELOAD, ERL_LIBS or GCC_EXEC_PREFIX.
    return {'PATH':closure['native_path'],'LANG':'C.UTF-8','LC_ALL':'C.UTF-8','HOME':str(Path(cache).parent),
        'ERL_FLAGS':original['ERL_FLAGS'],'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1','PYTHONPYCACHEPREFIX':str(cache),
        'DOCKER_HOST':'unix://'+str(socket),'DOCKER_CONFIG':str(bound),'NO_PROXY':'127.0.0.1,::1,localhost'}
