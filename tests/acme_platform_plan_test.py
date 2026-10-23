"""Inert deployment recipes: no sockets, commands, apps, CA or clusters."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('plan',Path(__file__).with_name('acme_platform_plan.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Plans(unittest.TestCase):
 def test_no_implicit_execute_or_shell(self):
  self.assertFalse(hasattr(m,'execute'))
  with patch('subprocess.run',side_effect=AssertionError('forbidden')),patch('subprocess.Popen',side_effect=AssertionError('forbidden')):
   for platform in ['compose','kind']:
    row=m.recipe(platform)
    self.assertEqual(row['public_ca_calls'],0);self.assertEqual(row['broker_starts'],0)
    self.assertTrue(all(isinstance(v,list) for v in row['commands']))
 def test_serial_platforms_retain_full_scenario_and_original_bounds(self):
  a,b=m.recipe('compose'),m.recipe('kind')
  self.assertEqual(a['checks'],b['checks']);self.assertEqual(len(a['checks']),13)
  self.assertEqual(a['scenario'],b['scenario'])
  self.assertEqual(a['bounds'],b['bounds']);self.assertEqual(a['bounds']['scheduled_renewal_seconds'],100)
  self.assertEqual(a['bounds']['initial_issuance_seconds'],35)
  self.assertIn('same_vm',a['checks'][7]);self.assertIn('same_volume',a['checks'][10])
 def test_public_private_listener_mapping_and_no_dependencies(self):
  a=m.recipe('compose')
  self.assertEqual(a['fixture_changes']['ports_override'],['127.0.0.1:18766:8766','127.0.0.2:80:8080','127.0.0.2:443:8443'])
  self.assertTrue(all('--no-deps' in command for command in a['commands']))
  self.assertEqual(a['tls_public_patch']['port'],8443);self.assertEqual(a['tls_public_patch']['challenge_port'],8080)
 def test_kind_fresh_cluster_retains_service_and_pvc_security_boundary(self):
  row=m.recipe('kind');self.assertEqual(row['owned_cluster'],'adhd-acme-platform01')
  self.assertNotIn('adhd-event-qual',str(row['commands']))
  self.assertEqual([p['hostPort'] for p in row['fixture_changes']['kind_published_ports']],[80,443])
  self.assertIn('UID precondition',row['cleanup']);self.assertIn('PVCUID',row['custody'])
  self.assertIn('No cloud-provider',row['fixture_changes']['public_service'])
 def test_same_real_ca_and_exclusive_relay_no_rewrite(self):
  for platform in ['compose','kind']:
   row=m.recipe(platform);self.assertEqual(row['endpoints']['challenge_relay'],'127.0.0.1:8080')
   self.assertEqual(row['endpoints']['relay_upstream'],'127.0.0.2:80')
   self.assertEqual(row['endpoints']['issuer'],'https://pebble:19104/dir')
   self.assertIn('No TLS termination',row['issuer_gateway'])
   self.assertEqual(row['tls_public_patch']['acme']['order_timeout_ms'],30000)
 def test_unknown_platform_rejected(self):
  for bad in ['docker','k8s','',None]:
   with self.assertRaises(AssertionError):m.recipe(bad)

if __name__=='__main__':unittest.main()
