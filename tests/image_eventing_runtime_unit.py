"""Pure observer argv checks; no Docker or application processes."""
from pathlib import Path
from image_eventing_runtime import instrument_argv, OBSERVER


def main():
    base = ['docker', 'run', '--rm', '--network', 'host', '--read-only', 'sha256:' + 'a' * 64]
    result = instrument_argv(base, Path('/owned/observer.so'), '/owned/config', '/owned/state',
                             '/owned/sentinel', 'transition-decision')
    assert '--rm' not in result and '--rm' in base
    assert 'type=bind,src=/owned/observer.so,dst=' + OBSERVER + ',readonly' in result
    assert 'LD_PRELOAD=' + OBSERVER in result and result[-1] == base[-1]
    assert result[result.index('--network') + 1] == 'host' and '--pid' not in result
    for bad in (base[:-1] + ['--pid=host', base[-1]], base[:-1] + ['--pid', 'host', base[-1]]):
        try:
            instrument_argv(bad, Path('/owned/observer.so'), '/owned/config', '/owned/state',
                            '/owned/sentinel', 'transition-project')
        except AssertionError:
            pass
        else:
            raise AssertionError('Image observer admitted shared host PID namespace')
    print('PASS image eventing argv3: retained custody, readonly observer mount, private PID namespace')


if __name__ == '__main__':
    main()
