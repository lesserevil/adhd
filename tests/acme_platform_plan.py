#!/usr/bin/env python3
"""Inert ACME deployment preparation. This program cannot launch resources.

The target is deliberately unbound until a proper accepted artifact/image exists.
This is a concrete deployment/acceptance recipe, not an execution-ready gate.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

FILES=(
 'deploy/app.compose.yaml','deploy/app.acme.compose.yaml','deploy/events.compose.yaml',
 'deploy/k8s/hub.yaml','deploy/k8s/events.yaml','deploy/k8s/private.yaml','deploy/k8s/kustomization.yaml',
 'deploy/k8s/acme/kustomization.yaml','deploy/k8s/acme/hub-listeners.yaml',
 'deploy/k8s/acme/public-service.yaml','deploy/init-config.py',
 'tests/acme_challenge_relay.py','tests/acme_runtime.py','tests/acme_acceptance_fixtures.py',
 'tests/acme_process_observer.py','tests/image_compiled_inputs.py',
 'tests/kafka_oauth_custody.py','tests/container_fixture.py','tests/kafka_platform_vm.py',
 'tests/network_policy_image_custody.py','tests/acme_issuer_gateway.py','tests/acme_platform_adapters.py',
 'tests/acme_platform_commands.py','tests/acme_platform_scenario.py','tests/acme_platform_matrix.py')
CHECKS=(
 'actual_admitted_image_source_cache_tool_identity',
 'shipped_public_80_443_mappings_private_8766_boundary',
 'single_writer_private_config_and_data_mounts',
 'default_disabled_public_admin_initialization',
 'real_ca_http01_token_host_proof',
 'challenge_non_token_and_private_http_not_public',
 'trusted_hostname_verified_https_and_admin',
 'manual_real_renew_receipt_replay_same_vm',
 'scheduled_real_renew_without_manual_request_same_vm',
 'managed_account_active_key_and_leaf_private_state',
 'replacement_new_container_or_pod_same_volume_account_leaf',
 'replacement_trusted_https_no_reissue_required',
 'strict_all_owned_resource_cleanup_protected_resources_unchanged')


def digest(raw):return hashlib.sha256(raw).hexdigest()


def regular(path,limit=8*1024*1024):
 path=Path(path).absolute();assert path.resolve(strict=True)==path
 before=path.lstat();assert stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=limit
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
 identity=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
 with os.fdopen(fd,'rb') as source:
  assert identity(os.fstat(source.fileno()))==identity(before)
  raw=source.read(limit+1);assert len(raw)<=limit
  assert identity(os.fstat(source.fileno()))==identity(before)
 assert identity(path.lstat())==identity(before)
 return raw


def ca_binding(path,expected):
 raw=regular(path);assert digest(raw)==expected
 value=json.loads(raw)
 assert value['schema']=='adhd/acme-pebble-owned-fixture@1'
 assert value['ready'] is True and value['real_validation'] is True and value['nonce_validation'] is True
 assert value['public_ca_calls']==0 and value['validation_http_port']==8080 and value['validity_seconds']==90
 assert value['directory_url']=='https://localhost:19100/dir'
 assert value['initial_domain_routes']['one.acme.test']=='127.0.0.1'
 assert type(value['lifetime_seconds']) is int and 1<=value['lifetime_seconds']<=10800
 for name in ('frontend_root','issuer_root'):
  assert digest(regular(value[name]))==value[name+'_sha256']
 return {'manifest_sha256':expected,'generation_issuer_root_sha256':value['issuer_root_sha256'],
         'frontend_root_sha256':value['frontend_root_sha256'],'owner_pid':value['owner_pid'],
         'processes':value['processes'],'lifetime_seconds':value['lifetime_seconds'],
         'actual_live_lease_revalidated':False}


def private_port(value):
 assert type(value) is int and 1024<=value<=65535
 assert value not in {8080,8443,8766,18082,18085,18088,18089,18443,18770,19100,19101,19102,19103,19104,19153},'Reserved service port'
 return value


def recipe(platform,private_http_port=18766):
 assert platform in ('compose','kind');private_http_port=private_port(private_http_port)
 common={'checks':list(CHECKS),'ordered':True,'public_ca_calls':0,'provider_calls':0,'broker_starts':0,
 'endpoints':{'private_http':'http://127.0.0.1:'+str(private_http_port),'https':'https://one.acme.test',
              'https_connect_ip':'127.0.0.2','challenge_relay':'127.0.0.1:8080',
              'relay_upstream':'127.0.0.2:80','issuer':'https://pebble:19104/dir'},
 'tls_public_patch':{'enabled':True,'host':'0.0.0.0','port':8443,'challenge_host':'0.0.0.0','challenge_port':8080,
   'acme':{'enabled':True,'directory_url':'https://pebble:19104/dir','email':'operator@one.acme.test',
           'domains':['one.acme.test'],'accept_terms':True,'renew_before_days':1,'retry_seconds':30,
           'order_timeout_ms':30000,'ca_cert_file':'directory-root.pem'}},
 'bounds':{'startup_seconds':45,'initial_issuance_seconds':35,'manual_renewal_seconds':40,
           'scheduled_renewal_seconds':100,'relay_requests':128,'relay_concurrency':8,
           'replacement_seconds':45,'cleanup_seconds':180},
 'scenario':[
  'Public Admin login with own initial password; publicly initialize only unknown projects; eventing false and matcher null.',
  'Assert disabled TLS and private HTTP health; observe actual immutable runtime custody before enabling TLS.',
  'Submit confirmed public config_update with the declared TLS patch and HTTPS public_url; real CA GET must match a real active token proof.',
  'Verify wrong token/foreign Host/non-challenge paths do not expose application data on public80; only native TLS on443.',
  'Verify real issuer chain plus one.acme.test hostname via trusted HTTPS; Admin session uses Secure cookie on HTTPS.',
  'Submit one public tls_renew; observe changed serial/leaf/SPKI and identical VM; replay exact receipt without second operation.',
  'Make no further renewal request; observe actual scheduled generation rotation in100s and same VM.',
  'Gracefully stop only own hub; fingerprint actual private account/current generation/leaf/key and config identity without logging secret bytes.',
  'Replace container or pod, never delete/reseed its config/data volume; require new immutable runtime identity and exact retained account/current leaf/key.',
  'Verify trusted HTTPS/public status on replacement before any scheduled transition; if real leaf expired/due, report timing failure rather than weaken equality.',
  'Finally independently close relay/issuer gateway/clients/owned deployment; qualify only after all recorded resources absent and protected snapshot unchanged.'],
 'relay_ownership':'One explicit exclusive relay owner, coordinated with acceptance at quiet boundary; no native/fault/browser overlap.',
 'issuer_gateway':'New test-only byte-transparent TCP gateway bound to exact owned bridge-host IP19104, source-restricted to actual owned app/node IP. Forward unchanged TLS to127.0.0.1:19100. CA frontend SAN already includes pebble. No TLS termination/header/body rewriting, no0.0.0.0 bind.',
 'state_evidence':'Initial UID10001 read-only/network-none/drop-ALL owned probe verifies private state/config/data without inaccessible host-child traversal. Hash-only stopped account/current certificate/private-key inventory with exact modes/UID, no private key/account content in durable report.'}
 if platform=='compose':
  common.update(owned_project='adhd-acme-platform-compose01',
   preparation=['docker compose -f deploy/app.compose.yaml -f deploy/app.acme.compose.yaml -f fixture.compose.yaml config --format json'],
   commands=[['docker','compose','--project-name','adhd-acme-platform-compose01','-f','deploy/app.compose.yaml','-f','deploy/app.acme.compose.yaml','-f','fixture.compose.yaml','up','-d','--no-deps','hub'],
             ['docker','compose','--project-name','adhd-acme-platform-compose01','-f','deploy/app.compose.yaml','-f','deploy/app.acme.compose.yaml','-f','fixture.compose.yaml','up','-d','--no-deps','--force-recreate','hub']],
   fixture_changes={'ports_override':['127.0.0.1:'+str(private_http_port)+':8766','127.0.0.2:80:8080','127.0.0.2:443:8443'],
     'extra_hosts':['pebble:<ACTUAL_OWNED_BRIDGE_HOST_IP>'],
     'mounts':'Same complete private config/data across replacement; frontend trust under config. No mount over/runtime/adhd.',
     'eventing':'disabled in own fresh seed; --no-deps must start only hub; no broker/REST containers'},
   custody='Exact project/service labels, image config/source/cache/tool hashes, Docker host PID/startticks/BEAM argv, read-only root, user10001, cap-drop/no-new-privileges; replacement CID/PID must differ.',
   cleanup='Inspect exact labels/IDs before down; preserve private stopped state as evidence. Remove only own containers/networks, no -v against unrelated state; strict ID+name absence and project census. No Kafka/proxy start permitted.')
 else:
  common.update(owned_cluster='adhd-acme-platform01',owned_namespace='adhd-acme-platform01',
   preparation=['kubectl kustomize deploy/k8s/acme; select shipped hub/PVC/private/public Service only; exclude event resources from AUTH-only fixture explicitly'],
   commands=[['kind','create','cluster','--name','adhd-acme-platform01','--config','fixture-kind.yaml'],
             ['kind','load','docker-image','<ACTUAL_ACCEPTED_TAG>','--name','adhd-acme-platform01'],
             ['kubectl','--kubeconfig','<OWN_INLINE_KUBECONFIG>','create','-f','owned-namespace.json','-o','json'],
             ['kubectl','--kubeconfig','<OWN_INLINE_KUBECONFIG>','apply','-f','owned-rendered-acme.yaml']],
   fixture_changes={'kind_published_ports':[{'listenAddress':'127.0.0.2','hostPort':80,'containerPort':32080},
       {'listenAddress':'127.0.0.2','hostPort':443,'containerPort':32443}],
     'public_service':'Shipped LoadBalancer type80/443/targetPort retained; assign explicit owned nodePorts32080/32443 for Kind TCP mapping. No cloud-provider LB provisioning claim.',
     'private_access':'Only owned kubectl port-forward loopback'+str(private_http_port)+'→private ClusterIP8766; public Service must not contain8766.',
     'hostAliases':'pebble maps exact reachable owned bridge-host issuer gateway, no hostDNS edits.',
     'volume':'Original Recreate1/PVC/UID10001/RO-root/cap-drop/security retained; only owned PVC seeded once, retained across pod replacement.'},
   custody='New owned nodeCID/image/starttime/APIbinding and loaded CRI config digest; actual hub PodUID/containerID/manifest-config/BEAM process custody; same PVCUID, new PodUID after preconditioned delete.',
   cleanup='Namespace issued nonce before create; observe UID even ambiguous create; delete with UID precondition; independent namespace/PVC/PV absence. Delete only exact owned Kind node/network/anonymous volumes, strict ID/name absence. Protected existing clusters and all original namespaceUIDs unchanged.')
 return common


def prepare(args):
 root=Path(args.repo_root).absolute();assert root.resolve(strict=True)==root
 work=Path(args.work).absolute();assert work.resolve()==work and not work.exists()
 assert re.fullmatch('[a-f0-9]{64}',args.ca_manifest_sha256)
 ca=ca_binding(args.ca_manifest,args.ca_manifest_sha256)
 files={name:digest(regular(root/name)) for name in FILES}
 plan={'schema':'adhd/acme-platform-inert-preparation@1','execution_ready':False,'execution_supported':False,
       'target_binding':None,'source_count_or_native_count_frozen':False,'ca':ca,'files':files,
       'platforms':[recipe('compose',args.private_http_port),recipe('kind',args.private_http_port)],
       'serial_only':True,'relay_owner_count':1,'public_ca_calls':0,'provider_calls':0,
       'scope':'New managed ACME platform gates only; not Kafka/model/federation or providerLoadBalancer/CNI qualification.',
       'required_before_freeze':['Actual proper receipt/export/context/admission and compiled image/tool/cache identity.',
        'Review concrete gateway/adapters and bind actual owned bridge IP/client-source restrictions.',
        'Integrate concrete adapters/public scenario into final closed target driver; preserve all declared checks, no declaration-as-pass.',
        'Closed full helper/deployment/host tools/socket/kubeconfig/fresh resource identity and once-marker snapshot.',
        'Actual current CA generation process/starttick/trust/remaining lease check at quiet boundary; acceptance relay ownership release.',
        'Root GO of fresh fully bound executable plan; no tool in this program starts any runtime.']}
 work.mkdir(parents=True,mode=0o700)
 output=work/'plan.json'
 with output.open('x') as stream:json.dump(plan,stream,indent=2);stream.write('\n')
 output.chmod(0o600)
 print(json.dumps({'prepared':True,'executed':False,'execution_ready':False,'plan_sha256':digest(regular(output))}))


def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--repo-root',type=Path,required=True);parser.add_argument('--work',type=Path,required=True)
 parser.add_argument('--private-http-port',type=int,default=18766)
 parser.add_argument('--ca-manifest',type=Path,required=True);parser.add_argument('--ca-manifest-sha256',required=True)
 prepare(parser.parse_args())

if __name__=='__main__':main()
