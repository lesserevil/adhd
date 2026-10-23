"""Pure closed inventory and protected-broker guard checks; no resources."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import protocol22_qualification as q


class Guards(unittest.TestCase):
    def test_export_prefix_requires_actual_whole_passes_same_artifact_and_raw_bytes(self):
        with tempfile.TemporaryDirectory()as raw:
            root=Path(raw);(root/'bound/exports').mkdir(parents=True)
            stages=[]
            for name in ('schema','openapi'):
                file=root/'bound/exports'/(name+'.json');file.write_text('{"actual":"'+name+'"}')
                stages.append({'name':'export-'+name,'kind':'export','stdout':str(file)})
            before={'artifact_sha256':'exact','stages':stages};q.write(root/'bound/prior-plan.json',before)
            result={'passed':False,'artifact_sha256':'exact','plan_sha256':q.sha(root/'bound/prior-plan.json'),
              'cleanup_errors':[],'stages':[{'name':s['name'],'passed':True,'exit_code':0}for s in stages]}
            q.write(root/'bound/prior-result.json',result)
            plan={'artifact_sha256':'exact','stages':[{'name':n}for n in ['conservation26','scope-inventory','wire8']],
              'qualified_export_prefix':{'prior_plan_sha256':q.sha(root/'bound/prior-plan.json'),
              'prior_false_result_sha256':q.sha(root/'bound/prior-result.json'),
              'exports':{n+'.json':q.sha(root/'bound/exports'/(n+'.json'))for n in ('schema','openapi')}}}
            q.verify_export_prefix(root,plan)
            for mutate in [lambda p:p.update(artifact_sha256='other'),lambda p:p['qualified_export_prefix']['exports'].update({'schema.json':'wrong'})]:
                bad=copy.deepcopy(plan);mutate(bad)
                with self.assertRaises(AssertionError):q.verify_export_prefix(root,bad)
            changed=copy.deepcopy(result);changed['stages'][1]['passed']=False
            (root/'bound/prior-result.json').write_text(json.dumps(changed))
            plan['qualified_export_prefix']['prior_false_result_sha256']=q.sha(root/'bound/prior-result.json')
            with self.assertRaises(AssertionError):q.verify_export_prefix(root,plan)

    def test_exact_inventory_rejects_redirect_and_tracks_empty_directory(self):
        with tempfile.TemporaryDirectory()as raw:
            root=Path(raw);(root/'input').write_bytes(b'actual bytes');expected=q.inventory(root)
            (root/'extra').mkdir();self.assertNotEqual(q.inventory(root),expected)
            (root/'extra').rmdir();(root/'input').unlink();(root/'input').symlink_to('/dev/null')
            with self.assertRaises(AssertionError):q.inventory(root)

    def test_broker_identity_and_ownership_or_cluster_drift_reject(self):
        row={'Id':'a'*64,'Name':'/owned','Image':'sha256:'+'b'*64,'RestartCount':0,
          'State':{'Running':True,'StartedAt':'original'},'NetworkSettings':{'Networks':{},'Ports':{}},
          'Config':{'Labels':{'com.docker.compose.project':'adhd-event-qual'}}}
        expected={k:row[k]for k in ('Id','Name','Image','RestartCount')}
        expected.update(StartedAt='original',Running=True,Networks={},Ports={},Labels=row['Config']['Labels'])
        plan={'broker_containers':[expected],'docker':'/bound/docker','rest_url':'http://127.0.0.1:18082','cluster_id':'owned'}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return b'{"data":[{"cluster_id":"owned"}]}'
        with patch.object(q,'urlopen',return_value=Response())as get,patch.object(q.subprocess,'check_output',return_value=json.dumps([row]).encode())as run:
            q.broker(plan);run.assert_called_once_with(['/bound/docker','inspect','a'*64]);get.assert_called_once_with('http://127.0.0.1:18082/v3/clusters',timeout=5)
        for change in [lambda r:r.update(Image='sha256:'+'c'*64),lambda r:r['State'].update(StartedAt='new'),
                       lambda r:r['Config']['Labels'].update({'com.docker.compose.project':'foreign'})]:
            changed=copy.deepcopy(row);change(changed)
            with patch.object(q.subprocess,'check_output',return_value=json.dumps([changed]).encode()),patch.object(q,'urlopen')as get:
                with self.assertRaises(AssertionError):q.broker(plan)
                get.assert_not_called()


if __name__=='__main__':unittest.main()
