#!/usr/bin/env python3
"""Observe the unchanged OIDC policy gate with retained container/VM custody."""
import argparse
import hashlib
import json
from pathlib import Path
import os
import sys

import oidc_policy as policy
from image_filesystem_fault import RetainedImage


def vm_identity(row):
    pid = row['State']['Pid']
    assert type(pid) is int and pid > 0 and row['State']['Running']
    root = Path('/proc') / str(pid)
    raw = (root/'stat').read_text().rsplit(')', 1)[1].split()
    command = (root/'cmdline').read_bytes()
    executable = os.readlink(root/'exe')
    namespace = os.readlink(root/'ns/pid')
    assert Path(executable).name == 'beam.smp' and b'/app/hub.exs' in command
    assert namespace != os.readlink('/proc/self/ns/pid')
    return {'host_pid':pid, 'kernel_start_time':raw[19], 'pid_namespace':namespace,
            'executable':executable, 'command_sha256':hashlib.sha256(command).hexdigest()}


class ObservedImage(RetainedImage):
    def __init__(self, *args):
        super().__init__(*args)
        self.vm_observations = []
        self.vm_by_container = {}

    def observe(self):
        super().observe()
        row = json.loads(self.docker('inspect', self.container_id).stdout)[0]
        assert row['Id'] == self.container_id and row['Image'] == self.image_id
        host = row['HostConfig']
        assert host['ReadonlyRootfs'] and host['NetworkMode'] == 'host'
        assert host['Memory'] == 768*1024*1024 and host['NanoCpus'] == 2000000000 and host['PidsLimit'] == 256
        current = vm_identity(row)
        previous = self.vm_by_container.setdefault(self.container_id, current)
        assert current == previous, 'Owned kernel VM identity changed within one container lifetime'
        self.vm_observations.append({'container_id':self.container_id, **current})

    def identity(self):
        result = super().identity()
        result['kernel_vm_observations'] = self.vm_observations
        return result


def passive_identity(image):
    # Observability on failure must never invoke verify/probe as a new action.
    return {'kind':'docker', 'image_config_identity':getattr(image,'image_id',None),
            'canonical_manifest_sha256':hashlib.sha256(image.manifest_bytes).hexdigest(),
            'artifact_sha256':image.manifest['files']['hub.exs'],
            'payload_verified':image.verified, 'probe_cleanup_blocked':getattr(image,'probe_cleanup_blocked',False),
            'cleanup_blocked':getattr(image,'cleanup_blocked',False),
            'container_lifecycle':image.events, 'payload_probe_lifecycle':getattr(image,'probe_events',[]),
            'kernel_vm_observations':image.vm_observations}


IMAGES = []


class ObservedRuntime(policy.UpgradeRuntime):
    def __init__(self, root, command, image=None, manifest=None):
        assert image is not None, 'This narrow runner accepts an actual image only'
        super().__init__(root, command, image, manifest)
        self.owned_image = ObservedImage(image, manifest, self.root)
        IMAGES.append(self.owned_image)


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--custody-report', type=Path, required=True)
    args, original = parser.parse_known_args()
    assert '--image' in original and '--command' not in original
    sys.argv = [policy.__file__] + original
    policy.UpgradeRuntime = ObservedRuntime
    failure = None
    try:
        policy.main()
    except BaseException as error:
        failure = type(error).__name__
        raise
    finally:
        value = {'schema':'adhd/oidc-policy-image-custody@1', 'application_assertions_unchanged':True,
                 'failure_type':failure, 'runtimes':[passive_identity(image) for image in IMAGES]}
        args.custody_report.parent.mkdir(parents=True, exist_ok=True)
        args.custody_report.write_text(json.dumps(value, indent=2)+'\n')


if __name__ == '__main__':
    main()
