"""Pure preparation checks; never compiles/starts a runtime or opens a socket."""
from pathlib import Path
from workflow_provider_isolation import model_endpoints, NativeProviderFence, isolated_image_argv, stop_independently


def main():
    config = {'matcher': {'url': 'http://127.0.0.1:18770/v1/systemone'}, 'history': {'url': None},
              'host': '0.0.0.0', 'port': 32123, 'public_url': 'http://127.0.0.1:32123'}
    assert model_endpoints(config) == [('127.0.0.1', 18770)]
    base = ['docker', 'run', '--network', 'host', '--read-only', 'sha256:' + 'a' * 64]
    argv = isolated_image_argv(base, config)
    assert argv[argv.index('--network') + 1] == 'bridge'
    assert argv[-3:] == ['--publish', '127.0.0.1:32123:32123', base[-1]] and base[3] == 'host'
    for bad in ({**config, 'matcher': {'url': 'http://example.invalid:18770'}},
                {**config, 'matcher': {'url': 'http://user:password@127.0.0.1:18770'}}):
        try:
            model_endpoints(bad)
        except AssertionError:
            pass
        else:
            raise AssertionError('Unsafe model route admitted')
    try:
        NativeProviderFence(Path('/unused-no-execution'), {**config, 'history': {'url': 'http://localhost:18771'}})
    except AssertionError:
        pass
    else:
        raise AssertionError('Single-port native fence admitted another effective port')
    try:
        model_endpoints({**config, 'projects': [{'id': 'hidden', 'settings': {
            'history': {'url': 'http://external.invalid:18770'}}}]})
    except AssertionError:
        pass
    else:
        raise AssertionError('Project model override escaped route validation')
    inherited = {**config, 'projects': [{'id': 'local', 'settings': {
        'matcher': {'url': 'http://localhost:18770'}, 'history': {'url': None}}}]}
    assert model_endpoints(inherited) == [('127.0.0.1', 18770), ('localhost', 18770)]
    calls = []
    original = RuntimeError('owned target cleanup failure')
    class FakeRuntime:
        def __init__(self, name):
            self.name = name
        def stop(self):
            calls.append(self.name)
            if self.name == 'target':
                raise original
    errors = stop_independently((('target', FakeRuntime('target')), ('producer', FakeRuntime('producer'))))
    assert calls == ['target', 'producer'] and errors == [('target', original)]
    print('PASS workflow isolation7: effective routes, bridge mapping, unsafe routes, complete native port coverage')


if __name__ == '__main__':
    main()
