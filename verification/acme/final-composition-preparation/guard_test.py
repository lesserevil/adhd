"""Read-only evidence guards; never starts services or invokes cleanup."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('composition', HERE / 'compose.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
request = json.loads((HERE / 'request.json').read_bytes())
ref = request['platforms']['compose']
support = request['compose_support']
actual = m.compose_proof(ref, support)
assert actual['original_aggregate_passed'] is False
assert len(actual['selected_whole_named_checks']) == 9
assert hashlib.sha256((HERE / 'compose12-plan.json').read_bytes()).hexdigest() == support['plan']['sha256']
negative_vectors = 0

def denied(fn):
    global negative_vectors
    try:
        fn()
    except (AssertionError, KeyError):
        negative_vectors += 1
    else:
        raise AssertionError('Required rejection did not occur')

plan = m.read(support['plan'])
result = m.read(support['result'])
row = result['platforms'][0]
for index in range(9):
    changed = copy.deepcopy(row)
    changed['scenario']['checks'].pop(index)
    denied(lambda: m.platform_row(changed, 'compose'))
for mutate in (
    lambda r: r.update(passed=False),
    lambda r: r['cleanup_errors'].append('unknown'),
    lambda r: r['scenario']['checks'][-1].pop('private_state_sha256'),
    lambda r: r['scenario']['runtime_identities'].__setitem__(1, r['scenario']['runtime_identities'][0]),
    lambda r: r['scenario']['runtime_identities'][0].update(image='foreign'),
    lambda r: r['gateway'].update(all_threads_closed=False),
    lambda r: r['relay'].update(closed=False),
):
    changed = copy.deepcopy(row)
    mutate(changed)
    denied(lambda: m.platform_row(changed, 'compose'))

# Exercise actual durable-layout adapter, mutating one decoded dependency at a time.
original_read = m.read
for key, mutate in (
    ('negative_review', lambda v: v.update(passed=True)),
    ('negative_review', lambda v: v.update(inputs_unchanged=False)),
    ('negative_review', lambda v: v.update(lease_released_and_independently_acquired=False)),
    ('result', lambda v: v.update(passed=True)),
    ('result', lambda v: v.update(inputs_unchanged=False)),
    ('result', lambda v: v['commands'].update(all_closed=False)),
    ('result', lambda v: v['platforms'][0]['scenario']['runtime_identities'][0].update(image='foreign')),
    ('cleanup', lambda v: v.update(passed=False)),
    ('cleanup', lambda v: v['checks'][0].update(absent=False)),
    ('cleanup', lambda v: v.update(lease_independently_released=False)),
    ('plan', lambda v: v['target'].update(source_admission_sha256='0' * 64)),
    ('plan', lambda v: v['bound'].update({'context/manifest.json': '0' * 64})),
):
    changed = copy.deepcopy(original_read(support[key]))
    mutate(changed)
    def altered_read(r):
        return changed if r == support[key] else original_read(r)
    with patch.object(m, 'read', side_effect=altered_read):
        denied(lambda: m.compose_proof(ref, support))

changed_support = copy.deepcopy(support)
changed_support['cleanup']['sha256'] = '0' * 64
denied(lambda: m.compose_proof(ref, changed_support))
kind_row = copy.deepcopy(row)
kind_row['platform'] = 'kind'
synthetic = {'schema': result['schema'], 'passed': True, 'platforms': [kind_row]}
assert m.platform_selection('kind', {'order': ['kind']}, synthetic, 'synthetic') == kind_row
bad = copy.deepcopy(synthetic)
bad['passed'] = False
denied(lambda: m.platform_selection('kind', {'order': ['kind']}, bad, 'synthetic'))
denied(lambda: m.platform_selection('kind', {'order': ['compose', 'kind']}, synthetic, 'synthetic'))
status = m.collect(request)
assert status['passed'] is False and status['unique_fault_contracts'] == 15
assert status['pending'] == [{'gate': 'platform/kind', 'reason': 'Missing/pending actual positive binding'}]
assert status['platform_composition']['single_aggregate_matrix_pass_claimed'] is False
assert request['platforms']['kind'] is None
print(json.dumps({'passed': True, 'negative_vectors': negative_vectors,
    'actual_compose_row_accepted': True, 'original_aggregate_still_false': True,
    'actual_compose_plan_copy_exact': True, 'all15_unique_faults_browser_visual_bound': True,
    'pending': status['pending'], 'synthetic_kind_is_not_runtime_evidence': True,
    'runtime_calls': 0, 'writer_invoked': False}, indent=2))
