"""Owned direct API bootstrap input; no commands or sockets on import."""
import base64
import hashlib
import ipaddress
import re
import socket
import ssl

NAME='kubernetes-services-endpoint'
PORT=6443

def address_for(node,api,plan,known_id,known_network):
 assert node['Id']==known_id and node['Name']=='/'+plan['node'] and node['State']['Running']
 assert node['Image']==plan['node_image']['configuration_digest']
 assert node['Config']['Labels']['io.x-k8s.kind.cluster']==plan['cluster']
 assert node['Config']['Labels']['io.x-k8s.kind.role']=='control-plane'
 assert set(node['NetworkSettings']['Networks'])=={plan['network']}
 network=node['NetworkSettings']['Networks'][plan['network']];assert network['NetworkID']==known_network
 assert api['metadata']['name']==plan['node'] and api['metadata']['uid']
 addresses=[v['address']for v in api['status']['addresses']if v['type']=='InternalIP']
 assert addresses==[network['IPAddress']]
 address=ipaddress.ip_address(addresses[0]);subnet=ipaddress.ip_network(plan['bridge_subnet'])
 assert address.version==4 and address in subnet and address not in (subnet.network_address,subnet.broadcast_address) and not address.is_loopback
 return str(address)

def authority(kubeconfig,cluster):
 assert len(kubeconfig['clusters'])==1
 row=kubeconfig['clusters'][0];assert row['name']=='kind-'+cluster
 assert set(row['cluster'])=={'server','certificate-authority-data'}
 raw=base64.b64decode(row['cluster']['certificate-authority-data'],validate=True)
 assert 0<len(raw)<=65536 and b'BEGIN CERTIFICATE'in raw and b'PRIVATE KEY'not in raw
 return raw

def verify_tls(address,ca):
 assert str(ipaddress.IPv4Address(address))==address
 context=ssl.create_default_context(cadata=ca.decode('ascii'))
 assert context.verify_mode==ssl.CERT_REQUIRED and context.check_hostname
 with socket.create_connection((address,PORT),timeout=5)as raw:
  with context.wrap_socket(raw,server_hostname=address)as secured:
   certificate=secured.getpeercert(binary_form=True);assert certificate
 return {'authority_sha256':hashlib.sha256(ca).hexdigest(),'server_certificate_sha256':hashlib.sha256(certificate).hexdigest(),'verify_peer':True,'hostname_checked':address,'port':PORT,'timeout_seconds':5}

def configmap(address,namespace_uid,node_uid,nonce):
 assert str(ipaddress.IPv4Address(address))==address and re.fullmatch('[a-f0-9]{32}',nonce)
 assert all(re.fullmatch('[A-Za-z0-9-]{1,128}',value)for value in [namespace_uid,node_uid])
 return {'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':NAME,'namespace':'kube-system','labels':{'adhd-policy-owner':nonce},'annotations':{'adhd.policy/namespace-uid':namespace_uid,'adhd.policy/node-uid':node_uid}},'data':{'KUBERNETES_SERVICE_HOST':address,'KUBERNETES_SERVICE_PORT':str(PORT)}}

def inside_command(node_id,address):
 assert re.fullmatch('[a-f0-9]{64}',node_id)and str(ipaddress.IPv4Address(address))==address
 return ['exec',node_id,'kubectl','--kubeconfig=/etc/kubernetes/admin.conf','--server=https://'+address+':6443','get','namespace','kube-system','-o','json','--request-timeout=10s']


def controller_patch(deployment,expected,actual_configmap,proof):
 """One guarded diagnostic overlay, only the pinned controller's absent envFrom."""
 import copy
 metadata=deployment['metadata'];assert deployment['kind']==expected['kind']=='Deployment'
 assert metadata['name']==expected['metadata']['name']=='calico-kube-controllers'
 assert metadata['namespace']=='kube-system'and metadata['uid']
 assert deployment['spec']['selector']==expected['spec']['selector']
 assert deployment['spec']['template']['metadata']['labels']==expected['spec']['template']['metadata']['labels']
 containers=deployment['spec']['template']['spec']['containers'];pinned=expected['spec']['template']['spec']['containers']
 assert len(containers)==len(pinned)==1
 assert containers[0]['name']==pinned[0]['name']=='calico-kube-controllers'and'envFrom'not in containers[0]
 # API-defaulted termination fields are the only container additions permitted.
 assert set(containers[0])<=set(pinned[0])|{'resources','terminationMessagePath','terminationMessagePolicy'}
 assert containers[0].get('resources',{})==pinned[0].get('resources',{})
 for key,value in pinned[0].items():
  if key in ('livenessProbe','readinessProbe'):
   value=dict({'failureThreshold':3,'periodSeconds':10,'successThreshold':1,'timeoutSeconds':1},**value)
  assert containers[0][key]==value
 assert containers[0].get('terminationMessagePath','/dev/termination-log')=='/dev/termination-log'
 assert containers[0].get('terminationMessagePolicy','File')=='File'
 value=configmap(proof['address'],proof['namespace_uid'],proof['node_uid'],proof['owner_nonce'])
 cm=actual_configmap;assert cm['metadata']['uid']==proof['configmap_uid']
 assert cm['metadata']['name']==NAME and cm['metadata']['namespace']=='kube-system'
 assert cm['data']==value['data']and cm['metadata']['labels']==value['metadata']['labels']and cm['metadata']['annotations']==value['metadata']['annotations']
 patch=[{'op':'test','path':'/metadata/uid','value':metadata['uid']},
  {'op':'test','path':'/spec/template/spec/containers','value':copy.deepcopy(containers)},
  {'op':'add','path':'/spec/template/spec/containers/0/envFrom','value':[{'configMapRef':{'name':NAME}}]}]
 return patch
