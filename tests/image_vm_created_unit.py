"""Mocked actual observer Created→BEAM custody, denial states and held barrier."""
import copy,json,os,time,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from image_rebind_runtime import ImageRebindRuntime

ZERO='0001-01-01T00:00:00Z'


def created():
    return {'Id':'c'*64,'Image':'sha256:'+'a'*64,'Name':'/owned',
        'State':{'Status':'created','Running':False,'Pid':0,'Paused':False,'Restarting':False,'Dead':False,'OOMKilled':False,'ExitCode':0,'Error':'','StartedAt':ZERO,'FinishedAt':ZERO},
        'Config':{'User':f'{os.getuid()}:{os.getgid()}'},
        'HostConfig':{'PidMode':'private','Privileged':False,'NetworkMode':'none'}}


def observe(mode):
    first=created();running=copy.deepcopy(first);running['State'].update(Status='running',Running=True,Pid=992999,StartedAt='2026-10-22T00:00:00Z')
    if mode=='replaced':running['Id']='d'*64
    if mode=='exited':first['State'].update(Status='exited',ExitCode=1,StartedAt='2026-10-22T00:00:00Z',FinishedAt='2026-10-22T00:00:01Z')
    if mode=='foreign':first['HostConfig']['NetworkMode']='host'
    rows=[first,running,running];inspects=[];slept=[]
    def docker(*args,**kwargs):
        row=rows[min(len(inspects),2)];inspects.append(row)
        return SimpleNamespace(returncode=0,stdout=json.dumps([row]).encode())
    target=SimpleNamespace(name='owned',image_id=first['Image'],docker=docker,observe=lambda:None)
    session={'target':target,'process':SimpleNamespace(poll=lambda:None),'component_argv':['/original/vector.exs','/original/source'],'offline':True,'command_kind':'component'}
    value=object.__new__(ImageRebindRuntime)
    original_bytes=Path.read_bytes;original_text=Path.read_text
    def raw(path,*a,**k):
        if str(path)=='/proc/992999/cmdline':return b'/original/vector.exs\0/original/source\0'
        return original_bytes(path,*a,**k)
    def text(path,*a,**k):
        if str(path)=='/proc/992999/stat':return '992999 (beam.smp) S '+' '.join(['0']*18+['12345'])
        return original_text(path,*a,**k)
    def link(path):
        return {'/proc/992999/exe':'/container-only/beam.smp','/proc/992999/ns/pid':'pid:[private]','/proc/self/ns/pid':'pid:[host]'}[path]
    with patch.object(Path,'read_bytes',raw),patch.object(Path,'read_text',text),patch('os.readlink',link),patch('time.sleep',lambda seconds:slept.append(seconds)):
        try:value.observe_vm(session,time.monotonic()+1)
        except AssertionError:assert mode!='valid'
        else:assert mode=='valid' and session['custody']['namespace_pid']==1
    assert session['vm_observations'][0]['State']==first['State']
    if mode=='valid':assert slept==[.02] and len(session['vm_observations'])==2 and session['observed_container_id']==first['Id']
    elif mode in ('exited','foreign'):assert len(inspects)==1 and not slept and 'custody' not in session
    else:assert slept==[.02] and 'custody' not in session


def main():
    checks=0
    for mode in ('valid','replaced','exited','foreign'):observe(mode);checks+=1
    for key,bad in [('Pid',1),('Running',True),('Paused',True),('Dead',True),('OOMKilled',True),('Restarting',True),('ExitCode',1),('Error','daemon error'),('StartedAt','2026-01-01T00:00:00Z'),('FinishedAt','2026-01-01T00:00:00Z')]:
        state=created()['State'];state[key]=bad
        try:ImageRebindRuntime.pending_created(state)
        except AssertionError:pass
        else:raise AssertionError('Invalid Created state accepted: '+key)
        checks+=1
    print('PASS image VM Created pure'+str(checks)+': pending exact never-started state to actual bound BEAM; foreignCID/network and exited/dead/paused/restarting/started denials; unchanged .02cadence; runtimes0')


if __name__=='__main__':main()
