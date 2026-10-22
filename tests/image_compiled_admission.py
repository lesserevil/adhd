"""Capture compiled-image admission from actual source receipt and offline audit.

This does not issue a receipt, compile source, start containers, or qualify
runtime/deployment. --execute is explicit; immutable predecessor evidence stays
unchanged and every target/source/context/output path is a required argument.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

_HELPERS = Path(__file__).absolute().parent
assert Path(__file__).resolve(strict=True) == Path(__file__).absolute()
if str(_HELPERS) not in sys.path:
    sys.path.insert(0, str(_HELPERS))
from image_payload_audit import Docker, checked_directory, digest, json_bytes, regular
from image_compiled_inputs import compiled_context, compiled_admission


PROVENANCE = ('component_lock_identity', 'base_authority_identity', 'rebuild_authority_identity',
              'receipt_identity', 'framework_distribution_identity')


def source_binding(source_bytes, expected_source_admission, receipt_bytes, rebuild_bytes, artifact):
    assert digest(source_bytes) == expected_source_admission
    source = json.loads(source_bytes)
    assert source['passed'] is True and source['artifact_sha256'] == artifact
    assert digest(receipt_bytes) == source['files']['receipt.json']
    assert digest(rebuild_bytes) == source['files']['rebuild.json']
    receipt = json.loads(receipt_bytes)
    envelope = json.loads(rebuild_bytes)
    rebuild = envelope['result']
    assert envelope['command'] == 'rebuild' and envelope['ok'] is True
    assert rebuild['passed'] is True and rebuild['specification'] == 'components/hub'
    assert rebuild['receipt_identity'] == receipt['receipt_identity'] == source['receipt_identity']
    assert rebuild['lifecycle_result_identity'] == receipt['receipt']['result']
    assert rebuild['lifecycle_request_identity'] == receipt['lifecycle_request_identity']
    for field in PROVENANCE:
        assert re.fullmatch('sha256:[a-f0-9]{64}', source[field])
    return source


def cache_binding(context, image, artifact, expected_context, audit_bytes, expected_audit,
                  cache_bytes, metadata_bytes):
    assert digest(audit_bytes) == expected_audit
    audit = json.loads(audit_bytes)
    assert audit['passed'] is True and audit['image_id'] == image
    assert audit['artifact_sha256'] == artifact and audit['canonical_manifest_sha256'] == expected_context
    assert audit['container_started'] is False and audit['owned_container_absent'] is True
    assert audit['runtime_parent_mtime'] == 0 and audit['cache_all_zero_timestamps'] is True
    binding = compiled_context(context, expected_context, artifact)
    counts=binding['payload_counts']
    module_count=len(counts['modules']) if counts else 59
    assert audit['actual_app_files'] == (counts['app_files'] if counts else 59) and audit['canonical_specifications'] == (counts['specifications'] if counts else 33)
    assert audit['cache_modules'] == module_count and audit['cache_entries'] == module_count+6+len(binding['acme_files'])
    cache = json.loads(cache_bytes)
    metadata = json.loads(metadata_bytes)
    assert len(cache['modules']) == len(set(cache['modules'])) == module_count and len(metadata) == module_count+7+len(binding['acme_files'])
    if counts:assert cache['modules']==counts['modules']
    assert cache['source_sha256'] == artifact and cache['payload_manifest_sha256'] == expected_context
    assert cache['inputs_sha256'] == binding['compiler_inputs_sha256']
    assert digest(cache_bytes) == metadata['adhd/manifest.json']['sha256']
    names = cache['modules']
    directories = {'adhd', 'adhd/ebin'}
    files = {'adhd/manifest.json', 'adhd/inputs.json', 'adhd/boot.exs', 'adhd/build.exs'} | {'adhd/ebin/' + n + '.beam' for n in names} | {'adhd/'+n for n in binding['acme_files']}
    assert set(metadata) == {'/runtime'} | directories | files
    assert metadata['/runtime'] == {'mode': '0o755', 'mtime': 0, 'sha256': None}
    for name in directories:
        assert metadata[name] == {'mode': '0o555', 'mtime': 0, 'sha256': None}
    for name in files:
        assert metadata[name]['mode'] == ('0o555' if name in ['adhd/lego','adhd/acme-guard'] else '0o444') and metadata[name]['mtime'] == 0
        assert re.fullmatch('[a-f0-9]{64}', metadata[name]['sha256'])
    if binding['acme_files']:
        assert cache['schema']=='adhd/precompiled-cache@2' and cache['acme']=={n:binding['packaging_files_sha256'][n] for n in binding['acme_files']}
        for name,value in cache['acme'].items():assert metadata['adhd/'+name]['sha256']==value
    else:assert cache['schema']=='adhd/precompiled-cache@1'
    assert set(cache['beams']) == {n + '.beam' for n in names}
    for name in names:
        assert metadata['adhd/ebin/' + name + '.beam']['sha256'] == cache['beams'][name + '.beam']
    for name in ('boot', 'build'):
        assert metadata['adhd/' + name + '.exs']['sha256'] == cache[name + '_sha256'] == binding['packaging_files_sha256'][name + '.exs']
    assert metadata['adhd/inputs.json']['sha256'] == binding['compiler_inputs_sha256']
    return audit, cache


def capture(args, docker=None):
    assert re.fullmatch('sha256:[a-f0-9]{64}', args.image)
    for value in (args.artifact_sha256, args.context_sha256, args.source_admission_sha256, args.payload_audit_sha256):
        assert re.fullmatch('[a-f0-9]{64}', value)
    context = checked_directory(args.context)
    audit_dir = checked_directory(args.audit_directory)
    source_bytes = regular(args.source_admission)
    receipt_bytes = regular(args.receipt)
    rebuild_bytes = regular(args.rebuild)
    source = source_binding(source_bytes, args.source_admission_sha256, receipt_bytes, rebuild_bytes, args.artifact_sha256)
    assert digest(regular(context / 'manifest.json')) == args.context_sha256
    audit_bytes = regular(audit_dir / 'image-payload.json')
    cache_bytes = regular(audit_dir / 'cache-manifest.json')
    metadata_bytes = regular(audit_dir / 'cache-metadata.json')
    audit, cache = cache_binding(context, args.image, args.artifact_sha256, args.context_sha256,
                                 audit_bytes, args.payload_audit_sha256, cache_bytes, metadata_bytes)
    build_log = regular(args.build_log)
    assert build_log, 'Actual compiler build log is required'
    output = Path(args.output).absolute()
    assert output.parent.resolve(strict=True) == output.parent and not output.exists()
    docker = docker or Docker(args.docker, args.docker_socket, args.docker_config)
    inspect = docker.checked(['image', 'inspect', args.image])
    rows = json.loads(inspect)
    assert len(rows) == 1 and rows[0]['Id'] == args.image
    config = rows[0]['Config']
    assert config['Entrypoint'] == ['elixir', '/runtime/adhd/boot.exs', '/app/hub.exs'] and config['User'] == '10001:10001'
    assert config['Cmd'] == ['["serve","/config/hub.json"]']
    output.mkdir(mode=0o700)
    files = {'source-admission.json': source_bytes, 'receipt.json': receipt_bytes,
             'rebuild.json': rebuild_bytes, 'image-build.log': build_log,
             'cache-manifest.json': cache_bytes, 'cache-metadata.json': metadata_bytes,
             'image-payload.json': audit_bytes, 'image-inspect.json': inspect}
    for name, body in files.items():
        (output / name).write_bytes(body)
    report = {k: source[k] for k in PROVENANCE}
    report.update(schema='adhd/compiled40-admission-and-image-binding@1', passed=True,
                  image_built=True, release_qualified=False, qualification_complete=False,
                  artifact_sha256=args.artifact_sha256, image_config_identity=args.image,
                  canonical_manifest_sha256=args.context_sha256, payload_audit=audit,
                  prior_source_admission_sha256=args.source_admission_sha256)
    report['compiled_runtime_audit'] = {
        'passed': True, 'image_id': args.image, 'artifact_sha256': args.artifact_sha256,
        'canonical_manifest_sha256': args.context_sha256,
        'cache_manifest_sha256': digest(cache_bytes), 'cache_metadata_sha256': digest(metadata_bytes),
        'compiler_inputs_sha256': cache['inputs_sha256'], 'cache_modules': audit['cache_modules'], 'cache_entries': audit['cache_entries'],
        'entrypoint': config['Entrypoint'], 'container_started': False, 'owned_container_absent': True}
    report['files'] = {name: digest(body) for name, body in files.items()}
    report['scope'] = ('Actual formal source receipt/rebuild and exact compiled image offline payload/cache/entrypoint audit. '
                       'No new receipt is issued here. Runtime/SDK/readiness, independent-build reproducibility and deployment '
                       'qualification remain separate gates. Schema name is retained for validator compatibility; actual identities are parameters.')
    # Revalidate all actual sibling cache files and the staged compiler closure
    # through the same pure validator used by downstream existing drivers.
    provisional = output / 'manifest.json.pending'
    provisional.write_bytes(json_bytes(report))
    try:
        compiled_admission(context, provisional, digest(regular(provisional)), args.image, args.artifact_sha256, required=True)
    except BaseException as error:
        report['passed'] = False
        report['failure_type'] = type(error).__name__
        try:
            provisional.write_bytes(json_bytes(report))
        except BaseException as persistence_error:
            error.add_note('Failed admission persistence: ' + type(persistence_error).__name__)
        raise
    provisional.rename(output / 'manifest.json')
    print(json.dumps({'passed': True, 'image': args.image,
                      'admission_sha256': digest(regular(output / 'manifest.json')), 'runtime_qualified': False}))
    return report


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute', action='store_true', required=True)
    for name in ('source-admission', 'receipt', 'rebuild', 'context', 'audit-directory', 'build-log',
                 'output', 'docker', 'docker-socket', 'docker-config'):
        p.add_argument('--' + name, type=Path, required=True)
    for name in ('image', 'artifact-sha256', 'context-sha256', 'source-admission-sha256', 'payload-audit-sha256'):
        p.add_argument('--' + name, required=True)
    return p


if __name__ == '__main__':
    capture(parser().parse_args())
