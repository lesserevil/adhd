#!/usr/bin/env python3
"""Independent OIDC authorization-code integration with signed provider tokens."""
from __future__ import annotations
import argparse, asyncio, base64, hashlib, json, os, secrets, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4
sys.path.insert(0,str(Path.cwd()/'tests'))
from hub_acceptance import Hub, ModelFixture
import httpx
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes

def b64(data): return base64.urlsafe_b64encode(data).rstrip(b'=').decode()
def integer(n): return b64(n.to_bytes((n.bit_length()+7)//8,'big'))

class Provider:
    def __init__(self):
        self.key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        self.mode='valid';self.codes={};self.calls=[];self.tokens=[];self.client_secret=None;self.auth_method='client_secret_basic'
        provider=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def respond(self,status,body,location=None):
                payload=json.dumps(body).encode();self.send_response(status)
                if location:self.send_header('Location',location)
                self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)))
                self.end_headers();self.wfile.write(payload)
            def do_GET(self):
                path=urlsplit(self.path);provider.calls.append(path.path)
                if provider.mode=='unavailable':self.respond(503,{'error':'unavailable'});return
                if path.path=='/.well-known/openid-configuration':
                    self.respond(200,{'issuer':provider.base,'authorization_endpoint':provider.base+'/authorize',
                        'token_endpoint':provider.base+'/token','jwks_uri':provider.base+'/jwks',
                        'response_types_supported':['code'],'subject_types_supported':['public'],
                        'id_token_signing_alg_values_supported':['RS256'],
                        'code_challenge_methods_supported':['S256'],'token_endpoint_auth_methods_supported':[provider.auth_method]});return
                if path.path=='/jwks':
                    n=provider.key.public_key().public_numbers()
                    self.respond(200,{'keys':[{'kty':'RSA','kid':'acceptance-signing-key','use':'sig',
                        'alg':'RS256','n':integer(n.n),'e':integer(n.e)}]});return
                if path.path=='/authorize':
                    q={k:v[0] for k,v in parse_qs(path.query).items()}
                    assert q['response_type']=='code' and q['scope']=='openid'
                    assert q['code_challenge_method']=='S256'
                    code=secrets.token_urlsafe(24);provider.codes[code]=q
                    self.respond(302,{},q['redirect_uri']+'?'+urlencode({'code':code,'state':q['state']}));return
                self.respond(404,{})
            def do_POST(self):
                assert self.path=='/token'
                if provider.mode=='unavailable':self.respond(503,{});return
                values={k:v[0] for k,v in parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode()).items()}
                if provider.client_secret:
                    if provider.auth_method=='client_secret_basic':
                        assert base64.b64decode(self.headers['Authorization'].split(' ',1)[1]).decode()=='acceptance-client:'+provider.client_secret
                        assert 'client_secret' not in values
                    else:
                        assert values['client_secret']==provider.client_secret
                        assert not self.headers.get('Authorization')
                saved=provider.codes.pop(values.get('code',''),None)
                if not saved:self.respond(400,{});return
                assert values['grant_type']=='authorization_code'
                assert b64(hashlib.sha256(values['code_verifier'].encode()).digest())==saved['code_challenge']
                assert values['redirect_uri']==saved['redirect_uri']
                now=int(time.time())
                claims={'iss':provider.base,'sub':'admin-subject','aud':saved['client_id'],
                    'exp':now+120,'iat':now,'nonce':saved['nonce']}
                headers={'alg':'RS256','kid':'acceptance-signing-key','typ':'JWT'}
                if provider.mode=='denied':claims['sub']='unlisted-subject'
                if provider.mode=='issuer':claims['iss']='https://wrong.example.invalid'
                if provider.mode=='audience':claims['aud']='wrong-client'
                if provider.mode=='multi_audience':claims['aud']=[saved['client_id'],'another'];claims['azp']='wrong-client'
                if provider.mode=='nonce':claims['nonce']='wrong-nonce'
                if provider.mode=='expired':claims['exp']=now-120
                if provider.mode=='future':claims['iat']=now+3600
                if provider.mode=='nbf':claims['nbf']=now+3600
                if provider.mode=='short':claims['exp']=now+2
                if provider.mode=='kid':headers['kid']='unknown-key'
                if provider.mode=='none':headers['alg']='none'
                if provider.mode=='hs256':headers['alg']='HS256'
                payload=json.dumps(claims,separators=(',',':'))
                if provider.mode=='duplicate':payload=payload[:-1]+',"sub":"admin-subject"}'
                signing=(b64(json.dumps(headers).encode())+'.'+b64(payload.encode())).encode()
                key=rsa.generate_private_key(public_exponent=65537,key_size=2048) if provider.mode=='signature' else provider.key
                token=signing.decode()+'.'+b64(key.sign(signing,padding.PKCS1v15(),hashes.SHA256()))
                provider.tokens.append(token);self.respond(200,{'id_token':token,'token_type':'Bearer'})
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.base=f'http://127.0.0.1:{self.server.server_port}'
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(timeout=3)

async def checks(command,root,record):
    model=ModelFixture();provider=Provider();hub=Hub(command,root/'oidc',model.url)
    hub.config.update(admin_auth='oidc',admin_token=secrets.token_urlsafe(32),public_url=hub.base,
        oidc={'issuer':provider.base,'client_id':'acceptance-client',
        'allowed_subjects':['admin-subject'],'allow_insecure_loopback':True,
        'session_seconds':60,'idle_seconds':30})
    hub.config_file.write_text(json.dumps(hub.config));hub.start()
    try:
        async with httpx.AsyncClient(base_url=hub.base,timeout=15,follow_redirects=True) as client:
            assert (await client.get('/admin/auth')).json()=={'mode':'oidc'}
            assert (await client.post('/admin/api',json={'op':'overview'},headers={
                'Authorization':'Bearer '+hub.config['admin_token']})).status_code==401
            login=await client.get('/admin/login')
            assert login.status_code==200,login.text
            session=await client.get('/admin/session');assert session.status_code==200,session.text
            csrf=session.json()['csrf'];headers={'Origin':hub.base,'X-CSRF-Token':csrf}
            assert (await client.post('/admin/api',json={'op':'overview'},headers=headers)).status_code==200
            assert (await client.post('/admin/api',json={'op':'overview'})).status_code==403
            assert (await client.post('/admin/api',json={'op':'overview'},headers={
                **headers,'Origin':'https://evil.example.invalid'})).status_code==403
            provider.mode='unavailable'
            assert (await client.post('/admin/api',json={'op':'overview'},headers=headers)).status_code==200
            provider.mode='valid'
            callbacks=[r.request.url for r in login.history if r.request.url.path=='/admin/callback']
            assert callbacks and (await client.get(str(callbacks[0]))).status_code==401
            record('oidc-code-pkce-signed-token-session-csrf-origin-and-state-replay')
            logout=await client.post('/admin/logout',headers=headers);assert logout.status_code==200
            assert (await client.get('/admin/session')).status_code==401
            record('oidc-local-logout-clears-session-without-key-fallback')
        for mode in ['denied','issuer','audience','multi_audience','nonce','expired','future','nbf','kid','none','hs256','duplicate','signature']:
            provider.mode=mode
            async with httpx.AsyncClient(base_url=hub.base,timeout=15,follow_redirects=True) as client:
                login=await client.get('/admin/login')
                assert login.status_code in (401,403), (mode,login.status_code,login.text)
                assert (await client.get('/admin/session')).status_code==401
        record('oidc-authorization-and-jwt-claim-signature-algorithm-rejection')
        provider.mode='short'
        async with httpx.AsyncClient(base_url=hub.base,timeout=15,follow_redirects=True) as client:
            assert (await client.get('/admin/login')).status_code==200
            await asyncio.sleep(3)
            assert (await client.get('/admin/session')).status_code==401
        provider.mode='valid'
        async with httpx.AsyncClient(base_url=hub.base,timeout=15,follow_redirects=True) as client:
            assert (await client.get('/admin/login')).status_code==200
            hub.stop(hard=True);hub.start()
            assert (await client.get('/admin/session')).status_code==401
            assert (await client.get('/admin/callback?code=invalid&state=invalid')).status_code==401
        record('oidc-token-expiry-restart-invalidation-and-browser-binding')
        logs=(root/'oidc'/'stderr.log').read_text(errors='replace')
        store=(root/'oidc'/'hub.dets').read_bytes()+(root/'oidc'/'hub.dets.journal').read_bytes()
        assert not any(token in logs or token.encode() in store for token in provider.tokens)
        assert hub.config['admin_token'] not in logs
        record('oidc-provider-tokens-and-credentials-never-persist-or-log')
        secret=secrets.token_urlsafe(32);os.environ['ADHD_TEST_OIDC_SECRET']=secret
        provider.client_secret=secret;hub.config['oidc']['client_secret_env']='ADHD_TEST_OIDC_SECRET'
        hub.config_file.write_text(json.dumps(hub.config))
        for method in ['client_secret_basic','client_secret_post']:
            provider.auth_method=method;hub.config['oidc']['token_endpoint_auth_method']=method
            hub.config_file.write_text(json.dumps(hub.config));hub.stop();hub.start()
            async with httpx.AsyncClient(base_url=hub.base,timeout=15,follow_redirects=True) as client:
                assert (await client.get('/admin/login')).status_code==200
                assert (await client.get('/admin/session')).status_code==200
        assert secret.encode() not in (root/'oidc'/'hub.dets').read_bytes()
        record('oidc-confidential-client-basic-and-post-authentication')
    finally:hub.stop();provider.close();model.close();os.environ.pop('ADHD_TEST_OIDC_SECRET',None)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--command',required=True)
    p.add_argument('--work-dir',default='_build/tests/oidc');p.add_argument('--report',default='verification/oidc-acceptance.json')
    args=p.parse_args();root=Path(args.work_dir).resolve()/str(uuid4());root.mkdir(parents=True)
    cases=[]
    def record(name):cases.append({'case':name,'passed':True});print('PASS',name,flush=True)
    asyncio.run(checks(json.loads(args.command),root,record))
    Path(args.report).write_text(json.dumps({'schema':'adhd/oidc-acceptance@1','passed':True,'cases':cases},indent=2)+'\n')
if __name__=='__main__':main()
