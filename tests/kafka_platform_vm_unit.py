"""Actual-process custody parser/transport mocks, no Docker/process/socket starts."""
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import kafka_platform_vm as vm


def stat(pid,ticks,cpu='0'):
    fields=['S']+['0']*18+[str(ticks)]+['0']*6;fields[10]=cpu
    return (str(pid)+' (beam.smp) '+' '.join(fields)).encode()


def main():
    args=b'/usr/lib/erlang/erts/bin/beam.smp\0-extra\0/runtime/adhd/boot.exs\0/app/hub.exs\0["serve","/config/hub.json"]\0'
    witness=vm.process_witness(args,b'/container-only/beam.smp',stat(123,99),stat(123,99,'12'),123)
    assert witness['start_ticks']=='99' and witness['actual_compiled_boot_and_app_arguments']
    for cmd,exe,before,after,pid in [(args,b'/bin/sh',stat(123,99),stat(123,99),123),(args.replace(b'/runtime/adhd/boot.exs',b'/other'),b'/beam.smp',stat(123,99),stat(123,99),123),(args,b'/beam.smp',stat(123,99),stat(123,100),123),(args,b'/beam.smp',stat(122,99),stat(122,99),123)]:
        try:vm.process_witness(cmd,exe,before,after,pid)
        except AssertionError:pass
        else:raise AssertionError('Wrong process accepted')
    assert vm.COMMAND==['["serve","/config/hub.json"]']
    with tempfile.TemporaryDirectory() as temp:
        directory=Path(temp)/'123';directory.mkdir();(directory/'stat').write_bytes(stat(123,99));(directory/'cmdline').write_bytes(args)
        row={'Id':'owned','Image':'image','State':{'Running':True,'Pid':123,'StartedAt':'now'},'RestartCount':0,
            'Config':{'Entrypoint':vm.ENTRYPOINT,'Cmd':vm.COMMAND},'HostConfig':{'PidMode':''}}
        def mapped(value):
            value=str(value)
            return Path(temp) if value=='/proc' else Path(value)
        with patch.object(vm,'Path',side_effect=mapped),patch('os.readlink',return_value='/container-only/beam.smp'):
            proof=vm.compose(lambda *a,**k:json.dumps([row]).encode(),'owned','image')
            assert proof['process']['actual_compiled_boot_and_app_arguments']
            row['Config']['Cmd']=[]
            try:vm.compose(lambda *a,**k:json.dumps([row]).encode(),'owned','image')
            except AssertionError:pass
            else:raise AssertionError('Wrong serving command accepted')
    cid='a'*64;pod={'metadata':{'uid':'owned-pod'},'spec':{'containers':[{'name':'hub'}]},'status':{'containerStatuses':[{'name':'hub','containerID':'containerd://'+cid,'ready':True,'state':{'running':{'startedAt':'now'}},'restartCount':0}]}}
    events=[]
    def command(argv,**kwargs):
        assert kwargs=={'capture':True};events.append(argv)
        if 'inspect' in argv:return json.dumps({'status':{'id':cid},'info':{'pid':123}}).encode()
        if argv[-1].endswith('/stat'):return stat(123,99)
        if argv[-1].endswith('/cmdline'):return args
        if argv[-1].endswith('/exe'):return b'/container-only/beam.smp\n'
        raise AssertionError(argv)
    proof=vm.kind(command,'owned-node',pod,'image')
    assert proof['container_id']=='containerd://'+cid and len(events)==6
    assert events[0]==['docker','exec','owned-node','crictl','inspect',cid]
    assert any(a==['docker','exec','owned-node','cat','/proc/123/cmdline'] for a in events)
    pod['spec']['containers'][0]['command']=['sh']
    try:vm.kind(lambda *a,**k:(_ for _ in ()).throw(AssertionError('No commands')), 'owned-node',pod,'image')
    except AssertionError as error:assert 'entrypoint' in str(error)
    else:raise AssertionError('Overridden entrypoint accepted')
    print(json.dumps({'passed':True,'checks':9,'apps_models_sockets_started':False}))


if __name__=='__main__':main()
