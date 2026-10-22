"""Pure evidence grammar/resource identity checks; no Docker or process starts."""
import subprocess
import unittest
from recovery_full25_terminal_audit import authoritative_absence,owned_resources


class AuditTest(unittest.TestCase):
    def test_absence_requires_exact_daemon_grammar_identifier_and_exit(self):
        name='adhd-owned-fixture'
        def row(code=1,err=None,out=b'[]'):
            return subprocess.CompletedProcess([],code,out,err or('error: no such object: '+name).encode())
        self.assertTrue(authoritative_absence(row(),name))
        for value in [row(code=0),row(code=2),row(out=b'{}'),
                      row(err=b'error: no such object: foreign'),
                      row(err=('error: no such object: '+name+'\ndaemon unavailable').encode()),
                      row(err=b'cannot connect to Docker daemon: no such object')]:
            self.assertFalse(authoritative_absence(value,name))

    def test_namespace_pid_is_not_invented_host_process_identity(self):
        cid='a'*64
        ids,names,pids=owned_resources([{'container_id':cid,'namespace_pid':1,
            'host_vm_pid':123,'vm_start_time_ticks':'456','owned_name':'adhd-known',
            'child':{'host_container_pid':789,'namespace_pid':1},'name':'arbitrary'}])
        self.assertEqual(ids,{cid});self.assertEqual(names,{'adhd-known'})
        self.assertEqual(pids,{(123,'456'),(789,None)})

if __name__=='__main__':unittest.main()
