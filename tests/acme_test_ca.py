#!/usr/bin/env python3
"""Owned loopback-only Pebble fixture; never contacts a public ACME service."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import ssl
import subprocess
import time
import urllib.request

SHA = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

def run(args):
    work = args.work.resolve()
    work.mkdir(mode=0o700, parents=True, exist_ok=False)
    source = next((args.tools/'pebble-source').iterdir())
    binaries = {
        'pebble': args.tools/'testca-bin/pebble-linux-amd64/linux/amd64/pebble',
        'dns': args.tools/'testca-bin/pebble-challtestsrv-linux-amd64/linux/amd64/pebble-challtestsrv'}
    release = json.loads((args.tools/'pebble-release.json').read_text())
    assert release['tag_name'] == 'v2.10.1'
    assets = {v['name']: v for v in release['assets']}
    for name in ('pebble-linux-amd64.tar.gz','pebble-challtestsrv-linux-amd64.tar.gz'):
        assert 'sha256:'+SHA(args.tools/name) == assets[name]['digest']
    for name, original in {'frontend-root.pem':'test/certs/pebble.minica.pem',
                            'frontend-cert.pem':'test/certs/localhost/cert.pem',
                            'frontend-key.pem':'test/certs/localhost/key.pem'}.items():
        shutil.copyfile(source/original,work/name)
        (work/name).chmod(0o600)
    for port in (19100,19101,19102,19153):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',port))
    cfg={'pebble':{'listenAddress':'127.0.0.1:19100','managementListenAddress':'127.0.0.1:19101',
        'certificate':str(work/'frontend-cert.pem'),'privateKey':str(work/'frontend-key.pem'),
        'httpPort':8080,'tlsPort':18444,'externalAccountBindingRequired':False,
        'retryAfter':{'authz':1,'order':1},'keyAlgorithm':'ecdsa',
        'profiles':{'default':{'description':'Owned ACME acceptance only','validityPeriod':90}}}}
    (work/'config.json').write_text(json.dumps(cfg,indent=2)+'\n')
    (work/'config.json').chmod(0o600)
    env={'PATH':os.environ['PATH'],'GOMAXPROCS':'2','PEBBLE_VA_NOSLEEP':'1','PEBBLE_WFE_NONCEREJECT':'0'}
    argv={
      'dns':[str(binaries['dns']),'-dnsserver','127.0.0.1:19153','-management','127.0.0.1:19102',
        '-defaultIPv4','127.0.0.1','-defaultIPv6','','-http01','','-https01','','-tlsalpn01','','-doh',''],
      'pebble':[str(binaries['pebble']),'-config',str(work/'config.json'),'-dnsserver','127.0.0.1:19153','-strict']}
    children=[];logs=[];stopped=False
    def stop(_number,_frame):
        nonlocal stopped
        stopped=True
    for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(sig,stop)
    closed=[]
    try:
        for name in ('dns','pebble'):
            log=(work/(name+'.log')).open('xb');os.chmod(log.name,0o600);logs.append(log)
            p=subprocess.Popen(argv[name],stdin=subprocess.DEVNULL,stdout=log,stderr=log,env=env,start_new_session=True)
            children.append((name,p))
        context=ssl.create_default_context(cafile=str(work/'frontend-root.pem'))
        end=time.monotonic()+15
        while True:
            for _,p in children:
                if p.poll() is not None:raise RuntimeError('owned test CA failed before readiness')
            try:
                with urllib.request.urlopen('https://localhost:19100/dir',context=context,timeout=1) as r:
                    directory=json.load(r)
                with urllib.request.urlopen('https://localhost:19101/roots/0',context=context,timeout=1) as r:
                    issuer=r.read(16384)
                if not issuer.startswith(b'-----BEGIN CERTIFICATE-----'):raise ValueError('issuer root')
                break
            except Exception:
                if time.monotonic()>=end:raise
                time.sleep(.05)
        (work/'issuer-root.pem').write_bytes(issuer);(work/'issuer-root.pem').chmod(0o600)
        manifest={'schema':'adhd/acme-pebble-owned-fixture@1','ready':True,'pebble_version':'v2.10.1',
          'directory_url':'https://localhost:19100/dir','management_url':'https://localhost:19101',
          'dns_management_url':'http://127.0.0.1:19102','dns_server':'127.0.0.1:19153',
          'frontend_root':str(work/'frontend-root.pem'),'frontend_root_sha256':SHA(work/'frontend-root.pem'),
          'issuer_root':str(work/'issuer-root.pem'),'issuer_root_sha256':SHA(work/'issuer-root.pem'),
          'validation_http_port':8080,'initial_domain_routes':{'one.acme.test':'127.0.0.1','two.acme.test':'127.0.0.1'},
          'real_validation':True,'nonce_validation':True,'valid_nonce_random_reject_percent':0,
          'validity_seconds':90,'public_ca_calls':0,'config_sha256':SHA(work/'config.json'),
          'binary_sha256':{n:SHA(v) for n,v in binaries.items()},
          'processes':[{ 'name':n,'pid':p.pid,'start_ticks':Path('/proc',str(p.pid),'stat').read_text().split(') ')[1].split()[19]} for n,p in children],
          'owner_pid':os.getpid(),'argv':argv,'lifetime_seconds':args.lifetime_seconds}
        (work/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        print(json.dumps({'ready':True,'manifest':str(work/'manifest.json')}),flush=True)
        deadline=time.monotonic()+args.lifetime_seconds
        while not stopped and time.monotonic()<deadline:
            for _,p in children:
                if p.poll() is not None:raise RuntimeError('owned test CA exited')
            time.sleep(.1)
    finally:
        for name,p in reversed(children):
            try:
                if p.poll() is None:os.killpg(p.pid,signal.SIGTERM)
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=3)
            closed.append({'name':name,'pid':p.pid,'exit_code':p.returncode,'absent':not Path('/proc',str(p.pid)).exists()})
        for log in logs:log.close()
        (work/'cleanup.json').write_text(json.dumps({'closed':closed,'all_absent':all(v['absent'] for v in closed)},indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tools',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--lifetime-seconds',type=int,default=3600)
    args=parser.parse_args()
    if not 1<=args.lifetime_seconds<=7200:parser.error('bounded test fixture lifetime required')
    args.tools=args.tools.resolve()
    run(args)
