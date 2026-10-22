"""Read-only comparison; only ten explicitly named required-array paths are unordered."""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path('/home/horde/src/adhd')
NAMES = ('ArchiveQuery', 'FeedbackAttempt', 'FeedbackAttemptSummary', 'OptimizationProposal', 'ReplayQuery')

def sha(data):
    return hashlib.sha256(data).hexdigest()

def load(path):
    data = path.read_bytes()
    def unique(pairs):
        result = {}
        for k, v in pairs:
            assert k not in result, ('duplicate key', k)
            result[k] = v
        return result
    return data, json.loads(data, object_pairs_hook=unique)

def exact(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(exact(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(exact(x, y) for x, y in zip(left, right))
    return left == right

def compare(left, right, prefix):
    a, b = copy.deepcopy(left), copy.deepcopy(right)
    rows = []
    for name in NAMES:
        keys = prefix + (name, 'required')
        x, y = a, b
        for key in keys[:-1]:
            x, y = x[key], y[key]
        old, actual = x[keys[-1]], y[keys[-1]]
        for value in (old, actual):
            assert type(value) is list and all(type(s) is str for s in value)
            assert len(value) == len(set(value))
        assert set(old) == set(actual)
        rows.append({'pointer': '/' + '/'.join(keys), 'published': old, 'actual': actual,
                     'unique_string_sets_equal': True, 'ordering_differs': old != actual})
        # Replace ONLY these named arrays; every other array/value remains untouched.
        y[keys[-1]] = old
    assert exact(a, b), 'unapproved semantic difference'
    return rows

def main():
    audit_path = ROOT / 'verification/container-cache41-positive/audit.json'
    _, cache = load(audit_path)
    documents = {}
    for name, prefix in (('schema', ('$defs',)), ('openapi', ('components', 'schemas'))):
        published_path = ROOT / f'docs/protocol/{name}.json'
        actual_path = ROOT / f'_build/cache41-compiled01/protocol-{name}.stdout'
        published_bytes, published = load(published_path)
        actual_bytes, actual = load(actual_path)
        bound = cache['raw_files'][actual_path.name]
        assert bound == {'sha256': sha(actual_bytes), 'bytes': len(actual_bytes)}
        core_path = ROOT / f'_build/core41-compiled03/exports/{name}.json'
        core_bytes, core = load(core_path)
        # Separate exact comparison establishes the served/CLI core snapshot's semantics.
        assert exact(core, actual)
        documents[name] = {'published_path': str(published_path.relative_to(ROOT)),
            'published_sha256': sha(published_bytes), 'actual_export_path': str(actual_path.relative_to(ROOT)),
            'actual_sha256': sha(actual_bytes), 'actual_bytes': len(actual_bytes),
            'core_export_path': str(core_path.relative_to(ROOT)), 'core_export_sha256': sha(core_bytes),
            'core_parsed_export_equal': True, 'allowed_required_arrays': compare(published, actual, prefix),
            'all_other_arrays_examples_enums_values_exact': True, 'byte_identical': published_bytes == actual_bytes}
    _, wire = load(ROOT / 'verification/ownedMULTI008/source41-core13-positive/wire.json')
    _, core_schema = load(ROOT / '_build/core41-compiled03/exports/schema.json')
    admission_path = ROOT / '_build/roadmap/final/compiled41-01/compiled-admission/manifest.json'
    admission_bytes, admission = load(admission_path)
    assert sha(admission_bytes) == 'b62bf37502c54b7800c57ffd6fede457808d93bf4b701f1ac75aaa38ebd3fdad'
    assert admission['passed'] and cache['passed']
    assert admission['artifact_sha256'] == cache['artifact_sha256'] == wire['artifact_sha256']
    assert admission['image_config_identity'] == cache['image_config_identity'] == wire['image']
    canonical = json.dumps(core_schema, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    assert sha(canonical) == wire['schema_sha256']
    assert wire['passed'] and len(wire['cases']) == 8
    # Adversarial comparison checks require no application execution.
    _, basis = load(ROOT / 'docs/protocol/schema.json')
    reordered = copy.deepcopy(basis)
    for name in NAMES:
        reordered['$defs'][name]['required'].reverse()
    compare(basis, reordered, ('$defs',))
    for key, value in (('enum', ['a', 'b']), ('examples', [1, 2]), ('unlisted_required', ['a', 'b'])):
        a, b = copy.deepcopy(basis), copy.deepcopy(basis)
        a[key] = value
        b[key] = list(reversed(value))
        try:
            compare(a, b, ('$defs',))
        except AssertionError:
            pass
        else:
            raise AssertionError(('unexpected array permission', key))
    assert not exact({'value': 1}, {'value': True})
    result = {'schema': 'adhd/source41-protocol-conservation-review@1', 'passed': True,
        'scope': 'Read-only semantic conservation, not byte conservation or a new runtime gate.',
        'artifact_sha256': wire['artifact_sha256'], 'image': wire['image'],
        'compiled_admission_sha256': sha(admission_bytes),
        'cache_audit_sha256': sha(audit_path.read_bytes()), 'documents': documents,
        'object_key_serialization_order_ignored': True, 'no_other_array_order_ignored': True,
        'wire8_report': 'verification/ownedMULTI008/source41-core13-positive/wire.json',
        'wire8_report_sha256': sha((ROOT / 'verification/ownedMULTI008/source41-core13-positive/wire.json').read_bytes()),
        'wire_schema_sha256_is_sorted_object_key_compact_json': wire['schema_sha256'],
        'published_files_unchanged': True,
        'comparison_checks': {'named_required_reordering_accepted': True,
            'other_enum_example_unlisted_arrays_rejected': True, 'boolean_integer_type_change_rejected': True}}
    print(json.dumps(result, indent=2) + '\n', end='')

if __name__ == '__main__':
    main()
