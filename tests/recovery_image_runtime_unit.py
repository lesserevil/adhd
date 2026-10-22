#!/usr/bin/env python3
"""Pure custody/command rejection tests. Never starts Docker, hubs or HTTP."""
import asyncio
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from multi_support import arguments, Evidence
from recovery_image_runtime import (OBSERVER, ARTIFACT, ObserverImage, RecoveryImageRuntime,
    observer_argv, inspected_vm, same_vm, bind_down, finish_callback)

IMAGE='sha256:'+'a'*64
STATUS='Name:\tbeam.smp\nPid:\t1\nNSpid:\t1\n'
CMD=b'beam.smp\0'+OBSERVER.encode()+b'\0'+ARTIFACT.encode()+b'\0'


class Custody(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.root.chmod(0o700)
        self.observer=self.root/'observer.exs';self.observer.write_text('unchanged observer')
        self.manifest=self.root/'manifest.json'
        self.manifest.write_text(json.dumps({'schema':'adhd/container-inputs@1','files':{'hub.exs':'b'*64}}))
        self.row={'Id':'c'*64,'Image':IMAGE,'State':{'Running':True,'Pid':34567},
            'HostConfig':{'PidMode':'','ReadonlyRootfs':True},
            'Mounts':[{'Type':'bind','Source':str(self.observer),'Destination':OBSERVER,'RW':False}]}
    def tearDown(self):self.temp.cleanup()
    def identity(self,row=None,status=STATUS,cmd=CMD):
        return inspected_vm(row or self.row,status,'/usr/lib/erlang/beam.smp\n',cmd,IMAGE,self.observer)
    def test_argv_keeps_immutable_payload_private_pid_and_readonly_observer(self):
        base=['docker','run','--read-only','--network','host',IMAGE]
        argv=observer_argv(base,self.observer)
        self.assertEqual(argv[-3:],[IMAGE,OBSERVER,ARTIFACT])
        self.assertIn('type=bind,src='+str(self.observer)+',dst='+OBSERVER+',readonly',argv)
        self.assertEqual(base[-1],IMAGE)
    def test_reject_host_pid_or_mutable_image(self):
        for base in (['docker','run','--pid=host',IMAGE],['docker','run','--pid','host',IMAGE],
                     ['docker','run','adhd:latest'],['docker','run','--entrypoint','sh',IMAGE]):
            with self.subTest(base=base),self.assertRaises(AssertionError):observer_argv(base,self.observer)
    def test_namespace_pid_not_docker_client_or_host_pid(self):
        identity=self.identity();self.assertEqual(identity['namespace_vm_pid'],1)
        self.assertEqual(identity['host_vm_pid'],34567)
        bind_down(identity,{'nonce':'nonce','project_id':'red','reason':'killed','vm_pid':'1'},'nonce','red')
        with self.assertRaises(AssertionError):
            bind_down(identity,{'nonce':'nonce','project_id':'red','reason':'killed','vm_pid':'34567'},'nonce','red')
    def test_reject_wrong_vm_container_mount_and_namespace(self):
        for change in ('image','hostpid','writable','stopped','wrongmount'):
            row=copy.deepcopy(self.row)
            if change=='image':row['Image']='sha256:'+'d'*64
            if change=='hostpid':row['HostConfig']['PidMode']='host'
            if change=='writable':row['Mounts'][0]['RW']=True
            if change=='stopped':row['State']['Running']=False
            if change=='wrongmount':row['Mounts'][0]['Source']='/another/observer.exs'
            with self.subTest(change=change),self.assertRaises(AssertionError):self.identity(row)
        with self.assertRaises(AssertionError):self.identity(status=STATUS.replace('Pid:\t1','Pid:\t99'))
        with self.assertRaises(AssertionError):self.identity(cmd=b'beam.smp\0/app/other.exs\0')
    def test_same_vm_and_down_are_exactly_bound(self):
        first=self.identity()
        for key in ('container_id','host_vm_pid','namespace_vm_pid','image_config_identity'):
            second=first.copy();second[key]='different'
            with self.subTest(key=key),self.assertRaises(AssertionError):same_vm(first,second)
        for key in ('nonce','project_id','reason'):
            down={'nonce':'nonce','project_id':'red','reason':'killed','vm_pid':'1'};down[key]='different'
            with self.subTest(key=key),self.assertRaises(AssertionError):bind_down(first,down,'nonce','red')
    def test_constructor_rejects_observer_symlink_without_startup(self):
        link=self.root/'link';link.symlink_to(self.observer)
        with patch('subprocess.Popen',side_effect=AssertionError('Startup forbidden')),patch('subprocess.run',side_effect=AssertionError('Docker forbidden')):
            with self.assertRaises(AssertionError):ObserverImage(IMAGE,self.manifest,self.root,link)
    def test_bad_logs_fail_before_docker_or_child_and_close_partial_handle(self):
        for kind in ('symlink','hardlink'):
            work=self.root/kind;work.mkdir(mode=0o700)
            source=self.root/(kind+'-source');source.write_text('private');source.chmod(0o600)
            log=work/'stderr.log'
            if kind=='symlink':log.symlink_to(source)
            else:os.link(source,log)
            args=arguments('unit').parse_args(['--image',IMAGE,'--image-manifest',str(self.manifest),'--keep-work',str(work),'--report',str(work/'report.json')])
            runtime=RecoveryImageRuntime(args,self.observer)
            with patch('subprocess.Popen',side_effect=AssertionError('Startup forbidden')) as start,patch('subprocess.run',side_effect=AssertionError('Docker forbidden')) as docker:
                with self.assertRaises(Exception):asyncio.run(runtime.start())
                self.assertEqual(start.call_count,0);self.assertEqual(docker.call_count,0)
                self.assertEqual(runtime.logs,[]);self.assertIsNone(runtime.process)
            self.assertEqual(source.read_text(),'private')
    def test_cleanup_failure_retains_original_and_still_closes_dependent(self):
        class Failed:
            async def close(self):raise RuntimeError('owned cleanup failed')
        evidence=Evidence(self.root/'report.json','unit');closed=[];original=ValueError('original')
        with self.assertRaises(ValueError) as raised:
            asyncio.run(finish_callback(Failed(),evidence,original,lambda:closed.append(True)))
        self.assertIs(raised.exception,original);self.assertEqual(closed,[True])
        self.assertFalse(evidence.value['passed']);self.assertEqual(evidence.value['cleanup_failure_types'],['RuntimeError'])


if __name__=='__main__':unittest.main()
