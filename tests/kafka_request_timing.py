"""Transparent measured real-broker relay; original move acceptance unchanged."""
import asyncio,importlib.util,json,statistics,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import httpx
spec=importlib.util.spec_from_file_location('move',Path(__file__).with_name('multi_store_move.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
from multi_support import arguments
p=arguments(__doc__);p.add_argument('--no-default',action='store_true');p.add_argument('--http-report',type=Path,required=True);a=p.parse_args()
upstream=a.eventing_rest_url.rstrip('/');rows=[];phase=['setup'];lock=threading.Lock();slots=threading.BoundedSemaphore(16);active=[0]
client=httpx.Client(timeout=10,trust_env=False,limits=httpx.Limits(max_connections=16,max_keepalive_connections=16))
def kind(method,path):
 if '/records?' in path:return 'consume'
 if path.endswith('/offsets'):return 'commit' if method=='POST' else 'broker-offsets'
 if path.startswith('/topics/') and method=='POST':return 'produce'
 if path.endswith('/positions'):return 'position'
 if path.endswith('/assignments'):return 'assignment'
 if path.startswith('/consumers/'):return 'consumer-control'
 return 'metadata'
class Handler(BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1'
 def log_message(self,*_):pass
 def forward(self):
  start=time.monotonic();label=phase[0];status=None
  if not slots.acquire(timeout=.1):
   self.send_error(503);return
  with lock:active[0]+=1
  try:
   n=int(self.headers.get('content-length','0'));assert 0<=n<=1048576
   data=self.rfile.read(n)
   headers={k:v for k,v in self.headers.items() if k.lower() not in ('host','connection','content-length','transfer-encoding')}
   result=client.request(self.command,upstream+self.path,content=data,headers=headers)
   status=result.status_code
   self.send_response(status)
   for k,v in result.headers.items():
    if k.lower() not in ('content-length','transfer-encoding','connection','content-encoding'):self.send_header(k,v)
   self.send_header('Content-Length',str(len(result.content)));self.end_headers();self.wfile.write(result.content)
  except (BrokenPipeError,ConnectionResetError):pass
  finally:
   with lock:rows.append({'phase':label,'operation':kind(self.command,self.path),'seconds':time.monotonic()-start,'upstream_status':status})
   with lock:active[0]-=1
   slots.release()
 do_GET=forward;do_POST=forward;do_DELETE=forward;do_PUT=forward
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
BaseFixture=m.Fixture
class Fixture(BaseFixture):
 def __init__(self,*args,**kw):
  super().__init__(*args,**kw);self.config['eventing']['rest_url']='http://127.0.0.1:'+str(server.server_port)
 def admin(self):
  admin=super().admin()
  if not getattr(admin,'measured',False):
   original=admin.call
   def call(command,*args,**kw):
    if command.get('op')=='config_update' and command.get('patch',{}).get('store_path')==str(self.root/'relocated/all.dets'):
     phase[0]='moving'
     try:return original(command,*args,**kw)
     finally:phase[0]='after-move'
    return original(command,*args,**kw)
   admin.call=call;admin.measured=True
  return admin
m.Fixture=Fixture
try:asyncio.run(m.main(a))
finally:
 server.shutdown();server.server_close();thread.join(timeout=5)
 deadline=time.monotonic()+12
 while time.monotonic()<deadline:
  with lock:pending=active[0]
  if not pending:break
  time.sleep(.05)
 assert not pending,'Measured relay still has an active upstream request'
 client.close()
 summary={}
 for op in sorted({r['operation']for r in rows}):
  values=[r['seconds']for r in rows if r['operation']==op]
  summary[op]={'calls':len(values),'median_seconds':statistics.median(values),'max_seconds':max(values),'total_seconds':sum(values)}
 a.http_report.write_text(json.dumps({'schema':'adhd/diagnostic-http-duration@1','transparent_actual_upstream':True,'qualification':False,'original_acceptance_deadline_seconds':a.deadline,'scope':'No request or response bodies, credentials, URLs or topic names retained. Real upstream status and elapsed receipt durations only.','summary':summary,'requests':rows},indent=2)+'\n')
