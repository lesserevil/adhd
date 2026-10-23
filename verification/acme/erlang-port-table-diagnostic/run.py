from pathlib import Path
import sys,json,hashlib,re,time,subprocess
sys.path.insert(0,'/home/horde/src/adhd/tests')
from acme_platform_commands import Commands
from container_fixture import OwnedImage
w=Path(__file__).resolve().parent;image='sha256:3f82e4c4cefd0ebd539dc7b98f599d12f2d67d71439e9b0c623d44cd6fbd040c'
tools={'docker':'/usr/bin/docker','kind':'/home/horde/src/adhd/.worktrees/deployment/_build/kafka/kind','kubectl':'/home/horde/src/adhd/.worktrees/deployment/_build/kafka/kubectl'}
env={'PATH':'/usr/bin:/bin','HOME':str(w),'DOCKER_HOST':'unix:///run/docker.sock','DOCKER_CONFIG':'/home/horde/src/adhd/_build/acme/docker-config42-01','KUBECONFIG':str(w/'unused'),'LANG':'C.UTF-8'}
commands=Commands(tools,env,w);rows=[];primary=None
try:
 actual=json.loads(commands(['docker','image','inspect',image],capture=True).stdout);assert len(actual)==1 and actual[0]['Id']==image
 for index,flags in enumerate(['+S 2:2','+S 2:2 +Q 65536']):
  row={'variant':'unbounded_ports' if index==0 else 'Q65536','erl_flags':flags,'issued_name':'adhd-acme-port-table01-'+str(index),'id':None,'absent':False};rows.append(row)
  name=row['issued_name'];assert OwnedImage.probe_absence(commands(['docker','inspect',name],capture=True,check=False),name)
  try:
   script='/bin/busybox cat /proc/self/limits; exec elixir -e \'IO.puts("ADHD_PORT_LIMIT=" <> Integer.to_string(:erlang.system_info(:port_limit)))\''
   argv=['docker','create','--name',name,'--label','adhd.acme.diagnostic=port-table01','--network','none','--read-only','--user','10001:10001','--cap-drop','ALL','--security-opt','no-new-privileges','--memory','1g','--cpus','2','--pids-limit','256','--ulimit','nofile=1073741816:1073741816','--tmpfs','/tmp:rw,nosuid,noexec,size=64m','--env','ERL_FLAGS='+flags,'--entrypoint','/bin/busybox',image,'sh','-c',script]
   raw=commands(argv,capture=True).stdout.decode().strip();assert re.fullmatch('[a-f0-9]{64}',raw);row['id']=raw
   def inspect():
    values=json.loads(commands(['docker','inspect',row['id']],capture=True).stdout);assert len(values)==1;v=values[0];assert v['Id']==row['id'] and v['Name']=='/'+name and v['Image']==image and v['Config']['Labels']['adhd.acme.diagnostic']=='port-table01';return v
   before=inspect();h=before['HostConfig'];assert before['Config']['User']=='10001:10001' and h['NetworkMode']=='none' and h['ReadonlyRootfs'] and h['Memory']==1073741824 and h['NanoCpus']==2000000000
   assert h['CapDrop']==['ALL'] and h['SecurityOpt']==['no-new-privileges'] and not before['Mounts'];assert h['Ulimits']==[{'Name':'nofile','Hard':1073741816,'Soft':1073741816}]
   row['requested_limits']={'memory_bytes':h['Memory'],'nano_cpus':h['NanoCpus'],'ulimits':h['Ulimits'],'user':before['Config']['User'],'network':'none'}
   started=time.monotonic();p=commands(['docker','start','--attach',row['id']],capture=True,check=False,timeout=60);row['elapsed_seconds']=time.monotonic()-started;row['attach_exit_code']=p.returncode
   for key,data in [('stdout',p.stdout),('stderr',p.stderr)]:
    assert len(data)<=65536;f=w/(row['variant']+'.'+key);f.write_bytes(data);f.chmod(0o600);row[key+'_sha256']=hashlib.sha256(data).hexdigest()
   after=inspect();row['state']={k:after['State'][k] for k in ['Status','Running','ExitCode','OOMKilled','Pid','StartedAt','FinishedAt']};assert not after['State']['Running']
   text=p.stdout.decode();line=next(v for v in text.splitlines() if v.startswith('Max open files'));row['actual_open_files_limit']=line;assert line.split()[3:5]==['1073741816','1073741816']
   values=re.findall(r'^ADHD_PORT_LIMIT=([0-9]+)$',text,re.M);row['actual_erlang_port_limit']=int(values[0]) if len(values)==1 else None
  finally:
   # Cleanup by validated ID, or only issued exact name if create output was malformed.
   key=row['id'] or name;p=commands(['docker','inspect',key],capture=True,check=False)
   if p.returncode==0:
    v=json.loads(p.stdout)[0];assert v['Name']=='/'+name and v['Image']==image and v['Config']['Labels']['adhd.acme.diagnostic']=='port-table01';assert row['id'] in (None,v['Id']);row['id']=v['Id']
    commands(['docker','rm','--force',row['id']],capture=True)
   else:assert OwnedImage.probe_absence(p,key)
   for key in [row['id'],name]:
    if key:assert OwnedImage.probe_absence(commands(['docker','inspect',key],capture=True,check=False),key)
   row['absent']=True
except BaseException as e:primary=e
finally:
 try:commands.close()
 except BaseException as e:
  if primary is None:primary=e
 result={'schema':'adhd/acme-port-table-diagnostic@1','passed':primary is None,'image':image,'rows':rows,'commands':commands.evidence(),'scope':'Network-none Elixir utility only; no app/default-entrypoint/Kind/ACME qualification','source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'tool_sha256':hashlib.sha256(Path('/usr/bin/docker').read_bytes()).hexdigest(),'failure_type':type(primary).__name__ if primary else None}
 p=w/'result.json';p.write_text(json.dumps(result,indent=2)+'\n');p.chmod(0o600)
if primary:raise primary
