"""Continue an actual prepared legacy upgrade on an isolated same-path copy.

The existing reviewed image supplies only its OTP/Elixir runtime; the separately
mounted development artifact is not an admitted successor image.
"""
import argparse,hashlib,json,os,secrets,shutil,stat,subprocess,time
from pathlib import Path

HTTP = r''':inets.start();[base,requests]=JSON.decode!(hd(System.argv()));out=Enum.map(requests,fn r->headers=Enum.map(r["headers"]||%{},fn {k,v}->{String.to_charlist(k),String.to_charlist(v)} end);url=String.to_charlist(base<>r["path"]);spec=if r["body"],do: {url,headers,~c"application/json",JSON.encode!(r["body"])},else: {url,headers};method=if r["body"],do: :post,else: :get;case :httpc.request(method,spec,[timeout: 5000,connect_timeout: 2000],[body_format: :binary]) do {:ok,{{_,code,_},_,body}}->%{"status"=>code,"body"=>JSON.decode!(body)};_->%{"status"=>0,"body"=>%{}} end end);IO.puts(JSON.encode!(out))'''

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def identity(path):
 s=path.lstat();return {'sha256':digest(path),'mode':stat.S_IMODE(s.st_mode),'inode':s.st_ino,'device':s.st_dev,'uid':s.st_uid,'links':s.st_nlink,'bytes':s.st_size}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ('hub','legacy-config','work','report'):p.add_argument('--'+key,type=Path,required=True)
 p.add_argument('--runtime-image',required=True);a=p.parse_args();a.hub=a.hub.resolve();a.legacy_config=a.legacy_config.resolve();a.work=a.work.resolve()
 assert not a.work.exists();a.work.mkdir(parents=True,mode=0o700);copy=a.work/'copy';original_root=a.legacy_config.parent
 protected=[x for x in original_root.iterdir()if x.is_file()and x.name not in ('stdout.log','stderr.log')]
 before={x.name:identity(x)for x in protected};assert before['hub.dets']['mode']==0o664
 marker=json.loads(Path(str(a.legacy_config)+'.project-upgrade').read_text());assert marker['phase']=='prepared'
 raw=subprocess.check_output(['elixir',str(Path(__file__).with_name('local_legacy_expectations.exs')),str(a.hub),str(a.legacy_config)],text=True)
 expected=json.loads(raw);assert expected['schema']==1 and expected['publications'] and expected['receipts']
 shutil.copytree(original_root,copy,copy_function=shutil.copy2);copy.chmod(0o700)
 # Copy preserves every original configuration/marker byte and absolute binding.
 for n,v in before.items():assert digest(copy/n)==v['sha256']
 copy_protected={n:identity(copy/n)for n in before if n=='hub.dets' or n.endswith('.before-projects')}
 lifecycle=[];checks=[];active=None
 image=json.loads(subprocess.check_output(['docker','image','inspect',a.runtime_image],text=True))[0]['Id'];assert image==a.runtime_image
 config=json.loads(a.legacy_config.read_text());base='http://127.0.0.1:'+str(config['port'])
 def call(requests):
  r=subprocess.run(['docker','exec',active,'elixir','-e',HTTP,json.dumps([base,requests],ensure_ascii=False)],capture_output=True,text=True,timeout=25)
  if r.returncode:return None
  return json.loads(r.stdout)
 def start():
  nonlocal active
  active='adhd-local-copy-'+secrets.token_hex(6)
  argv=['docker','run','--detach','--name',active,'--network','none','--read-only','--user',f'{os.getuid()}:{os.getgid()}',
   '--cap-drop','ALL','--security-opt','no-new-privileges','--memory','1g','--cpus','2','--pids-limit','256',
   '--tmpfs','/tmp:rw,nosuid,noexec,size=128m','--env',f'ADHD_CONFIG_FILE={a.legacy_config}',
   '--mount',f'type=bind,src={copy},dst={original_root}',
   '--mount',f'type=bind,src={a.hub},dst=/diagnostic/adhd.exs,readonly',
   '--entrypoint','elixir',image,'/diagnostic/adhd.exs',json.dumps(['serve',str(a.legacy_config)])]
  container=subprocess.check_output(argv,text=True).strip();end=time.monotonic()+90
  while time.monotonic()<end:
   state=json.loads(subprocess.check_output(['docker','inspect',active],text=True))[0]
   assert state['State']['Running'],'Diagnostic continuation exited during startup; inspect owned container logs'
   result=call([{'path':'/health','headers':{}}])
   if result and result[0]['status']==200:break
   time.sleep(.2)
  else:raise AssertionError('Diagnostic continuation readiness bound')
  assert state['Image']==image and state['HostConfig']['NetworkMode']=='none' and state['HostConfig']['ReadonlyRootfs']
  mounted=subprocess.check_output(['docker','exec',active,'sha256sum','/diagnostic/adhd.exs'],text=True).split()[0];assert mounted==digest(a.hub)
  lifecycle.append({'action':'started','container_id':container,'image_config_identity':image,'network':'none','mounted_artifact_sha256':mounted})
 def stop(hard=False):
  nonlocal active
  if active is None:return
  state=json.loads(subprocess.check_output(['docker','inspect',active],text=True))[0];container=state['Id']
  if state['State']['Running']:subprocess.run(['docker','kill'if hard else'stop',active],capture_output=True,check=True,timeout=35)
  code=int(subprocess.check_output(['docker','wait',active],text=True).strip())
  if hard:assert code==137
  subprocess.run(['docker','logs',active],stdout=(a.work/(container[:12]+'.stdout')).open('w'),stderr=(a.work/(container[:12]+'.stderr')).open('w'),check=True)
  subprocess.run(['docker','rm',active],capture_output=True,check=True);active=None
  lifecycle.append({'action':'hard-killed-and-removed'if hard else'stopped-and-removed','container_id':container,'exit_code':code})
 def rpc(command,actor='agent-a',mid=None):
  req={'path':'/a2a','headers':{'Authorization':'Bearer '+config['agents'][actor]},'body':{'jsonrpc':'2.0','id':1,'method':'SendMessage','params':{'message':{'messageId':mid or secrets.token_hex(16),'role':'ROLE_USER','parts':[{'data':command}]}}}}
  result=call([req]);assert result and result[0]['status']==200
  envelope=result[0]['body'];assert 'error'not in envelope,'Actual continuation A2A command rejected'
  return envelope['result']['message']['parts'][0]['data']
 def verify_data():
  for pub in expected['publications']:
   got=rpc({'op':'get','publication_id':pub['id']})['publication'];assert all(got.get(k)==v for k,v in pub.items())
  rows=rpc({'op':'poll'},'agent-b')['deliveries'];assert rows==expected['unacked_deliveries']
  assert not(set(expected['acked_delivery_ids'])&{r['id']for r in rows})
  for receipt in expected['receipts']:
   got=rpc(receipt['command'],receipt['agent'],receipt['message_id']);assert got==receipt['result'],'Accepted legacy mutation receipt changed'
 try:
  start();verify_data();checks.append({'name':'same-absolute-path-prepared-upgrade-preserves-all-originals-private-acks-and-exact-mutation-receipts','passed':True,'publications':len(expected['publications']),'receipts':len(expected['receipts'])})
  current=json.loads((copy/a.legacy_config.name).read_text());registry=json.loads(Path(str(copy/a.legacy_config.name)+'.stores').read_text());server=current['server_id'];assert len(server)==32 and registry['server_id']==server
  assert json.loads(Path(str(copy/a.legacy_config.name)+'.project-upgrade').read_text())['phase']=='completed'
  selected=Path(registry['projects'][expected['project_id']]['storage_anchor']);selected_copy=copy/selected.relative_to(original_root)
  assert stat.S_IMODE(selected_copy.stat().st_mode)==0o600 and stat.S_IMODE(Path(str(selected_copy)+'.snapshot').stat().st_mode)==0o600
  assert all(identity(copy/n)==v for n,v in copy_protected.items())
  checks.append({'name':'complete-adoption-persists-one-generated-server-identity-in-private-selected-generation-with-untouched-rollback-sources','passed':True})
  stop(hard=True);start();verify_data();assert json.loads((copy/a.legacy_config.name).read_text())['server_id']==server
  assert lifecycle[-1]['container_id']!=lifecycle[0]['container_id'];checks.append({'name':'actual-hard-kill-new-container-cold-restart-preserves-generated-identity-and-receipts-with-no-ack-redelivery','passed':True})
 finally:stop()
 assert all(identity(original_root/n)==v for n,v in before.items())
 assert all(identity(copy/n)==v for n,v in copy_protected.items())
 checks.append({'name':'original-interrupted-fixture-and-copied-old-checkpoint-rollback-bytes-modes-inodes-remain-unchanged','passed':True})
 result={'schema':'adhd/local-legacy-runtime@1','passed':True,'lifecycle_admitted':False,'artifact_sha256':digest(a.hub),'runtime_image_config_identity':image,
 'scope':'Actual prepared schema1 mode0664 fixture continued from byte-exact privatecopy mounted at its originalabsolute path; image34supplies runtimeonly withnetworknone, readonlynew37artifact. No matching-successbroker/model repliesfabricated.','checks':checks,'container_lifecycle':lifecycle,'harness_sha256':digest(Path(__file__)),'expectations_harness_sha256':digest(Path(__file__).with_name('local_legacy_expectations.exs')),'original_input_proof':before,'limitations':['Notanadmittedsuccessorimage; separatemounteddevelopmentartifact.','No model/Kafka/networkquality claim; container hasnetworknone.','No originalhostfixture mutations or hand-rebinding ofconfig/marker paths/hashes.']}
 a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,indent=2)+'\n');print('PASS actual prepared local continuation',len(checks),flush=True)

if __name__=='__main__':main()
