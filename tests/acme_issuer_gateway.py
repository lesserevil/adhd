"""Owned byte-transparent Pebble TCP gateway. Construction never opens sockets."""
import ipaddress
import selectors
import socket
import threading
import time


class IssuerGateway:
    def __init__(self, bind, network, clients, *, lease_seconds=600, max_connections=128,
                 concurrency=8, connection_seconds=40, max_bytes=4*1024*1024):
        net=ipaddress.ip_network(network,strict=True);address=ipaddress.ip_address(bind)
        addresses={str(ipaddress.ip_address(value)) for value in clients}
        assert net.version==4 and net.is_private and address in net
        assert not address.is_loopback and not address.is_unspecified and not address.is_multicast
        assert addresses and str(address) not in addresses
        assert all(ipaddress.ip_address(value) in net and not ipaddress.ip_address(value).is_loopback for value in addresses)
        assert type(lease_seconds) is int and 1<=lease_seconds<=1800
        assert type(max_connections) is int and 1<=max_connections<=256
        assert type(concurrency) is int and 1<=concurrency<=8
        assert type(connection_seconds) is int and 1<=connection_seconds<=40
        assert type(max_bytes) is int and 1<=max_bytes<=4*1024*1024
        self.bind=str(address);self.network=str(net);self.clients=addresses
        self.lease=lease_seconds;self.limit=max_connections;self.concurrency=concurrency
        self.connection_seconds=connection_seconds;self.byte_limit=max_bytes
        self.listener=None;self.thread=None;self.stop_event=threading.Event();self.lock=threading.Lock()
        self.active=set();self.workers=[];self.events=[];self.errors=[];self.error_count=0;self.accepted=0

    def error(self,kind):
        with self.lock:
            self.error_count+=1
            if len(self.errors)<128:self.errors.append(kind)

    def forward(self, incoming, peer):
        outgoing=None;sent=received=0;failure=None
        try:
            assert peer in self.clients,'Unregistered source'
            incoming.setblocking(False)
            outgoing=socket.create_connection(('127.0.0.1',19100),timeout=3)
            outgoing.setblocking(False)
            with self.lock:self.active.add(outgoing)
            deadline=time.monotonic()+self.connection_seconds
            # Backpressure is bounded; neither direction accumulates a TLS record stream.
            pending={incoming:bytearray(),outgoing:bytearray()};reading={incoming,outgoing}
            peers={incoming:outgoing,outgoing:incoming}
            with selectors.DefaultSelector() as selector:
                while (reading or any(pending.values())) and not self.stop_event.is_set():
                    remaining=deadline-time.monotonic();assert remaining>0,'Gateway connection deadline'
                    for key in list(selector.get_map().values()):selector.unregister(key.fileobj)
                    for stream in (incoming,outgoing):
                        flags=(selectors.EVENT_READ if stream in reading and len(pending[peers[stream]])<65536 else 0)
                        if pending[stream]:flags|=selectors.EVENT_WRITE
                        if flags:selector.register(stream,flags)
                    for key,events in selector.select(min(.1,remaining)):
                        stream=key.fileobj
                        if events & selectors.EVENT_READ:
                            try:block=stream.recv(min(16384,65536-len(pending[peers[stream]])))
                            except BlockingIOError:continue
                            if block:
                                if stream is incoming:sent+=len(block)
                                else:received+=len(block)
                                assert sent+received<=self.byte_limit,'Gateway byte budget'
                                pending[peers[stream]].extend(block)
                            else:reading.remove(stream)
                        if events & selectors.EVENT_WRITE:
                            try:n=stream.send(pending[stream])
                            except BlockingIOError:continue
                            assert n>0;del pending[stream][:n]
                    for stream in (incoming,outgoing):
                        if peers[stream] not in reading and not pending[stream]:
                            try:stream.shutdown(socket.SHUT_WR)
                            except OSError:pass
        except BaseException as error:
            failure=type(error).__name__
            self.error(failure)
        finally:
            for stream in (incoming,outgoing):
                if stream is not None:
                    try:stream.close()
                    finally:
                        with self.lock:self.active.discard(stream)
            with self.lock:self.events.append({'client_allowed':peer in self.clients,'bytes_to_ca':sent,
                                              'bytes_from_ca':received,'failure_type':failure})

    def start(self):
        assert self.listener is None and not self.stop_event.is_set()
        server=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        try:
            server.bind((self.bind,19104));server.listen(8);server.settimeout(.1)
        except BaseException:
            server.close();raise
        self.listener=server;self.deadline=time.monotonic()+self.lease
        def accept():
            try:
                while not self.stop_event.is_set() and time.monotonic()<self.deadline:
                    try:stream,address=server.accept()
                    except socket.timeout:continue
                    except OSError:
                        if self.stop_event.is_set():break
                        raise
                    with self.lock:
                        count=sum(worker.is_alive() for worker in self.workers)
                        allowed=address[0] in self.clients and self.accepted<self.limit and count<self.concurrency
                        if allowed:self.accepted+=1;self.active.add(stream)
                    if not allowed:
                        stream.close()
                        self.error('SourceOrConnectionBudget')
                        continue
                    worker=threading.Thread(target=self.forward,args=(stream,address[0]),daemon=False)
                    self.workers.append(worker)
                    try:worker.start()
                    except BaseException:
                        self.workers.remove(worker);stream.close()
                        with self.lock:self.active.discard(stream)
                        raise
            except BaseException as error:
                self.error(type(error).__name__)
            finally:self.stop_event.set()
        self.thread=threading.Thread(target=accept,daemon=False)
        try:self.thread.start()
        except BaseException:
            self.stop_event.set();server.close();self.listener=None;self.thread=None
            raise

    def close(self):
        self.stop_event.set()
        if self.listener:self.listener.close()
        if self.thread:self.thread.join(3);assert not self.thread.is_alive(),'Gateway accept thread remains'
        with self.lock:streams=list(self.active)
        for stream in streams:
            try:stream.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            stream.close()
        deadline=time.monotonic()+5
        for worker in self.workers:worker.join(max(0,deadline-time.monotonic()))
        assert not any(worker.is_alive() for worker in self.workers),'Gateway connection remains'
        with self.lock:assert not self.active,'Gateway socket remains'
        self.listener=None

    def evidence(self):
        with self.lock:
            return {'bound_ip':self.bind,'source_allowlist':sorted(self.clients),'port':19104,
                    'target':'127.0.0.1:19100','tls_terminated':False,'acme_bytes_rewritten':False,
                    'accepted':self.accepted,'connections':list(self.events),'errors':list(self.errors),'error_count':self.error_count,
                    'active_sockets':len(self.active),'all_threads_closed':not any(t.is_alive() for t in [self.thread,*self.workers] if t)}
