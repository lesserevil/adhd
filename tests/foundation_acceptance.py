#!/usr/bin/env python3
"""Independent black-box checks of live settings, local users, OIDC and roles."""
import argparse
import base64
from http.cookiejar import CookieJar
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, HTTPCookieProcessor, build_opener
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hub_acceptance import ModelFixture


def b64(data):
    return base64.urlsafe_b64encode(data).decode().rstrip('=')


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Runtime:
    def __init__(self, root, command, image=None, *, initialize_projects=True):
        self.root, self.command, self.image = root, command, image
        self.initialize_projects = initialize_projects
        root.mkdir(mode=0o700)
        self.file = root / 'hub.json'
        self.base = 'http://127.0.0.1:8766'
        self.process = self.container = None
        self.logs = []

    @property
    def config(self):
        return json.loads(self.file.read_text())

    def start(self):
        if self.file.exists():
            self.base = 'http://127.0.0.1:' + str(self.config.get('port', 8766))
        self.logs = [(self.root / n).open('ab') for n in ('stdout.log', 'stderr.log')]
        command = self.command
        if self.image:
            self.container = 'adhd-foundation-' + uuid4().hex[:12]
            command = ['docker','run','--rm','--name',self.container,'--network','host',
                       '--user',f'{os.getuid()}:{os.getgid()}','--read-only','--cap-drop','ALL',
                       '--security-opt','no-new-privileges','--memory','768m','--cpus','2',
                       '--pids-limit','256','--tmpfs','/tmp:rw,nosuid,noexec,size=128m',
                       '--mount',f'type=bind,src={self.root},dst={self.root}',
                       '--env',f'ADHD_CONFIG_FILE={self.file}',self.image]
        self.process = subprocess.Popen(command + [json.dumps(['serve', str(self.file)])],
                                        stdout=self.logs[0],stderr=self.logs[1],start_new_session=True)
        self.pid = self.process.pid
        deadline = time.monotonic()+45
        while time.monotonic()<deadline:
            if self.process.poll() is not None:
                raise AssertionError('Runtime exited; inspect private work directory')
            try:
                if self.file.exists():
                    self.base = 'http://127.0.0.1:' + str(self.config.get('port', 8766))
                if Client(self).get('/health')[0] == 200:
                    self.initialize_unknown_projects()
                    return
            except (URLError,ConnectionError,TimeoutError): pass
            time.sleep(.1)
        raise AssertionError('Runtime readiness deadline')

    def initialize_unknown_projects(self):
        """Fixture-only public Admin admission; known missing stores never initialize."""
        if not self.initialize_projects:
            return
        status, schema, _ = Client(self).get('/protocol/schema')
        if status != 200 or schema.get('$id') != 'urn:adhd:protocol:2.1':
            return
        client = Client(self, self.config.get('admin_token'))
        if not client.bearer:
            text = (self.root / 'initial-admin-password.txt').read_text()
            client.login('admin', re.search(r'^Password: (.+)$', text, re.M)[1])
        # This fixture family tests the pre-Kafka/model-only surface. A pristine
        # bootstrap advertises eventing without a broker endpoint: select the
        # documented disabled transport explicitly, never invent broker success.
        eventing = self.config.get('eventing') or {}
        if eventing.get('enabled') is True and not eventing.get('rest_url'):
            client.api({'op': 'config_update', 'patch': {'eventing': {'enabled': False}}}, mutation=True)
        projects = client.api({'op': 'list_projects'})['projects']
        for project in projects:
            project_id = project['id']
            def call(op, **fields):
                return client.api({'op': op, 'project_id': project_id, **fields})
            availability = call('project_restore_status')['availability']
            if availability == 'ready':
                continue
            assert availability == 'uninitialized', 'Fixture must not initialize an existing unavailable project'
            revision = client.api({'op': 'config_get'})['config_revision']
            def settle(receipt, desired):
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    op = call('project_restore_status', operation_id=receipt['operation_id'])['operation']
                    if op['state'] == desired:
                        return op
                    assert op['state'] not in ('failed', 'blocked', 'expired', 'stale'), op['failure']
                    time.sleep(.05)
                raise AssertionError('Fixture Admin admission deadline')
            receipt = call('project_restore_plan', mode='initialize', expected_revision=revision,
                           confirm=True, message_id=uuid4().hex)
            plan = settle(receipt, 'ready')['plan']
            applied = call('project_restore_apply', plan_id=plan['plan_id'], plan_sha256=plan['plan_sha256'],
                           expected_revision=revision, confirm=True, message_id=uuid4().hex)
            assert settle(applied, 'complete')['result']['initialized'] is True
            assert client.api({'op': 'config_get'})['config_revision'] == revision

    def stop(self, hard=False):
        if self.container:
            subprocess.run(['docker','kill' if hard else 'stop',self.container],
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if self.process and self.process.poll() is None:
            os.killpg(self.process.pid,signal.SIGKILL if hard else signal.SIGTERM)
            try: self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid,signal.SIGKILL);self.process.wait(timeout=5)
        for log in self.logs: log.close()
        self.logs=[]
        if self.container:
            subprocess.run(['docker','rm','-f',self.container],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            self.container=None


class Client:
    def __init__(self, runtime, bearer=None):
        self.runtime, self.bearer = runtime, bearer
        self.cookies=CookieJar()
        self.opener=build_opener(HTTPCookieProcessor(self.cookies))
        self.csrf=None

    def request(self,path,data=None,headers=None):
        hs={'Origin':self.runtime.base}
        if data is not None: hs['Content-Type']='application/json'
        if self.bearer: hs['Authorization']='Bearer '+self.bearer
        if self.csrf: hs['X-CSRF-Token']=self.csrf
        hs.update(headers or {})
        raw=json.dumps(data).encode() if data is not None else None
        try: response=self.opener.open(Request(self.runtime.base+path,data=raw,headers=hs),timeout=15)
        except HTTPError as e: response=e
        with response:
            body=response.read()
            value=json.loads(body) if response.headers.get('Content-Type','').startswith('application/json') else body.decode()
            return response.status,value,response.headers

    def get(self,path): return self.request(path)

    def login(self, username, password):
        status,body,headers=self.request('/admin/login',{'username':username,'password':password})
        assert status==200,(status,body)
        status,session,_=self.get('/admin/session')
        assert status==200 and session['authenticated'],session
        self.csrf=session['csrf']
        return session['user']

    def api(self,body,expected=200,mutation=False,headers=None):
        if mutation:
            body={**body,'expected_revision':self.runtime.config.get('config_revision',1),
                  'message_id':uuid4().hex,'confirm':True}
        status,value,_=self.request('/admin/api',body,headers)
        assert status==expected,(body['op'],status,expected,value)
        return value

    def rpc(self,body, token, mid=None):
        envelope={'jsonrpc':'2.0','id':1,'method':'SendMessage','params':{
            'message':{'messageId':mid or uuid4().hex,'role':'ROLE_USER','parts':[{'data':body}]}}}
        status,value,_=self.request('/a2a',envelope,{'Authorization':'Bearer '+token})
        assert status==200 and 'error' not in value,(status,value)
        return value['result']['message']['parts'][0]['data']


class Provider:
    def __init__(self,root):
        self.key=root/'provider-key.pem'
        subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:2048',
                        '-out',str(self.key)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self.key.chmod(0o600)
        modulus=subprocess.check_output(['openssl','rsa','-in',str(self.key),'-modulus','-noout'],stderr=subprocess.DEVNULL).decode().strip().split('=')[1]
        self.n=b64(bytes.fromhex(modulus));self.codes={};self.mode='normal';self.exchanges=0
        self.groups=['admins','engineering','readers'];self.subject='fixture-person';self.nonce=None;self.available=True
        self.last_callback=None;self.claim_overrides={};self.omit_claims=set()
        fixture=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_): pass
            def reply(self,status,value):
                raw=json.dumps(value).encode();self.send_response(status)
                self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)))
                self.end_headers();self.wfile.write(raw)
            def do_GET(self):
                if not fixture.available:return self.reply(503,{'error':'unavailable'})
                path=urlsplit(self.path)
                if path.path=='/.well-known/openid-configuration':
                    self.reply(200,{'issuer':fixture.issuer,'authorization_endpoint':fixture.issuer+'/authorize',
                        'token_endpoint':fixture.issuer+'/token','jwks_uri':fixture.issuer+'/jwks',
                        'response_types_supported':['code'],'id_token_signing_alg_values_supported':['RS256'],
                        'code_challenge_methods_supported':['S256'],'subject_types_supported':['public'],
                        'token_endpoint_auth_methods_supported':['client_secret_basic','none']})
                elif path.path=='/jwks':
                    self.reply(200,{'keys':[{'kty':'RSA','alg':'RS256','use':'sig','kid':'fixture-rsa',
                                          'n':fixture.n,'e':'AQAB'}]})
                elif path.path=='/authorize':
                    q={k:v[0] for k,v in parse_qs(path.query).items()}
                    assert q['response_type']=='code' and q['client_id']=='independent-client'
                    assert q['code_challenge_method']=='S256' and len(q['nonce'])>=32
                    code=secrets.token_urlsafe(24);fixture.codes[code]=q
                    target=q['redirect_uri']+'?'+urlencode({'code':code,'state':q['state']})
                    fixture.last_callback=target
                    self.send_response(302);self.send_header('Location',target);self.send_header('Content-Length','0');self.end_headers()
                else:self.reply(404,{'error':'not-found'})
            def do_POST(self):
                if not fixture.available:return self.reply(503,{'error':'unavailable'})
                q={k:v[0] for k,v in parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode()).items()}
                auth=self.headers.get('Authorization')
                assert auth=='Basic '+base64.b64encode(b'independent-client:fixture-client-secret').decode()
                stored=fixture.codes.pop(q['code'])
                assert q['grant_type']=='authorization_code' and q['redirect_uri']==stored['redirect_uri']
                assert b64(hashlib.sha256(q['code_verifier'].encode()).digest())==stored['code_challenge']
                fixture.exchanges+=1
                claims={'iss':fixture.issuer,'sub':fixture.subject,'aud':'independent-client',
                        'iat':int(time.time()),'exp':int(time.time())+300,'nonce':stored['nonce'],
                        'name':'Independent OIDC Person','email':'person@example.invalid','email_verified':True,
                        'groups':fixture.groups}
                claims.update(fixture.claim_overrides)
                claims={k:v for k,v in claims.items() if k not in fixture.omit_claims}
                if fixture.mode=='wrong-nonce':claims['nonce']='incorrect'
                elif fixture.mode=='expired':claims['exp']=int(time.time())-60
                elif fixture.mode=='wrong-issuer':claims['iss']='https://wrong-issuer.invalid'
                elif fixture.mode=='wrong-audience':claims['aud']='different-client'
                header={'typ':'JWT','alg':'RS256','kid':'fixture-rsa'}
                if fixture.mode=='unknown-kid':header['kid']='untrusted-key'
                encoded=b64(json.dumps(header).encode())+'.'+b64(json.dumps(claims).encode())
                signature=subprocess.check_output(['openssl','dgst','-sha256','-sign',str(fixture.key)],input=encoded.encode())
                if fixture.mode=='tampered':signature=bytes([signature[0]^1])+signature[1:]
                self.reply(200,{'access_token':'fixture-access-token','token_type':'Bearer',
                                'id_token':encoded+'.'+b64(signature)})
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.issuer='http://127.0.0.1:'+str(self.server.server_port)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def close(self): self.server.shutdown();self.server.server_close();self.thread.join(timeout=3)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--command');choice.add_argument('--image')
    parser.add_argument('--report',default='verification/foundation-acceptance.json')
    parser.add_argument('--protocol-version',type=int,choices=(1,2),default=1,help='Expected published profile; use 2 for the multi-project/Kafka candidate')
    parser.add_argument('--protocol-profile',choices=('1','2','2.1'),help='Exact expected schema profile, including a required minor version')
    args=parser.parse_args()
    parent=Path('_build/roadmap/tests').resolve();parent.mkdir(parents=True,exist_ok=True)
    root=Path(tempfile.mkdtemp(prefix='run-',dir=parent))
    runtime=Runtime(root/'hub',json.loads(args.command) if args.command else [],args.image)
    model=ModelFixture();provider=Provider(root);cases=[]
    def record(name):cases.append({'case':name,'passed':True});print('PASS',name,flush=True)
    try:
        runtime.start();pid=runtime.pid
        multi='projects' in runtime.config
        assert multi == (args.protocol_version==2), 'Bootstrap must match the explicitly selected product profile'
        text=(runtime.root/'initial-admin-password.txt').read_text()
        password=re.search(r'^Password: (.+)$',text,re.M)[1]
        assert len(password)>=40 and 'Username: admin' in text
        assert stat.S_IMODE((runtime.root/'initial-admin-password.txt').stat().st_mode)==0o600
        original_password_file=text
        wrong=Client(runtime)
        status,error,_=wrong.request('/admin/login',{'username':'admin','password':'incorrect-password'})
        assert status==401 and password not in json.dumps(error)
        status,unknown,_=wrong.request('/admin/login',{'username':'not-a-user','password':'incorrect-password'})
        assert status==401 and error==unknown
        admin=Client(runtime);user=admin.login('admin',password)
        assert user['role']=='Admin'
        settings=admin.api({'op':'config_get'});serialized=json.dumps(settings)
        assert password not in serialized
        assert all('password_hash' not in u for u in settings['config']['users'])
        assert all(type(value) is bool for value in settings['secrets'].values())
        assert runtime.config['users'][0]['password_hash']['key'] not in serialized
        admin.api({'op':'update_profile','name':'Initial Administrator','email':'admin@example.invalid'},mutation=True)
        cookies=list(admin.cookies);assert cookies and all(c.has_nonstandard_attr('HttpOnly') for c in cookies)
        record('first-install-private-random-admin-password-and-real-session')

        devpass='developer-test-password-001';viewpass='viewer-test-password-001'
        dev=admin.api({'op':'save_user','user':{'username':'developer','name':'A Developer',
                       'email':'dev@example.invalid','role':'Developer','password':devpass}},mutation=True)['user']
        view=admin.api({'op':'save_user','user':{'username':'viewer','name':'A Viewer',
                        'email':'viewer@example.invalid','role':'Viewer','password':viewpass}},mutation=True)['user']
        developer=Client(runtime);developer.login('developer',devpass)
        viewer=Client(runtime);viewer.login('viewer',viewpass)
        grants=[p['id'] for p in runtime.config['projects']] if multi else []
        if multi:
            assert developer.api({'op':'list_projects'})['projects']==[]
            assert viewer.api({'op':'list_projects'})['projects']==[]
            viewer.api({'op':'overview'},expected=404)
            for principal in (dev,view):
                admin.api({'op':'save_user','user':{**{k:principal[k] for k in ('id','name','email','role')},'project_ids':grants}},mutation=True)
        viewer.api({'op':'overview'})
        for role_client in (developer,viewer):
            role_client.api({'op':'config_get'},expected=403)
            role_client.api({'op':'link_oidc','user_id':dev['id'],
                'expected_revision':runtime.config['config_revision'],'confirm':True},expected=403)
            role_client.api({'op':'save_user','user':{'id':view['id'],'name':'A Viewer',
                 'email':'viewer@example.invalid','role':'Admin'}},expected=403,mutation=True)
        viewer.api({'op':'create_agent','agent_id':'viewer-forbidden','token':'x'*32},expected=403,mutation=True)
        developer.api({'op':'create_agent','agent_id':'spoof-owner','token':'x'*32,'owner_user_id':user['id']},
                      expected=403,mutation=True)
        token=secrets.token_urlsafe(32)
        agent=developer.api({'op':'create_agent','agent_id':'developer-agent','token':token,**({'project_ids':grants} if multi else {})},mutation=True)
        assert agent['owner_user_id']==dev['id'] and token not in json.dumps(agent)
        assert developer.rpc({'op':'whoami'},token)['agent_id']=='developer-agent'
        record('one-role-per-user-admin-only-assignment-and-self-owned-agent')

        status,_,_=admin.request('/admin/api',{'op':'config_update','expected_revision':runtime.config['config_revision'],
            'patch':{'threshold_ppm':123456},'confirm':True,'message_id':uuid4().hex},{'X-CSRF-Token':'wrong'})
        assert status==403
        status,_,_=admin.request('/admin/api',{'op':'overview'},{'Origin':'https://hostile.invalid'})
        assert status==403
        record('cookie-api-csrf-and-origin-enforcement')

        old_token=token;token=secrets.token_urlsafe(32)
        admin.api({'op':'config_update','patch':{'agents':{'developer-agent':token}}},mutation=True)
        status,_,_=Client(runtime,bearer=old_token).request('/a2a',{
            'jsonrpc':'2.0','id':1,'method':'SendMessage','params':{'message':{
                'messageId':uuid4().hex,'role':'ROLE_USER','parts':[{'data':{'op':'whoami'}}]}}})
        assert status==401
        assert developer.rpc({'op':'whoami'},token)['agent_id']=='developer-agent'
        record('agent-token-rotation-live-revokes-old-credential-without-changing-agent')

        previous=runtime.config['config_revision']
        patch={'threshold_ppm':875000,'matcher':{'url':model.url,'model':'Nemotron-Deciffusion-8B-v2.1','timeout_ms':1500,'retry_ms':120}}
        command={'op':'config_update','patch':patch,'expected_revision':previous,'confirm':True,'message_id':'stable-config-write'}
        changed=admin.api(command)
        assert admin.api(command)==changed
        admin.api({**command,'patch':{'threshold_ppm':900000}},expected=409)
        admin.api({'op':'config_update','patch':{'threshold_ppm':900000},'expected_revision':previous,
                   'confirm':True,'message_id':uuid4().hex},expected=409)
        assert runtime.process.poll() is None and runtime.process.pid==pid
        assert runtime.config['threshold_ppm']==875000
        record('durable-revision-conflict-and-response-loss-idempotency')

        promoted=admin.api({'op':'save_user','user':{'id':view['id'],'name':'A Viewer',
             'email':'viewer@example.invalid','role':'Developer'}},mutation=True)
        assert viewer.api({'op':'create_agent','agent_id':'promoted-agent','token':'p'*32},mutation=True)['owner_user_id']==view['id']
        admin.api({'op':'save_user','user':{'id':view['id'],'name':'A Viewer',
             'email':'viewer@example.invalid','role':'Viewer'}},mutation=True)
        viewer.api({'op':'create_agent','agent_id':'demoted-agent','token':'p'*32},expected=403,mutation=True)
        record('existing-session-promotion-and-demotion-take-effect-live')

        for disabled in (True,False):
            admin.api({'op':'save_user','user':{'id':view['id'],'name':'A Viewer',
                'email':'viewer@example.invalid','role':'Viewer','disabled':disabled}},mutation=True)
            viewer.api({'op':'overview'},expected=401)
        viewer.login('viewer',viewpass)
        record('disable-revokes-session-and-reenable-cannot-resurrect-old-cookie')

        publication=developer.rpc({'op':'publish','text':'Durable original across hot store moves.'},token,mid='before-store-move')['publication']
        delivery=developer.rpc({'op':'send','recipient_id':'developer-agent','text':'Private migration sentinel'},token)['delivery']
        assert admin.api({'op':'private_delivery','delivery_id':delivery['id']})['delivery']['text']=='Private migration sentinel'
        developer.api({'op':'private_delivery','delivery_id':delivery['id']},expected=403)
        viewer.api({'op':'private_delivery','delivery_id':delivery['id']},expected=403)
        record('admin-full-private-data-access-with-developer-viewer-denial')
        newstore=runtime.root/'moved-store.dets'
        admin.api({'op':'config_update','patch':{'store_path':str(newstore)}},mutation=True)
        assert runtime.config['store_path']==str(newstore)
        selected_store=newstore
        if Path(str(runtime.file)+'.stores').exists():
            from project_recovery_state import route
            selected_store=route(runtime.file,runtime.config['project_id'])[1]
        assert selected_store.is_file()
        assert developer.rpc({'op':'get','publication_id':publication['id']},token)['publication']['id']==publication['id']
        assert delivery['id'] in [d['id'] for d in developer.rpc({'op':'poll'},token)['deliveries']]
        developer.rpc({'op':'ack','delivery_ids':[delivery['id']]},token)
        occupied=runtime.root/'occupied.dets'
        protected=Path(str(occupied)+str(selected_store)[len(str(newstore)):])
        protected.parent.mkdir(parents=True,exist_ok=True)
        protected.write_text('must not overwrite')
        admin.api({'op':'config_update','patch':{'store_path':str(occupied)}},expected=409,mutation=True)
        assert protected.read_text()=='must not overwrite' and runtime.config['store_path']==str(newstore)
        record('live-store-migration-preserves-history-deliveries-and-failed-move-rollback')

        held=socket.socket();held.bind(('127.0.0.1',0));held.listen()
        try:
            admin.api({'op':'config_update','patch':{'port':held.getsockname()[1]}},expected=409,mutation=True)
        finally: held.close()
        newport=free_port()
        admin.api({'op':'config_update','patch':{'port':newport}},mutation=True)
        runtime.base='http://127.0.0.1:'+str(newport)
        assert admin.api({'op':'overview'})
        assert runtime.process.poll() is None and runtime.process.pid==pid
        record('live-listener-rebind-and-occupied-port-rollback-with-same-process')

        cfg=runtime.config;cfg['threshold_ppm']=812345
        tmp=runtime.root/'edited.json';tmp.write_text(json.dumps(cfg));tmp.chmod(0o600);tmp.replace(runtime.file)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if admin.api({'op':'config_get'})['config']['threshold_ppm']==812345:break
            time.sleep(.1)
        else:raise AssertionError('External configuration reload did not apply')
        bad={**runtime.config,'threshold_ppm':True}
        runtime.file.write_text(json.dumps(bad))
        time.sleep(.7)
        assert admin.api({'op':'config_get'})['config']['threshold_ppm']==812345
        tmp.write_text(json.dumps(cfg));tmp.chmod(0o600);tmp.replace(runtime.file);time.sleep(.7)
        record('atomic-external-file-reload-and-invalid-update-retains-last-good')

        oidc={'provider_id':'independent-provider','issuer':provider.issuer,'client_id':'independent-client',
              'client_secret':'fixture-client-secret','redirect_uri':runtime.base+'/admin/oidc/callback',
              'scopes':['openid','profile','email'],'groups_claim':'groups',
              'role_groups':{'Admin':['admins'],'Developer':['engineering'],'Viewer':['readers']},
              'default_role':None,'timeout_ms':3000}
        admin.api({'op':'test_oidc','settings':oidc})
        admin.api({'op':'config_update','patch':{'auth':{'mode':'both','oidc':oidc}}},mutation=True)
        for mode in ('normal','wrong-nonce','expired','wrong-issuer','wrong-audience','unknown-kid','tampered'):
            provider.mode=mode
            login=Client(runtime)
            status,_,_=login.get('/admin/oidc/start')
            _,session,_=login.get('/admin/session')
            if mode=='normal':
                assert session['authenticated'] and session['user']['role']=='Admin',session
                assert session['user']['name']=='Independent OIDC Person'
                assert session['user']['email']=='person@example.invalid'
                assert session['user']['oidc']['issuer']==provider.issuer
                assert session['user']['oidc']['subject']==provider.subject
                oidc_admin=login;oidc_admin.csrf=session['csrf'];oidc_id=session['user']['id']
                completed_callback=provider.last_callback
            else: assert not session.get('authenticated'),mode
        assert provider.exchanges>=7
        record('real-oidc-code-pkce-rsa-jwt-validation-and-highest-group-role')
        exchanges=provider.exchanges
        replay=Client(runtime)
        callback=urlsplit(completed_callback)
        status,_,_=replay.get(callback.path+'?'+callback.query)
        assert status>=400 and provider.exchanges==exchanges
        status,session,_=replay.get('/admin/session')
        assert status==200 and not session['authenticated']
        status,_,_=replay.get('/admin/oidc/callback?state=untrusted-state&code=untrusted-code')
        assert status>=400 and provider.exchanges==exchanges
        record('oidc-consumed-state-replay-and-missing-flow-cookie-rejected-before-exchange')
        provider.mode='normal'

        admin.api({'op':'config_update','patch':{'auth':{'mode':'oidc'}}},mutation=True)
        admin.api({'op':'overview'},expected=401)
        oidc_admin.api({'op':'config_update','patch':{'auth':{'oidc':{'role_groups':{
            'Admin':[],'Developer':['engineering'],'Viewer':['readers']}}}}},expected=409,mutation=True)
        assert runtime.config['auth']['mode']=='oidc'
        assert runtime.config['auth']['oidc']['role_groups']['Admin']==['admins']
        oidc_admin.api({'op':'config_update','patch':{'auth':{'mode':'both'}}},mutation=True)
        admin.api({'op':'overview'},expected=401)
        admin.login('admin',password)
        record('hot-oidc-only-mode-provider-session-revocation-and-last-admin-recovery')

        admin.api({'op':'config_update','patch':{'auth':{'oidc':{'role_groups':{
            'Admin':[],'Developer':['engineering'],'Viewer':['readers']}}}}},mutation=True)
        _,session,_=oidc_admin.get('/admin/session')
        assert session['user']['role']=='Developer' and session['user']['id']==oidc_id
        oidc_admin.api({'op':'config_get'},expected=403)
        record('live-oidc-group-mapping-demotion-is-server-local')

        link_admin=Client(runtime);link_admin.login('admin',password)
        link_admin.api({'op':'link_oidc','user_id':user['id'],
            'expected_revision':runtime.config['config_revision'],'confirm':True},expected=409)
        link_admin.api({'op':'link_oidc','user_id':dev['id'],
            'expected_revision':runtime.config['config_revision'],'confirm':True,
            'oidc':{'issuer':provider.issuer,'subject':'unproved'}},expected=400)
        def follow_link(expected):
            prepared=link_admin.api({'op':'link_oidc','user_id':dev['id'],
                'expected_revision':runtime.config['config_revision'],'confirm':True})
            try: response=link_admin.opener.open(prepared['authorization_url'],timeout=15)
            except HTTPError as e: response=e
            with response: assert response.status==expected,response.status
        # The already registered fixture identity cannot absorb a local account.
        follow_link(409)
        assert next(u for u in runtime.config['users'] if u['id']==dev['id'])['provider']=='local'
        provider.subject='new-linked-person'
        follow_link(200)
        _,linked,_=link_admin.get('/admin/session')
        assert linked['authenticated'] and linked['user']['id']==dev['id']
        assert linked['user']['role']=='Developer' and linked['user']['provider']=='oidc'
        assert linked['user']['oidc']['subject']=='new-linked-person'
        assert runtime.config['agent_owners']['developer-agent']==dev['id']
        developer.api({'op':'overview'},expected=401)
        again_linked=Client(runtime);again_linked.get('/admin/oidc/start')
        _,same,_=again_linked.get('/admin/session')
        assert same['user']['id']==dev['id'] and same['user']['role']=='Developer'
        provider.subject='fixture-person'
        record('explicit-oidc-link-proof-conflict-rejection-stable-id-role-and-agent-ownership')

        if multi:
            original_project=runtime.config['project_id']
            before=runtime.config
            status,error,_=admin.request('/admin/api',{'op':'config_update','patch':{'project_id':'renamed-project'},'expected_revision':before['config_revision'],'confirm':True,'message_id':uuid4().hex})
            assert status==404 and error['error']['code']=='PROJECT_NOT_FOUND'
            assert runtime.config==before
            registry=runtime.config['projects']
            renamed=[{**p,'name':'Renamed project display'} if p['id']==original_project else p for p in registry]
            admin.api({'op':'config_update','patch':{'projects':renamed}},mutation=True)
            assert developer.rpc({'op':'whoami'},token)['project_id']==original_project
            assert next(p for p in admin.api({'op':'list_projects'})['projects'] if p['id']==original_project)['name']=='Renamed project display'
        else:
            admin.api({'op':'config_update','patch':{'project_id':'renamed-project'}},mutation=True)
            assert developer.rpc({'op':'whoami'},token)['project_id']=='renamed-project'
        assert developer.rpc({'op':'get','publication_id':publication['id']},token)['publication']['id']==publication['id']
        runtime.stop(hard=True);runtime.start()
        assert (runtime.root/'initial-admin-password.txt').read_text()==original_password_file
        again=Client(runtime);assert again.login('admin',password)['id']==user['id']
        assert developer.rpc({'op':'publish','text':'Durable original across hot store moves.'},token,mid='before-store-move')['publication']==publication
        assert not any(d['id']==delivery['id'] for d in developer.rpc({'op':'poll'},token)['deliveries'])
        record('stable-project-id-display-rename-and-hard-restart-preserve-replay-and-acknowledgements' if multi else 'project-rename-and-hard-restart-preserve-identity-replay-and-acknowledgements')

        protected=again.api({'op':'config_get'})
        raw=json.dumps(protected)
        assert all(secret not in raw for secret in (password,devpass,viewpass,token,'fixture-client-secret','fixture-access-token'))
        for name in ('stdout.log','stderr.log'):
            log=(runtime.root/name).read_text()
            assert all(secret not in log for secret in (password,devpass,viewpass,token,'fixture-client-secret'))
        status,descriptor,_=again.get('/protocol');assert status==200 and descriptor['version']==args.protocol_version
        status,schema,_=again.get('/protocol/schema');assert status==200 and schema['$id']=='urn:adhd:protocol:'+(args.protocol_profile or str(args.protocol_version))
        assert len(schema.get('$defs',{}))>=10
        status,openapi,_=again.get('/protocol/openapi');assert status==200 and openapi['openapi']=='3.1.0'
        assert '/admin/login' in openapi['paths'] and '/admin/api' in openapi['paths']
        record('published-protocol-schema-openapi-and-secret-exclusion')

        # An authenticated session must lose access on logout; replaying the
        # previous CSRF token cannot restore its revoked cookie credential.
        old_csrf=again.csrf
        status,_,_=again.request('/admin/logout',{})
        assert status==200
        status,session,_=again.get('/admin/session')
        assert status==200 and not session['authenticated']
        again.csrf=old_csrf
        again.api({'op':'overview'},expected=401)
        record('logout-revokes-session-and-stale-csrf-cannot-authenticate')

        # Exercise independent username and whole-server limits without a
        # minute-long delay or a shared counter reset hidden inside the hub.
        limited=Client(runtime)
        results=[]
        for attempt in range(6):
            status,_,headers=limited.request('/admin/login',
                {'username':'limited-user','password':'incorrect-password'})
            results.append(status)
        assert results[:5]==[401]*5 and results[5]==429,results
        assert 1<=int(headers['Retry-After'])<=60
        server_limited=False
        for attempt in range(31):
            status,_,headers=limited.request('/admin/login',
                {'username':'missing-'+str(attempt),'password':'incorrect-password'})
            if status==429:
                assert 1<=int(headers['Retry-After'])<=60
                server_limited=True
                break
            assert status==401
        assert server_limited
        record('bounded-local-login-rate-limits-per-user-and-per-server')

        report={'schema':'adhd/foundation-acceptance@1','passed':True,'protocol_version':args.protocol_version,'cases':cases}
        if args.command:
            report['artifact_sha256']=hashlib.sha256(Path(json.loads(args.command)[-1]).read_bytes()).hexdigest()
            report['input_sha256']={Path(p).name:hashlib.sha256(Path(p).read_bytes()).hexdigest()
                                   for p in json.loads(args.command) if Path(p).is_file()}
        if args.image:
            report['image_id']=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',args.image],text=True).strip()
        Path(args.report).write_text(json.dumps(report,indent=2)+'\n')
    finally:
        runtime.stop();model.close();provider.close()

if __name__=='__main__':
    # Both bootstrap suites deliberately verify the documented default port.
    # Serialize that shared fixture when independent suites run concurrently.
    import fcntl
    lock_path=Path('_build/roadmap/foundation-port.lock');lock_path.parent.mkdir(parents=True,exist_ok=True)
    with lock_path.open('a') as port_lock:
        fcntl.flock(port_lock,fcntl.LOCK_EX)
        main()
