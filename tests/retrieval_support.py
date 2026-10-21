"""Independent typed usefulness endpoint for retrieval transport and crash checks."""
import copy
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class NoulFixture:
    def __init__(self):
        self.mode='normal';self.delay=.7;self.requests=[];self.lock=threading.Lock();fixture=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                raw=self.rfile.read(int(self.headers['Content-Length']));body=json.loads(raw)
                with fixture.lock:
                    mode,delay=fixture.mode,fixture.delay
                    fixture.requests.append({'request':body,'raw':raw.decode(),'at':time.monotonic()})
                relevance='relevance' in body['questions']
                if mode=='slow' and not relevance:time.sleep(delay)
                key='relevance' if relevance else 'useful'
                result={'model':body['model'],'answers':{key:{'type':'noul','noul':.99}}};status=200
                if not relevance:
                    answer=result['answers'][key]
                    if mode=='error':status=503;result={'error':'controlled outage'}
                    elif mode=='wrong-model':result['model']='different-model'
                    elif mode=='boolean':answer['noul']=True
                    elif mode=='wrong-type':answer['type']='choice'
                    elif mode=='extra-answer':result['answers']['unexpected']=copy.deepcopy(answer)
                    elif mode=='extra-field':answer['unexpected']=True
                    elif mode=='missing':answer.pop('noul')
                    elif mode=='out-of-range':answer['noul']=1.01
                    elif mode=='nonfinite':answer['noul']=float('nan')
                    elif mode=='oversized':result['usage']={'padding':'x'*270000}
                    elif mode=='nonmatch':answer['noul']=.01
                raw=json.dumps(result).encode()
                if mode=='duplicate' and not relevance:raw=raw.replace(b'"noul": 0.99',b'"noul": 0.99, "noul": 0.99')
                self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers()
                try:self.wfile.write(raw)
                except (BrokenPipeError,ConnectionResetError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)+'/v1/systemone'
    def useful(self):
        with self.lock:return [x for x in self.requests if 'useful' in x['request']['questions']]
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
