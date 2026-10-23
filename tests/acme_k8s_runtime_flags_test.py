"""Shipped K8s runtime bound and exact-PID1 limit custody; no runtime starts."""
from pathlib import Path
import copy,json,subprocess,tempfile,unittest
from unittest.mock import patch
import yaml
import acme_platform_adapters as adapters

class Flags(unittest.TestCase):
 def hub(self):
  docs=list(yaml.safe_load_all((Path(__file__).resolve().parents[1]/'deploy/k8s/hub.yaml').read_text()))
  return next(d for d in docs if d['kind']=='Deployment')['spec']['template']['spec']['containers'][0]
 def test_shipped_bound_preserves_memory_cpu_security_entrypoint(self):
  hub=self.hub();self.assertEqual(adapters.bounded_runtime_flags(hub),'+S 2:2 +Q 65536')
  self.assertEqual(hub['resources']['limits'],{'cpu':'2','memory':'1Gi'})
  self.assertNotIn('command',hub);self.assertNotIn('args',hub);self.assertTrue(hub['securityContext']['readOnlyRootFilesystem'])
  self.assertEqual(hub['securityContext']['capabilities']['drop'],['ALL'])
 def test_missing_duplicate_unbounded_conflicting_flags_denied(self):
  for change in [lambda h:h.update(env=[e for e in h['env'] if e['name']!='ERL_FLAGS']),lambda h:h['env'].append({'name':'ERL_FLAGS','value':'+S 2:2 +Q 65536'}),lambda h:h['env'][0].update(value='+S 2:2'),lambda h:h['env'][0].update(value='+S 2:2 +Q 1073741824'),lambda h:h['env'].append({'name':'ERL_AFLAGS','value':'+Q 1073741824'}),lambda h:h['env'][0].update(valueFrom={'secretKeyRef':{}})]:
   hub=self.hub();change(hub)
   with self.assertRaises(AssertionError):adapters.bounded_runtime_flags(hub)
 def test_actual_pid1_limits_retained_with_same_vm_start_and_pod_uid(self):
  for bad in (None,'pid','pod'):
   with tempfile.TemporaryDirectory() as raw:
    k=adapters.Kind.__new__(adapters.Kind);k.work=Path(raw);k.node_id='a'*64;k.image='sha256:'+'b'*64
    row={'metadata':{'name':'hub-owned','uid':'pod-uid'},'spec':{'containers':[self.hub()]},'status':{'containerStatuses':[{'containerID':'containerd://'+'c'*64}]}}
    calls=[]
    def observe():
     v=copy.deepcopy(row)
     if bad=='pod' and calls:v['metadata']['uid']='foreign'
     return v
    k.observe=observe;k.image_identity=lambda r:None
    def command(*args,**kwargs):
     calls.append(args);self.assertEqual(args[:6],('exec','hub-owned','-c','hub','--','/bin/busybox'))
     if args[-1].endswith('/limits'):out=b'Max open files            1073741816           1073741816           files\n'
     else:
      fields=['S']+['0']*19;fields[19]='changed' if bad=='pid' else '12345';out=('1 (beam.smp) '+' '.join(fields)+'\n').encode()
     return subprocess.CompletedProcess(args,0,out,b'')
    k.namespaced=command
    with patch.object(adapters.vm,'kind',return_value={'process':{'start_ticks':'12345'}}):
     if bad:
      with self.assertRaises(AssertionError):k.custody()
     else:
      proof=k.custody();self.assertEqual(proof['inherited_open_files']['soft'],'1073741816');self.assertEqual(len(list(k.work.glob('pid1-limits-*.txt'))),1)

if __name__=='__main__':unittest.main()
