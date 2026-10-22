from pathlib import Path
import json,hashlib,importlib.util,subprocess,re,ast,collections,shutil,urllib.parse
ROOT=Path('/home/horde/src/adhd');w=ROOT/'_build/quality40-compiled05-01';out=Path('/home/horde/src/adhd/.worktrees/contracts/verification/quality40-compiled05-positive');out.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
spec=importlib.util.spec_from_file_location('quality05',w/'run.py');driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
p=json.load(open(w/'plan.json'));driver.verify(p,w);matrix=json.load(open(w/'matrix.json'));assert matrix['passed'] and matrix['plan_sha256']==sha(w/'plan.json') and not matrix['unrun_suites'];assert len(matrix['rows'])==4
assert p['expected_groups']==69 and p['automatic_retries']==0 and p['relay_retries']==0 and p['parallelism']==1
assert p['maximum_provider_posts']==288 and p['extra_provider_health_or_warmup_calls']==0
manifest=json.load(open(w/'image-manifest.json'));expected_payload=hashlib.sha256(json.dumps({'/app/'+k:v for k,v in manifest['files'].items() if k!='Dockerfile'},sort_keys=True).encode()).hexdigest()
closures=[];pid_observations=[];providers=[];starts=0;groups=0;ports=set();requests=0;gold_checks={}
def missing(identifier):
 result=subprocess.run(['/usr/bin/docker','inspect',identifier],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
 assert result.returncode==1 and result.stdout.strip() in (b'',b'[]') and re.fullmatch(r'(?i:(?:Error(?: response from daemon)?:\s*)?No such (?:object|container):\s*)'+re.escape(identifier),result.stderr.decode().strip())
 return {'identifier':identifier,'returncode':1,'stdout':result.stdout.decode(),'stderr':result.stderr.decode(),'strict_absent':True}
def process_gone(pid,start=None):
 file=Path('/proc')/str(pid)/'stat'
 try:
  raw=file.read_text();actual=raw[raw.rfind(')')+2:].split()[19]
 except FileNotFoundError:return {'pid':pid,'expected_starttime':start,'kernel_absent':True}
 assert start is not None and str(actual)!=str(start),'Owned process still present or no prior starttime to disambiguate'
 return {'pid':pid,'expected_starttime':str(start),'current_different_starttime':actual,'pid_reused':True}
def no_prompt_fields(x):
 if isinstance(x,dict):
  assert not (set(x)&{'request_json','response_text','prompt','questions'})
  for v in x.values():no_prompt_fields(v)
 elif isinstance(x,list):
  for v in x:no_prompt_fields(v)
for job,row in zip(p['jobs'],matrix['rows']):
 name=job['name'];assert row['suite']==name and row['passed'] and row['exit_code']==0 and not row['failure_type'] and not row['cleanup_failure_type']
 assert row['elapsed_seconds']<=job['provider_window_seconds']
 report=json.load(open(w/(name+'.json')));c=json.load(open(w/(name+'-custody.json')));launch=json.load(open(w/(name+'-launches.json')))
 assert report['passed'] and len(report['cases'])==job['expected_groups'] and all(x['passed'] for x in report['cases']);groups+=len(report['cases'])
 assert sha(w/(name+'.json'))==row['report_sha256'] and sha(w/(name+'-custody.json'))==row['custody_report_sha256'] and sha(w/(name+'.log'))==row['log_sha256']
 assert (w/'frozen/tests'/ (name+'.py')).read_bytes()==(ROOT/'tests'/(name+'.py')).read_bytes(),'Original quality corpus/gold/assertions changed'
 assert c['passed'] and not c['cleanup_failure_types'] and c['primary_failure_type'] is None
 assert c['image_config_identity']==p['image_config_identity'] and c['canonical_manifest_sha256']==p['canonical_manifest_sha256']
 assert len(c['runtime_events'])==len(launch)==len(row['cleanup'])==job['expected_image_starts']
 for event,issued in zip(c['runtime_events'],launch):
  assert event['action']=='start' and event['completed'] and event['kind']=='docker' and event['observed_absent'] and event['docker_client_exited']
  assert event['full_payload_files_verified']==59 and event['actual_payload_sha256']==expected_payload and event['namespace_vm_pid']==1 and event['pid_namespace_mode']==''
  cache=event['compiled_cache'];assert cache['manifest_sha256']==p['compiled_cache']['manifest_sha256'] and cache['modules']==59 and cache['cache_and_toolchain_files_verified']==67 and cache['custody_after_original_health_only'] and cache['extra_health_or_warmup_requests']==0
  assert cache['entrypoint']==['elixir','/runtime/adhd/boot.exs','/app/hub.exs']
  assert event['container_id']==issued['container_id'] and event['container_name']==issued['name'] and issued['image']==p['image_config_identity']
  closures.extend([missing(event['container_id']),missing(event['container_name'])]);pid_observations.append(process_gone(issued['client_pid'],issued['client_starttime']));pid_observations.append(process_gone(event['host_vm_pid']));starts+=1
  for model in event['selected_models']:
   url=urllib.parse.urlsplit(model['url']);assert url.hostname=='127.0.0.1' and url.port!=18770;ports.add(url.port)
 provider=c['provider'];assert provider==row['provider'] and provider['closed'] and provider['inflight']==provider['handlers']==0 and not provider['violations'] and not provider['provider_error_types'] and provider['relay_retries']==0
 raw=(w/(name+'-provider.jsonl')).read_bytes();assert hashlib.sha256(raw).hexdigest()==provider['exchange_log_sha256']
 ledger=[json.loads(line) for line in raw.splitlines()];assert 0<len(ledger)==provider['upstream_http_posts']<=job['provider_post_cap'];assert provider['post_cap']==job['provider_post_cap'] and provider['window_seconds']==job['provider_window_seconds']
 typed=collections.Counter();sanitized=[]
 for i,x in enumerate(ledger,1):
  assert x['sequence']==i and x['status']==200 and 'transport_error_type' not in x and x['elapsed_seconds']<=10.1
  request=x['request_json'].encode();response=x['response_text'].encode();assert hashlib.sha256(request).hexdigest()==x['request_sha256'] and hashlib.sha256(response).hexdigest()==x['response_sha256']
  q=json.loads(request);a=json.loads(response);assert q['model']==p['provider_model'] and isinstance(q['state'],dict) and set(q['questions']) in ({'intent'},{'useful'},{'answer','assessment'})
  assert set(a['answers'])==set(q['questions'])
  for key,question in q['questions'].items():
   value=a['answers'][key];assert value['type']==question['type'];typed[key]+=1
   if value['type']=='noul':assert type(value['noul']) in (int,float) and 0<=value['noul']<=1
   else:
    assert value['type']=='choice' and set(value['probabilities'])==set(question['criteria']) and value['choice'] in question['criteria']
    assert all(type(v) in (int,float) and 0<=v<=1 for v in value['probabilities'].values())
  sanitized.append({k:x[k] for k in ['sequence','request_sha256','status','response_sha256','elapsed_seconds']} | {'question_types':sorted(q['questions'])})
 requests+=len(ledger);providers.append({'suite':name,'actual_posts':len(ledger),'cap':job['provider_post_cap'],'window_seconds':job['provider_window_seconds'],'suite_elapsed_seconds':row['elapsed_seconds'],'typed_questions':dict(typed),'raw_ledger_sha256':hashlib.sha256(raw).hexdigest(),'retained_raw_prompts':False})
 (out/(name+'-provider-accounting.json')).write_text(json.dumps(sanitized,indent=2)+'\n')
 for suffix in ['.json','-custody.json','-launches.json']:
  value=json.load(open(w/(name+suffix)));no_prompt_fields(value);shutil.copyfile(w/(name+suffix),out/(name+suffix))
 # Independently check history fixed expected labels from literal source; other
 # corpora are pinned unchanged and original exhaustive assertions passed.
 if name=='history_quality':
  tree=ast.parse((w/'frozen/tests/history_quality.py').read_text());values={node.targets[0].id:ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('DEVELOPMENT','HELD_OUT')}
  expected=values['DEVELOPMENT']+values['HELD_OUT'];assert [v['case'] for v in report['cases']]==[v[0] for v in expected]
  for case,gold in zip(report['cases'],expected):
   allowed={'insufficient','no_evidence'} if gold[4]=='unknown' else {gold[3]}
   assert case['outcome'] in allowed
   if gold[4] is not None:assert case['selection']==gold[4]
  gold_checks[name]='22 literal fixed gold targets and selections independently compared, including original unknown-selection allowance insufficient/no_evidence.'
 else:
  if name=='archive_quality':
   assert all(case['outcome'] in case['expected_outcomes'] for case in report['cases'])
  gold_checks[name]='Original exact source/case-count/hash and all unmodified per-vector assertions retained; no changed gold or adaptation.'
assert starts==25 and groups==69 and requests<=288
for network in ['/proc/net/tcp','/proc/net/tcp6']:
 rows=Path(network).read_text().splitlines()[1:]
 for line in rows:
  fields=line.split()
  if fields[3]=='0A':assert int(fields[1].rsplit(':',1)[1],16) not in ports,'Owned relay port still listening'
lease_path=ROOT/'_build/model-quality40-compiled05-lease01/result.json';lease=json.load(open(lease_path));assert lease['passed'] and lease['child_returncode']==0 and lease['child_reaped'] and lease['lease_acquired'] and lease['lease_released'] and not lease['failed_metadata_clients']
a,b=lease['model_before'].copy(),lease['model_after'].copy();a.pop('metadata_client');b.pop('metadata_client');assert a==b
pid_observations.append(process_gone(lease['child_pid']))
for name in ['plan.json','matrix.json','admission.json','image-manifest.json','cache-manifest.json','cache-metadata.json','receipt.json','rebuild.json']:shutil.copyfile(w/name,out/name)
shutil.copyfile(lease_path,out/'model-lease-result.json')
audit={'schema':'adhd/final05-quality69-independent-audit@1','passed':True,'image':p['image_config_identity'],'artifact_sha256':p['artifact_sha256'],'plan_sha256':sha(w/'plan.json'),'groups':69,'actual_starts':25,'source_files_verified_each':59,'cache_toolchain_files_verified_each':67,'provider_posts':requests,'provider_cap':288,'provider_suites':providers,'original_corpus_scripts_and_golds':gold_checks,'strict_container_absence':closures,'kernel_process_closure':pid_observations,'relay_ports_now_not_listening':sorted(ports),'model_lease_released_model_unchanged':True,'raw_provider_prompts_retained':False,'scope':'Exact final05 live quality69 only. Historical optimizer/SDK/platform gates remain distinct; no physical-egress firewall or exclusive exclusion of unrelated model users claimed. VM PIDs checked absent; original runtime events do not retain VM starttime, while Docker-client starttimes are checked explicitly.','retained_files':{f.name:sha(f) for f in out.iterdir()}}
(out/'audit.json').write_text(json.dumps(audit,indent=2)+'\n');print(json.dumps({'passed':True,'groups':groups,'starts':starts,'posts':requests,'strict_container_absence':len(closures),'kernel_process_checks':len(pid_observations),'relays':len(ports)}))
