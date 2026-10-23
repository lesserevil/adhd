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
