"""Read-only actual deployed BEAM/compiled entrypoint custody; no model calls."""
import hashlib
import json
from pathlib import Path

ENTRYPOINT=['elixir','/runtime/adhd/boot.exs','/app/hub.exs']
COMMAND=['["serve","/config/hub.json"]']


def process_witness(cmdline,exe,before,after,pid):
    assert type(pid) is int and pid>0
    # Use kernel cmdline bytes, never the configured OCI command as a substitute.
    args=cmdline.rstrip(b'\0').split(b'\0')
    assert b'/runtime/adhd/boot.exs' in args and b'/app/hub.exs' in args and COMMAND[0].encode() in args
    assert Path(exe.decode().strip()).name=='beam.smp'
    def identity(raw):
        text=raw.decode();assert text.split(' ',1)[0]==str(pid) and ') ' in text
        ticks=text[text.rindex(')')+2:].split()[19];assert ticks.isdigit();return ticks
    start_ticks=identity(before);assert start_ticks==identity(after),'VM identity changed while observing process'
    return {'pid':pid,'start_ticks':start_ticks,'executable_basename':'beam.smp',
        'actual_cmdline_sha256':hashlib.sha256(cmdline).hexdigest(),'actual_compiled_boot_and_app_arguments':True}


def compose(command,identifier,image):
    row=json.loads(command(['docker','inspect',identifier],capture=True))[0]
    assert row['Id']==identifier and row['Image']==image and row['State']['Running']
    assert row['Config']['Entrypoint']==ENTRYPOINT and row['Config']['Cmd']==COMMAND
    assert row['HostConfig']['PidMode'] in ('',None)
    pid=row['State']['Pid'];base=Path('/proc')/str(pid)
    before=(base/'stat').read_bytes();cmdline=(base/'cmdline').read_bytes()
    # Magic link readlink text may refer to a path absent on the host.
    import os
    exe=os.readlink(base/'exe').encode();after=(base/'stat').read_bytes()
    proof=process_witness(cmdline,exe,before,after,pid)
    again=json.loads(command(['docker','inspect',identifier],capture=True))[0]
    assert (again['Id'],again['Image'],again['State']['Pid'],again['State']['StartedAt'],again['RestartCount'])==(row['Id'],row['Image'],pid,row['State']['StartedAt'],row['RestartCount'])
    return {'scope':'actual Docker host PID private container','container_id':identifier,'image':image,'entrypoint':ENTRYPOINT,'process':proof,
        'started_at':row['State']['StartedAt'],'restart_count':row['RestartCount']}


def kind(command,node,pod,image):
    assert pod['spec'].get('hostPID',False) is False
    spec=next(c for c in pod['spec']['containers'] if c['name']=='hub')
    assert not spec.get('command') and not spec.get('args'),'Packaged entrypoint must not be overridden'
    status=next(c for c in pod['status']['containerStatuses'] if c['name']=='hub')
    assert status['ready'] and 'running' in status['state']
    prefix='containerd://';assert status['containerID'].startswith(prefix)
    identifier=status['containerID'][len(prefix):];assert len(identifier)==64 and all(c in '0123456789abcdef' for c in identifier)
    row=json.loads(command(['docker','exec',node,'crictl','inspect',identifier],capture=True))
    assert row['status']['id']==identifier
    pid=row['info']['pid'];assert type(pid) is int and pid>0
    def read(name):return command(['docker','exec',node,'cat','/proc/'+str(pid)+'/'+name],capture=True)
    before=read('stat');cmdline=read('cmdline');exe=command(['docker','exec',node,'readlink','/proc/'+str(pid)+'/exe'],capture=True);after=read('stat')
    proof=process_witness(cmdline,exe,before,after,pid)
    again=json.loads(command(['docker','exec',node,'crictl','inspect',identifier],capture=True))
    assert again['status']['id']==identifier and again['info']['pid']==pid
    # Actual image config is independently bound by the parent platform harness.
    return {'scope':'actual Kind node PID namespace app process','pod_uid':pod['metadata']['uid'],'container_id':status['containerID'],'image':image,
        'process':proof,'started_at':status['state']['running']['startedAt'],'restart_count':status['restartCount']}
