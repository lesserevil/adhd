"""Owned image VM adapter for the existing configuration crash scenarios."""
import json
from pathlib import Path

from foundation_acceptance import Runtime
from image_filesystem_fault import fault_image


class ConfigurationFaultRuntime(Runtime):
    def __init__(self, root, args, boundary):
        super().__init__(root, [])
        self.arm = root / 'config-fault.armed'
        self.sentinel = root / 'config-fault.json'
        self.boundary = boundary
        prefix = 'ADHD_CONFIG_FAULT_'
        self.image_runtime = fault_image(args, root, 'config_rename_fault.c', {
            prefix + 'CONFIG': str(self.file), prefix + 'STAGE': boundary,
            prefix + 'ARM': str(self.arm), prefix + 'SENTINEL': str(self.sentinel)})

    def start(self):
        try:
            self.command = self.image_runtime.argv(self.file)
            super().start()
            self.image_runtime.observe()
        except BaseException as error:
            try:
                self.stop()
            except BaseException as cleanup:
                error.add_note('Owned configuration image cleanup failure: ' + type(cleanup).__name__)
            raise

    def arm_mutation(self):
        assert not self.arm.exists() and not self.sentinel.exists()
        with self.arm.open('xb') as output:
            output.write(b'configuration-mutation-only\n')
        self.arm.chmod(0o600)

    def observe_boundary(self):
        try:
            raw = self.sentinel.read_bytes()
        except FileNotFoundError:
            return False
        assert len(raw) <= 256, 'Oversized configuration boundary witness'
        try:
            trace = json.loads(raw)
        except json.JSONDecodeError:
            # O_EXCL creates the sentinel before the observer writes it. A
            # partial record is not a boundary witness; keep the original wait.
            return False
        assert trace['stage'] == self.boundary and trace['pid'] == 1 and trace['rename_result'] == 0
        self.image_runtime.stop_at_observed_boundary(trace)
        return True

    def stop(self, hard=False):
        errors = []
        try:
            self.image_runtime.stop(hard=hard)
        except BaseException as error:
            errors.append(error)
        if self.process is not None:
            try:
                self.process.wait(timeout=15)
            except BaseException as error:
                errors.append(error)
        for log in self.logs:
            log.close()
        self.logs = []
        if hard and not errors:
            assert self.process.returncode == 137 and self.image_runtime.last_exit_code == 137
        if errors:
            raise errors[0]
