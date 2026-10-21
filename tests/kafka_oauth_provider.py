"""Bounded synthetic HTTPS JWKS issuer and private TLS material for real Kafka probes.

This is a test fixture, not an identity service shipped in the application.
"""
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
import ipaddress
import json
import os
from pathlib import Path
import secrets
import ssl
import subprocess
import threading
import time

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

PROXY_IMAGE='confluentinc/cp-kafka-rest@sha256:85f286aa0b8b6cfc1977d81bdb9b5eb3ece4942563afd49862e14d5e92ac7058'


def b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


def private(path, data):
    path.write_bytes(data)
    path.chmod(0o600)


class Issuer:
    def __init__(self, directory, bind, wrong_hostname=False):
        self.root=Path(directory).resolve()
        self.root.mkdir(mode=0o700)
        self.password=secrets.token_urlsafe(24)
        self.ca_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Synthetic ADHD qualification root')])
        now=datetime.now(timezone.utc)
        self.ca=(x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(self.ca_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=2))
            .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
            .add_extension(x509.KeyUsage(False,False,False,False,False,True,True,False,False),critical=True)
            .sign(self.ca_key,hashes.SHA256()))
        self.ca_pem=self.ca.public_bytes(serialization.Encoding.PEM)
        private(self.root/'ca.pem',self.ca_pem)
        private(self.root/'password.txt',self.password.encode())
        self.signing={kid:rsa.generate_private_key(public_exponent=65537,key_size=2048) for kid in ('first','second')}
        self.lock=threading.Lock()
        self.active_keys=['first','second']
        self.requests=0
        self.cert('rest',[x509.IPAddress(ipaddress.ip_address('127.0.0.1')),x509.DNSName('localhost'),x509.DNSName('kafka-rest')])
        self.cert('issuer',[x509.IPAddress(ipaddress.ip_address('127.0.0.1' if wrong_hostname else bind))])
        fixture=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):
                pass
            def do_GET(self):
                if self.path!='/jwks':
                    self.send_error(404)
                    return
                with fixture.lock:
                    fixture.requests+=1
                    keys=list(fixture.active_keys)
                body=json.dumps({'keys':[fixture.jwk(kid) for kid in keys]}).encode()
                self.send_response(200)
                self.send_header('Content-Type','application/json')
                self.send_header('Cache-Control','public, max-age=1')
                self.send_header('Content-Length',str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        class Server(ThreadingHTTPServer):
            daemon_threads=True
            request_queue_size=16
            slots=threading.BoundedSemaphore(16)
            def get_request(self):
                request,address=super().get_request()
                request.settimeout(5)
                try:
                    request=self.tls_context.wrap_socket(request,server_side=True)
                except Exception:
                    request.close()
                    raise
                return request,address
            def process_request(self,request,address):
                if not self.slots.acquire(blocking=False):
                    self.shutdown_request(request)
                    return
                try:
                    super().process_request(request,address)
                except Exception:
                    self.slots.release()
                    raise
            def process_request_thread(self,request,address):
                try:
                    super().process_request_thread(request,address)
                finally:
                    self.slots.release()
        self.server=Server((bind,0),Handler)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version=ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(self.root/'issuer.pem',self.root/'issuer-key.pem')
        self.server.tls_context=context
        self.issuer='https://'+bind+':'+str(self.server.server_port)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def cert(self,name,sans):
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,name)])
        now=datetime.now(timezone.utc)
        cert=(x509.CertificateBuilder().subject_name(subject).issuer_name(self.ca.subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=2))
            .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
            .add_extension(x509.SubjectAlternativeName(sans),critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=False)
            .sign(self.ca_key,hashes.SHA256()))
        private(self.root/(name+'.pem'),cert.public_bytes(serialization.Encoding.PEM))
        private(self.root/(name+'-key.pem'),key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        private(self.root/(name+'.p12'),pkcs12.serialize_key_and_certificates(name.encode(),key,cert,[self.ca],
            serialization.BestAvailableEncryption(self.password.encode())))

    def repair_hostname(self,bind):
        self.cert('issuer',[x509.IPAddress(ipaddress.ip_address(bind))])
        self.server.tls_context.load_cert_chain(self.root/'issuer.pem',self.root/'issuer-key.pem')

    def java_truststore(self):
        subprocess.run(['docker','run','--rm','--user',str(os.getuid())+':'+str(os.getgid()),
            '--network','none','--entrypoint','/usr/bin/keytool','-v',str(self.root)+':/fixture',PROXY_IMAGE,
            '-importcert','-noprompt','-alias','issuer-ca','-file','/fixture/ca.pem',
            '-keystore','/fixture/issuer-trust.p12','-storetype','PKCS12',
            '-storepass:file','/fixture/password.txt'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        (self.root/'issuer-trust.p12').chmod(0o600)

    def jwk(self,kid):
        public=self.signing[kid].public_key().public_numbers()
        return {'kty':'RSA','alg':'RS256','use':'sig','kid':kid,
                'n':b64(public.n.to_bytes((public.n.bit_length()+7)//8,'big')),
                'e':b64(public.e.to_bytes((public.e.bit_length()+7)//8,'big'))}

    def token(self,kid='first',**overrides):
        now=int(time.time())
        claims={'iss':self.issuer,'aud':'adhd-event-service','sub':'synthetic-hub',
                'groups':['event-service'],'iat':now-2,'nbf':now-2,'exp':now+300,**overrides}
        unsigned=(b64(json.dumps({'alg':'RS256','typ':'JWT','kid':kid},separators=(',',':')).encode())+'.'+
                  b64(json.dumps(claims,separators=(',',':')).encode()))
        signature=self.signing[kid].sign(unsigned.encode(),padding.PKCS1v15(),hashes.SHA256())
        return unsigned+'.'+b64(signature)

    def retire(self,kid):
        with self.lock:
            self.active_keys=[key for key in self.active_keys if key!=kid]

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
