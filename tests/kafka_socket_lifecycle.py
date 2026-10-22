"""Owned real broker socket lifecycle diagnostic; no model calls."""
import asyncio,json,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import httpx
from multi_support import Fixture,arguments
p=arguments(__doc__);a=p.parse_args();assert a.hub and not a.rest_url and not a.with_model
upstream=a.eventing_rest_url.rstrip('/');requests=[];lock=threading.Lock();active=[0];connections=[0];peak=[0]
client=httpx.Client(timeout=10,trust_env=False,limits=httpx.Limits(max_connections=16,max_keepalive_connections=16))
class Handler(BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1'
 def log_message(self,*_):pass
 def setup(self):
  super().setup()
  with lock:connections[0]+=1;peak[0]=max(peak[0],connections[0])
 def finish(self):
  try:super().finish()
  finally:
   with lock:connections[0]-=1
 def forward(self):
  with lock:active[0]+=1;requests.append({'connection_close':self.headers.get('Connection','').lower()=='close'})
  try:
   n=int(self.headers.get('Content-Length','0'));assert 0<=n<=1048576
   r=client.request(self.command,upstream+self.path,content=self.rfile.read(n),headers={k:v for k,v in self.headers.items()if k.lower()not in('host','content-length','connection','transfer-encoding')})
   self.send_response(r.status_code)
   for k,v in r.headers.items():
    if k.lower()not in('content-length','content-encoding','connection','transfer-encoding'):self.send_header(k,v)
   self.send_header('Content-Length',str(len(r.content)));self.end_headers();self.wfile.write(r.content)
  except (BrokenPipeError,ConnectionResetError):pass
  finally:
   with lock:active[0]-=1
 do_GET=forward;do_POST=forward;do_DELETE=forward;do_PUT=forward
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
def socket_count(pid):
 total=0
 for p in Path('/proc',str(pid),'fd').iterdir():
  try:total+=p.readlink().as_posix().startswith('socket:')
  except FileNotFoundError:pass
 return total
async def main():
 f=Fixture(a);f.config['eventing']['rest_url']='http://127.0.0.1:'+str(server.server_port)
 result={'diagnostic_only':True,'model_calls':0,'eventing_idle_samples':[],'disabled_idle_samples':[]}
 try:
  await f.start()
  for _ in range(16):
   with lock:count=connections[0];pending=active[0]
   result['eventing_idle_samples'].append({'hub_sockets':socket_count(f.process.pid),'relay_connections':count,'active_requests':pending})
   await asyncio.sleep(.5)
  f.admin().call({'op':'config_update','patch':{'eventing':{'enabled':False}}},mutation=True)
  await asyncio.sleep(3)
  for _ in range(8):
   with lock:count=connections[0];pending=active[0]
   result['disabled_idle_samples'].append({'hub_sockets':socket_count(f.process.pid),'relay_connections':count,'active_requests':pending})
   await asyncio.sleep(.5)
 finally:
  await f.close()
  server.shutdown();server.server_close();thread.join(timeout=5);client.close()
  with lock:result.update(request_count=len(requests),connection_close_requests=sum(x['connection_close']for x in requests),peak_relay_connections=peak[0])
  a.report.write_text(json.dumps(result,indent=2)+'\n')
asyncio.run(main())
