#!/usr/bin/env python3
"""Independent original-evidence, frozen context and legacy upgrade checks."""
import argparse,hashlib,json,secrets,tempfile,subprocess,time
from pathlib import Path
from uuid import uuid4
from foundation_acceptance import Runtime,Client,ModelFixture,free_port
from protocol_acceptance import ByteValidator


def main():
    p=argparse.ArgumentParser(description=__doc__);rt=p.add_mutually_exclusive_group(required=True);rt.add_argument('--command');rt.add_argument('--image')
    p.add_argument('--legacy-command',action='append',default=[]);p.add_argument('--report',default='verification/context-acceptance.json')
    args=p.parse_args();command=json.loads(args.command) if args.command else [];parent=Path('_build/roadmap/context-tests').resolve();parent.mkdir(parents=True,exist_ok=True)
    root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));model=ModelFixture();hubs=[];cases=[]
    def record(name):cases.append({'case':name,'passed':True});print('PASS',name,flush=True)
    def runtime(name,cmd,native=False):
        r=Runtime(root/name,cmd,None if native else args.image);r.file.write_text(json.dumps({'project_id':'context-fixture','port':free_port(),
            'store_path':str(r.root/'hub.dets'),'agents':{'alice':secrets.token_urlsafe(32),'bob':secrets.token_urlsafe(32)},
            'admin_token':secrets.token_urlsafe(32),'matcher':{'url':model.url,'model':'Nemotron-Deciffusion-8B-v2.1','timeout_ms':500,'retry_ms':100}}));r.file.chmod(0o600);hubs.append(r);r.start();return r
    try:
        r=runtime('current',command);client=Client(r);schema=client.get('/protocol/schema')[1]
        def valid(name,value):ByteValidator({'$defs':schema['$defs'],'$ref':'#/$defs/'+name}).validate(value)
        def rpc(cmd,mid=None):
            valid('agent_'+cmd['op'],cmd);v=client.rpc(cmd,r.config['agents']['alice'],mid=mid);valid('result_'+cmd['op'],v);return v
        def reject(cmd,expected):
            body={'jsonrpc':'2.0','id':1,'method':'SendMessage','params':{'message':{'messageId':uuid4().hex,'role':'ROLE_USER','parts':[{'data':cmd}]}}}
            status,value,_=client.request('/a2a',body,{'Authorization':'Bearer '+r.config['agents']['alice']})
            assert status==200 and 'error' in value,(status,value)
            actual='INVALID_PARAMS' if value['error']['code']==-32602 else value['error'].get('data',[{}])[0].get('metadata',{}).get('code')
            assert actual==expected,(status,value)
        def publish(text,context=None,**extra):
            cmd={'op':'publish_record','text':text,**extra}
            if context is not None:cmd['context']=context
            return rpc(cmd)['record']
        original=publish('Yes',{'question':'Is there a bird in that tree?','subject':'tree-1','conversation':'walk-1'},data={'arbitrary':['λ',None,True,3.5]})
        oid=original['publication']['id'];assert original['publication']['text']=='Yes' and original['publication']['data']=={'arbitrary':['λ',None,True,3.5]}
        assert original['context']['question']=='Is there a bird in that tree?'
        digest=hashlib.sha256(json.dumps({'context':original['context'],'links':original['links']},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        assert original['context_identity']==digest
        old=rpc({'op':'get_record','publication_id':oid});mark=old['snapshot']['watermark']
        species=publish('I see a cardinal in that tree.',{'subject':'tree-1','links':[{'relation':'supports','publication_id':oid}]})
        color=publish('There is a red bird on the branch.',{'subject':'tree-1','task':'look-1'})
        corrected=publish('Actually, that was a leaf.',{'subject':'tree-1','links':[{'relation':'corrects','publication_id':species['publication']['id']}]})
        expanded=rpc({'op':'get_record','publication_id':oid})
        assert {v['publication']['text'] for v in expanded['related']}=={species['publication']['text'],color['publication']['text'],corrected['publication']['text']}
        assert expanded['record']==original and rpc({'op':'get_record','publication_id':oid,'watermark':mark})==old
        assert rpc({'op':'get','publication_id':oid})['publication']==original['publication']
        record('verbatim-yes-question-referent-cardinal-color-correction-and-frozen-history')
        command_event={'op':'publish_record','text':'Source observation','context':{'subject':'unknown-new-concept','links':[{'relation':'related','publication_id':oid}]},'source':{'kind':'slack','id':'channel-1','item_id':'event-1'}}
        first=rpc(command_event,mid='context-event-once');assert rpc(command_event,mid='context-event-retry')==first
        reject({**command_event,'context':{'subject':'changed'}},'SOURCE_CONFLICT')
        cross={'op':'publish','text':'Cross-operation observation','source':{'kind':'email','id':'mail','item_id':'cross-event'}}
        plain=rpc(cross);wrapped=rpc({**cross,'op':'publish_record'});assert wrapped['record']['publication']==plain['publication'] and wrapped['record']['context'] is None
        assert rpc(cross)==plain
        record('context-source-dedup-and-compatible-cross-operation-retries')
        private=rpc({'op':'send','recipient_id':'bob','text':'PRIVATE CONTEXT MUST NEVER EXPAND'})['delivery']['id']
        unres=publish('References are claims',{'links':[{'relation':'reply','publication_id':private},{'relation':'related','publication_id':'missing-record'}],
            'external':[{'uri':'https://archive.example.invalid/changing'}]})
        view=rpc({'op':'get_record','publication_id':unres['publication']['id']})
        assert not view['related'] and [x['reason'] for x in view['gaps']]==['unresolved','unresolved','missing_snapshot']
        assert all(link['target_identity'] is None for link in unres['links']) and 'PRIVATE CONTEXT' not in json.dumps(view)
        reject({'op':'get_record','publication_id':private},'NOT_FOUND');reject({'op':'get_record','publication_id':'missing-record'},'NOT_FOUND')
        # Test-only prediction creates an actual later target for this immutability
        # check. Clients still treat IDs as opaque. Modern allocation is separate
        # from the publication watermark and includes private/administrative IDs.
        if Path(str(r.file)+'.stores').exists():
            from project_recovery_state import route,snapshot
            state=snapshot(str(route(r.file,r.config['project_id'])[1])+'.snapshot')
            def future_id(number):
                encoded=''
                while number:
                    number,digit=divmod(number,36);encoded='0123456789abcdefghijklmnopqrstuvwxyz'[digit]+encoded
                return 'publication_'+state['allocation_epoch']+'_'+encoded
            # Index generations also allocate IDs asynchronously. Cover a bounded
            # future range, then require an actual later publication to occupy it.
            futures=[future_id(state['allocation_counter']+offset) for offset in range(1,17)]
        else:
            current=rpc({'op':'get_record','publication_id':oid})['snapshot']['watermark'];futures=[oid.rsplit('-',1)[0]+'-'+str(current+3)]
        waiting=publish('Unresolved when accepted',{'links':[{'relation':'reply','publication_id':future} for future in futures]})
        publish('Filler');later=publish('This arrived later');assert later['publication']['id'] in futures
        frozen=rpc({'op':'get_record','publication_id':waiting['publication']['id']});assert all(link['target_identity'] is None for link in frozen['record']['links']) and not frozen['related']
        record('private-absent-and-future-references-remain-unresolved-without-leaking-content')
        truncated=rpc({'op':'get_record','publication_id':oid,'max_depth':0});assert not truncated['related'] and truncated['truncated'] and any(g['reason']=='depth' for g in truncated['gaps'])
        limited=rpc({'op':'get_record','publication_id':oid,'limit':2});assert len(limited['related'])==1 and limited['truncated'] and any(g['reason']=='limit' for g in limited['gaps'])
        assert any(g['reason']=='cycle' for g in expanded['gaps'])
        reject({'op':'get_record','publication_id':later['publication']['id'],'watermark':mark},'NOT_FOUND')
        reject({'op':'get_record','publication_id':oid,'watermark':9007199254740991},'INVALID_PARAMS')
        record('bounded-deterministic-traversal-gaps-cycles-and-publication-watermarks')
        snapshot='Immutable external words: λ';sha=hashlib.sha256(snapshot.encode()).hexdigest()
        ext=publish('External evidence',{'external':[{'uri':'https://archive.example.invalid/snapshot','snapshot':snapshot,'sha256':sha}]})
        assert not rpc({'op':'get_record','publication_id':ext['publication']['id']})['gaps']
        bad=[{'context':None},{'context':{'fact_taxonomy':True}},{'context':{'links':[{'relation':'truth','publication_id':oid}]}},
             {'context':{'question':'λ'*2049}},{'context':{'external':[{'uri':'https://user:pass@example.invalid'}]}},
             {'context':{'external':[{'uri':'https://archive.example.invalid','snapshot':snapshot,'sha256':'0'*64}]}},
             {'context':{'external':[{'uri':'https://archive.example.invalid','sha256':sha}]}}]
        for fields in bad:reject({'op':'publish_record','text':'Invalid',**fields},'INVALID_PARAMS')
        for field,value in [('limit',True),('watermark',1.0),('max_depth',5)]:reject({'op':'get_record','publication_id':oid,field:value},'INVALID_PARAMS')
        record('external-snapshot-hashes-byte-bounds-unknown-fields-and-integer-token-rejection')
        admin=Client(r,r.config['admin_token']);assert admin.api({'op':'record','publication_id':oid,'watermark':mark})==old
        r.stop(hard=True);r.start();client=Client(r)
        assert rpc({'op':'get_record','publication_id':oid,'watermark':mark})==old
        assert rpc(command_event,mid='context-event-once')==first
        restarted=rpc({'op':'get_record','publication_id':waiting['publication']['id']})
        assert restarted==frozen
        assert rpc({'op':'search','query':'cardinal'})['publications'][0]['text']==species['publication']['text']
        record('hard-restart-keeps-record-identities-context-retries-unresolved-links-and-literal-search')
        # Acknowledgement and retries cannot delete original contextual evidence.
        sub=rpc({'op':'subscribe','description':'Observe immutable context records'})['subscription']
        event={'op':'publish_record','text':'Observation after subscription','context':{'question':'Is it observable?','subject':'ack-context'},'source':{'kind':'email','id':'ack-origin','item_id':'ack-event'}}
        observed=rpc(event)['record'];deadline=time.monotonic()+15;deliveries=[]
        while time.monotonic()<deadline:
            deliveries=rpc({'op':'poll'})['deliveries']
            if deliveries:break
            time.sleep(.1)
        assert len(deliveries)==1 and deliveries[0]['publication_id']==observed['publication']['id']
        rpc({'op':'ack','delivery_ids':[deliveries[0]['id']]});rpc(event)
        assert rpc({'op':'poll'})['deliveries']==[] and rpc({'op':'get_record','publication_id':observed['publication']['id']})['record']==observed
        rpc({'op':'unsubscribe','subscription_id':sub['id']})
        record('acknowledgement-and-source-retries-retain-original-context-without-redelivery')

        for index,legacy in enumerate(args.legacy_command):
            oldr=runtime('legacy-'+str(index),json.loads(legacy),native=True);oldclient=Client(oldr)
            publication=oldclient.rpc({'op':'publish','text':'Legacy observation'},oldr.config['agents']['alice'])['publication'];pid=publication['id']
            oldr.stop(hard=True);oldr.command=command;oldr.image=args.image;oldr.start();newclient=Client(oldr)
            upgraded=newclient.rpc({'op':'get_record','publication_id':pid},oldr.config['agents']['alice'])
            assert upgraded['record']['publication']['text']=='Legacy observation' and upgraded['record']['context'] is None and upgraded['record']['links']==[]
            oldr.stop(hard=True);oldr.start();assert newclient.rpc({'op':'get_record','publication_id':pid},oldr.config['agents']['alice'])==upgraded
        if args.legacy_command:record('actual-store-producers-preserve-evidence-through-upgrade-and-restart')
        Path(args.report).write_text(json.dumps({'schema':'adhd/context-acceptance@1','upgrade_producer_sha256':[hashlib.sha256(Path(json.loads(cmd)[-1]).read_bytes()).hexdigest() for cmd in args.legacy_command],'passed':True,'cases':cases,**({'image_id':subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',args.image],text=True).strip()} if args.image else {'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest()})},indent=2)+'\n')
    finally:
        for r in hubs:r.stop()
        model.close()


if __name__=='__main__':main()
