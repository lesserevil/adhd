"""Static optional listener overlays; no Compose/Kubernetes/API execution."""
from pathlib import Path
import unittest,yaml
ROOT=Path(__file__).resolve().parents[1]/'deploy'
class Templates(unittest.TestCase):
 def test_compose_adds_only_public_challenge_and_tls(self):
  base=yaml.safe_load((ROOT/'app.compose.yaml').read_text());overlay=yaml.safe_load((ROOT/'app.acme.compose.yaml').read_text())
  self.assertEqual(overlay,{'services':{'hub':{'ports':['80:8080','443:8443']}}})
  self.assertEqual(base['services']['hub']['ports'],['127.0.0.1:${ADHD_PORT:-8766}:8766'])
  hub=base['services']['hub'];self.assertTrue(hub['read_only']);self.assertEqual(hub['cap_drop'],['ALL']);self.assertEqual(hub['environment']['ADHD_CONFIG_FILE'],'/config/hub.json')
  self.assertEqual({v['target'] for v in hub['volumes']},{'/config','/data'})
 def test_kubernetes_patch_changes_only_listener_declarations(self):
  patch=yaml.safe_load((ROOT/'k8s/acme/hub-listeners.yaml').read_text())
  self.assertEqual(patch['spec'],{'template':{'spec':{'containers':[{'name':'hub','ports':[{'name':'acme-http01','containerPort':8080},{'name':'native-https','containerPort':8443}]}]}}})
  base=list(yaml.safe_load_all((ROOT/'k8s/hub.yaml').read_text()));deploy=next(x for x in base if x['kind']=='Deployment')
  self.assertEqual(deploy['spec']['replicas'],1);self.assertEqual(deploy['spec']['strategy']['type'],'Recreate')
  hub=deploy['spec']['template']['spec']['containers'][0];self.assertTrue(hub['securityContext']['readOnlyRootFilesystem']);self.assertFalse(hub['securityContext']['allowPrivilegeEscalation'])
  self.assertEqual(next(v for v in hub['volumeMounts'] if v['mountPath']=='/config')['name'],'state')
 def test_public_service_does_not_publish_private_http(self):
  s=yaml.safe_load((ROOT/'k8s/acme/public-service.yaml').read_text());self.assertEqual(s['spec']['type'],'LoadBalancer');self.assertEqual(s['spec']['selector'],{'app':'hub'})
  self.assertEqual(s['spec']['ports'],[{'name':'acme-http01','port':80,'targetPort':'acme-http01','protocol':'TCP'},{'name':'native-https','port':443,'targetPort':'native-https','protocol':'TCP'}])
  k=yaml.safe_load((ROOT/'k8s/acme/kustomization.yaml').read_text());self.assertEqual(k['resources'],['..','public-service.yaml']);self.assertEqual(k['patches'],[{'path':'hub-listeners.yaml'}])
if __name__=='__main__':unittest.main()
