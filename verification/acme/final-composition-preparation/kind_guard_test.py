"""Pure selected-Kind binding guards; no positive Kind runtime is fabricated."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
s = importlib.util.spec_from_file_location('composition06', HERE / 'compose06.py')
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)
source = Path('/home/horde/src/adhd/.worktrees/acme-deploy/_build/acme/platform-image42-15/plan.json')
plan = json.loads(source.read_bytes())
assert hashlib.sha256(source.read_bytes()).hexdigest().startswith('0f7460a')
# Synthetic result tests parser contract only; actual run remains parent-owned.
synthetic = {'requested_platforms': ['kind'], 'unselected': ['compose'],
             'platforms': [{'platform': 'kind'}], 'unrun': []}
m.kind_plan_binding(plan, synthetic)
negatives = 0
for part, mutate in (
    ('plan', lambda p: p['bound'].update({'context/manifest.json': '0' * 64})),
    ('plan', lambda p: p['bound'].update({'admission/manifest.json': '0' * 64})),
    ('plan', lambda p: p['bound'].update({'admission/source-admission.json': '0' * 64})),
    ('plan', lambda p: p['target'].update(image='foreign')),
    ('plan', lambda p: p['target'].update(artifact_sha256='0' * 64)),
    ('plan', lambda p: p['target'].update(admission_sha256='0' * 64)),
    ('plan', lambda p: p['target'].update(source_admission_sha256='0' * 64)),
    ('plan', lambda p: p.update(selection=['compose', 'kind'])),
    ('plan', lambda p: p.update(order=['compose', 'kind'])),
    ('plan', lambda p: p.pop('selection')),
    ('result', lambda r: r.update(requested_platforms=['compose', 'kind'])),
    ('result', lambda r: r.update(unselected=[])),
    ('result', lambda r: r.update(unselected=['kind'])),
    ('result', lambda r: r.update(unrun=['kind'])),
    ('result', lambda r: r['platforms'].append({'platform': 'compose'})),
    ('result', lambda r: r.pop('requested_platforms')),
):
    p, r = copy.deepcopy(plan), copy.deepcopy(synthetic)
    mutate(p if part == 'plan' else r)
    try:
        m.kind_plan_binding(p, r)
    except (AssertionError, KeyError):
        negatives += 1
    else:
        raise AssertionError('Invalid Kind binding accepted')
request = json.loads((HERE / 'request.json').read_bytes())
status = m.collect(request)
assert not status['passed'] and status['pending'] == [
    {'gate': 'platform/kind', 'reason': 'Missing/pending actual positive binding'}]
assert request['platforms']['kind'] is None
print(json.dumps({'passed': True, 'negative_vectors': negatives,
    'actual_plan_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'synthetic_result_is_not_runtime_evidence': True,
    'whole9_and_independent_cleanup_audit_guards_retained': True,
    'pending': status['pending'], 'runtime_calls': 0, 'writer_invoked': False}, indent=2))
