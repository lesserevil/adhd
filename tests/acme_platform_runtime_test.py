"""Mocked transport/render/cleanup guards; no socket, compiler or resource starts."""
import importlib.util
import errno
import json
from pathlib import Path
import selectors
import sys
import tempfile
import unittest
from urllib.error import URLError
from unittest.mock import patch
import yaml

sys.path.insert(0,str(Path(__file__).resolve().parent))
import acme_issuer_gateway as gateway
import acme_platform_adapters as adapters
import acme_platform_scenario as scenario
import acme_platform_commands as commands
ROOT=Path(__file__).resolve().parents[1]

class Stream:
 def __init__(self,reads):self.reads=list(reads);self.sent=bytearray();self.closed=False
 def setblocking(self,value):pass
 def recv(self,n):
  block=self.reads.pop(0)
  if len(block)>n:self.reads.insert(0,block[n:]);block=block[:n]
  return block
 def send(self,block):self.sent+=block;return len(block)
 def shutdown(self,how):pass
 def close(self):self.closed=True

class Selector:
 def __init__(self):self.keys={}
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def get_map(self):return self.keys
 def unregister(self,stream):del self.keys[stream]
 def register(self,stream,flags):self.keys[stream]=type('Key',(),{'fileobj':stream,'events':flags})()
 def select(self,timeout):return [(key,key.events) for key in list(self.keys.values())]

class Gateway(unittest.TestCase):
 def create(self,**kw):return gateway.IssuerGateway('172.30.0.1','172.30.0.0/24',['172.30.0.2'],**kw)
 def test_constructor_inert_and_exact_source_binding(self):
  with patch.object(gateway.socket,'socket',side_effect=AssertionError('No listener')):
   value=self.create();self.assertIsNone(value.listener)
  for bind,net,clients in [('0.0.0.0','0.0.0.0/0',['172.30.0.2']),('127.0.0.1','127.0.0.0/8',['127.0.0.2']),
    ('172.30.0.1','172.30.0.0/24',['172.31.0.2']),('172.30.0.1','172.30.0.0/24',['172.30.0.1'])]:
   with self.assertRaises(AssertionError):gateway.IssuerGateway(bind,net,clients)
 def test_opaque_fragmented_tls_forwarding_both_directions(self):
  # Includes binaryTLS framing and HTTP-looking bytes; no TLS/HTTP transformation.
  request=b'\x16\x03\x03\x00\x12Host: pebble\r\n\x00'
  response=b'\x17\x03\x03\xff\x00opaqueACMEbytes'
  incoming=Stream([request[:3],request[3:],b'']);outgoing=Stream([response[:1],response[1:],b''])
  value=self.create();value.active.add(incoming)
  with patch.object(gateway.socket,'create_connection',return_value=outgoing) as connect,patch.object(gateway.selectors,'DefaultSelector',Selector):
   value.forward(incoming,'172.30.0.2')
   connect.assert_called_once_with(('127.0.0.1',19100),timeout=3)
  self.assertEqual(outgoing.sent,request);self.assertEqual(incoming.sent,response)
  self.assertEqual(value.errors,[]);self.assertFalse(value.active)
  self.assertTrue(incoming.closed and outgoing.closed)
 def test_unregistered_source_never_reaches_ca(self):
  value=self.create();incoming=Stream([]);value.active.add(incoming)
  with patch.object(gateway.socket,'create_connection',side_effect=AssertionError('No CA connection')) as connect:
   value.forward(incoming,'172.30.0.3');connect.assert_not_called()
  self.assertTrue(incoming.closed);self.assertFalse(value.active);self.assertTrue(value.errors)
 def test_byte_cap_and_selector_failure_close_both_streams(self):
  for broken in [False,True]:
   value=self.create(max_bytes=2);incoming=Stream([b'over-cap',b'']);outgoing=Stream([b'',b'']);value.active.add(incoming)
   selector=patch.object(gateway.selectors,'DefaultSelector',side_effect=OSError('controlled FD exhaustion')) if broken else patch.object(gateway.selectors,'DefaultSelector',Selector)
   with patch.object(gateway.socket,'create_connection',return_value=outgoing),selector:value.forward(incoming,'172.30.0.2')
   self.assertTrue(value.errors);self.assertTrue(incoming.closed and outgoing.closed);self.assertFalse(value.active)
 def test_listener_failure_closes_created_socket(self):
  class Failing:
   closed=False
   def bind(self,*a):raise OSError('occupied')
   def close(self):self.closed=True
  stream=Failing()
  with patch.object(gateway.socket,'socket',return_value=stream):
   with self.assertRaises(OSError):self.create().start()
  self.assertTrue(stream.closed)

class Deployment(unittest.TestCase):
 def test_both_adapter_constructors_inert(self):
  def denied(*a,**kw):raise AssertionError('No commands')
  with tempfile.TemporaryDirectory() as raw:
   work=Path(raw)
   adapters.Compose(denied,ROOT,work,'sha256:'+'a'*64,'adhd-acme-test',work/'seed',work/'state','172.30.0.1')
   adapters.Kind(denied,ROOT,work,'sha256:'+'a'*64,'adhd-acme-test','kindest/node@sha256:'+'b'*64,
                 '172.30.0.1','c'*64,'owned-acme-network',{},'adhd-hub:actual')
 def test_compose_only_fixture_host_bind_changes(self):
  with tempfile.TemporaryDirectory() as raw:
   work=Path(raw);argv=adapters.render_compose(ROOT,work,'172.30.0.1');text=(work/'fixture.compose.yaml').read_text()
   self.assertIn('ports: !override ["127.0.0.1:18766:8766", "127.0.0.2:80:8080", "127.0.0.2:443:8443"]',text)
   self.assertIn('pebble:172.30.0.1',text);self.assertNotIn('user:',text);self.assertNotIn('entrypoint:',text)
   self.assertEqual(len(argv),6)
 def test_kind_shipped_security_pvc_and_public_private_ports_preserved(self):
  docs=adapters.render_kind(ROOT,'adhd-final-acme-test','sha256:'+'a'*64,{'hub.json':json.dumps({'host':'0.0.0.0','port':8766,'store_path':'/data/hub.dets','matcher':None,'eventing':{'enabled':False},'projects':[{'settings':{}}]}),'directory-root.pem':'testCA'},'172.30.0.1','adhd-hub:actual')
  self.assertEqual(len(docs),5);self.assertNotIn('kafka',str([d['metadata']['name'] for d in docs]))
  deployment=next(d for d in docs if d['kind']=='Deployment');spec=deployment['spec'];pod=spec['template']['spec'];hub=pod['containers'][0]
  self.assertEqual(spec['strategy']['type'],'Recreate');self.assertEqual(spec['replicas'],1)
  self.assertEqual(pod['securityContext']['runAsUser'],10001);self.assertFalse(pod['automountServiceAccountToken'])
  self.assertTrue(hub['securityContext']['readOnlyRootFilesystem']);self.assertEqual(hub['securityContext']['capabilities']['drop'],['ALL'])
  self.assertFalse('command' in hub or 'args' in hub);self.assertEqual(hub['imagePullPolicy'],'Never')
  self.assertEqual([p['containerPort'] for p in hub['ports']],[8766,8080,8443])
  public=next(d for d in docs if d['kind']=='Service' and d['metadata']['name']=='hub-public-tls')
  self.assertEqual(public['spec']['type'],'LoadBalancer');self.assertEqual([p['port'] for p in public['spec']['ports']],[80,443])
  self.assertEqual([p['nodePort'] for p in public['spec']['ports']],[32080,32443])
  self.assertEqual(next(v for v in hub['volumeMounts'] if v['mountPath']=='/config')['name'],'state')
 def test_seed_denies_broker_model_or_private_listener_fallback(self):
  base={'host':'0.0.0.0','port':8766,'store_path':'/data/hub.dets','matcher':None,'eventing':{'enabled':False},'projects':[{'settings':{}}]}
  self.assertEqual(adapters.validate_seed(json.dumps(base)),base)
  for key,value in [('host','127.0.0.1'),('store_path','/foreign/store'),('matcher','http://provider'),('eventing',{'enabled':True}),('tls',{'enabled':True}),('projects',[{'settings':{'matcher':'http://provider'}}])]:
   bad=dict(base);bad[key]=value
   with self.assertRaises(AssertionError):adapters.validate_seed(json.dumps(bad))
 def test_state_probe_safe_exact_mount_no_app_entrypoint(self):
  with tempfile.TemporaryDirectory() as raw:
   calls=[]
   def command(argv,**kw):calls.append((argv,kw));return None
   probe=adapters.StateProbe(command,'sha256:'+'a'*64,Path(raw))
   probe.docker('run','--entrypoint','/bin/sh','sha256:'+'a'*64,'-ec',adapters.STATE)
   argv=calls[0][0];self.assertIn('10001:10001',argv);self.assertIn('type=bind,src='+raw+',dst=/config,readonly',argv)
   self.assertNotIn('CHOWN',argv);self.assertNotIn('hub.exs',str(argv))
 def test_only_connection_refusal_is_readiness_pending(self):
  class Client:
   def __init__(self,error):self.error=error
   def request(self,*a):raise self.error
  self.assertFalse(scenario.managed_health(Client(URLError(ConnectionRefusedError(errno.ECONNREFUSED,'refused')))))
  for error in [URLError(OSError(errno.EHOSTUNREACH,'unreachable')),ValueError('wrong TLS')]:
   with self.assertRaises(type(error)):scenario.managed_health(Client(error))

class Commands(unittest.TestCase):
 def instance(self,work):
  return commands.Commands({'docker':'/usr/bin/docker','kind':'/usr/local/bin/kind','kubectl':'/usr/local/bin/kubectl'},
   {'PATH':'/usr/bin:/bin','HOME':str(work),'DOCKER_HOST':'unix:///run/docker.sock',
    'DOCKER_CONFIG':str(work),'KUBECONFIG':str(work/'kubeconfig'),'LANG':'C.UTF-8'},work)
 def test_constructor_and_env_failclosed_without_process(self):
  with tempfile.TemporaryDirectory() as raw,patch.object(commands.subprocess,'Popen',side_effect=AssertionError('No spawn')):
   command=self.instance(Path(raw))
   with self.assertRaises(AssertionError):command.prepare(['sh','-c','arbitrary'],{})
   with self.assertRaises(AssertionError):command.prepare(['docker','inspect','owned'],{'DOCKER_HOST':'foreign'})
   actual,env=command.prepare(['docker','inspect','owned'],{'ADHD_PORT':'18766'})
   self.assertEqual(actual[0],'/usr/bin/docker');self.assertEqual(env['DOCKER_HOST'],'unix:///run/docker.sock')
 def test_selector_failure_preserves_primary_and_closes_owned_child(self):
  with tempfile.TemporaryDirectory() as raw:
   command=self.instance(Path(raw));record={'process':object()};closed=[]
   with patch.object(command,'issue',return_value=record),patch.object(command,'stop',side_effect=lambda row:closed.append(row)),\
        patch.object(commands.selectors,'DefaultSelector',side_effect=OSError('controlled selector failure')):
    # Need stdout handles to reach the actual selector-construction point.
    class Process:
     stdout=object();stderr=object();stdin=object()
    record['process']=Process()
    with self.assertRaisesRegex(OSError,'controlled selector failure'):command(['docker','inspect','owned'])
   self.assertEqual(closed,[record])
 def test_portforward_only_long_lived_command(self):
  with tempfile.TemporaryDirectory() as raw:
   command=self.instance(Path(raw))
   with patch.object(command,'issue',return_value='owned') as issue:
    self.assertEqual(command.start(['kubectl','port-forward','--address=127.0.0.1','service/hub','18766:8766']),'owned')
    self.assertTrue(issue.call_args.kwargs['persistent'])
    for argv in [['docker','run','arbitrary'],['kubectl','port-forward','--address=0.0.0.0']]:
     with self.assertRaises(AssertionError):command.start(argv)
 def test_reused_pid_never_signalled(self):
  with tempfile.TemporaryDirectory() as raw:
   command=self.instance(Path(raw))
   class Process:
    pid=99999
    def poll(self):return None
   record={'process':Process(),'closed':False,'start_ticks':'original'}
   with patch.object(commands,'ticks',return_value='changed'),patch.object(commands.os,'killpg') as kill:
    with self.assertRaises(AssertionError):command.stop(record)
    kill.assert_not_called()

if __name__=='__main__':unittest.main()
