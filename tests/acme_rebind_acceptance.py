"""Stopped full-copy ACME rebind companion. Inert until explicitly called.

Uses the existing closed public rebind-storage request; never rewrites copied
configuration, product stores, ACME keys or ownership digests in the fixture.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import time
from uuid import uuid4

from acme_runtime import NativeDiagnostic, PublicClient, regular, sha, ticks, wait_managed_https, verified_preload_code
from acme_acceptance_fixtures import certificate_facts


def inventory(root):
    root = Path(root)
    rows = {}
    for path in [root, *sorted(root.rglob('*'))]:
        value = path.lstat()
        assert value.st_uid == os.getuid() and not stat.S_ISLNK(value.st_mode)
        assert stat.S_ISDIR(value.st_mode) or stat.S_ISREG(value.st_mode)
        if stat.S_ISREG(value.st_mode):
            assert value.st_nlink == 1
            rows[str(path.relative_to(root))] = sha(path)
    return rows


def disjoint(old, new):
    old, new = Path(old).absolute(), Path(new).absolute()
    assert old == old.resolve() and new == new.resolve(), 'No redirected backup paths'
    assert old != new and not old.is_relative_to(new) and not new.is_relative_to(old)
    return old, new


def path_digest(path):
    # Independent ordinary ETF binary encoding, not an application-private call.
    value = str(Path(path).resolve()).encode('utf8')
    return hashlib.sha256(b'\x83m' + len(value).to_bytes(4, 'big') + value).hexdigest()


def request_for(config):
    config = Path(config).resolve()
    registry = json.loads(Path(str(config)+'.stores').read_text())
    old = Path(registry['config_file']).parent
    disjoint(old, config.parent)
    rows = []
    assert len(registry['projects']) <= 256
    for project, value in sorted(registry['projects'].items()):
        if not value['initialized']:
            continue
        previous = Path(value['storage_anchor'])
        assert previous.is_absolute() and previous.is_relative_to(old)
        current = config.parent/previous.relative_to(old)
        regular(current)
        regular(str(current)+'.snapshot')
        rows.append({'project_id':project,'store_path':str(current),'expected_route_generation':value['generation'],
                     'snapshot_sha256':sha(str(current)+'.snapshot'),'checkpoint_sha256':sha(current)})
    assert rows and len({row['store_path']for row in rows}) == len(rows)
    def digest(suffix, nullable=False):
        path = Path(str(config)+suffix)
        if nullable and not path.exists():
            return None
        regular(path)
        return sha(path)
    return {'config_file':str(config),'expected_server_id':registry['server_id'],
            'expected_config_sha256':sha(config),'expected_config_journal_sha256':digest('.journal',True),
            'expected_registry_sha256':digest('.stores'),'expected_recovery_journal_sha256':digest('.recovery'),
            'expected_marker_sha256':digest('.stores.marker'),'stores':rows,
            'message_id':uuid4().hex,'confirm':True,'confirm_stopped':True}


def run_stopped_copy(args, origin, destination, expected_leaf, issuer_root, origin_identities):
    """Caller must have stopped all original owners and retained their identities."""
    origin, destination = disjoint(origin, destination)
    expected_path = hashlib.sha256(str(origin/'hub.json').encode()).hexdigest()
    assert origin_identities and all(row['reaped'] is True and ticks(row['pid']) != row['start_ticks'] and
                                     row['config_path_sha256'] == expected_path
                                     for row in origin_identities), 'All actual old owners must be proved stopped before copy'
    assert not destination.exists() and not Path(str(origin/'hub.json')+'.transaction').exists()
    before = inventory(origin)
    witness = json.loads((origin/'hub.json.acme-owner.json').read_text())
    owner = json.loads((origin/'acme/owner.json').read_text())
    assert witness['phase'] == 'ready' and {key:value for key,value in witness.items()if key!='phase'} == owner
    assert witness['config_path'] == path_digest(origin/'hub.json')
    shutil.copytree(origin,destination,symlinks=False)
    assert inventory(destination) == before
    config = destination/'hub.json'
    request = request_for(config)
    runtime = NativeDiagnostic(destination,args.source,args.cache,args.elixir,args.cache_manifest_sha256,
                               erlang=args.erlang,peer_trust=issuer_root,peer_hosts=('one.acme.test','two.acme.test'))
    binding = runtime.verify()
    value = {'passed':False,'scope':'Actual stopped complete-server copy and public offline rebind; no original files edited',
             'checks':[],'cli_identity':None,'runtime_identities':runtime.identities,'binding':binding}
    process = None
    cli_ticks = None
    primary = None
    try:
        stdout = destination/'acme-rebind.stdout'
        stderr = destination/'acme-rebind.stderr'
        if hasattr(runtime,'offline_rebind'):
            completed,cli_identity=runtime.offline_rebind(request,stdout,stderr,timeout=150)
            value['cli_identity']=cli_identity
            assert completed.returncode==0 and stdout.stat().st_size<=65536 and stderr.stat().st_size<=65536
        else:
            env = {'PATH':str(runtime.elixir.parent)+':'+str(runtime.erlang.parent)+':/usr/bin:/bin',
                   'HOME':str(destination),'LANG':'C.UTF-8','ERL_FLAGS':'+S 2:2'}
            code = verified_preload_code(runtime.cache,binding) + '[payload] = System.argv(); result = ADHD.CLI.run(JSON.decode!(payload)); IO.puts(JSON.encode!(result))'
            value['offline_preloaded_beams'] = binding['beams']
            with stdout.open('xb') as out, stderr.open('xb') as err:
                stdout.chmod(0o600)
                stderr.chmod(0o600)
                process = subprocess.Popen([str(runtime.elixir),'-pa',str(runtime.cache),'-e',code,'--',
                                           json.dumps(['rebind-storage',request])],stdout=out,stderr=err,
                                           env=env,start_new_session=True)
                cli_ticks = ticks(process.pid)
                value['cli_identity'] = {'pid':process.pid,'start_ticks':cli_ticks,'reaped':False}
                process.wait(timeout=150)
            assert process.returncode == 0 and stdout.stat().st_size <= 65536 and stderr.stat().st_size <= 65536
        result = json.loads(stdout.read_text())
        assert result['rebound'] is True and result['server_id'] == request['expected_server_id']
        assert set(result['projects']) == {row['project_id']for row in request['stores']}
        assert sha(config) == before['hub.json'], 'Public rebind must not rewrite configuration'
        for row in request['stores']:
            assert sha(row['store_path']) == row['checkpoint_sha256'] and sha(row['store_path']+'.snapshot') == row['snapshot_sha256']
        moved_witness = json.loads((destination/'hub.json.acme-owner.json').read_text())
        moved_owner = json.loads((destination/'acme/owner.json').read_text())
        assert moved_witness == {**witness,'config_path':path_digest(config)}
        assert moved_owner == {**owner,'config_path':path_digest(config)}
        after = inventory(destination)
        for relative,digest in before.items():
            if relative.startswith('acme/') and relative != 'acme/owner.json':
                assert after[relative] == digest, 'Account/certificate/active state must remain byte-identical'
        value['checks'].append({'name':'public rebind preserves all account/certificate/key/state and product bytes',
                                'passed':True,'unchanged_acme_files':sum(k.startswith('acme/')and k!='acme/owner.json'for k in before)})
        runtime.start()
        admin = PublicClient('https://one.acme.test:18443',trust=issuer_root)
        wait_managed_https(admin,runtime)
        password = re.search(r'^Password: (.+)$',(destination/'initial-admin-password.txt').read_text(),re.M)[1]
        assert admin.login('admin',password)['role'] == 'Admin'
        status = admin.api({'op':'tls_status'})
        assert status['https_state'] == 'ready' and status['certificate']['sha256'] == expected_leaf
        secure = PublicClient('https://one.acme.test:18443',trust=issuer_root)
        assert secure.request('/health')[0] == 200
        facts = certificate_facts(secure.handshakes[-1]['der'],['one.acme.test'],datetime.now(timezone.utc))
        assert facts['leaf_der_sha256'] == expected_leaf
        assert secure.login('admin',password)['role'] == 'Admin'
        tokens = json.loads(config.read_text())['agents']
        assert secure.rpc({'op':'whoami'},tokens['agent-a'])['agent_id'] == 'agent-a'
        sent = secure.rpc({'op':'send','recipient_id':'agent-b','text':'Owned moved ACME new-store witness'},tokens['agent-a'])['delivery']
        rows = secure.rpc({'op':'poll'},tokens['agent-b'])['deliveries']
        assert any(row['id']==sent['id']for row in rows)
        secure.rpc({'op':'ack','delivery_ids':[sent['id']]},tokens['agent-b'])
        runtime.stop()
        assert inventory(origin) == before, 'Copied runtime must never modify the original stopped tree'
        value['checks'].append({'name':'moved real TLS same leaf, Admin and A2A with original untouched',
                                'passed':True,'certificate':facts,'original_tree_unchanged':True})
        value['passed'] = True
        return value
    except BaseException as error:
        primary = error
        value['failure_type'] = type(error).__name__
        raise
    finally:
        cleanup = []
        try:
            if process:
                if process.poll() is None:
                    assert ticks(process.pid) == cli_ticks
                    os.killpg(process.pid,signal.SIGKILL)
                process.wait(timeout=5)
                value['cli_identity'].update(reaped=True,original_identity_absent=ticks(process.pid)!=cli_ticks)
        except BaseException as error:
            cleanup.append(type(error).__name__)
        try:
            runtime.stop()
        except BaseException as error:
            cleanup.append(type(error).__name__)
        value['cleanup_errors'] = cleanup
        if cleanup:
            value['passed'] = False
            if primary:
                primary.add_note('ACME rebind owned cleanup failed: '+','.join(cleanup))
        try:
            report = destination/'acme-rebind-report.json'
            report.write_text(json.dumps(value,indent=2)+'\n')
            report.chmod(0o600)
        except BaseException as error:
            if primary:
                primary.add_note('ACME rebind evidence failure: '+type(error).__name__)
            else:
                raise
        if cleanup and primary is None:
            raise AssertionError('Owned rebind fixture cleanup failed')
