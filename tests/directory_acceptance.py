#!/usr/bin/env python3
"""Independent three-server catalog, identity isolation and canonical routing checks."""
import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
from email.utils import format_datetime
import json
from pathlib import Path
import secrets
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import tempfile
import time
from foundation_acceptance import Runtime, Client, Provider, free_port
from protocol_acceptance import ByteValidator
from federation_acceptance import Model, request as peer_request


def main():
    p=argparse.ArgumentParser(description=__doc__);runtime=p.add_mutually_exclusive_group(required=True)
    runtime.add_argument('--command');runtime.add_argument('--image')
    p.add_argument('--report',default='verification/directory-acceptance.json');args=p.parse_args()
    runtime_command=json.loads(args.command) if args.command else [];parent=Path('_build/roadmap/directory-tests').resolve();parent.mkdir(parents=True,exist_ok=True)
    root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));model=Model();hubs={};clients={};cases=[];schema=None;providers=[];fake_server=None;recovery_timing=None
    github={'provider':'github','host':'github.com','tenant':'foo','resource':'repo-123'}
    slack={'provider':'slack','host':'slack.com','tenant':'workspace-one','resource':'C001'}
    jira={'provider':'jira','host':'jira.example.invalid','tenant':'cloud-one','resource':'42'}
    def entry(scope,description,canonical=True,aliases=None):
        return {'scope':scope,'description':description,'canonical':canonical,'relationship':'contained','aliases':aliases or [],'export_publication_ids':[]}
    def record(name):cases.append({'case':name,'passed':True});print('PASS',name,flush=True)
    def wait(fn,description,seconds=20):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            value=fn()
            if value:return value
            time.sleep(.1)
        raise AssertionError(description)
    def validate(name,value):
        ByteValidator({'$defs':schema['$defs'],'$ref':'#/$defs/'+name}).validate(value)
    def rpc(name,body,mid=None):
        value=Client(hubs[name]).rpc(body,hubs[name].config['agents']['alice'],mid=mid)
        if schema:
            validate('agent_'+body['op'],body);validate('result_'+body['op'],value)
        return value
    def wire(name,body,origin='alpha',path='/federation/v1'):
        status,value=peer_request(hubs[name].base,path,body,tokens[origin,name])
        if path=='/federation/v1':
            validate('PeerV1Error' if status>=400 else 'PeerV1Result_'+('source' if body['op'].startswith('source_') else body['op']),value)
        return status,value

    def query(name,**fields):
        initial=rpc(name,{'op':'source_query','question':'Which source maintains image decoders?',**fields})['query']
        assert initial['status']=='pending'
        def read():
            value=rpc(name,{'op':'get_source_query','query_id':initial['id']})['query']
            return value if value['status']!='pending' else None
        return wait(read,'Source query did not terminate',35)
    def catalog_ready(name):
        v=rpc(name,{'op':'federation_directory'})
        return v if all(x['status']=='ready' for x in v['peers']) else None
    try:
        for name in ('alpha','beta','gamma'):
            r=Runtime(root/name,runtime_command,args.image);r.base='http://127.0.0.1:'+str(free_port());hubs[name]=r
        tokens={(a,b):secrets.token_urlsafe(32) for a in hubs for b in hubs if a!=b}
        entries={'alpha':[entry(slack,'We maintain image decoders in these Slack channels.',aliases=['general'])],
                 'beta':[entry(github,'We maintain image decoders for foo/baz.',aliases=['foo/baz'])],
                 'gamma':[entry(github,'A copy of image decoders evidence.',False,['foo/baz']),entry(jira,'We maintain financial reporting tools.',aliases=['OPS'])]}
        for name,r in hubs.items():
            config={'project_id':name,'port':int(r.base.rsplit(':',1)[1]),'store_path':str(r.root/'hub.dets'),
                'agents':{'alice':secrets.token_urlsafe(32),'bob':secrets.token_urlsafe(32)},
                'admin_token':secrets.token_urlsafe(32),'matcher':{'url':model.url,'model':'Nemotron-Deciffusion-8B-v2.1','timeout_ms':500,'retry_ms':100},
                'federation':{'description':'Independent '+name,'peers':[{'project_id':other,'url':hubs[other].base,
                    'token':tokens[name,other],'inbound_token':tokens[other,name]} for other in hubs if other!=name],
                    'timeout_ms':500,'retry_ms':100,'share_identities':True,'catalog':{'visible':True,'entries':entries[name]}}}
            r.file.write_text(json.dumps(config));r.file.chmod(0o600);r.start();clients[name]=Client(r,config['admin_token'])
        schema=clients['alpha'].get('/protocol/schema')[1]
        views={name:wait(lambda name=name:catalog_ready(name),'Initial catalog refresh failed for '+name) for name in hubs}
        server_ids={name:v['server_id'] for name,v in views.items()};assert len(set(server_ids.values()))==3
        for name,v in views.items():assert all(peer['server_id']==server_ids[peer['project_id']] for peer in v['peers'])
        record('three-authenticated-empty-or-populated-catalogs-with-stable-server-identities')
        roles={'alpha':'Admin','beta':'Viewer','gamma':'Developer'};users={}
        for name,admin in clients.items():
            u=admin.api({'op':'save_user','user':{'username':'same-person','name':'Same Person','email':'person@Example.invalid',
                'role':roles[name],'password':'same-person-independent-password'}},mutation=True)['user'];users[name]=u
            admin.api({'op':'config_update','patch':{'auth':{'mode':'local','allow_admin_token':True},'agent_owners':{'alice':u['id']}}},mutation=True)
        def all_matches():
            values={name:rpc(name,{'op':'identity_matches'}) for name in hubs}
            return values if all(len(v['matches'])==2 for v in values.values()) else None
        matches=wait(all_matches,'Same-email identities did not correlate')
        assert len({u['id'] for u in users.values()})==3
        for name,r in hubs.items():
            human=Client(r);u=human.login('same-person','same-person-independent-password');assert u['role']==roles[name]
            if name!='alpha':human.api({'op':'config_get'},expected=403)
            assert all('role' not in match and 'groups' not in match for match in matches[name]['matches'])
        record('same-email-correlates-distinct-users-with-independent-roles-and-agent-ownership')
        result=query('alpha',sources=[github]);assert result['status']=='completed',result
        answer=result['results'][0];assert answer['owner_project_id']=='beta' and answer['owner_server_id']==server_ids['beta']
        assert answer['response']['matched'] and answer['response']['scope']==github
        assert hubs['gamma'].config['project_id']=='gamma'
        record('source-question-dispatched-only-to-github-canonical-owner-with-provenance')
        result=query('alpha',aliases=[{'provider':'github','host':'github.com','tenant':'foo','alias':'FOO/BAZ'}]);assert result['status']=='completed',result
        assert result['results'][0]['owner_project_id']=='beta'
        result=query('alpha',sources=[slack,jira]);assert result['status']=='completed',result
        assert [r['owner_project_id'] for r in result['results']]==['alpha','gamma']
        assert [r['response']['matched'] for r in result['results']]==[True,False]
        record('aliases-and-multi-source-routing-select-local-slack-and-distinct-jira-owner')
        unknown={**github,'tenant':'different-tenant'};result=query('alpha',sources=[unknown])
        assert result['status']=='partial' and result['results'][0]['status']=='unknown',result
        record('tenant-collision-is-unknown-without-copy-fallback')
        gamma=hubs['gamma'];cat=gamma.config['federation']['catalog'];cat['entries'][0]['canonical']=True
        clients['gamma'].api({'op':'config_update','patch':{'federation':{'catalog':cat}}},mutation=True)
        wait(lambda:any(p['project_id']=='gamma' and any(e['scope']==github and e['canonical'] for e in p['catalog']) for p in rpc('alpha',{'op':'federation_directory'})['peers']),'Conflicting claim did not refresh')
        result=query('alpha',sources=[github]);assert result['status']=='partial' and result['results'][0]['status']=='conflict',result
        beta=hubs['beta'];cat=beta.config['federation']['catalog'];cat['entries'][0]['canonical']=False
        clients['beta'].api({'op':'config_update','patch':{'federation':{'catalog':cat}}},mutation=True)
        wait(lambda:any(p['project_id']=='beta' and all(not e['canonical'] for e in p['catalog']) for p in rpc('alpha',{'op':'federation_directory'})['peers']),'Old owner revocation did not refresh')
        result=query('alpha',sources=[github]);assert result['status']=='completed' and result['results'][0]['owner_project_id']=='gamma',result
        record('hot-conflict-detection-and-explicit-old-claim-revocation-before-ownership-transfer')
        previous=rpc('alpha',{'op':'federation_directory'})['server_id'];hubs['alpha'].stop(hard=True);hubs['alpha'].start()
        assert rpc('alpha',{'op':'federation_directory'})['server_id']==previous
        result=query('alpha',sources=[github]);assert result['status']=='completed' and result['results'][0]['owner_project_id']=='gamma',result
        record('server-identity-cache-and-canonical-routing-survive-hard-restart')
        hubs['beta'].stop()
        wait(lambda:any(p['project_id']=='beta' and p['status']=='unavailable' for p in rpc('alpha',{'op':'federation_directory'})['peers']),'Unrelated peer outage was not observed')
        result=query('alpha',sources=[github]);assert result['status']=='completed' and result['results'][0]['owner_project_id']=='gamma',result
        assert any(p['project_id']=='beta' and p['status']=='unavailable' for p in result['coverage'])
        hubs['beta'].start();wait(lambda:catalog_ready('alpha'),'Unrelated peer did not recover')
        record('established-fresh-owner-remains-available-with-explicit-incomplete-directory-coverage')
        # Durable source-job retries, owner isolation, cancellation and late replies.
        model.mode='slow'
        command={'op':'source_query','question':'Which source maintains image decoders?','sources':[github],'deadline_ms':30000}
        initial=rpc('alpha',command,mid='stable-source-create')['query']
        assert rpc('alpha',command,mid='stable-source-create')['query']==initial
        def raw_agent(body,agent='bob',mid='independent-forbidden-read'):
            envelope={'jsonrpc':'2.0','id':1,'method':'SendMessage','params':{'message':{
                'messageId':mid,'role':'ROLE_USER','parts':[{'data':body}]}}}
            return Client(hubs['alpha']).request('/a2a',envelope,{'Authorization':'Bearer '+hubs['alpha'].config['agents'][agent]})[1]
        denied=raw_agent({'op':'get_source_query','query_id':initial['id']});assert denied['error']['data'][0]['reason']=='FORBIDDEN'
        conflict=raw_agent({**command,'question':'Different question'},'alice','stable-source-create');assert conflict['error']['data'][0]['reason']=='IDEMPOTENCY_CONFLICT'
        cancelled=rpc('alpha',{'op':'cancel_source_query','query_id':initial['id']})['query'];assert cancelled['status']=='cancelled'
        hubs['alpha'].stop(hard=True);hubs['alpha'].start();model.mode='normal'
        assert rpc('alpha',{'op':'get_source_query','query_id':initial['id']})['query']['status']=='cancelled'
        # A restarted origin can still carry a transient unavailable observation.
        # Establish this fixture's ready-owner precondition before testing an
        # intentionally pending remote model job.
        wait(lambda:catalog_ready('alpha'),'Owner directory did not recover after origin restart')
        model.mode='error'
        # Two resource-constrained cold starts can consume a 30-second query.
        # Exercise recovery inside the protocol's existing 120-second limit;
        # deadline expiration is covered independently below.
        recovery_started=time.monotonic()
        pending=rpc('alpha',{**command,'deadline_ms':120000})['query']
        observed={'protocol_version':1,'op':'source_status','origin_project_id':'alpha','origin_server_id':server_ids['alpha'],
            'query_id':pending['id'],'scope':github}
        wait(lambda:wire('gamma',observed)[0]==200,'Pending remote source job not durably accepted')
        hubs['alpha'].stop(hard=True);hubs['gamma'].stop(hard=True);hubs['gamma'].start();hubs['alpha'].start()
        recovery_timing={'cold_recovery_ms':round((time.monotonic()-recovery_started)*1000),'requested_deadline_ms':120000}
        assert recovery_timing['cold_recovery_ms']<120000,recovery_timing
        model.mode='normal'
        recovered=wait(lambda:(v if (v:=rpc('alpha',{'op':'get_source_query','query_id':pending['id']})['query'])['status']!='pending' else None),'Source query failed to recover',35)
        assert recovered['status']=='completed',recovered
        record('source-job-dedup-owner-isolation-cancellation-late-results-and-two-process-restart')
        model.mode='slow';inflight=rpc('alpha',command)['query']
        observed['query_id']=inflight['id'];wait(lambda:wire('gamma',observed)[0]==200,'Revocation fixture not accepted')
        cat=hubs['gamma'].config['federation']['catalog'];cat['entries'][0]['canonical']=False
        clients['gamma'].api({'op':'config_update','patch':{'federation':{'catalog':cat}}},mutation=True)
        stopped=wait(lambda:(v if (v:=rpc('alpha',{'op':'get_source_query','query_id':inflight['id']})['query'])['status']!='pending' else None),'Revoked job did not terminate')
        assert stopped['status']=='partial' and stopped['results'][0]['status']=='revoked' and stopped['results'][0]['response'] is None,stopped
        cat=hubs['gamma'].config['federation']['catalog'];cat['entries'][0]['canonical']=True
        clients['gamma'].api({'op':'config_update','patch':{'federation':{'catalog':cat}}},mutation=True);model.mode='normal'
        assert rpc('alpha',{'op':'get_source_query','query_id':inflight['id']})['query']['status']=='partial'
        record('inflight-canonical-revocation-discards-late-results-and-never-resurrects-terminal-query')
        # Admins inspect/cancel through their own API, without using an agent credential.
        model.mode='error'
        pending_admin=rpc('alpha',command)['query']
        inspected=clients['alpha'].api({'op':'query_job','query_id':pending_admin['id']})
        validate('admin_result_query_job',inspected);assert inspected['kind']=='source' and inspected['query']['owner_id']=='alice'
        first_cancel={'op':'cancel_query_job','query_id':pending_admin['id'],'confirm':True,'message_id':'shared-product-id'}
        clients['alpha'].api(first_cancel)
        human_admin=Client(hubs['alpha']);human_admin.login('same-person','same-person-independent-password')
        another=rpc('alpha',command)['query'];second_cancel={**first_cancel,'query_id':another['id']}
        changed=human_admin.api(second_cancel);assert changed['query']['status']=='cancelled';assert human_admin.api(second_cancel)==changed
        human_admin.api({**second_cancel,'query_id':pending_admin['id']},expected=409)
        clients['alpha'].api({'op':'save_user','user':{'id':users['alpha']['id'],'name':'Same Person','email':'person@Example.invalid','role':'Viewer'}},mutation=True)
        human_admin.api(second_cancel,expected=403);human_admin.api({'op':'query_jobs'},expected=403)
        clients['alpha'].api({'op':'save_user','user':{'id':users['alpha']['id'],'name':'Same Person','email':'person@Example.invalid','role':'Admin'}},mutation=True)
        broad=rpc('alpha',{'op':'federated_query','question':'Which projects maintain image decoders?','deadline_ms':30000})['query']
        inspected=clients['alpha'].api({'op':'query_job','query_id':broad['id']});assert inspected['kind']=='discovery'
        clients['alpha'].api({'op':'cancel_query_job','query_id':broad['id'],'confirm':True,'message_id':'cancel-discovery'})
        assert rpc('alpha',{'op':'get_federated_query','query_id':broad['id']})['query']['status']=='cancelled'
        jobs=clients['alpha'].api({'op':'query_jobs','agent_id':'alice','limit':2});validate('admin_result_query_jobs',jobs)
        assert len(jobs['items'])==2 and jobs['truncated']
        model.mode='normal';record('admin-query-inspection-cancellation-actor-scoped-retries-and-demotion-before-replay')
        # Independent pagination client validates actual bodies and canonical revisions.
        cat=hubs['beta'].config['federation']['catalog']
        cat['entries']+= [entry({**github,'resource':'extra-'+str(i)},('Unicode λ / slash \"quoted\"\nline' if i==0 else 'Referenced source '+str(i)),False,['alias-'+str(i)]) for i in range(130)]
        clients['beta'].api({'op':'config_update','patch':{'federation':{'catalog':cat}}},mutation=True)
        command={'protocol_version':1,'op':'catalog','origin_project_id':'alpha'}
        status,first=wire('beta',command);assert status==200 and len(first['items'])==64
        rows=first['items'][:];cursor=first['next_cursor'];pages=1
        while cursor:
            status,page=wire('beta',{**command,'cursor':cursor});assert status==200 and page['revision']==first['revision']
            rows+=page['items'];cursor=page['next_cursor'];pages+=1
        canonical=json.dumps({'visible':True,'items':rows},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
        assert len(rows)==131 and pages==3 and hashlib.sha256(canonical).hexdigest()==first['revision']
        assert all('export_publication_ids' not in row for row in rows)
        changed=hubs['beta'].config['federation']['catalog'];changed['entries'][1]['description']='Changed metadata'
        clients['beta'].api({'op':'config_update','patch':{'federation':{'catalog':changed}}},mutation=True)
        status,value=wire('beta',{**command,'cursor':first['next_cursor']});assert status==409 and value['error']['code']=='SNAPSHOT_CHANGED'
        for malformed in ({**command,'extra':True},{**command,'protocol_version':True},{**command,'protocol_version':1.0},{**command,'cursor':'bad-cursor'}):
            status,value=wire('beta',malformed);assert status==400
        status,_=peer_request(hubs['beta'].base,'/federation/v1',command,hubs['beta'].config['agents']['alice']);assert status==401
        record('independent-paginated-wire-client-canonical-digest-stale-cursor-malformed-and-credential-checks')
        changed=hubs['beta'].config['federation']['catalog'];changed['entries'][1]['aliases']=['foo/baz']
        clients['beta'].api({'op':'config_update','patch':{'federation':{'catalog':changed}}},mutation=True)
        wait(lambda:any(p['project_id']=='beta' and len([e for e in p['catalog'] if 'foo/baz' in e['aliases']])==2 for p in rpc('alpha',{'op':'federation_directory'})['peers']),'Alias collision did not refresh')
        result=query('alpha',aliases=[{'provider':'github','host':'github.com','tenant':'foo','alias':'foo/baz'}])
        assert result['status']=='partial' and result['results'][0]['status']=='ambiguous',result
        record('colliding-aliases-remain-ambiguous-instead-of-selecting-a-convenient-owner')
        # An outage must not promote beta's noncanonical copy.
        hubs['gamma'].stop()
        result=query('alpha',sources=[github],deadline_ms=3000)
        assert result['status']=='partial' and result['results'][0]['status']=='unavailable',result
        hubs['gamma'].start();wait(lambda:catalog_ready('alpha'),'Owner did not recover')
        result=query('alpha',sources=[github]);assert result['status']=='completed',result
        record('owner-outage-and-expired-observations-never-fall-back-to-copy-holder')
        deadline=(datetime.now(timezone.utc)+timedelta(seconds=30)).isoformat(timespec='milliseconds').replace('+00:00','Z')
        gamma=hubs['gamma'];publication=rpc('gamma',{'op':'publish','text':'Approved evidence for this source.'})['publication']
        private=rpc('gamma',{'op':'send','recipient_id':'bob','text':'Never export this private addressed message.'})['delivery']
        cfg=gamma.config;cat=cfg['federation']['catalog'];cat['entries'][0]['export_publication_ids']=[publication['id']]
        clients['gamma'].api({'op':'config_update','patch':{'federation':{'catalog':cat,'description':'We maintain image decoders.','export_publication_ids':[publication['id']]}}},mutation=True)
        status,metadata=wire('gamma',{'protocol_version':1,'op':'catalog','origin_project_id':'alpha'});assert status==200
        assert publication['text'] not in json.dumps(metadata) and private['text'] not in json.dumps(metadata)
        source={'protocol_version':1,'op':'source_submit','origin_project_id':'alpha','origin_server_id':server_ids['alpha'],
            'query_id':'independent-source-policy','scope':github,'question':'Who maintains image decoders?','deadline_at':deadline,
            'owner_server_id':server_ids['gamma'],'catalog_revision':metadata['revision']}
        status,_=wire('gamma',source);assert status==202
        status_command={k:source[k] for k in ('protocol_version','origin_project_id','origin_server_id','query_id','scope')};status_command['op']='source_status'
        answer=wait(lambda:(v if (v:=wire('gamma',status_command)[1])['status']=='completed' else None),'Source evidence never completed')
        assert answer['response']['publications'][0]['id']==publication['id']
        legacy={'op':'submit','origin_project_id':'alpha','query_id':'independent-legacy-policy','question':'Who maintains image decoders?','deadline_at':deadline}
        assert wire('gamma',legacy,path='/federation')[0]==202
        legacy_status={k:legacy[k] for k in ('origin_project_id','query_id')};legacy_status['op']='status'
        old=wait(lambda:(v if (v:=wire('gamma',legacy_status,path='/federation')[1])['status']=='completed' else None),'Legacy evidence never completed')
        assert old['response']['publications'][0]['id']==publication['id']
        cat=gamma.config['federation']['catalog'];cat['entries'][0]['export_publication_ids']=[]
        clients['gamma'].api({'op':'config_update','patch':{'federation':{'catalog':cat,'export_publication_ids':[]}}},mutation=True)
        status,revoked=wire('gamma',status_command);assert status==200 and revoked['status']=='revoked' and 'response' not in revoked
        status,revoked=wire('gamma',legacy_status,path='/federation');assert status==403 and publication['text'] not in json.dumps(revoked)
        record('metadata-privacy-and-live-evidence-revocation-block-previous-source-and-legacy-results')
        # Distinct proved OIDC providers correlate by email without copying their roles.
        oidc_users={}
        for name,role in (('alpha','Admin'),('beta','Viewer')):
            provider=Provider(root);providers.append(provider)
            groups={'Admin':[],'Developer':[],'Viewer':[]};groups[role]=['admins']
            settings={'provider_id':'provider-'+name,'issuer':provider.issuer,'client_id':'independent-client',
                'client_secret':'fixture-client-secret','redirect_uri':hubs[name].base+'/admin/oidc/callback',
                'scopes':['openid','profile','email'],'groups_claim':'groups','role_groups':groups,'default_role':None,'timeout_ms':3000}
            clients[name].api({'op':'config_update','patch':{'auth':{'mode':'both','allow_admin_token':True,'oidc':settings}}},mutation=True)
            human=Client(hubs[name]);human.get('/admin/oidc/start');_,session,_=human.get('/admin/session')
            assert session['authenticated'] and session['user']['role']==role;oidc_users[name]=session['user']
        clients['alpha'].api({'op':'config_update','patch':{'agent_owners':{'alice':oidc_users['alpha']['id']}}},mutation=True)
        def oidc_matches():
            value=rpc('alpha',{'op':'identity_matches'})
            return value if any(m['user_id']==oidc_users['beta']['id'] for m in value['matches']) else None
        found=wait(oidc_matches,'Proved OIDC profiles did not correlate')
        assert oidc_users['alpha']['oidc']['issuer']!=oidc_users['beta']['oidc']['issuer']
        assert all('role' not in m and 'oidc' not in m and 'groups' not in m for m in found['matches'])
        record('same-email-correlates-proved-distinct-oidc-providers-with-server-local-roles')
        # Turn the mesh into a chain; cached profiles/roles must never relay.
        for name,removed in (('alpha','gamma'),('gamma','alpha')):
            peer_list=[p for p in hubs[name].config['federation']['peers'] if p['project_id']!=removed]
            clients[name].api({'op':'config_update','patch':{'federation':{'peers':peer_list}}},mutation=True)
        found=rpc('alpha',{'op':'identity_matches'});assert all(m['project_id']=='beta' for m in found['matches'])
        clients['alpha'].api({'op':'save_user','user':{'id':users['alpha']['id'],'name':'Same Person',
            'email':'person@Example.invalid','role':'Viewer'}},mutation=True)
        for name in ('beta','gamma'):
            assert next(u for u in hubs[name].config['users'] if u['id']==users[name]['id'])['role']==roles[name]
        assert len(rpc('alpha',{'op':'federation_directory'})['peers'])==1
        record('three-server-chain-never-relays-user-profiles-roles-or-agent-ownership')
        # A separately authored peer cannot turn an identity assertion into a role.
        rate_scope={'provider':'jira','host':'rate.example','tenant':'rate-site','resource':'rate-resource'}
        fake_mode={'role_injection':True,'retry_after':'2','submissions':[],'server_id':'d'*32};fake_token=secrets.token_urlsafe(32)
        class Peer(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert self.headers.get('Authorization')=='Bearer '+fake_token
                if body['op'].startswith('source_'):
                    validate('PeerV1_'+body['op'],body);fake_mode['submissions'].append(time.monotonic())
                    raw=json.dumps({'protocol_version':1,'error':{'code':'RESOURCE_EXHAUSTED','message':'Busy'}}).encode()
                    self.send_response(429);self.send_header('Content-Type','application/json');self.send_header('Retry-After',fake_mode['retry_after']);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
                items=[{k:v for k,v in entry(rate_scope,'Rate-limited canonical source.').items() if k!='export_publication_ids'}]
                if body['op']=='identities':
                    person={'user_id':'external-person','name':'Claimed Person','email':'person@example.invalid'}
                    if fake_mode['role_injection']:person['role']='Admin'
                    items=[person]
                snapshot={'visible':True,'items':items}
                digest=hashlib.sha256(json.dumps(snapshot,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
                value={'protocol_version':1,'server_id':fake_mode['server_id'],'project_id':'delta','revision':digest,
                    'generated_at':datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z'),
                    'max_age_ms':10000,'visible':True,'items':items,'next_cursor':None}
                raw=json.dumps(value).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        fake_server=ThreadingHTTPServer(('127.0.0.1',0),Peer);threading.Thread(target=fake_server.serve_forever,daemon=True).start()
        peer_list=hubs['alpha'].config['federation']['peers']+[{'project_id':'delta','url':'http://127.0.0.1:'+str(fake_server.server_port),
            'token':fake_token,'inbound_token':secrets.token_urlsafe(32)}]
        clients['alpha'].api({'op':'config_update','patch':{'federation':{'peers':peer_list}}},mutation=True)
        wait(lambda:any(p['project_id']=='delta' and p['status']=='unavailable' for p in rpc('alpha',{'op':'federation_directory'})['peers']),'Remote role assertion was not rejected')
        assert all(m['project_id']!='delta' for m in rpc('alpha',{'op':'identity_matches'})['matches'])
        fake_mode['role_injection']=False
        wait(lambda:any(m['project_id']=='delta' for m in rpc('alpha',{'op':'identity_matches'})['matches']),'Valid minimal identity snapshot was not accepted')
        human=Client(hubs['alpha']);assert human.login('same-person','same-person-independent-password')['role']=='Viewer'
        human.api({'op':'config_get'},expected=403)
        record('independent-peer-role-assertions-rejected-and-valid-correlation-grants-no-local-access')
        wait(lambda:catalog_ready('alpha'),'Rate-limited peer catalog not ready')
        for hint in ('2',format_datetime(datetime.now(timezone.utc)+timedelta(seconds=8),usegmt=True),'invalid-unbounded'):
            fake_mode['retry_after']=hint;before=len(fake_mode['submissions'])
            result=query('alpha',sources=[rate_scope],deadline_ms=3000 if hint=='invalid-unbounded' else 1000)
            assert result['status']=='partial' and result['results'][0]['status']=='unavailable',result
            attempts=len(fake_mode['submissions'])-before
            if hint!='invalid-unbounded':assert attempts==1,(hint,attempts)
            else:assert attempts>=2,(hint,attempts)
            start=time.monotonic();rpc('alpha',{'op':'publish','text':'Local traffic remains responsive during peer rate limits.'});assert time.monotonic()-start<1
        record('retry-after-seconds-http-date-and-invalid-hints-respect-deadline-and-local-responsiveness')
        # Replacing a peer requires explicit membership changes, even with its old token.
        fake_mode['server_id']='e'*32
        wait(lambda:any(p['project_id']=='delta' and p['status']=='identity_conflict' for p in rpc('alpha',{'op':'federation_directory'})['peers']),'Changed server ID was silently adopted')
        assert all(m['project_id']!='delta' for m in rpc('alpha',{'op':'identity_matches'})['matches'])
        current_peers=hubs['alpha'].config['federation']['peers'];without_delta=[p for p in current_peers if p['project_id']!='delta']
        clients['alpha'].api({'op':'config_update','patch':{'federation':{'peers':without_delta}}},mutation=True)
        clients['alpha'].api({'op':'config_update','patch':{'federation':{'peers':current_peers}}},mutation=True)
        wait(lambda:any(p['project_id']=='delta' and p['status']=='ready' and p['server_id']=='e'*32 for p in rpc('alpha',{'op':'federation_directory'})['peers']),'Explicit peer replacement did not reset pin')
        record('pinned-server-replacement-fails-closed-until-explicit-committed-remove-and-readd')
        clients['alpha'].api({'op':'config_update','patch':{'federation':{'peers':without_delta}}},mutation=True)
        fake_mode['server_id']=server_ids['beta']
        clients['alpha'].api({'op':'config_update','patch':{'federation':{'peers':current_peers}}},mutation=True)
        wait(lambda:all(p['status']=='identity_conflict' for p in rpc('alpha',{'op':'federation_directory'})['peers']),'Duplicate UUIDs were treated as separate trusted servers')
        assert rpc('alpha',{'op':'identity_matches'})['matches']==[]
        clients['alpha'].api({'op':'config_update','patch':{'federation':{'peers':without_delta}}},mutation=True)
        wait(lambda:catalog_ready('alpha'),'Original peer did not recover after duplicate removal')
        record('duplicate-server-identities-quarantine-both-directory-observations-with-explicit-recovery')
        serialized=json.dumps(model.states)
        assert private['text'] not in serialized
        assert all(token not in serialized for token in tokens.values())
        record('model-context-excludes-private-deliveries-peer-credentials-and-user-role-assertions')
        Path(args.report).write_text(json.dumps({'schema':'adhd/directory-acceptance@1','passed':True,'cases':cases,'two_server_restart':recovery_timing,
            **({'image':args.image,'image_id':subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',args.image],text=True).strip()} if args.image else {'artifact_sha256':hashlib.sha256(Path(runtime_command[-1]).read_bytes()).hexdigest()})},indent=2)+'\n')
    finally:
        for r in hubs.values():r.stop()
        if fake_server:fake_server.shutdown();fake_server.server_close()
        for provider in providers:provider.close()
        model.close()


if __name__=='__main__':main()
