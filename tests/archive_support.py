"""Independent typed endpoint for archive intent, relevance and original support."""
import json,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

class ArchiveFixture:
    def __init__(self):
        self.mode='normal';self.intent='bounded';self.assessment='direct';self.delay=1.3
        self.select_last=False;self.noul=.99;self.retrieval_noul=None;self.requests=[];self.lock=threading.Lock();fixture=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):self.send(200,{'ready':True})
            def send(self,status,body):
                raw=json.dumps(body).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers()
                try:self.wfile.write(raw)
                except (BrokenPipeError,ConnectionResetError):pass
            def do_POST(self):
                raw=self.rfile.read(int(self.headers['Content-Length']));body=json.loads(raw)
                with fixture.lock:
                    mode,intent,assessment,delay=fixture.mode,fixture.intent,fixture.assessment,fixture.delay
                    fixture.requests.append({'request':body,'raw':raw.decode(),'at':time.monotonic()})
                if mode=='slow':time.sleep(delay)
                if mode=='fail-retrieval' and 'useful' in body['questions']:self.send(503,{'error':'controlled retrieval outage'});return
                if mode=='error':self.send(503,{'error':'controlled outage'});return
                answers={}
                for key,value in body['questions'].items():
                    if value['type']=='noul':answers[key]={'type':'noul','noul':fixture.retrieval_noul if key=='useful' and fixture.retrieval_noul is not None else fixture.noul};continue
                    labels=value['criteria'];chosen=intent if key=='intent' else (assessment if key=='assessment' else 'quote_0')
                    if key=='answer' and fixture.select_last:
                        offered=[k for k in labels if k.startswith('quote_')];chosen=max(offered,key=lambda x:int(x.split('_')[1])) if offered else 'unknown'
                    if chosen not in labels:chosen='unknown'
                    answers[key]={'type':'choice','choice':chosen,'confidence':1.0,'probabilities':{label:float(label==chosen) for label in labels}}
                result={'model':body['model'],'answers':answers}
                if mode=='wrong-model':result['model']='unselected-model'
                if mode=='invalid-intent' and 'intent' in answers:answers['intent']['choice']='unoffered'
                self.send(200,result)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)+'/v1/systemone'
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
