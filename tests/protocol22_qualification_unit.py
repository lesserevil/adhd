"""Pure closed inventory and protected-broker guard checks; no resources."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import protocol22_qualification as q


class Guards(unittest.TestCase):
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
