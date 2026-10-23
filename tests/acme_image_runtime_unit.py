"""Pure command/foreign-object guards; no Docker, process or socket starts."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from acme_image_runtime import OwnedACMEImage
from acme_runtime import sha

class ImageChecks(unittest.TestCase):
    def fixture(self,d):
        root=Path(d);docker=root/'docker';docker.write_bytes(b'pinned executable fixture');docker.chmod(0o700)
        manifest=root/'manifest.json';manifest.write_text(json.dumps({'schema':'adhd/container-inputs@1','files':{'hub.exs':'a'*64}}))
        return OwnedACMEImage('sha256:'+'b'*64,manifest,root,manifest_sha256=sha(manifest),artifact_sha256='a'*64,
          assets={'lego':{'path':'/app/bin/lego','sha256':'c'*64},'acme-guard':{'path':'/app/bin/acme-guard','sha256':'d'*64}},
          docker=docker,docker_sha256=sha(docker),socket_path='/reviewed/docker.sock',docker_config=root/'private-docker')

    def test_constructor_inert_and_daemon_explicit(self):
        with tempfile.TemporaryDirectory()as d,patch('acme_image_runtime.subprocess.run')as run:
            image=self.fixture(d);run.assert_not_called()
            image.docker('version');argv=run.call_args.args[0]
            self.assertEqual(argv[0],str(Path(d)/'docker'))
            self.assertEqual(run.call_args.kwargs['env']['DOCKER_HOST'],'unix:///reviewed/docker.sock')
            self.assertEqual(set(run.call_args.kwargs['env']),{'PATH','HOME','LC_ALL','DOCKER_HOST','DOCKER_CONFIG'})

    def test_foreign_or_replaced_container_never_mutated(self):
        with tempfile.TemporaryDirectory()as d:
            for field,value in [('Image','sha256:'+'e'*64),('Id','f'*64),('Name','/foreign')]:
                image=self.fixture(d);image.name='owned';image.container_id='1'*64
                row={'Name':'/owned','Image':image.expected_image,'Id':'1'*64};row[field]=value
                image.docker=Mock(return_value=SimpleNamespace(returncode=0,stdout=json.dumps([row]).encode(),stderr=b''))
                with self.assertRaises(AssertionError):image.stop()
                self.assertEqual(image.docker.call_count,1)
                self.assertEqual(image.docker.call_args.args,('inspect','owned'))

    def test_daemon_error_never_proves_absence(self):
        with tempfile.TemporaryDirectory()as d:
            image=self.fixture(d);image.name='owned'
            image.docker=Mock(return_value=SimpleNamespace(returncode=1,stdout=b'',stderr=b'Cannot connect to Docker daemon: no such file'))
            with self.assertRaises(AssertionError):image.absent()

    def test_serve_uses_explicit_absolute_config_and_retains_product_entrypoint(self):
        from acme_image_session import runtime_class
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);config=root/'hub.json';config.write_text('{}');config.chmod(0o600)
            image=self.fixture(d);image.image_id=image.expected_image;image.verify=Mock()
            argv=image.argv(config)
            self.assertNotIn('--entrypoint',argv)
            self.assertEqual(argv[-2],[image.expected_image][0])
            self.assertEqual(json.loads(argv[-1]),['serve',str(config)])
            self.assertEqual(image.expected_cmd,[argv[-1]])
            runtime=runtime_class(Mock(),root)(root,None,None,None,None,erlang=None)
            runtime.image=image
            with_env=runtime._peer_environment(argv)
            position=with_env.index(image.expected_image)
            self.assertTrue(with_env[position-1].startswith('ERL_FLAGS='))
            self.assertEqual(with_env[position+1:],image.expected_cmd)
            self.assertNotIn('--entrypoint',with_env)

    def test_offline_public_rebind_replaces_serve_command_once(self):
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);config=root/'hub.json';config.write_text('{}');config.chmod(0o600)
            image=self.fixture(d);image.image_id=image.expected_image;image.verify=Mock()
            serialized=json.dumps(['rebind-storage',{'confirm_stopped':True}]);image.expected_cmd=[serialized]
            argv=image.argv(config)
            self.assertEqual(argv[argv.index(image.expected_image)+1:],[serialized])
            self.assertEqual(image.public_command,'rebind-storage');self.assertNotIn('--entrypoint',argv)

    def test_offline_runtime_launch_keeps_exactly_one_public_command(self):
        from acme_image_session import runtime_class
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);config=root/'hub.json';config.write_text('{}');config.chmod(0o600)
            image=self.fixture(d);image.image_id=image.expected_image;image.verify=Mock();image.stop=Mock()
            target=Mock();target.image.return_value=image
            runtime=runtime_class(target,root)(root,None,None,None,None,erlang=None)
            process=Mock(pid=99124,returncode=0)
            with patch('acme_image_session.subprocess.Popen',return_value=process)as launch,\
                 patch('acme_image_session.ticks',side_effect=['42',None]),\
                 patch.object(runtime,'_observe',return_value={'owned':True}):
                completed,identity=runtime.offline_rebind({'confirm_stopped':True},root/'out',root/'err')
            argv=launch.call_args.args[0]
            tail=argv[argv.index(image.expected_image)+1:]
            self.assertEqual(len(tail),1);self.assertEqual(json.loads(tail[0]),['rebind-storage',{'confirm_stopped':True}])
            self.assertEqual(argv[argv.index('--network')+1],'none')
            self.assertEqual(completed.returncode,0);self.assertTrue(identity['reaped'])
            self.assertNotIn('--entrypoint',argv)
