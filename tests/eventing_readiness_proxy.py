"""Bounded transparent real-Kafka REST faults; no broker success is invented."""
import http.client
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import unquote, urlsplit


QUEUE_HOLD_SECONDS=2.75
QUEUE_OBSERVATION_MAX_SECONDS=.5
QUEUE_VISIBILITY_FAILURES=20
QUEUE_RETRY_DELAY_SECONDS=.05
QUEUE_EVENTING_TIMEOUT_MS=3000
QUEUE_RECOVERY_TIMEOUT_MS=10000


def queue_premise(held_at,observed_at):
    """Validate the actual queued observation before evaluating product behavior."""
    elapsed=observed_at-held_at
    assert 0<=elapsed<=QUEUE_OBSERVATION_MAX_SECONDS, "Fixture premise failed: Red was not observed queued within0.5s of held Blue HTTP"
    minimum=QUEUE_HOLD_SECONDS-elapsed+QUEUE_VISIBILITY_FAILURES*QUEUE_RETRY_DELAY_SECONDS
    assert minimum>QUEUE_EVENTING_TIMEOUT_MS/1000
    return {"observed_after_hold_seconds":elapsed,"minimum_queue_plus_retry_seconds":minimum,
            "held_http_seconds":QUEUE_HOLD_SECONDS,"visibility_failures":QUEUE_VISIBILITY_FAILURES,
            "retry_delay_seconds":QUEUE_RETRY_DELAY_SECONDS,"eventing_timeout_ms":QUEUE_EVENTING_TIMEOUT_MS,
            "recovery_timeout_ms":QUEUE_RECOVERY_TIMEOUT_MS}


def classify(path,topic):
    path=unquote(urlsplit(path).path)
    if not topic:return None
    if path.endswith('/topics/'+topic):return 'metadata'
    if path.endswith('/topics/'+topic+'/configs'):return 'configs'
    if path.endswith('/topics/'+topic+'/configs:alter'):return 'alter'
    if path=='/topics/'+topic+'/partitions/0/offsets':return 'offsets'
    return None


def actual_configuration(status,body):
    """Only public Kafka policy values; no arbitrary row/name/body is retained."""
    if status!=200:return None
    try:value=json.loads(body)
    except (ValueError,UnicodeDecodeError):return {'invalid_data':True}
    if not isinstance(value,dict)or not isinstance(value.get('data'),list):return {'invalid_data':True}
    result={'cleanup_policy':[],'retention_ms':[]}
    for row in value['data']:
        if not isinstance(row,dict):continue
        if row.get('name')=='cleanup.policy':
            v=row.get('value');result['cleanup_policy'].append(v if isinstance(v,str)and v in ('delete','compact')else {'invalid_value_type':type(v).__name__})
        if row.get('name')=='retention.ms':
            v=row.get('value')
            valid=isinstance(v,str)and len(v)<=19 and re.fullmatch(r'-1|0|[1-9][0-9]*',v)is not None and int(v)<=9223372036854775807
            result['retention_ms'].append(v if valid else {'invalid_value_type':type(v).__name__})
    return result


def fault_response(mode,category,status,body,number,created):
    """Pure fault transform. Only the selected fresh topic can reach this seam."""
    if not created:return status,body,False
    if category=='configs':
        if mode=='never'or mode=='lag'and number<=2 or mode in ('queue','queue-control')and number<=QUEUE_VISIBILITY_FAILURES:
            return 404,b'{"error_code":40401,"message":"Declared visibility fault"}',True
        if mode in ('forbidden','server-error'):
            return (403 if mode=='forbidden'else 500),b'{"error_code":50001}',True
        if mode=='malformed':return 200,b'{"data":"invalid declared fixture"}',True
        if mode.startswith('retention-')and mode!='retention-recovery'and status==200:
            value=json.loads(body);rows=value['data']
            if mode=='retention-missing':value['data']=[r for r in rows if r['name']!='retention.ms']
            elif mode=='retention-duplicate':value['data']=rows+[next(dict(r)for r in rows if r['name']=='retention.ms')]
            else:
                for row in rows:
                    if row['name']=='retention.ms':row['value']=0.0 if mode=='retention-float'else '-2'
            return 200,json.dumps(value).encode(),True
        if mode=='bad-cleanup'and status==200:
            value=json.loads(body)
            for row in value['data']:
                if row['name']=='cleanup.policy':row['value']='compact'
            return status,json.dumps(value).encode(),True
    if category=='metadata'and mode=='metadata-lag'and number==1:return 404,b'{"error_code":40401,"message":"Declared metadata visibility fault"}',True
    if category=='metadata'and mode in ('duplicate-bad-topology','partitions-float')and status==200:
        value=json.loads(body);value['partitions_count']=1.0 if mode=='partitions-float'else 2;return status,json.dumps(value).encode(),True
    if category=='offsets'and mode.startswith('offset-')and status==200:
        values={'offset-nonzero':{'beginning_offset':0,'end_offset':1},'offset-negative':{'beginning_offset':-1,'end_offset':0},
            'offset-missing':{'beginning_offset':0},'offset-float':{'beginning_offset':0.0,'end_offset':0},'offset-string':{'beginning_offset':'0','end_offset':0},'offset-end-float':{'beginning_offset':0,'end_offset':0.0}}
        return 200,json.dumps(values[mode]).encode(),True
    return status,body,False


def confirmed_retention_alter(mode,category,method,status,transaction_present):
    selected=mode=='retention-recovery'and category=='alter'and method=='POST'and status==204
    if selected:assert transaction_present is True,'Selected alter lacks durable transaction'
    return selected


def retention_recovery_fault(mode,category,status,body,alter_confirmed):
    """Never invent broker success or fail predecision validation."""
    if mode=='retention-recovery'and category=='configs'and alter_confirmed:
        return 503,b'{"error_code":50301,"message":"Declared postdecision readback fault"}',True
    return status,body,False


class Server(ThreadingMixIn,HTTPServer):
    daemon_threads=True
    def process_request(self,request,address):
        if not self.slots.acquire(False):
            self.owner.failures.append('ProxyCapacityExceeded');self.shutdown_request(request);return
        try:super().process_request(request,address)
        except BaseException:self.slots.release();raise
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()


class ReadinessProxy:
    def __init__(self,backend):
        parsed=urlsplit(backend);assert parsed.scheme=='http'and parsed.hostname=='127.0.0.1'and parsed.port and parsed.port!=18770 and not(parsed.username or parsed.query or parsed.fragment or parsed.path.strip('/'))
        self.backend=(parsed.hostname,parsed.port);self.topic=None;self.mode=None;self.created=False;self.events=[];self.failures=[];self.counts={};self.lock=threading.Lock()
        self.alter_confirmed=False
        self.hold=False;self.held_at=None;self.held=threading.Event();self.release=threading.Event();self.handlers=0;self.transaction=None
        owner=self
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*_):pass
            def do_GET(self):self.respond()
            def do_POST(self):self.respond()
            def do_DELETE(self):self.respond()
            def respond(self):
                connection=None
                with owner.lock:owner.handlers+=1
                try:
                    size=int(self.headers.get('Content-Length','0'));assert 0<=size<=262144
                    self.connection.settimeout(4);body=self.rfile.read(size);assert len(body)==size
                    category=classify(self.path,owner.topic);created_request=False
                    if self.command=='POST'and urlsplit(self.path).path.endswith('/topics'):
                        value=json.loads(body);created_request=owner.topic is not None and value.get('topic_name')==owner.topic
                    if owner.hold and self.command=='GET'and '/records'in self.path and not owner.held.is_set():
                        owner.held_at=time.monotonic();owner.held.set();owner.release.wait(QUEUE_HOLD_SECONDS)
                    connection=http.client.HTTPConnection(*owner.backend,timeout=3)
                    headers={k:v for k,v in self.headers.items()if k.lower()not in ('host','connection','content-length')}
                    headers['Connection']='close';connection.request(self.command,self.path,body,headers)
                    response=connection.getresponse();data=response.read(262145);assert len(data)<=262144;status=response.status
                    configuration=actual_configuration(status,data)if category=='configs'else None
                    with owner.lock:
                        if created_request and status in range(200,300):
                            owner.created=True;owner.counts['metadata']=0
                            if owner.mode.startswith('duplicate'):status,data=400,b'{"error_code":40002}'
                        owner.counts[category]=owner.counts.get(category,0)+1
                        if confirmed_retention_alter(owner.mode,category,self.command,status,owner.transaction is not None and owner.transaction.exists()):
                            owner.alter_confirmed=True
                        status,data,injected=fault_response(owner.mode,category,status,data,owner.counts[category],owner.created)if owner.mode else(status,data,False)
                        status,data,retention_injected=retention_recovery_fault(owner.mode,category,status,data,owner.alter_confirmed)
                        injected=injected or retention_injected
                        assert len(owner.events)<256
                        owner.events.append({'at':time.monotonic(),'method':self.command,'category':category,'selected_create':created_request,'status':status,'injected':injected,'actual_configuration':configuration,'durable_transaction_present':self.server.owner.transaction.exists()if self.server.owner.transaction is not None else None})
                    self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.send_header('Connection','close');self.end_headers();self.wfile.write(data)
                except (BrokenPipeError,ConnectionResetError):pass # canceled owned HTTP is expected in deadline cases
                except BaseException as error:
                    owner.failures.append(type(error).__name__)
                    self.close_connection=True
                finally:
                    if connection:connection.close()
                    with owner.lock:owner.handlers-=1
        self.server=Server(('127.0.0.1',0),Handler);self.server.slots=threading.BoundedSemaphore(4);self.server.owner=self
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.url='http://127.0.0.1:'+str(self.server.server_port)
    def arm(self,topic,mode):
        with self.lock:self.topic=topic;self.mode=mode;self.created=False;self.events=[];self.counts={};self.alter_confirmed=False
    def disable_fault(self):
        with self.lock:self.mode=None
    def close(self):
        self.release.set();self.server.shutdown();self.server.server_close();self.thread.join(2)
        end=time.monotonic()+4
        while self.handlers and time.monotonic()<end:time.sleep(.01)
        assert not self.thread.is_alive()and self.handlers==0 and not self.failures,self.failures
