"""Pure actual-schema bridge validation; no receipt or application writes."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from source_authority_bridge import derive,compare_contexts,digest

ROOT=Path(__file__).absolute().parents[1]
OLD=ROOT/'verification/eventing-readiness-source41/admission'


class BridgeTest(unittest.TestCase):
    def fixtures(self):
        old=json.loads((OLD/'manifest.json').read_text())
        plan=json.loads((OLD/'retained-plan.json').read_text())
        receipt=json.loads((OLD/'receipt.json').read_text())
        rebuild=json.loads((OLD/'rebuild.json').read_text())
        return plan,receipt,rebuild,old,old['artifact_sha256']

    def test_actual_previous_passing_chain_derives_five_fields(self):
        plan,receipt,rebuild,old,artifact=self.fixtures()
        result=derive(plan,receipt,rebuild,old,artifact)
        self.assertEqual(result,{key:old[key]for key in result})

    def test_stale_or_failed_chain_rejected(self):
        baseline=self.fixtures()
        for mutate in [lambda p,r,b,o:r['receipt'].update(result='sha256:'+'0'*64),
                       lambda p,r,b,o:b['result'].update(passed=False),
                       lambda p,r,b,o:b['result'].update(receipt_committed=False),
                       lambda p,r,b,o:b['result'].update(project_revision_identity='sha256:'+'0'*64),
                       lambda p,r,b,o:b['result'].update(component_lock_identity='sha256:'+'0'*64),
                       lambda p,r,b,o:b['result']['test_summary'].update(passed=17)]:
            plan,receipt,rebuild,old,artifact=copy.deepcopy(baseline);mutate(plan,receipt,rebuild,old)
            with self.assertRaises(AssertionError):derive(plan,receipt,rebuild,old,artifact)

    def test_context_complete_set_and_bytes_required(self):
        with tempfile.TemporaryDirectory()as directory:
            old=Path(directory)/'old';new=Path(directory)/'new';old.mkdir();new.mkdir()
            body=json.dumps({'files':{str(i):'x'for i in range(60)}}).encode()
            for root in(old,new):(root/'manifest.json').write_bytes(body);(root/'payload.tar').write_bytes(b'actual-payload')
            self.assertTrue(compare_contexts(old,new,digest(body))['passed'])
            (new/'extra').write_bytes(b'x')
            with self.assertRaises(AssertionError):compare_contexts(old,new,digest(body))
            (new/'extra').unlink();(new/'payload.tar').write_bytes(b'changed')
            with self.assertRaises(AssertionError):compare_contexts(old,new,digest(body))
            (new/'payload.tar').unlink();(new/'payload.tar').symlink_to(old/'payload.tar')
            with self.assertRaises(AssertionError):compare_contexts(old,new,digest(body))

if __name__=='__main__':unittest.main()
