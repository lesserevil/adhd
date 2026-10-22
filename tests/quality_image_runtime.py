#!/usr/bin/env python3
"""Bounded live-provider relay and custody for unchanged four quality scripts."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import runpy
import socket
import sys
import threading
import time
sys.dont_write_bytecode=True
import controlled_sdk_runtime as sdk
from optimization_provider_io import exchange
from optimization_neutral_runtime import safe_append,append_held_log,regular,log_digest


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class Relay:
 def __init__(self,job,log):
  self.job=job;self.log=log;self.count=0;self.inflight=0;self.handlers=0;self.closed=False;self.violations=[];self.errors=[];self.events=[];self.log_sha256=None;self.sockets=set();self.lock=threading.Condition()
  self.deadline=time.monotonic()+job['provider_window_seconds'];self.handle=safe_append(log,require_new=True);info=os.fstat(self.handle.fileno());self.identity=(info.st_dev,info.st_ino);outer=self
  class Handler(BaseHTTPRequestHandler):
   def setup(self):
    super().setup();self.connection.settimeout(max(.001,min(10,outer.deadline-time.monotonic())));outer.register(self.connection)
   def finish(self):
    try:super().finish()
    finally:outer.unregister(self.connection)
   def log_message(self,*_):pass
   def do_POST(self):
    row=None;admitted=False
    try:
     length=self.headers.get('Content-Length','');assert length.isdecimal() and 0<int(length)<=65536 and self.path=='/v1/systemone'
     raw=self.rfile.read(int(length));assert len(raw)==int(length)
     payload=json.loads(raw);number=outer.admit(payload);admitted=True;started=time.monotonic();row={'sequence':number,'request_sha256':hashlib.sha256(raw).hexdigest(),'request_json':raw.decode()}
     try:status,body=exchange('http://127.0.0.1:18770/v1/systemone',raw,min(outer.deadline,started+10),outer.register,outer.unregister)
     except BaseException as error:status,body=502,b'{}';row['transport_error_type']=type(error).__name__
     row.update(status=status,response_sha256=hashlib.sha256(body).hexdigest(),response_text=body.decode(),elapsed_seconds=time.monotonic()-started)
     if not 200<=status<300:outer.errors.append('ProviderHTTP'+str(status))
     self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    except BaseException as error:
     with outer.lock:outer.errors.append(type(error).__name__)
     try:self.send_error(503)
     except OSError:pass
    finally:
     with outer.lock:
      if row is not None:
       try:append_held_log(outer.handle,outer.log,outer.identity,(json.dumps(row)+'\n').encode());outer.events.append(row)
       except BaseException as error:outer.violations.append('ExchangeLogCustody'+type(error).__name__)
      if admitted:outer.inflight-=1
      outer.lock.notify_all()
  class Server(ThreadingHTTPServer):
   daemon_threads=True
   slots=threading.BoundedSemaphore(2)
   def process_request(self,request,address):
    if not self.slots.acquire(False):request.close();return
    with outer.lock:outer.handlers+=1
    try:super().process_request(request,address)
    except BaseException:
     self.slots.release()
     with outer.lock:outer.handlers-=1;outer.lock.notify_all()
     raise
   def process_request_thread(self,request,address):
    try:super().process_request_thread(request,address)
    finally:
     self.slots.release()
     with outer.lock:outer.handlers-=1;outer.lock.notify_all()
  try:
   self.server=Server(('127.0.0.1',0),Handler);self.url='http://127.0.0.1:'+str(self.server.server_port)+'/v1/systemone'
   self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.timer=threading.Timer(job['provider_window_seconds'],self.stop);self.timer.daemon=True;self.timer.start()
  except BaseException:
   try:
    self.stop()
    if hasattr(self,'timer'):self.timer.cancel()
    if hasattr(self,'thread') and self.thread.is_alive():self.server.shutdown();self.thread.join(2)
    if hasattr(self,'server'):self.server.server_close()
   finally:self.handle.close()
   raise
 def admit(self,payload):
  with self.lock:
   valid=(isinstance(payload,dict) and payload.get('model')=='Nemotron-Deciffusion-8B-v2.1' and isinstance(payload.get('state'),dict)
          and isinstance(payload.get('questions'),dict) and set(payload['questions']) in ({'intent'},{'useful'},{'answer','assessment'}))
   if self.closed or time.monotonic()>=self.deadline or self.count>=self.job['provider_post_cap'] or not valid:
    self.violations.append('BudgetDeadlineOrQuestionScope');raise AssertionError('Provider budget/scope rejected')
   self.count+=1;self.inflight+=1;return self.count
 def register(self,sock):
  with self.lock:
   if self.closed:sock.close();raise TimeoutError('Provider window closed')
   self.sockets.add(sock)
 def unregister(self,sock):
  with self.lock:self.sockets.discard(sock)
 def stop(self):
  with self.lock:
   self.closed=True
   for sock in list(self.sockets):
    try:sock.shutdown(socket.SHUT_RDWR)
    except OSError:pass
    sock.close()
   self.lock.notify_all()
 def close(self):
  self.timer.cancel();self.stop()
  try:
   try:
    with self.lock:assert self.lock.wait_for(lambda:self.inflight==0 and self.handlers==0,12),'Owned relay failed to settle'
   finally:self.server.shutdown();self.server.server_close();self.thread.join(2);self.timer.join(2)
  finally:
   try:
    info=regular(self.log);assert (info.st_dev,info.st_ino)==self.identity
    self.log_sha256=log_digest(self.log,self.identity)
   except BaseException as error:self.violations.append('FinalLogCustody'+type(error).__name__);raise
   finally:self.handle.close()
  assert not self.thread.is_alive() and not self.timer.is_alive()
 def evidence(self):return {'upstream_http_posts':self.count,'post_accounting':'Counted upstream attempts, including failed connection attempts; successful HTTP responses counted separately','completed_upstream_http_responses':sum('transport_error_type' not in e for e in self.events),'successful_provider_responses':sum(200<=e.get('status',0)<300 and 'transport_error_type' not in e for e in self.events),'post_cap':self.job['provider_post_cap'],'window_seconds':self.job['provider_window_seconds'],'relay_retries':0,'closed':self.closed,'inflight':self.inflight,'handlers':self.handlers,'violations':self.violations,'provider_error_types':self.errors,'exchange_log_sha256':self.log_sha256}


class QualityCustody(sdk.SDKCustody):
 def start(self,original,obj,*args,**kwargs):
  assert self.is_image(obj),'Quality lane requires actual image; no native fallback'
  return super().start(original,obj,*args,**kwargs)


def install_live(custody,relay):
 # Use the original recursive selector audit with this single owned relay URL.
 original=sdk.base.audit_models
 sdk.base.audit_models=lambda value,allowed,path=():original(value,{relay.url},path)
 custody.install()
 import federation_acceptance
 for method in ['start','stop']:
  function=getattr(federation_acceptance.Hub,method);wrapper=custody.start if method=='start' else custody.stop
  def observed(obj,*args,_original=function,_wrapper=wrapper,**kw):return _wrapper(_original,obj,*args,**kw)
  setattr(federation_acceptance.Hub,method,observed)


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True);p.add_argument('--job',required=True);p.add_argument('--reviewed-plan-sha256',required=True);a=p.parse_args()
 assert sha(a.plan)==a.reviewed_plan_sha256;plan=json.loads(a.plan.read_text());assert sha(__file__)==plan['frozen_inputs']['tests/quality_image_runtime.py']
 assert json.loads((a.plan.parent/'started.json').read_text())['plan_sha256']==a.reviewed_plan_sha256
 job=next(j for j in plan['jobs'] if j['name']==a.job);custody=QualityCustody(plan,job,Path(job['custody_report']));relay=None;primary=None;cleanup=[]
 try:
  relay=Relay(job,Path(job['provider_log']));install_live(custody,relay)
  argv=[relay.url if item=='@OWNED_RELAY_URL@' else item for item in job['test_argv']];sys.argv=argv;runpy.run_path(argv[0],run_name='__main__')
 except BaseException as error:primary=error
 finally:
  try:custody.finish()
  except BaseException as error:cleanup.append(type(error).__name__)
  try:
   if relay:relay.close()
  except BaseException as error:cleanup.append(type(error).__name__)
  provider=relay.evidence() if relay else None
  passed=primary is None and not cleanup and provider is not None and not provider['violations'] and not provider['provider_error_types']
  Path(job['custody_report']).write_text(json.dumps({'schema':'adhd/live-quality-image-custody@1','passed':passed,'primary_failure_type':type(primary).__name__ if primary else None,'cleanup_failure_types':cleanup,'runtime_events':custody.events,'image_config_identity':plan['image_config_identity'],'artifact_sha256':plan['artifact_sha256'],'canonical_manifest_sha256':sha(plan['manifest']),'provider':provider,'scope':'Original exact69 corpus/gold unchanged; image actual59payload and namespaceVM; host-network endpoint selection, no physical egress firewall or optimizer172 equivalence.'},indent=2)+'\n')
 if primary:raise primary
 assert passed,'Provider or cleanup qualification failed'

if __name__=='__main__':main()
