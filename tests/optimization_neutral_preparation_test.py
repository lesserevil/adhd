#!/usr/bin/env python3
"""Read-only preparation guards. No application, Docker or provider startup."""
import asyncio
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from optimization_neutral_pair import (IMAGE_SERVER, NATIVE_ROOT, BUDGET,
    config_profile, main, original_bindings, parent_manifest, template, validate_plan)
from optimization_neutral_runtime import (SealedRuntime, canonical, private_seal,
    sha, validate_target, verify_pins, verify_seal)
from optimization_neutral_witness import original_gap_requirement

PARENT=Path(__file__).with_name('fixtures')/'optimizer-neutral-provider-prepared.json'


class Preparation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.parent=parent_manifest(PARENT)
    def setUp(self):
        self.stack=[]
        for name in ('subprocess.Popen','subprocess.run'):
            mock=patch(name,side_effect=AssertionError('No process startup in preparation checks'));mock.start();self.stack.append(mock)
    def tearDown(self):
        for mock in reversed(self.stack):mock.stop()
    def test_prospective_plan_no_runtime_calls(self):
        p=template(self.parent);validate_plan(p,self.parent)
        self.assertEqual(p['budgets']['per_runtime'],BUDGET)
        self.assertEqual(p['budgets']['aggregate_posts'],212)
        self.assertEqual(p['order'],['native','image'])
        self.assertTrue(p['execution_hold'])
        self.assertIsNone(p['targets']['image']['artifact_sha256'])
    def test_semantic_gold_cannot_be_amended_by_target_update(self):
        p=template(self.parent);p['semantic_plan']['preregistration']['cases'][6]['gold']['expectation']='supported'
        with self.assertRaises(AssertionError):validate_plan(p,self.parent)
    def test_identity_and_broker_cannot_be_reselected(self):
        for leg,key,value in [('native','fixture_root','/tmp/other'),('image','server_id','b'*32),('image','broker_rest_url','http://127.0.0.1:18082')]:
            p=template(self.parent);p['targets'][leg][key]=value
            with self.assertRaises(AssertionError):validate_plan(p,self.parent)
    def test_budget_order_cannot_borrow_or_adapt(self):
        for key,value in [('order',['image','native']),('adapt_to_other_result',True),('one_proposal_per_runtime',False)]:
            p=template(self.parent);p[key]=value
            with self.assertRaises(AssertionError):validate_plan(p,self.parent)
        p=template(self.parent);p['budgets']['aggregate_posts']=213
        with self.assertRaises(AssertionError):validate_plan(p,self.parent)
    def test_historical_manifest_bytes_remain_exact(self):
        self.assertEqual(sha(PARENT.read_bytes()),'b069fdf8f7bf4ff5e85754850cedc42deb6ef28dd7c5c876b3869df8a1f6724f')
    def test_dependency_closure_pins_critical_validators_and_container(self):
        p=template(self.parent);verify_pins(p['python_dependency_sha256'])
        for name in ('optimization_validation.py','optimization_provider_io.py','container_fixture.py','protocol_acceptance.py'):
            self.assertIn(name,p['python_dependency_sha256'])
        p['python_dependency_sha256']['optimization_validation.py']='0'*64
        with self.assertRaises(AssertionError):verify_pins(p['python_dependency_sha256'])
        p=template(self.parent);p['python_dependency_sha256'].pop('container_fixture.py')
        with self.assertRaises(AssertionError):validate_plan(p,self.parent)
    def test_existing_six_originals_are_same_exact_bindings(self):
        original_bindings(self.parent,{'server_id':self.parent['preregistration']['target']['server_id']},self.parent['continuation']['original_records'])
        altered=copy.deepcopy(self.parent['continuation']['original_records']);altered['train01:2']['publication']['text']='New answer'
        with self.assertRaises(AssertionError):original_bindings(self.parent,{'server_id':self.parent['preregistration']['target']['server_id']},altered)
    def test_image_server_is_fixed_derivation(self):
        self.assertEqual(IMAGE_SERVER,sha(b'neutral-index-witness:image:final37')[:32])
    def test_native_constructor_preserves_existing_installation(self):
        root=Path(NATIVE_ROOT);before=private_seal(root)
        target={'kind':'native','fixture_root':str(root),'server_id':self.parent['preregistration']['target']['server_id'],
            'broker_rest_url':'http://127.0.0.1:18082','artifact_sha256':'a'*64}
        args=SimpleNamespace(keep_work=root,with_model=False,image=None,image_manifest=None,rest_url=None,
            eventing_rest_url=target['broker_rest_url'])
        f=SealedRuntime(args,target,adopt=True)
        self.assertEqual(f.config,json.loads((root/'hub.json').read_bytes()))
        self.assertIsNone(f.process);asyncio.run(f.close());self.assertEqual(private_seal(root),before)
    def test_native_constructor_rejects_unknown_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with self.assertRaises(FileNotFoundError):SealedRuntime(None,{'fixture_root':str(root)},adopt=True)
    def test_seal_rejects_tampering_extra_files_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);root.chmod(0o700)
            for name in ('hub.json','hub.json.stores','hub.json.stores.marker'):
                (root/name).write_text('{}');(root/name).chmod(0o600)
            initial=private_seal(root);verify_seal(root,initial)
            (root/'hub.json').write_text('{"changed":true}')
            with self.assertRaises(AssertionError):verify_seal(root,initial)
            (root/'hub.json').write_text('{}');(root/'extra').symlink_to(root/'hub.json')
            with self.assertRaises(AssertionError):private_seal(root)
    def test_exact_image_manifest_validation_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);payload=b'not executed';(root/'hub').write_bytes(payload)
            raw=canonical({'schema':'adhd/container-inputs@1','files':{'hub.exs':sha(payload)}});(root/'manifest').write_bytes(raw)
            target={'kind':'image','server_id':IMAGE_SERVER,'fixture_root':str(root/'new'),
                'artifact_sha256':sha(payload),'broker_rest_url':'http://127.0.0.1:18085',
                'image_config_identity':'sha256:'+'a'*64,'image_manifest':str(root/'manifest'),'canonical_manifest_sha256':sha(raw)}
            validate_target(target,root/'hub')
            target['canonical_manifest_sha256']='b'*64
            with self.assertRaises(AssertionError):validate_target(target,root/'hub')
    def test_profile_rejects_pending_optimizer_or_federation(self):
        base={k:copy.deepcopy(self.parent['preregistration'][k]) for k in ('history','archive')}
        base['retrieval']={'recipe':self.parent['preregistration']['recipe']};config_profile(base,self.parent)
        for key,value in [('optimization',{'enabled':True}),('federation',{'peers':[{}]})]:
            changed=copy.deepcopy(base);changed[key]=value
            with self.assertRaises(AssertionError):config_profile(changed,self.parent)
    def test_scan_only_control_does_not_forge_training_gap(self):
        query={'search':None,'assessment':None,'fallback_reasons':[]}
        detail={'recipe':None,'adjudicated_diagnosis':'confirmed_exhaustive_scan'}
        original_gap_requirement(query,detail,{'cohort':'regression'},self.parent['preregistration']['recipe'])
        with self.assertRaises(AssertionError):original_gap_requirement(query,detail,{'cohort':'training'},self.parent['preregistration']['recipe'])
        query.update(search={'status':'completed','error':None,'candidates':[]},fallback_reasons=['no_candidates'])
        detail.update(recipe=self.parent['preregistration']['recipe'],adjudicated_diagnosis='confirmed_retrieval_gap')
        original_gap_requirement(query,detail,{'cohort':'training'},self.parent['preregistration']['recipe'])
        query['search']['candidates']=[{}]
        with self.assertRaises(AssertionError):original_gap_requirement(query,detail,{'cohort':'training'},self.parent['preregistration']['recipe'])
    def test_unbound_final_targets_cannot_start_preflight_or_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'plan.json';path.write_text(json.dumps(template(self.parent)))
            for phase in ('preflight-native','preflight-image','run'):
                args=SimpleNamespace(parent_manifest=PARENT,phase=phase,manifest=path)
                with patch('optimization_neutral_pair.RefusingModel',side_effect=AssertionError('Guard startup forbidden')) as guard:
                    with self.assertRaises(AssertionError):asyncio.run(main(args))
                    guard.assert_not_called()


if __name__=='__main__':unittest.main(verbosity=2)
