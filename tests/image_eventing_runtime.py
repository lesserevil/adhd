"""Owned exact-image BEAM kernel-cutover observer; no application code changes."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from container_fixture import OwnedImage
from image_eventing_fault import digest, stop_owned_process

OBSERVER = '/adhd-test/filesystem-observer.so'


def validate_observer(image, library, proof):
    library, proof = Path(library).resolve(), Path(proof).resolve()
    info = library.lstat()
    assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid()
    report = json.loads(proof.read_text())
    assert report['passed'] and report['application_started'] is False and report['owned_container_absent']
    assert report['image_config_identity'] == image and report['exit_code'] == 137
    assert report['observer']['library_sha256'] == digest(library)
    assert report['observer']['source_sha256'] == digest(Path(__file__).with_name('multi_fault.c'))
    assert report['observer']['needed_libraries'] == report['observer']['glibc_symbol_versions'] == []
    assert report['process_custody']['signal_method'] == 'ancestor-pidfd-SIGSTOP'
    return library, report


def instrument_argv(base, library, config, store, sentinel, stage):
    """Pure command adaptation; native/app bytes and PID namespace stay intact."""
    assert base[:2] == ['docker', 'run'] and '--rm' in base
    assert re.fullmatch('sha256:[a-f0-9]{64}', base[-1])
    assert '--pid' not in base and not any(value.startswith('--pid=') for value in base)
    assert stage in ('transition-decision', 'transition-project')
    result = list(base)
    result.remove('--rm')
    return result[:-1] + ['--mount', 'type=bind,src=' + str(library) + ',dst=' + OBSERVER + ',readonly',
        '--env', 'LD_PRELOAD=' + OBSERVER, '--env', 'ADHD_CRASH_STAGE=' + stage,
        '--env', 'ADHD_CRASH_CONFIG=' + str(config), '--env', 'ADHD_CRASH_STORE=' + str(store),
        '--env', 'ADHD_CRASH_SENTINEL=' + str(sentinel), result[-1]]


class EventingFaultImage(OwnedImage):
    def __init__(self, image, manifest, root, library, proof, stage, store):
        assert re.fullmatch('sha256:[a-f0-9]{64}', image)
        super().__init__(image, manifest, root)
        self.library, self.proof = validate_observer(image, library, proof)
        self.proof_sha256 = digest(proof)
        self.library_sha256 = digest(self.library)
        self.stage, self.store = stage, str(store)
        self.sentinel = Path(root) / 'transition-fault.json'
        self.armed = True
        self.config_file = None
        self.custody = []
        self.last_exit_code = None

    def argv(self, config_file):
        self.config_file = Path(config_file)
        base = super().argv(config_file)
        if not self.armed:
            base.remove('--rm')
            return base
        assert digest(self.library) == self.library_sha256
        assert self.proof['canonical_manifest_sha256'] == hashlib.sha256(self.manifest_bytes).hexdigest()
        assert self.proof['artifact_sha256'] == self.manifest['files']['hub.exs']
        return instrument_argv(base, self.library, self.config_file, self.store, self.sentinel, self.stage)

    def stop_at_observed_boundary(self, trace):
        assert self.armed and trace == {'stage': self.stage, 'pid': 1}
        self.observe()
        row = json.loads(self.docker('inspect', self.name).stdout)[0]
        mount = next(item for item in row['Mounts'] if item['Destination'] == OBSERVER)
        assert mount['Source'] == str(self.library) and mount['RW'] is False and mount['Type'] == 'bind'
        assert digest(self.library) == self.library_sha256
        arguments = ['/app/hub.exs', json.dumps(['serve', str(self.config_file)])]
        observed = stop_owned_process(row['Id'], self.image_id, trace, OBSERVER, 'beam.smp', arguments)
        self.custody.append({'container_id': row['Id'], 'image_config_identity': self.image_id,
            'stage': self.stage, 'observer_sha256': self.library_sha256, **observed})
        return observed

    def stop(self, hard=False):
        if self.name is None:
            return
        row = json.loads(self.docker('inspect', self.name).stdout)[0]
        assert row['Image'] == self.image_id
        identifier = row['Id']
        running = row['State']['Running']
        if hard:
            assert running and self.container_id == identifier, 'Hard kill requires actual live owned image'
        try:
            if running:
                self.observe()
                if hard:
                    self.docker('kill', '--signal', 'KILL', identifier)
                else:
                    self.docker('stop', '--time', '8', identifier)
            exit_code = int(self.docker('wait', identifier).stdout)
            state = json.loads(self.docker('inspect', identifier).stdout)[0]
            assert not state['State']['Running'] and state['State']['ExitCode'] == exit_code
            if hard:
                assert exit_code == 137
            self.last_exit_code = exit_code
            self.docker('rm', identifier)
            assert self.absent()
            self.events.append({'action': 'hard-killed' if hard else 'stopped', 'container_id': identifier,
                                'exit_code': exit_code, 'wait_observed': True, 'observed_absent': True})
        except BaseException:
            self.docker('rm', '--force', identifier, check=False)
            assert self.absent(), 'Owned image failure cleanup unproven'
            raise
        finally:
            self.name = self.container_id = None
            if hard:
                self.armed = False

    def identity(self):
        result = super().identity()
        result.update(observer_library_sha256=self.library_sha256, observer_loader_proof_sha256=self.proof_sha256,
                      actual_beam_kernel_custody=self.custody, observer_disarmed_after_kill=not self.armed)
        return result
