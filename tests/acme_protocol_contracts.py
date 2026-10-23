#!/usr/bin/env python3
"""Independent schema-only ACME extension/conservation checks; starts no services."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import jsonschema
from protocol_acceptance import normalized_schema_required


def conservation_delta(schema, baseline):
    raw = {name for name, value in baseline['$defs'].items() if value != schema['$defs'].get(name)}
    current, prior = normalized_schema_required(schema), normalized_schema_required(baseline)
    semantic = {name for name, value in prior['$defs'].items() if value != current['$defs'].get(name)}
    return raw, semantic, current, prior


def verify(schema, baseline, openapi, baseline_openapi, authority):
    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema['$id'] == 'urn:adhd:protocol:2.2'
    assert openapi['info']['version'] == '2.2.0'
    allowed = {'AdminCommand', 'AdminResult', 'PublicConfig', 'MergePatch', 'Error'}
    raw_changed, changed, semantic_schema, semantic_baseline = conservation_delta(schema, baseline)
    assert changed == allowed, changed
    for name in set(baseline['$defs']) - allowed:
        assert semantic_baseline['$defs'][name] == semantic_schema['$defs'][name], name
    for name, union, prefix in [('AdminCommand', 'oneOf', 'admin_'), ('AdminResult', 'anyOf', 'admin_result_')]:
        assert schema['$defs'][name][union] == baseline['$defs'][name][union] + [
            {'$ref': '#/$defs/' + prefix + op} for op in ['tls_status', 'tls_renew']]
    assert schema['$defs']['Descriptor'] == baseline['$defs']['Descriptor']
    for name in ['ProjectSettings', 'ProjectInput', 'Project']:
        assert schema['$defs'][name] == baseline['$defs'][name]
    for path, value in baseline_openapi['paths'].items():
        assert openapi['paths'][path] == value, path
    assert set(openapi['paths']) - set(baseline_openapi['paths']) == {'/.well-known/acme-challenge/{token}'}
    challenge = openapi['paths']['/.well-known/acme-challenge/{token}']
    assert challenge['x-adhd-listener'] == 'acme-challenge'
    assert challenge['get']['security'] == [] and set(challenge['get']['responses']) == {'200', '404', '405'}
    refs = []
    def walk(value):
        if isinstance(value, dict):
            if '$ref' in value:
                refs.append(value['$ref'])
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(schema)
    for ref in refs:
        assert ref.startswith('#/$defs/') and ref[8:] in schema['$defs'], ref
    def name(key):
        return key if key.startswith(('TLS', 'ACME')) else 'ACME' + key
    def translate(value):
        if isinstance(value, dict):
            out = {k: '#/$defs/' + name(v[8:]) if k == '$ref' else translate(v) for k, v in value.items()}
            if out.get('type') == 'integer':
                out['x-integerToken'] = True
            return out
        return [translate(x) for x in value] if isinstance(value, list) else value
    for key, shape in authority['$defs'].items():
        assert schema['$defs'][name(key)] == translate(shape), key
    rows = []
    def case(label, definition, value, valid):
        validator = jsonschema.Draft202012Validator({'$schema': schema['$schema'], '$defs': schema['$defs'], '$ref': '#/$defs/' + definition}, format_checker=jsonschema.FormatChecker())
        actual = validator.is_valid(value)
        assert actual == valid, (label, list(validator.iter_errors(value)))
        rows.append({'case': label, 'passed': True, 'expected_valid': valid})
    case('tls-read-union', 'AdminCommand', {'op': 'tls_status'}, True)
    case('read-rejects-message-id', 'AdminCommand', {'op': 'tls_status', 'message_id': 'x'}, False)
    renewal = {'op': 'tls_renew', 'expected_revision': 3, 'confirm': True, 'message_id': 'renew-3'}
    case('renew-union', 'AdminCommand', renewal, True)
    case('renew-confirm-false', 'AdminCommand', dict(renewal, confirm=False), False)
    case('renew-extra-path', 'AdminCommand', dict(renewal, key_path='/private/key'), False)
    case('renew-obsolete-revision-key', 'AdminCommand', {'op': 'tls_renew', 'config_revision': 3, 'confirm': True, 'message_id': 'x'}, False)
    case('renew-accepted-union', 'AdminResult', {'accepted': True, 'config_revision': 3}, True)
    case('normalized-config-requires-fields', 'TLSConfig', {'enabled': False}, False)
    case('raw-input-omission-defaults', 'TLSConfigInput', {'enabled': False}, True)
    case('raw-input-inconsistent-enable', 'TLSConfigInput', {'acme': {'enabled': True}}, False)
    case('nested-partial-merge', 'MergePatch', {'tls': {'acme': {'retry_seconds': 300}}}, True)
    case('nested-null-remove', 'MergePatch', {'tls': {'acme': {'email': None}}}, True)
    case('whole-null-remove', 'MergePatch', {'tls': None}, True)
    case('nested-secret-reject', 'MergePatch', {'tls': {'acme': {'dns_secret': 'private'}}}, False)
    case('nested-bound-reject', 'MergePatch', {'tls': {'acme': {'order_timeout_ms': 999}}}, False)
    case('domain-count-limit', 'MergePatch', {'tls': {'acme': {'domains': [f'a{i}.example.org' for i in range(21)]}}}, False)
    case('wildcard-reject', 'MergePatch', {'tls': {'acme': {'domains': ['*.example.org']}}}, False)
    case('directory-insecure-reject', 'MergePatch', {'tls': {'acme': {'directory_url': 'http://example.org/directory'}}}, False)
    status = {'enabled': False, 'https_state': 'disabled', 'acme_state': 'disabled', 'domains': [], 'active_domains': [], 'certificate': None, 'last_attempt_at': None, 'next_attempt_at': None, 'last_success_at': None, 'last_error': None, 'config_revision': 3}
    case('status-union', 'AdminResult', status, True)
    case('status-key-leak-reject', 'TLSStatus', dict(status, private_key='secret'), False)
    case('ready-no-cert-reject', 'TLSStatus', dict(status, enabled=True, https_state='ready'), False)
    case('backoff-no-timestamp-reject', 'TLSStatus', dict(status, enabled=True, https_state='waiting', acme_state='backoff'), False)
    case('ordering-recorded-time-required', 'TLSStatus', dict(status, enabled=True, https_state='waiting', acme_state='ordering'), False)
    error = {'error': {'code': 'TLS_RENEW_UNAVAILABLE', 'message': 'Managed ACME renewal is disabled.'}}
    case('renew-disabled-exact-error', 'Error', error, True)
    bad = copy.deepcopy(error); bad['error']['message'] = '/private/raw-output'
    case('renew-error-private-message-reject', 'Error', bad, False)
    bad = copy.deepcopy(error); bad['error']['current_revision'] = 3
    case('renew-error-extra-revision-reject', 'Error', bad, False)
    return {'passed': True, 'schema_only': True, 'unchanged_baseline_definitions': len(baseline['$defs']) - len(changed), 'changed_old_definitions': sorted(changed), 'raw_changed_old_definitions': sorted(raw_changed), 'required_order_only_old_definitions': sorted(raw_changed-changed), 'comparison': 'Existing protocol_acceptance JSON Schema required-name order rule only; raw exports remain untouched; membership, constraints, literals, annotations and all other array order remain strict', 'added_definitions': len(schema['$defs']) - len(baseline['$defs']), 'actual_vectors': rows, 'runtime_started': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['schema', 'baseline', 'openapi', 'baseline-openapi', 'authority', 'report']:
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    inputs = {key: getattr(args, key) for key in ['schema', 'baseline', 'openapi', 'baseline_openapi', 'authority']}
    result = verify(*(json.loads(inputs[key].read_text()) for key in inputs))
    result['input_sha256'] = {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in inputs.items()}
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key not in ['actual_vectors', 'input_sha256']}))


if __name__ == '__main__':
    main()
