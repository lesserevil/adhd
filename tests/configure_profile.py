#!/usr/bin/env python3
"""Check fresh profile-2 configuration and explicit legacy helper compatibility."""
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile


def main():
    helper = Path(__file__).resolve().parents[1] / 'scripts/configure_hub.py'
    with tempfile.TemporaryDirectory(prefix='adhd-configure-') as temporary:
        root = Path(temporary)
        def create(name, *args):
            directory = root / name
            result = subprocess.run([sys.executable, str(helper), '--directory', str(directory),
                                     '--store-path', str(directory / 'data/hub.dets'), *args],
                                    text=True, capture_output=True)
            assert result.returncode == 0, result.stderr
            config = json.loads((directory / 'hub.json').read_text())
            for path in directory.iterdir():
                if path.is_file(): assert stat.S_IMODE(path.stat().st_mode) == 0o600
            assert config['agents']['agent-a'] not in result.stdout
            return config
        fresh = create('fresh', '--project', 'second')
        assert fresh['matcher'] is None and fresh['eventing']['enabled'] is True
        assert [row['id'] for row in fresh['projects']] == ['shared-project', 'second']
        assert all(ids == ['shared-project', 'second'] for ids in fresh['agent_projects'].values())
        model = create('model', '--matcher-url', 'http://127.0.0.1:18770/v1/systemone')
        assert model['matcher']['url'].endswith('/v1/systemone')
        legacy = create('legacy', '--legacy-single-project')
        assert not any(key in legacy for key in ('projects', 'eventing', 'agent_projects'))
        assert legacy['matcher'] is not None
        bad = root / 'bad'
        result = subprocess.run([sys.executable, str(helper), '--directory', str(bad),
                                 '--project', 'shared-project'], capture_output=True)
        assert result.returncode != 0 and not bad.exists()
    print('PASS model-free multi-project defaults, optional model, explicit legacy, private files and preflight')


if __name__ == '__main__': main()
