"""Owned HTTPS issuer-availability fault relay; construction/import are inert.

Pass mode forwards to the real fixed local Pebble with normal root/hostname
verification and unchanged proxy Host. Fault mode substitutes ONLY /dir503/429,
never ACME success/nonces/accounts/challenges/certificates. No key/body is logged.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import stat
import ssl
import threading
import time

MAX_HEADER=16384
MAX_BODY=1048576



class HeaderFields(dict):
    """Singleton lookup plus exact ordered wire fields (repeatable Link only)."""
    def __init__(self):super().__init__();self.fields=[]


def header_checkpoint(raw, *, response=False):
    """Bounded fixed-vocabulary names/counts only; never header values."""
    known={b'link',b'content-length',b'transfer-encoding',b'content-type',b'replay-nonce',
      b'location',b'connection',b'date',b'cache-control',b'content-encoding',b'host',
      b'user-agent',b'accept',b'accept-encoding'}
    result={'header_bytes':len(raw),'name_counts':{}}
    if len(raw)>MAX_HEADER:return result
    rows=raw.split(b'\r\n')
    if response:
        status=re.fullmatch(rb'HTTP/1\.[01] ([2-5][0-9][0-9])(?: [^\r\n]*)?',rows[0])
        if status:result['status']=int(status[1])
    for row in rows[1:65]:
        if not row:continue
        name,sep,_=row.partition(b':');name=name.lower()
        label=name.decode('ascii')if sep and name in known else 'other'
        counts=result['name_counts'];counts[label]=counts.get(label,0)+1
    return result


def selected_response_fields(fields):
    allowed=(b'content-type',b'location',b'replay-nonce',b'link',b'retry-after')
    return b''.join(k+b': '+v+b'\r\n'for k,v in fields.fields if k in allowed)


def headers(raw, response=False):
    assert len(raw)<=MAX_HEADER and raw.endswith(b'\r\n\r\n')
    rows=raw[:-4].split(b'\r\n');assert len(rows)<=65
    first=rows.pop(0);result=HeaderFields()
    for row in rows:
        name,sep,value=row.partition(b':')
        assert sep and re.fullmatch(rb'[!#$%&\'*+.^_`|~0-9A-Za-z-]+',name)
        name=name.lower();value=value.strip()
        assert (name not in result or response and name==b'link')and all(c==9 or 32<=c<127 for c in value)
        result.fields.append((name,value))
        if name not in result:result[name]=value
    assert not (b'transfer-encoding'in result and b'content-length'in result)
    if response:
        status=re.fullmatch(rb'HTTP/1\.[01] ([2-5][0-9][0-9])(?: [^\r\n]*)?',first)
        assert status
        return int(status[1]),result
    method,target,protocol=first.split(b' ')
    assert method in (b'GET',b'HEAD',b'POST')and protocol in (b'HTTP/1.0',b'HTTP/1.1')
    assert target.startswith(b'/')and not target.startswith(b'//')and all(33<=c<127 for c in target)
    assert b'transfer-encoding'not in result
    return method,target,result


class Wire:
    def __init__(self,sock,deadline):self.sock,self.deadline=sock,deadline;self.buffer=bytearray()
    def recv(self,n):
        remaining=self.deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('Owned exchange deadline')
        self.sock.settimeout(min(3,remaining));return self.sock.recv(n)
    def head(self):
        while b'\r\n\r\n'not in self.buffer:
            assert len(self.buffer)<MAX_HEADER
            raw=self.recv(min(4096,MAX_HEADER-len(self.buffer)));assert raw
            self.buffer.extend(raw)
        end=self.buffer.index(b'\r\n\r\n')+4
        value=bytes(self.buffer[:end]);del self.buffer[:end];return value
    def exact(self,n):
        assert 0<=n<=MAX_BODY
        while len(self.buffer)<n:
            raw=self.recv(min(4096,n-len(self.buffer)));assert raw
            self.buffer.extend(raw)
        value=bytes(self.buffer[:n]);del self.buffer[:n];return value
    def line(self):
        while b'\r\n'not in self.buffer:
            assert len(self.buffer)<MAX_HEADER
            raw=self.recv(min(4096,MAX_HEADER-len(self.buffer)));assert raw
            self.buffer.extend(raw)
        end=self.buffer.index(b'\r\n');value=bytes(self.buffer[:end]);del self.buffer[:end+2];return value
    def body(self,h,*,head=False):
        if head:return b''
        if b'content-length'in h:
            value=h[b'content-length'];assert re.fullmatch(rb'[0-9]{1,8}',value)
            return self.exact(int(value))
        if b'transfer-encoding'in h:
            assert h[b'transfer-encoding'].lower()==b'chunked';result=bytearray()
            while True:
                size=self.line().split(b';',1)[0];assert re.fullmatch(rb'[a-fA-F0-9]{1,8}',size)
                count=int(size,16);assert len(result)+count<=MAX_BODY
                if count==0:
                    total=0
                    while True:
                        line=self.line();total+=len(line)+2;assert total<=MAX_HEADER
                        if not line:break
                    return bytes(result)
                result.extend(self.exact(count));assert self.exact(2)==b'\r\n'
        result=bytearray(self.buffer);self.buffer.clear()
        while True:
            raw=self.recv(min(4096,MAX_BODY-len(result)+1))
            if not raw:return bytes(result)
            assert len(result)+len(raw)<=MAX_BODY;result.extend(raw)


def fault_bytes(status,retry_seconds):
    assert status in (429,503)and type(retry_seconds)is int and 1<=retry_seconds<=600
    kind='rateLimited'if status==429 else 'serverInternal'
    body=json.dumps({'type':'urn:ietf:params:acme:error:'+kind,'detail':'Owned isolated availability fault'}).encode()
    return (f'HTTP/1.1 {status} Owned Fault\r\nContent-Type: application/problem+json\r\nRetry-After: {retry_seconds}\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n'.encode()+body)


class IssuerFaultRelay:
    def __init__(self,*,cert_file,key_file,root_file,cert_sha256,key_sha256,root_sha256,
                 port=19103,max_requests=256,lifetime_seconds=600):
        assert port==19103 and 1<=max_requests<=256 and 1<=lifetime_seconds<=600
        self.files={}
        for name,path,digest in [('cert',cert_file,cert_sha256),('key',key_file,key_sha256),('root',root_file,root_sha256)]:
            path=Path(path).absolute();assert path==path.resolve(),'No redirected issuer fixture files'
            assert re.fullmatch('[0-9a-f]{64}',digest)
            # No process/network operation here. Actual fixture identity is
            # supplied by the reviewed CA manifest/stock test-cert pins.
            entry=path.lstat()
            assert stat.S_ISREG(entry.st_mode)and entry.st_uid==os.getuid()and entry.st_nlink==1 and entry.st_size<=1048576
            if name=='key':assert stat.S_IMODE(entry.st_mode)==0o600
            assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
            self.files[name]=str(path)
        self.port,self.max_requests,self.lifetime=port,max_requests,lifetime_seconds
        self.server=self.thread=None;self.lock=threading.Lock();self.close_lock=threading.Lock();self.closing=threading.Event()
        self.sockets=set();self.active=self.requests=0;self.events=[];self.errors=[];self.error_total=0;self.failure_checkpoints=[];self.workers=[];self.exchange_timers=[]
        self.mode='pass';self.retry_seconds=120;self.started=None;self.lifetime_timer=None

    def _error_locked(self,kind):
        self.error_total+=1
        if len(self.errors)<128:self.errors.append(kind[:64])

    def _failure_locked(self,error,checkpoint):
        self._error_locked(type(error).__name__)
        if len(self.failure_checkpoints)<128:self.failure_checkpoints.append(dict(checkpoint))

    def _claim_request(self,request):
        with self.lock:
            if self.active>=4 or self.requests>=self.max_requests or self.closing.is_set()or time.monotonic()-self.started>=self.lifetime:
                self._error_locked('scope-cap');request.close();return False
            self.active+=1;self.requests+=1;self.sockets.add(request)
            return True

    def _run_worker(self,run,request,address):
        try:run(request,address)
        finally:
            request.close()
            with self.lock:
                self.sockets.discard(request)
                self.active-=1

    def _spawn_worker(self,run,request,address):
        worker=threading.Thread(target=self._run_worker,args=(run,request,address),daemon=True)
        with self.lock:self.workers.append(worker)
        try:worker.start()
        except BaseException:
            with self.lock:self.active-=1;self.sockets.discard(request)
            request.close();raise

    def set_fault(self,status=None,retry_seconds=120):
        assert status is None or status in (429,503)
        fault_bytes(status or 503,retry_seconds)
        with self.lock:
            assert self.active==0,'Mode changes only at observed exchange boundaries'
            self.mode='pass'if status is None else status;self.retry_seconds=retry_seconds

    def start(self):
        assert self.server is None and not self.closing.is_set()
        owner=self
        server_context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);server_context.minimum_version=ssl.TLSVersion.TLSv1_2
        server_context.load_cert_chain(self.files['cert'],self.files['key'])
        upstream_context=ssl.create_default_context(cafile=self.files['root']);upstream_context.minimum_version=ssl.TLSVersion.TLSv1_2
        class Server(socketserver.ThreadingTCPServer):
            # Rebind after owned TIME-WAIT; never share a live listener.
            allow_reuse_address=True;allow_reuse_port=False
            daemon_threads=True;block_on_close=False
            def process_request(self,request,address):
                if owner._claim_request(request):
                    owner._spawn_worker(super().process_request_thread,request,address)
            def handle_error(self,request,address):
                with owner.lock:owner._error_locked('handler-error')
        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                sockets=[self.request];deadline=time.monotonic()+10
                def abort():
                    for sock in list(sockets):
                        try:sock.shutdown(socket.SHUT_RDWR)
                        except OSError:pass
                        try:sock.close()
                        except OSError:pass
                timer=threading.Timer(10,abort);timer.daemon=True
                with owner.lock:owner.exchange_timers.append(timer)
                timer.start()
                checkpoint={'stage':'client-handshake'}
                try:
                    self.request.settimeout(3)
                    client=server_context.wrap_socket(self.request,server_side=True,do_handshake_on_connect=False)
                    sockets.append(client)
                    with owner.lock:owner.sockets.add(client)
                    client.do_handshake();wire=Wire(client,deadline)
                    checkpoint['stage']='request-headers'
                    raw_head=wire.head();checkpoint['request_headers']=header_checkpoint(raw_head)
                    method,target,h=headers(raw_head)
                    assert h.get(b'host')==b'localhost:19103'
                    checkpoint['stage']='request-body'
                    body=wire.body({b'content-length':h.get(b'content-length',b'0')})
                    assert not wire.buffer,'Unexpected request pipeline/trailing bytes'
                    with owner.lock:mode,retry=owner.mode,owner.retry_seconds
                    event={'at_monotonic':time.monotonic(),'method':method.decode(),'directory':target==b'/dir',
                           'request_bytes':len(body),'fault_status':None,'upstream_status':None}
                    if mode!='pass'and method==b'GET'and target==b'/dir':
                        client.sendall(fault_bytes(mode,retry));event.update(fault_status=mode,retry_seconds=retry)
                    else:
                        checkpoint['stage']='upstream-connect'
                        raw=socket.create_connection(('127.0.0.1',19100),timeout=min(3,max(.001,deadline-time.monotonic())))
                        sockets.append(raw)
                        upstream=upstream_context.wrap_socket(raw,server_hostname='localhost',do_handshake_on_connect=False);sockets.append(upstream)
                        with owner.lock:owner.sockets.update([raw,upstream])
                        checkpoint['stage']='upstream-handshake'
                        upstream.do_handshake()
                        allowed=(b'host',b'content-type',b'accept',b'user-agent')
                        request=method+b' '+target+b' HTTP/1.1\r\n'+b''.join(k+b': '+v+b'\r\n'for k,v in h.items()if k in allowed)
                        request+=b'Content-Length: '+str(len(body)).encode()+b'\r\nConnection: close\r\nAccept-Encoding: identity\r\n\r\n'+body
                        checkpoint['stage']='upstream-send'
                        upstream.sendall(request);response=Wire(upstream,deadline)
                        checkpoint['stage']='response-headers'
                        raw_head=response.head();checkpoint['response_headers']=header_checkpoint(raw_head,response=True)
                        status,rh=headers(raw_head,response=True)
                        assert rh.get(b'content-encoding',b'identity').lower()==b'identity'
                        checkpoint['stage']='response-body'
                        payload=response.body(rh,head=method==b'HEAD')
                        head=f'HTTP/1.1 {status} Upstream\r\n'.encode()+selected_response_fields(rh)
                        head+=b'Content-Length: '+str(len(payload)).encode()+b'\r\nConnection: close\r\n\r\n'
                        checkpoint['stage']='response-send'
                        client.sendall(head+payload);event.update(upstream_status=status,response_bytes=len(payload),response_headers=checkpoint['response_headers'])
                    checkpoint['stage']='exchange-deadline'
                    assert time.monotonic()<=deadline
                    event['completed_monotonic']=time.monotonic()
                    with owner.lock:owner.events.append(event)
                except BaseException as error:
                    with owner.lock:owner._failure_locked(error,checkpoint)
                finally:
                    timer.cancel();abort()
                    timer.join(timeout=2)
                    assert not timer.is_alive(),'Owned exchange timer not closed'
                    with owner.lock:
                        for sock in sockets:owner.sockets.discard(sock)
        self.started=time.monotonic()
        self.server=Server(('127.0.0.1',self.port),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.05},daemon=True)
        try:
            self.thread.start()
            self.lifetime_timer=threading.Timer(self.lifetime,self.close);self.lifetime_timer.daemon=True;self.lifetime_timer.start()
            return self
        except BaseException as error:
            try:self.close()
            except BaseException as cleanup:error.add_note('Owned issuer-relay startup cleanup: '+type(cleanup).__name__)
            raise

    def snapshot(self):
        with self.lock:
            accept_alive=bool(self.thread and self.thread.is_alive())
            workers_alive=sum(thread.is_alive()for thread in self.workers)
            timers_alive=sum(thread.is_alive()for thread in self.exchange_timers)
            lifetime_alive=bool(self.lifetime_timer and self.lifetime_timer.is_alive())
            return {'requests':self.requests,'active':self.active,'events':list(self.events),
              'errors':list(self.errors),'error_total':self.error_total,'failure_checkpoints':list(self.failure_checkpoints),
              'accept_thread_alive':accept_alive,'worker_threads_alive':workers_alive,
              'exchange_timers_alive':timers_alive,'lifetime_timer_alive':lifetime_alive,
              'recorded_worker_threads':len(self.workers),'recorded_exchange_timers':len(self.exchange_timers),
              'closed':self.closing.is_set()and not accept_alive and not workers_alive and not timers_alive
                and not lifetime_alive and self.active==0 and not self.sockets}

    def _join(self,threads,deadline):
        current=threading.current_thread()
        for thread in threads:
            if thread is current:
                assert thread is self.lifetime_timer,'Unexpected relay close from owned worker'
                continue
            if thread.is_alive():thread.join(timeout=max(0,deadline-time.monotonic()))
            assert not thread.is_alive(),'Owned relay thread did not exit'

    def close(self):
        deadline=time.monotonic()+12
        with self.close_lock:
            self.closing.set()
            if self.lifetime_timer:self.lifetime_timer.cancel()
            with self.lock:
                sockets=list(self.sockets)
                timers=list(self.exchange_timers)
            for timer in timers:timer.cancel()
            for sock in sockets:
                try:sock.shutdown(socket.SHUT_RDWR)
                except OSError:pass
            if self.server:
                if self.thread and self.thread.is_alive():self.server.shutdown()
                self.server.server_close()
            if self.thread:self._join([self.thread],deadline)
            # Shutdown the accept loop first; its complete retained worker set
            # cannot grow. A worker may still register its exchange timer, so
            # join workers before taking the final timer set.
            with self.lock:workers=list(self.workers)
            self._join(workers,deadline)
            with self.lock:timers=list(self.exchange_timers)
            for timer in timers:timer.cancel()
            self._join(timers,deadline)
            assert self.active==0 and not self.sockets,'Owned relay connections not closed'
        # A lifetime callback may itself be waiting for close_lock. Join it
        # outside the lock; the callback skips only its own join. Snapshot keeps
        # reporting false until that callback actually returns.
        if self.lifetime_timer:self._join([self.lifetime_timer],deadline)
