"""Pure fault-fixture finally checks. No application imports, HTTP or subprocesses."""
import ast
import asyncio
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
from unittest.mock import Mock
from uuid import uuid4

SOURCE=Path(__file__).with_name('eventing_readiness_faults.py')
TREE=ast.parse(SOURCE.read_text())
selected=[n for n in TREE.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))and n.name in ('sanitized_case_diagnostic','assert_queue_control_capacity','assert_retention_policy_capacity','run_case')]
NAMESPACE={'asyncio':asyncio,'copy':copy,'time':time,'Path':Path,'uuid4':uuid4,'QUEUE_EVENTING_TIMEOUT_MS':3000,'QUEUE_RECOVERY_TIMEOUT_MS':10000,'BLUE':'blue','RED':'red'}
exec(compile(ast.Module(body=selected,type_ignores=[]),str(SOURCE),'exec'),NAMESPACE)
diagnostic=NAMESPACE['sanitized_case_diagnostic']

class Pure(unittest.TestCase):
 def test_whitelists_match_public_schema_exactly(self):
  schema=json.loads((SOURCE.parents[1]/'components/hub/project-recovery/interface.schema.json').read_bytes())['$defs']
  expected_states={row['properties']['state']['const']for row in schema['Operation']['oneOf']}
  fn=next(n for n in TREE.body if isinstance(n,ast.FunctionDef)and n.name=='sanitized_case_diagnostic')
  declared={n.targets[0].id:ast.literal_eval(n.value)for n in fn.body if isinstance(n,ast.Assign)and isinstance(n.targets[0],ast.Name)and n.targets[0].id in ('states','codes','reasons')}
  self.assertEqual(declared['states'],expected_states)
  self.assertEqual(declared['codes'],set(schema['Failure']['properties']['code']['enum']))
  self.assertEqual(declared['reasons'],set(schema['Reason']['enum']))
  for state in expected_states:self.assertEqual(diagnostic('lag',None,{'state':state},0,{},None,[])['selected_operation']['state'],state)
  self.assertIsNone(diagnostic('lag',None,{'state':'applying'},0,{},None,[])['selected_operation']['state'])
 def test_bounded_public_only(self):
  event={'at':1.5,'method':'GET','category':'configs','status':404,'selected_create':False,'injected':True,'actual_configuration':{'cleanup_policy':['delete','SECRET'],'retention_ms':['604800000','SECRET']},'authorization':'SECRET','path':'SECRET','body':'SECRET','topic':'SECRET'}
  proxy=SimpleNamespace(events=[event]*257)
  op={'state':'failed','operation_id':'SECRET','failure':{'code':'RESTORE_IO_ERROR','reason':'io','message':'SECRET','retryable':True},'result':'SECRET'}
  d=diagnostic('queue-control',proxy,op,3.2,{'eventing':{'timeout_ms':3000,'bearer_token':'SECRET'},'recovery':{'timeout_ms':10000}},AssertionError('SECRET'),['ValueError'])
  self.assertNotIn('SECRET',json.dumps(d));self.assertEqual(len(d['events']),256);self.assertTrue(d['events_truncated']);self.assertEqual(d['event_count'],257)
  self.assertEqual(d['selected_operation'],{'state':'failed','failure':{'code':'RESTORE_IO_ERROR','reason':'io','retryable':True}})
  self.assertEqual(d['cleanup_failure_types'],['ValueError']);self.assertEqual(d['assertion_or_primary_type'],'AssertionError')
 def test_no_operation_and_nonfinite_observation(self):
  d=diagnostic('lag',None,None,float('nan'),{},None,[])
  self.assertIsNone(d['selected_operation']);self.assertIsNone(d['elapsed_seconds']);self.assertEqual(d['events'],[])
 def test_incomplete_proxy_construction_has_no_events(self):
  for proxy in [None,SimpleNamespace()]:
   d=diagnostic('lag',proxy,None,None,{},ValueError('private'),[])
   self.assertFalse(d['events_available']);self.assertEqual(d['events'],[]);self.assertEqual(d['assertion_or_primary_type'],'ValueError')
 def test_unknown_failure_is_not_retained(self):
  d=diagnostic('queue',None,{'state':'SECRET','failure':{'code':'SECRET','reason':'SECRET','retryable':'SECRET'}},1,{},None,[])
  self.assertNotIn('SECRET',json.dumps(d));self.assertEqual(d['selected_operation'],{'state':None,'failure':{'code':None,'reason':None,'retryable':None}})
 def test_policy_arrays_are_bounded(self):
  p=SimpleNamespace(events=[{'actual_configuration':{'retention_ms':['1']*20,'cleanup_policy':['delete']*20}}])
  d=diagnostic('lag',p,None,1,{},None,[]);c=d['events'][0]['actual_configuration'];self.assertEqual(len(c['retention_ms']),8);self.assertTrue(c['retention_ms_truncated']);self.assertTrue(c['cleanup_policy_truncated'])
 def test_real_independent_capacity_premise(self):
  check=NAMESPACE['assert_queue_control_capacity']
  for active in [0,1]:
   status={'limits':{'eventing_concurrency':2,'project_eventing_concurrency':1},'lanes':{'eventing':{'active':active,'queued':0,'projects':{'blue':{'active':active,'queued':0},'red':{'active':0,'queued':0}}}}}
   self.assertGreaterEqual(check(status)['independent_red_slots_at_observation'],1)
  for change in ['global1','local2','red-active','red-queued','blue-queued','unknown-active']:
   status={'limits':{'eventing_concurrency':2,'project_eventing_concurrency':1},'lanes':{'eventing':{'active':1,'queued':0,'projects':{'blue':{'active':1,'queued':0}}}}}
   lane=status['lanes']['eventing']
   if change=='global1':status['limits']['eventing_concurrency']=1
   elif change=='local2':status['limits']['project_eventing_concurrency']=2
   elif change=='red-active':lane['projects']['red']={'active':1,'queued':0};lane['active']=2
   elif change=='red-queued':lane['projects']['red']={'active':0,'queued':1};lane['queued']=1
   elif change=='blue-queued':lane['projects']['blue']['queued']=1;lane['queued']=1
   else:lane['projects']['unknown']={'active':1,'queued':0};lane['active']=2
   with self.assertRaises(AssertionError):check(status)
 def test_only_positive_resource_profile_changes(self):
  # Evaluate the actual assignment expression, not a parallel test definition.
  assignment=next(n for n in ast.walk(TREE)if isinstance(n,ast.Assign)and isinstance(n.value,ast.Dict)and any(isinstance(k,ast.Constant)and k.value=='eventing_concurrency'for k in n.value.keys))
  for case,want in [('queue',1),('queue-control',2)]:
   value=eval(compile(ast.Expression(assignment.value),str(SOURCE),'eval'),{'case':case})
   self.assertEqual(value,{'eventing_concurrency':want,'project_eventing_concurrency':1})
 def _failure_case(self,case):
  # Execute the real run_case coroutine, with every product/service boundary
  # replaced by in-memory fakes; force the original line141 assertion to fail.
  self_outer=self;calls=[];publication={'id':'public-id'}
  class Actor:
   async def call(self,command):
    if command['op']=='publish_record':return {'record':{'publication':publication}}
    if command['op']=='get_record':return {'record':{'publication':publication}}
    if command['op']=='poll':return {'deliveries':[]}
    return {}
  class Fixture:
   def __init__(self,*a,**kw):self.config={'eventing':{}};self.image_runtime=True;self.file=Path('/not-opened');self.process=None
   async def start(self):calls.append('start-fake')
   async def agent(self,*a):return Actor()
   def admin(self):
    status={'limits':{'eventing_concurrency':2 if case=='queue-control'else 16,'project_eventing_concurrency':1 if case=='queue-control'else 2},'lanes':{'eventing':{'active':1,'queued':0,'projects':{'blue':{'active':1,'queued':0}}}}}
    def call(command,**kw):
     if command['op']=='resource_status':calls.append('capacity');return status
     if command['op']=='config_update':
      self_outer.assertIn(case,e.value['retention_policy_capacity']);self_outer.assertEqual(self.config['eventing']['timeout_ms'],1000);calls.append('config-update');raise RuntimeError('declared fake stop after capacity')
     return {'config_revision':1,'config':{'eventing':{'retention_ms':604800000}}}
    return SimpleNamespace(call=call)
   async def close(self):calls.append('fixture-close');raise ValueError('SECRET cleanup detail')
   def bind_evidence(self,*a,**kw):calls.append('bind')
  class Proxy:
   def __init__(self,*a):
    self.url='http://unused';self.events=[];self.release=Mock();self.handlers=0;self.failures=[];self.thread=SimpleNamespace(is_alive=lambda:False)
   def arm(self,*a):self.events=[{'at':1,'method':'POST','category':None,'selected_create':True,'status':201,'injected':False},{'at':1.1,'method':'GET','category':'configs','selected_create':False,'status':404,'injected':True,'actual_configuration':{'cleanup_policy':['delete'],'retention_ms':['604800000']}}]
   def close(self):calls.append('proxy-close')
  class Recovery:
   def __init__(self,*a):self.n=0
   async def initialize(self,*a):return [{'result':{'topic':'not retained'}}]
   def call(self,*a,**kw):return {}
   def revision(self):return 1
   async def settle(self,*a):
    self.n+=1
    return {'plan':{'plan_id':'plan','plan_sha256':'a'*64,'selected':{'topic':'not retained'}}}if self.n==1 else {'state':'failed','failure':{'code':'RESTORE_IO_ERROR','reason':'io','retryable':True}}
   def assert_plan(self,*a):pass
  async def poll_until(*a):return [{'id':'delivery','publication_id':'public-id'}]
  class Evidence:
   value={}
   def __init__(self):self.value={};self.writes=0
   def write(self):self.writes+=1
  NAMESPACE.update(Fixture=Fixture,ReadinessProxy=Proxy,Recovery=Recovery,scoped=lambda project,op,**kw:{'op':op,**kw},route=lambda *a:({'fixed':'route'},None),poll_until=poll_until,reap_owned_native=lambda *a:None)
  e=Evidence();args=SimpleNamespace(keep_work=None,eventing_rest_url='unused',recovery_schema=None,deadline=1)
  expected=AssertionError if case=='queue-control'else RuntimeError
  with self.assertRaises(expected)as caught:asyncio.run(NAMESPACE['run_case'](args,case,e))
  self.assertEqual(type(caught.exception),expected);self.assertIn('ValueError',caught.exception.__notes__[0]);self.assertEqual(e.writes,1)
  d=e.value['case_diagnostics'][case];self.assertEqual(d['eventing_timeout_ms'],3000 if case=='queue-control'else 1000)
  self.assertEqual(len(d['events']),2);self.assertEqual(d['cleanup_failure_types'],['ValueError']);self.assertEqual(d['assertion_or_primary_type'],expected.__name__);self.assertIn('proxy-close',calls);self.assertNotIn('SECRET',json.dumps(e.value))
  return e,calls
 def test_actual_run_case_failure_capture_and_primary_survives_cleanup(self):
  e,calls=self._failure_case('queue-control');d=e.value['case_diagnostics']['queue-control']
  self.assertEqual(e.value['queue_control_capacity']['queue-control']['premise']['independent_red_slots_at_observation'],1)
  self.assertEqual(d['selected_operation']['state'],'failed');self.assertEqual(d['selected_operation']['failure']['reason'],'io');self.assertEqual(d['recovery_timeout_ms'],10000)
 def test_existing_retention_checks_capacity_before_config_update(self):
  e,calls=self._failure_case('existing-retention')
  self.assertLess(calls.index('capacity'),calls.index('config-update'))
  self.assertEqual(e.value['retention_policy_capacity']['existing-retention']['premise']['spare_blue_tickets_at_observation'],1)
 def test_retention_capacity_guard_and_default_global(self):
  check=NAMESPACE['assert_retention_policy_capacity']
  for active in [0,1]:
   status={'limits':{'eventing_concurrency':16,'project_eventing_concurrency':2},'lanes':{'eventing':{'active':active,'queued':0,'projects':{'blue':{'active':active,'queued':0}}}}}
   self.assertGreaterEqual(check(status)['spare_blue_tickets_at_observation'],1)
  for change in ['old-local1','wrong-global','blue-full','blue-queued','other-active','other-queued']:
   status={'limits':{'eventing_concurrency':16,'project_eventing_concurrency':2},'lanes':{'eventing':{'active':1,'queued':0,'projects':{'blue':{'active':1,'queued':0}}}}}
   lane=status['lanes']['eventing']
   if change=='old-local1':status['limits']['project_eventing_concurrency']=1
   elif change=='wrong-global':status['limits']['eventing_concurrency']=2
   elif change=='blue-full':lane['projects']['blue']['active']=2;lane['active']=2
   elif change=='blue-queued':lane['projects']['blue']['queued']=1;lane['queued']=1
   elif change=='other-active':lane['projects']['red']={'active':1,'queued':0};lane['active']=2
   else:lane['projects']['red']={'active':0,'queued':1};lane['queued']=1
   with self.assertRaises(AssertionError):check(status)
  assignment=next(n for n in ast.walk(TREE)if isinstance(n,ast.Assign)and isinstance(n.value,ast.Dict)and len(n.value.keys)==1 and isinstance(n.value.keys[0],ast.Constant)and n.value.keys[0].value=='project_eventing_concurrency')
  self.assertEqual(ast.literal_eval(assignment.value),{'project_eventing_concurrency':2})


if __name__=='__main__':unittest.main()
