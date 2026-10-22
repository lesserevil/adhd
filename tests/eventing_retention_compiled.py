#!/usr/bin/env python3
"""Compiled-image custody around the unchanged retention companion.

The original readiness loop runs first, with its original deadline. These
read-only observations add no readiness attempts, warmups or application calls.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
from unittest.mock import patch

import container_fixture
import eventing_retention_recovery as scenario
from image_filesystem_fault import RetainedImage


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def cache_files(value):
    return {
        '/runtime/adhd/boot.exs': value['boot_sha256'],
        '/runtime/adhd/build.exs': value['build_sha256'],
        '/runtime/adhd/inputs.json': value['inputs_sha256'],
        **{'/runtime/adhd/ebin/' + name: sha for name, sha in value['beams'].items()},
        **{('/proc/1/exe' if name == '/proc/self/exe' else name): sha
           for name, sha in value['toolchain']['anchors'].items()},
    }


def check_running(row, image, identifier, name):
    assert row['Id'] == identifier and row['Image'] == image
    assert row['Name'] == '/' + name and row['State']['Running']
    assert row['State']['Pid'] > 0 and row['HostConfig']['PidMode'] != 'host'
    assert row['HostConfig']['ReadonlyRootfs'] is True
    assert row['Config']['Entrypoint'] == ['elixir', '/runtime/adhd/boot.exs', '/app/hub.exs']
    for mount in row['Mounts']:
        target = mount['Destination'].rstrip('/') or '/'
        for protected in ('/app', '/runtime/adhd'):
            assert not (target == '/' or target == protected or
                        target.startswith(protected + '/') or protected.startswith(target + '/'))


class Custody:
    def __init__(self, plan, ledger):
        self.plan, self.ledger = plan, Path(ledger)
        self.images, self.starts, self.launches = [], [], []

    def save(self):
        self.ledger.write_text(json.dumps({
            'starts': self.starts, 'launches': self.launches,
            # identity() may verify an as-yet unverified image. Evidence capture
            # must never start a probe, especially on a startup failure.
            'images': [{'image_config_identity': image.image_id,
                        'container_lifecycle': image.events,
                        'payload_probe_lifecycle': image.probe_events,
                        'cleanup_blocked': getattr(image, 'cleanup_blocked', False),
                        'probe_cleanup_blocked': image.probe_cleanup_blocked}
                       for image in self.images],
        }, indent=2) + '\n')

    def observe(self, image):
        image.observe()
        identifier, name = image.container_id, image.name
        row = json.loads(image.docker('inspect', identifier).stdout)[0]
        check_running(row, self.plan['image'], identifier, name)
        assert row['Config']['Cmd'] == [json.dumps(['serve', str(image.config_file)])]
        assert row['Config']['User'] == f'{os.getuid()}:{os.getgid()}'
        manifest = self.plan['payload_manifest']
        assert image.docker('exec', identifier, 'cat', '/app/manifest.json').stdout == bytes.fromhex(self.plan['payload_manifest_hex'])
        expected = {'/app/' + key: value for key, value in manifest['files'].items() if key != 'Dockerfile'}
        assert len(expected) == 59
        cache = self.plan['cache_manifest']
        raw = image.docker('exec', identifier, 'cat', '/runtime/adhd/manifest.json').stdout
        assert digest(raw) == self.plan['cache_manifest_sha256'] and json.loads(raw) == cache
        files = cache_files(cache)
        assert len(files) == 67
        output = image.docker('exec', identifier, 'sha256sum', *expected, *files).stdout.decode().splitlines()
        observed = {line.split(None, 1)[1].strip(): line.split(None, 1)[0] for line in output}
        assert observed == {**expected, **files}
        assert image.docker('exec', identifier, 'readlink', '/proc/1/exe').stdout.decode().strip().endswith('/beam.smp')
        again = json.loads(image.docker('inspect', identifier).stdout)[0]
        check_running(again, self.plan['image'], identifier, name)
        assert again['State']['Pid'] == row['State']['Pid']
        pid = row['State']['Pid']
        start_ticks = int(Path('/proc', str(pid), 'stat').read_text().split(') ', 1)[1].split()[19])
        assert identifier not in {value['container_id'] for value in self.starts}
        self.starts.append({'container_id': identifier, 'owned_name': name, 'host_vm_pid': pid,
                            'start_ticks': start_ticks, 'app_files': 59, 'cache_and_toolchain_files': 67,
                            'same_actual_VM': True, 'default_entrypoint': True,
                            'cache_manifest_sha256': digest(raw)})
        self.save()

    def image_class(self):
        """Same strict owned-image adapter, reusable by unchanged scenarios."""
        custody = self

        class Image(RetainedImage):
            def __init__(self, image, manifest, root):
                assert image == custody.plan['image']
                super().__init__(image, manifest, root)
                custody.images.append(self)

            def docker(self, *args, check=True):
                return subprocess.run([custody.plan['docker'], *args], capture_output=True,
                                      check=check, timeout=30)

            def argv(self, config_file):
                self.config_file = Path(config_file)
                argv = super().argv(config_file)
                assert '--entrypoint' not in argv
                argv[0] = custody.plan['docker']
                custody.launches.append({'owned_name': self.name})
                custody.save()
                return argv

        return Image

    def install(self):
        custody = self

        original = scenario.TrackedFixture.start

        async def start(fixture):
            await original(fixture)
            custody.observe(fixture.image_runtime)

        return patch.object(container_fixture, 'OwnedImage', self.image_class()), patch.object(scenario.TrackedFixture, 'start', start)

    def close(self):
        failures = []
        for image in self.images:
            try:
                image.stop()
                assert not getattr(image, 'cleanup_blocked', False) and not image.probe_cleanup_blocked
                for row in image.events:
                    if row.get('container_id'):
                        assert image.authoritative_absence(image.docker('inspect', row['container_id'], check=False), row['container_id'])
                for row in image.probe_events:
                    for identifier in dict.fromkeys(v for v in (row.get('container_id'), row.get('owned_name')) if v):
                        assert image.probe_absence(image.docker('inspect', identifier, check=False), identifier)
            except BaseException as error:
                failures.append(type(error).__name__)
        for row in self.launches:
            try:
                image = self.images[0]
                row['actual_name_absent'] = image.authoritative_absence(
                    image.docker('inspect', row['owned_name'], check=False), row['owned_name'])
                assert row['actual_name_absent']
            except BaseException as error:
                failures.append(type(error).__name__)
        self.save()
        assert not failures, 'Compiled retention cleanup failures: ' + ','.join(failures)


def main():
    parser = scenario.arguments(__doc__)
    parser.add_argument('--recovery-schema', type=Path, required=True)
    parser.add_argument('--custody-plan', type=Path, required=True)
    parser.add_argument('--custody-ledger', type=Path, required=True)
    args = parser.parse_args()
    assert args.image and not (args.command or args.rest_url or args.with_model)
    plan = json.loads(args.custody_plan.read_text())
    assert plan['image'] == args.image
    custody = Custody(plan, args.custody_ledger)
    patches = custody.install()
    primary = None
    try:
        with patches[0], patches[1]:
            asyncio.run(scenario.main(args))
        assert len(custody.starts) == 3
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            custody.close()
        except BaseException as error:
            if primary is None:
                raise
            primary.add_note('Compiled custody cleanup failure: ' + type(error).__name__)


if __name__ == '__main__':
    main()
