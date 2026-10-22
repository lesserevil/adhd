"""Controlled runner admission checks: no hubs, containers or providers."""
import concurrent.futures
import threading
from multi_eventing_matrix import bounded_jobs


def main():
    active = set()
    admitted = []
    lock = threading.Lock()
    started = threading.Barrier(2)
    fail_observed = threading.Event()
    peak = [0]
    def run(job):
        with lock:
            admitted.append(job)
            active.add(job)
            peak[0] = max(peak[0], len(active))
        started.wait(timeout=5)
        if job == 'failure':
            code = 1
        else:
            assert fail_observed.wait(timeout=5)
            code = 0
        with lock:
            active.remove(job)
        return {'name': job, 'exit_code': code}
    real_wait = concurrent.futures.wait
    def observed_wait(*args, **kwargs):
        done, pending = real_wait(*args, **kwargs)
        if any(future.result()['exit_code'] != 0 for future in done):
            fail_observed.set()
        return done, pending
    concurrent.futures.wait = observed_wait
    try:
        results = bounded_jobs(['failure', 'running', 'unrun-a', 'unrun-b'], run, 2, True)
    finally:
        concurrent.futures.wait = real_wait
    assert set(admitted) == {'failure', 'running'} and peak == [2]
    assert results == [{'name':'failure','exit_code':1}, {'name':'running','exit_code':0}]
    full = bounded_jobs(list(range(4)), lambda n: {'name':n,'exit_code':n==0}, 2, False)
    assert len(full) == 4
    serial = bounded_jobs([0,1,2], lambda n: {'name':n,'exit_code':1}, 1, True)
    assert serial == [{'name':0,'exit_code':1}]
    print('PASS bounded scheduling3: fail-fast admission, default full admission, serial first failure')


if __name__ == '__main__':
    main()
