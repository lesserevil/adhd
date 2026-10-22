#!/usr/bin/env python3
"""Read-only preparation guards. No application, Docker or provider startup."""
import asyncio
import copy
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from optimization_neutral_pair import (IMAGE_SERVER, NATIVE_ROOT, BUDGET,
    config_profile,continuation_safe,failure_class,main,original_bindings,parent_manifest,template,validate_plan)
from optimization_neutral_runtime import (SealedRuntime, canonical, private_seal,
    CustodyViolation,ExperimentFailed,ProviderUnavailable,RuntimeUnavailable,
    append_held_log,safe_append,sha,validate_target,verify_pins,verify_seal)
from optimization_neutral_witness import ProviderBudget,original_gap_requirement

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
    def test_excluded_logs_still_reject_symlink_and_hardlink(self):
        for kind in ('symlink','hardlink'):
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);root.chmod(0o700)
                for name in ('hub.json','hub.json.stores','hub.json.stores.marker'):
                    (root/name).write_text('{}');(root/name).chmod(0o600)
                target=root/'synthetic-target';target.write_text('unchanged');target.chmod(0o600)
                if kind=='symlink':(root/'stdout.log').symlink_to(target)
                else:os.link(target,root/'stdout.log')
                with self.assertRaises(CustodyViolation):private_seal(root)
                with self.assertRaises(CustodyViolation):safe_append(root/'stdout.log')
                self.assertEqual(target.read_text(),'unchanged')
    def test_bad_subprocess_logs_prevent_native_or_image_startup(self):
        for kind in ('native','image'):
            for link in ('symlink','hardlink'):
                with tempfile.TemporaryDirectory() as directory:
                    root=Path(directory);root.chmod(0o700)
                    payload=root/'payload';payload.write_text('not executable');manifest=root/'manifest'
                    manifest.write_bytes(canonical({'schema':'adhd/container-inputs@1','files':{'hub.exs':sha(payload.read_bytes())}}))
                    config={'server_id':'a'*32,'agents':{'bridge':'synthetic-not-live'},'port':12345,'eventing':{'rest_url':'http://127.0.0.1:18085'}}
                    (root/'hub.json').write_text(json.dumps(config));(root/'hub.json').chmod(0o600)
                    target={'kind':kind,'fixture_root':str(root),'server_id':'a'*32,'broker_rest_url':config['eventing']['rest_url'],
                        'artifact_sha256':sha(payload.read_bytes()),'image_config_identity':'sha256:'+'b'*64,'canonical_manifest_sha256':sha(manifest.read_bytes())}
                    args=SimpleNamespace(keep_work=root,with_model=False,image=target['image_config_identity'] if kind=='image' else None,
                        image_manifest=manifest,rest_url=None,eventing_rest_url=config['eventing']['rest_url'],hub=payload)
                    # The first handle opens, then bad stderr must reject before
                    # argv/image probes/Popen, and finally close that first FD.
                    sink=root/'synthetic-target';sink.write_text('untouched');sink.chmod(0o600)
                    if link=='symlink':(root/'stderr.log').symlink_to(sink)
                    else:os.link(sink,root/'stderr.log')
                    f=SealedRuntime(args,target,adopt=True)
                    with patch('optimization_neutral_runtime.subprocess.Popen') as popen:
                        with self.assertRaises(CustodyViolation):asyncio.run(f.start())
                        popen.assert_not_called()
                    handles=list(f.logs);asyncio.run(f.close())
                    self.assertTrue(handles and all(handle.closed for handle in handles))
                    self.assertEqual(sink.read_text(),'untouched')
                    if f.image_runtime:self.assertFalse(f.image_runtime.verified)
    def test_safe_append_rejects_replace_during_open_and_closes_fd(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'log';path.write_text('original');opened=[];real_open=os.open
            def replaced(*args,**kwargs):
                fd=real_open(*args,**kwargs);opened.append(fd)
                path.unlink();path.write_text('replacement');return fd
            with patch('optimization_neutral_runtime.os.open',side_effect=replaced):
                with self.assertRaises(CustodyViolation):safe_append(path)
            with self.assertRaises(OSError):os.fstat(opened[0])
    def test_final_subprocess_log_inode_checked_after_close(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);root.chmod(0o700)
            target={'kind':'native','fixture_root':str(root),'server_id':'a'*32,'broker_rest_url':'http://127.0.0.1:18082'}
            (root/'hub.json').write_text(json.dumps({'server_id':'a'*32,'agents':{},'port':12345,'eventing':{'rest_url':target['broker_rest_url']}}));(root/'hub.json').chmod(0o600)
            args=SimpleNamespace(keep_work=root,with_model=False,image=None,rest_url=None,eventing_rest_url=target['broker_rest_url'])
            f=SealedRuntime(args,target,adopt=True);path=root/'stdout.log';handle=safe_append(path);info=os.fstat(handle.fileno())
            f.logs=[handle];f.log_identities={'stdout.log':(info.st_dev,info.st_ino)}
            path.unlink();path.write_text('replaced')
            with self.assertRaises(CustodyViolation):asyncio.run(f.close())
            self.assertTrue(handle.closed);self.assertTrue(f.custody_failures)
    def test_failure_classes_and_continuation_require_clean_independent_proof(self):
        proof={key:True for key in ('owned_runtime_closed','relay_closed','no_budget_scope_violation','current_custody_valid')}
        for error,expected in [(None,'none'),(ExperimentFailed('gold'),'experiment_failed'),(ProviderUnavailable('typed response'),'provider_unavailable'),
            (RuntimeUnavailable('readiness'),'runtime_unavailable'),(AssertionError('unknown'),'harness_error'),(CustodyViolation('wrong cluster'),'custody_violation')]:
            observed=failure_class(error,'experiment');self.assertEqual(observed,expected)
            allowed=expected in ('none','experiment_failed','provider_unavailable','runtime_unavailable')
            self.assertEqual(continuation_safe(observed,proof,pins_intact=True,unrun_seals_intact=True),allowed)
        for key in proof:
            broken={**proof,key:False};self.assertFalse(continuation_safe('experiment_failed',broken,pins_intact=True,unrun_seals_intact=True))
        self.assertFalse(continuation_safe('provider_unavailable',proof,pins_intact=False,unrun_seals_intact=True))
        self.assertFalse(continuation_safe('runtime_unavailable',proof,pins_intact=True,unrun_seals_intact=False))
        self.assertEqual(failure_class(ExperimentFailed('quality'),'experiment',cleanup_failed=True),'cleanup_failed')
        self.assertEqual(failure_class(None,'experiment',budget_violations=True),'budget_scope_violation')
    def test_provider_log_replacement_detected_after_zero_call_close(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'log';manifest={'provider':{'url':'http://127.0.0.1:9/never-called','model':'fixture'},'provider_budget':BUDGET,
                'preregistration':{'cases':[{'question':'not sent'}]}}
            relay=ProviderBudget(manifest,path);path.unlink();path.write_text('replaced');path.chmod(0o600)
            with self.assertRaises(CustodyViolation):append_held_log(relay.log_handle,path,relay.log_identity,b'not written')
            self.assertEqual(path.read_text(),'replaced');self.assertEqual(os.lseek(relay.log_handle.fileno(),0,os.SEEK_END),0)
            with self.assertRaises(CustodyViolation):relay.close()
            self.assertEqual(relay.count,0);self.assertEqual(relay.inflight,0);self.assertEqual(relay.handlers,0)
            self.assertFalse(relay.thread.is_alive());self.assertFalse(relay.timer.is_alive());self.assertTrue(relay.custody_errors)
            self.assertTrue(relay.log_handle.closed)
    def test_partial_relay_construction_closes_own_server_before_error(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest={'provider':{'url':'http://127.0.0.1:9/never-called','model':'fixture'},'provider_budget':BUDGET,
                'preregistration':{'cases':[{'question':'not sent'}]}}
            before={t.ident for t in threading.enumerate()}
            handles=[]
            def tracked(*args,**kwargs):
                handle=safe_append(*args,**kwargs);handles.append(handle);return handle
            with patch('optimization_neutral_witness.safe_append',side_effect=tracked):
                with patch('threading.Timer.start',side_effect=RuntimeError('owned synthetic timer fault')):
                    with self.assertRaises(RuntimeError):ProviderBudget(manifest,Path(directory)/'log')
            self.assertEqual({t.ident for t in threading.enumerate()},before)
            self.assertTrue(handles and all(handle.closed for handle in handles))


if __name__=='__main__':unittest.main(verbosity=2)
