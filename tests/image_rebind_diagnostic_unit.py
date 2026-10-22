"""No-startup regression: actual observer retains sanitized mismatch and rejects it."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from image_rebind_runtime import ImageRebindRuntime


class ArgumentDiagnosticTest(unittest.TestCase):
    def test_mismatch_is_retained_before_original_assertion(self):
        secret='never-retain-this-request-secret'
        serialized=json.dumps(['rebind-storage',{'credential':secret}])
        row={'Id':'a'*64,'Image':'sha256:'+'b'*64,'Name':'/owned',
             'Config':{'User':f'{os.getuid()}:{os.getgid()}','Cmd':[serialized]},
             'HostConfig':{'PidMode':'','Privileged':False,'NetworkMode':'none'},
             'State':{'Running':True,'Pid':123,'Status':'running'}}
        target=SimpleNamespace(name='owned',image_id=row['Image'],
            docker=lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps([row])))
        session={'target':target,'process':SimpleNamespace(poll=lambda:None),
                 'command_kind':'rebind-storage','serialized':serialized,'offline':True}
        owner=object.__new__(ImageRebindRuntime)
        def link(path):
            if path.endswith('/exe'):return '/runtime/beam.smp'
            return 'pid:[private]' if '/123/' in path else 'pid:[host]'
        with patch('image_rebind_runtime.os.readlink',side_effect=link), \
             patch.object(Path,'read_bytes',return_value=b'beam\0/app/hub.exs\0different-command\0'), \
             patch.object(Path,'read_text',return_value='123 (beam) '+' '.join(['S']+['0']*18+['987'])):
            with self.assertRaises(AssertionError):owner.observe_vm(session,float('inf'))
        observations=target.rebind_argument_observations
        self.assertIs(observations,session['argument_observations'])
        self.assertEqual(len(observations),1)
        proof=observations[0]
        self.assertEqual([t['matched'] for t in proof['expected_tokens']],[True,False])
        self.assertTrue(proof['docker_cmd_equals_serialized'])
        self.assertTrue(proof['stable_proc_identity_before_assert'])
        self.assertEqual(proof['vm_start_time_ticks'],'987')
        self.assertNotIn(secret,json.dumps(proof))
        self.assertNotIn('different-command',json.dumps(proof))
        self.assertEqual(proof['actual_token_count'],4)
        self.assertNotIn('custody',session)


if __name__=='__main__':unittest.main()
