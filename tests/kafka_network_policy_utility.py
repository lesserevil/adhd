"""One original Kind TCP utility and pre-cleanup diagnostics; never route proof."""
import argparse,json,os,re,secrets,subprocess,time
from pathlib import Path
from kafka_network_policy import pod,namespace_delete
from kafka_network_policy_cri import context,owned_node,owned_network
from kafka_network_policy_diagnostics import bounded,CommandUnavailable
from kafka_network_policy_readiness import capture


def main(args):
 root=args.work.absolute();assert root.resolve()==root and not root.exists();root.mkdir(mode=0o700)
 c=context();assert c and args.kind_node==c['node_name'];assert args.namespace=='adhd-netpol-utility40'
 kubectl=[str(args.kubectl.resolve()),'--kubeconfig',str(args.kubeconfig.resolve())]
 nonce=secrets.token_hex(16);uid=None;issued=False;primary=None;report={'schema':'adhd/one-kind-utility-diagnostic@1','passed':False,'diagnostic_only':True,'original_ready_passed':False,'diagnostic_completed':False,'routes_qualified':0,'fixture_pods':1,'namespace_cleanup':[],'commands':[]}
 used=0;calls=0
 def run(name,argv,seconds=40):
  nonlocal used,calls
  assert calls<16 and used<4*1024*1024;calls+=1
  code,out,err=bounded(argv,dict(os.environ),root,seconds,min(524288,4*1024*1024-used));used+=len(out)+len(err)
  row={'name':name,'returncode':code}
  import hashlib
  for label,data in [('stdout',out),('stderr',err)]:
   f=root/(str(calls)+'-'+label);f.write_bytes(data);f.chmod(0o600);row[label]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
  report['commands'].append(row);return code,out,err
 def checked(name,argv,seconds=40):
  r=run(name,kubectl+argv,seconds);assert r[0]==0,name+' failed';return r[1]
 def read(name):
  raw=checked(name,['get','namespace',args.namespace,'--ignore-not-found','-o','json']);return json.loads(raw)if raw.strip()else None
 try:
  node=run('verify-node',[c['docker']['path'],'inspect',c['node_id']]);assert node[0]==0;owned_node(json.loads(node[1])[0],c)
  network=run('verify-network',[c['docker']['path'],'network','inspect',c['network_id']]);assert network[0]==0;owned_network(json.loads(network[1])[0],c)
  assert read('namespace-absent')is None
  value={'apiVersion':'v1','kind':'Namespace','metadata':{'name':args.namespace,'labels':{'adhd-policy-owner':nonce}}}
  file=root/'namespace.json';file.write_text(json.dumps(value));file.chmod(0o600);issued=True
  checked('create-namespace',['create','-f',str(file)]);actual=read('namespace-created');assert actual['metadata']['name']==args.namespace and actual['metadata']['labels']['adhd-policy-owner']==nonce;uid=actual['metadata']['uid']
  value=pod('broker','kafka',args.namespace,args.cluster_image)
  # Exact original Pod: allow the original scheduler path, then verify owned node.
  file=root/'pod.json';file.write_text(json.dumps(value));file.chmod(0o600)
  checked('create-original-pod',['create','-f',str(file)])
  try:
   checked('original-ready30',['-n',args.namespace,'wait','--for=condition=Ready','pod/broker','--timeout=30s']);report['original_ready_passed']=True
  except (AssertionError,subprocess.TimeoutExpired,CommandUnavailable)as error:primary=error;report['original_ready_error_type']=type(error).__name__
  report['readiness_diagnostics']=capture(root/'readiness-private',kubectl,args.namespace,uid,nonce,'broker','kafka',args.cluster_image,args.kind_node)
  observation=report['readiness_diagnostics'].get('owned_node_observation')or{}
  report['diagnostic_completed']=report['readiness_diagnostics']['capture_passed']and observation.get('available')is True and observation.get('cgroup_layout_supported')is True and observation.get('cgroup_read_returncode')==0
  if primary:raise primary
 except BaseException as error:
  if primary is None:primary=error
  report['error_type']=type(error).__name__
 finally:
  errors=[]
  if issued:
   row={'namespace':args.namespace,'observed_absent':False}
   try:
    actual=read('namespace-cleanup-before')
    if actual is not None:
     assert actual['metadata']['name']==args.namespace and actual['metadata']['labels']['adhd-policy-owner']==nonce
     assert uid is None or actual['metadata']['uid']==uid;uid=actual['metadata']['uid'];row['uid']=uid
     argv,body=namespace_delete(args.namespace,uid);file=root/'delete-options.json';file.write_bytes(body);file.chmod(0o600)
     # Original namespace_delete uses stdin; fixed file carries the identical body.
     assert argv[-1]=='-';argv[-1]=str(file);checked('delete-owned-namespace',argv)
     checked('wait-owned-namespace-gone',['wait','--for=delete','namespace/'+args.namespace,'--timeout=30s'])
    assert read('namespace-cleanup-after')is None;row['observed_absent']=True
   except BaseException as error:errors.append(type(error).__name__);row['error_type']=type(error).__name__
   report['namespace_cleanup'].append(row)
  report['cleanup_errors']=errors;report['original_error_preserved']=type(primary).__name__ if primary else None;report['command_bytes']=used
  args.report.write_text(json.dumps(report,indent=2)+'\n')
 return 1 if primary or errors else 0

if __name__=='__main__':
 p=argparse.ArgumentParser();
 for n in ('kubectl','kubeconfig','work','report'):p.add_argument('--'+n,type=Path,required=True)
 for n in ('kind-node','cluster-image','namespace'):p.add_argument('--'+n,required=True)
 raise SystemExit(main(p.parse_args()))
