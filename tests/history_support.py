"""Independent controlled HTTP evaluator for history lifecycle/fault scenarios."""
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import threading,time

class ChoiceFixture:
    def __init__(self):
        self.mode='normal';self.delay=1.2;self.requests=[];self.lock=threading.Lock()
        fixture=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def send(self,status,value):
                raw=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers()
                try:self.wfile.write(raw)
                except (BrokenPipeError,ConnectionResetError):pass
            def do_GET(self):self.send(200,{'ready':True})
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                with fixture.lock:
                    mode,delay=fixture.mode,fixture.delay
                    fixture.requests.append({'request':body,'at':time.monotonic()})
                if 'relevance' in body.get('questions',{}):
                    self.send(200,{'model':body['model'],'answers':{'relevance':{'type':'noul','noul':.99}}});return
                if mode=='slow':time.sleep(delay)
                if mode=='error':self.send(503,{'error':'controlled provider outage'});return
                answers={}
                for key,question in body['questions'].items():
                    labels=question['criteria'];chosen='direct' if key=='assessment' else 'quote_0'
                    if chosen not in labels:chosen='unknown'
                    answers[key]={'type':'choice','choice':chosen,'confidence':1.0,'probabilities':{label:float(label==chosen) for label in labels}}
                result={'model':body['model'],'answers':answers}
                answer=answers['answer']
                if mode=='wrong-model':result['model']='unselected-model'
                elif mode=='boolean':answers['assessment']=True
                elif mode=='wrong-type':answer['type']='noul'
                elif mode=='missing-choice':answer.pop('choice')
                elif mode=='unknown-choice':answer['choice']='unoffered'
                elif mode=='missing-probability':answer['probabilities'].pop('unknown')
                elif mode=='extra-probability':answer['probabilities']['unoffered']=0
                elif mode=='sum':answer['probabilities']['unknown']=.2
                elif mode=='not-maximum':answer['choice']='unknown';answer['confidence']=0
                elif mode=='confidence':answer['confidence']=.25
                elif mode=='extra-answer':answers['unasked']=answers['assessment']
                elif mode=='extra-field':answer['unexpected']=True
                elif mode=='oversized':result['usage']={'padding':'x'*270000}
                elif mode=='low-confidence':
                    for item in answers.values():
                        item['probabilities']={label:1/len(item['probabilities']) for label in item['probabilities']};item['confidence']=1/len(item['probabilities'])
                self.send(200,result)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.url='http://127.0.0.1:'+str(self.server.server_port)+'/v1/systemone'
    def choices(self):
        with self.lock:return [x for x in self.requests if 'assessment' in x['request'].get('questions',{})]
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
