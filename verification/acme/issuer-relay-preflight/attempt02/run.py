from pathlib import Path
import hashlib,http.client,json,os,signal,socket,ssl,sys,time
root=Path(__file__).absolute().parent
plan=json.loads((root/'plan.json').read_bytes())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def ticks(pid):
 try:return Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[19]
 except FileNotFoundError:return None
assert plan['maximum_http_requests']==3 and plan['budget_seconds']==30
ca_path=Path(plan['ca_manifest']);assert sha(ca_path)==plan['ca_manifest_sha256']
ca=json.loads(ca_path.read_bytes())
for p in ca['processes']:assert ticks(p['pid'])==p['start_ticks']
helper=Path(plan['helper']);assert helper.resolve(strict=True)==helper and sha(helper)==plan['helper_sha256']
sys.path.insert(0,str(helper.parent))
from acme_issuer_fault_relay import IssuerFaultRelay
relay=IssuerFaultRelay(**plan['fixture'],lifetime_seconds=30,max_requests=3)
ctx=ssl.create_default_context(cafile=plan['fixture']['root_file'])
report={'schema':plan['schema'],'passed':False,'requests':[],'orders':0,'generated_application_starts':0,'public_ca_calls':0,'plan_sha256':sha(root/'plan.json'),'driver_sha256':sha(__file__)}
primary=None
def expired(*args):raise TimeoutError('Fixed directory-only preflight30s')
old=signal.signal(signal.SIGALRM,expired);signal.alarm(30)
try:
 fd=os.open(root/'started.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'w')as mark:json.dump({'pid':os.getpid(),'driver_sha256':sha(__file__)},mark);mark.flush();os.fsync(mark.fileno())
 fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
 relay.start()
 for mode,expected in [(None,200),(503,503),(429,429)]:
  relay.set_fault(mode,120)if mode else relay.set_fault(None)
  conn=http.client.HTTPSConnection('localhost',19103,context=ctx,timeout=5)
  try:
   conn.request('GET','/dir',headers={'Host':'localhost:19103','Connection':'close','User-Agent':'ADHD-ACME-Relay-Preflight/1'})
   response=conn.getresponse();body=response.read(1048577)
   report['last_observed_status']=response.status
   assert len(body)<=1048576 and response.status==expected
   value=json.loads(body)
   if mode:assert response.getheader('Retry-After')=='120'
   else:
    from urllib.parse import urlsplit
    for name in ['newNonce','newAccount','newOrder']:
     parsed=urlsplit(value[name]);assert parsed.scheme=='https'and parsed.hostname=='localhost'and parsed.port==19103
   report['requests'].append({'expected_status':expected,'actual_status':response.status,'verified_tls_root_and_hostname':True,'body_sha256':hashlib.sha256(body).hexdigest(),'directory_links_remain_on_relay':mode is None})
  finally:conn.close()
  deadline=time.monotonic()+3
  while relay.snapshot()['active'] and time.monotonic()<deadline:time.sleep(.02)
  assert relay.snapshot()['active']==0
 report['passed']=True
except BaseException as e:primary=e;report['failure_type']=type(e).__name__;raise
finally:
 try:relay.close()
 except BaseException as e:
  report['passed']=False;report['cleanup_failure_type']=type(e).__name__
  if primary:primary.add_note('Owned relay close: '+type(e).__name__)
  else:primary=e
 signal.alarm(0);signal.signal(signal.SIGALRM,old)
 report['relay']=relay.snapshot()
 report['ca_original_identities_preserved']=all(ticks(p['pid'])==p['start_ticks']for p in ca['processes'])
 report['passed']=report['passed']and report['ca_original_identities_preserved']and not primary
 with (root/'result.json').open('x')as out:json.dump(report,out,indent=2);out.write('\n')
 (root/'result.json').chmod(0o600)
 if primary:raise primary
print(json.dumps({'passed':report['passed'],'requests':len(report['requests']),'app_starts':0,'orders':0}))
