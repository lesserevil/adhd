"""Bounded HTTP/1 exchange for the explicitly approved loopback model endpoint.

No DNS, redirects, retries, decompression or unbounded response buffering. Every
connect/send/header/body operation shares one absolute monotonic deadline.
"""
import errno
import ipaddress
import re
import select
import socket
import time
from urllib.parse import urlsplit

MAX_BODY=262144
MAX_HEADER=16384


def exchange(url,body,deadline,register=lambda _:None,unregister=lambda _:None):
    target=urlsplit(url);address=ipaddress.ip_address(target.hostname)
    assert target.scheme=='http' and address.is_loopback and not target.username and not target.password and not target.fragment
    family=socket.AF_INET6 if address.version==6 else socket.AF_INET
    sock=socket.socket(family,socket.SOCK_STREAM);sock.setblocking(False);buffer=bytearray()
    def wait(write=False):
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('Absolute exchange deadline')
        reads,writes,_=select.select([] if write else [sock],[sock] if write else [],[],remaining)
        if not reads and not writes:raise TimeoutError('Absolute exchange deadline')
    def receive(n):
        while True:
            wait()
            try:return sock.recv(n)
            except BlockingIOError:continue
    def exact(n):
        while len(buffer)<n:
            part=receive(min(4096,n-len(buffer)))
            if not part:raise ValueError('Truncated HTTP body')
            buffer.extend(part)
        value=bytes(buffer[:n]);del buffer[:n];return value
    def line(limit):
        while True:
            end=buffer.find(b'\r\n')
            if end>=0:
                if end+2>limit:raise ValueError('HTTP line bound')
                value=bytes(buffer[:end]);del buffer[:end+2];return value
            if len(buffer)>=limit:raise ValueError('HTTP line bound')
            part=receive(min(4096,limit-len(buffer)))
            if not part:raise ValueError('Truncated HTTP line')
            buffer.extend(part)
    try:
        register(sock)
        code=sock.connect_ex((str(address),target.port or 80))
        if code not in (0,errno.EINPROGRESS,errno.EWOULDBLOCK,errno.EALREADY,errno.EINTR):raise OSError(code,'Connect failed')
        if code:
            wait(True);error=sock.getsockopt(socket.SOL_SOCKET,socket.SO_ERROR)
            if error:raise OSError(error,'Connect failed')
        host=('['+str(address)+']') if address.version==6 else str(address)
        path=target.path or '/'
        if target.query:path+='?'+target.query
        request=(f'POST {path} HTTP/1.1\r\nHost: {host}:{target.port or 80}\r\nContent-Type: application/json\r\nAccept-Encoding: identity\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n').encode('ascii')+body
        sent=0
        while sent<len(request):
            wait(True)
            try:n=sock.send(memoryview(request)[sent:])
            except BlockingIOError:continue
            if n==0:raise ValueError('Closed HTTP request')
            sent+=n
        while b'\r\n\r\n' not in buffer:
            if len(buffer)>=MAX_HEADER:raise ValueError('HTTP header bound')
            part=receive(min(4096,MAX_HEADER-len(buffer)))
            if not part:raise ValueError('Truncated HTTP headers')
            buffer.extend(part)
        end=buffer.index(b'\r\n\r\n');header=bytes(buffer[:end]);del buffer[:end+4]
        rows=header.split(b'\r\n');status=re.fullmatch(rb'HTTP/1\.[01] ([2-5][0-9][0-9])(?: [^\r\n]*)?',rows.pop(0))
        if not status or len(rows)>100:raise ValueError('HTTP status/header count')
        headers={}
        for row in rows:
            name,sep,value=row.partition(b':')
            if not sep or not re.fullmatch(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+",name):raise ValueError('HTTP header syntax')
            key=name.lower();value=value.strip()
            if key in headers:raise ValueError('Duplicate HTTP header')
            headers[key]=value
        encoding=headers.get(b'content-encoding',b'identity').lower()
        if encoding!=b'identity':raise ValueError('Unexpected compressed response')
        length=headers.get(b'content-length');transfer=headers.get(b'transfer-encoding')
        if length is not None and transfer is not None:raise ValueError('Ambiguous HTTP framing')
        if length is not None:
            if not re.fullmatch(rb'[0-9]{1,9}',length):raise ValueError('HTTP content length')
            n=int(length)
            if n>MAX_BODY:raise ValueError('HTTP body bound')
            if len(buffer)>n:raise ValueError('Unexpected HTTP trailing bytes')
            result=exact(n)
        elif transfer is not None:
            if transfer.lower()!=b'chunked':raise ValueError('Unsupported HTTP transfer')
            result=bytearray()
            while True:
                size=line(1024).split(b';',1)[0]
                if not re.fullmatch(rb'[0-9a-fA-F]{1,8}',size):raise ValueError('HTTP chunk syntax')
                n=int(size,16)
                if n==0:
                    total=count=0
                    while True:
                        trailer=line(MAX_HEADER);total+=len(trailer)+2;count+=1
                        if total>MAX_HEADER or count>100:raise ValueError('HTTP trailer bound')
                        if not trailer:break
                    break
                if n>MAX_BODY-len(result):raise ValueError('HTTP body bound')
                result.extend(exact(n))
                if exact(2)!=b'\r\n':raise ValueError('HTTP chunk separator')
            result=bytes(result)
        else:
            result=bytearray(buffer);buffer.clear()
            while True:
                part=receive(min(4096,MAX_BODY-len(result)+1))
                if not part:break
                if len(part)>MAX_BODY-len(result):raise ValueError('HTTP body bound')
                result.extend(part)
            result=bytes(result)
        if time.monotonic()>deadline:raise TimeoutError('Absolute exchange deadline')
        return int(status[1]),result
    finally:
        unregister(sock);sock.close()
