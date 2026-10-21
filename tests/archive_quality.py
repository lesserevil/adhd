#!/usr/bin/env python3
"""Real Nemotron archive intent/support tests with independently authored expectations."""
import argparse,hashlib,json,tempfile,time
from pathlib import Path
import jsonschema
from federation_acceptance import Hub,request
from protocol_acceptance import ByteValidator

def main():
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--command');mode.add_argument('--image')
    parser.add_argument('--matcher-url',default='http://127.0.0.1:18770/v1/systemone');parser.add_argument('--report',default='verification/archive-quality.json');args=parser.parse_args()
    command=json.loads(args.command) if args.command else [];Hub.image=args.image
    parent=Path('_build/roadmap/archive-quality').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent))
    hub=Hub(command,root/'hub','archive-quality',args.matcher_url);hub.config.pop('federation');hub.config['archive']={'audit_rate_ppm':0};cases=[]
    def wait(fn):
        end=time.monotonic()+45
        while time.monotonic()<end:
            if value:=fn():return value
            time.sleep(.05)
        raise AssertionError('Real archive query deadline')
    def update(patch):
        revision=json.loads((hub.root/'config.json').read_text()).get('config_revision',1)
        status,value=request(hub.base,'/admin/api',{'op':'config_update','patch':patch,'expected_revision':revision,'message_id':'quality-'+str(time.time_ns()),'confirm':True},hub.config['admin_token'])
        assert status==200,value
    def run(case):
        kind='archive-quality-'+str(len(cases));ids=[]
        for source in case['records']:
            source=json.loads(json.dumps(source))
            for link in source.get('context',{}).get('links',[]):
                if link['publication_id'].startswith('$'):link['publication_id']=ids[int(link['publication_id'][1:])]
            ids.append(hub.call({'op':'publish_record','information_type':kind,**source})['record']['publication']['id'])
        wait(lambda:hub.call({'op':'retrieval_index'})['index']['status']=='ready')
        q=hub.call({'op':'query_archive','question':case['question'],'scope':{'information_type':kind},**case.get('options',{})})['query']
        q=wait(lambda:v if (v:=hub.call({'op':'get_archive_query','query_id':q['id']})['query'])['status']!='pending' else None)
        (root/(case['case']+'.json')).write_text(json.dumps(q,indent=2)+'\n')
        ByteValidator({'$defs':schema['$defs'],'$ref':'#/$defs/ArchiveQuery'},format_checker=jsonschema.FormatChecker()).validate(q)
        assert q['status']=='completed',(case['case'],q['error']);assert q['outcome'] in case['expected'],(case['case'],q['outcome'],case['expected'])
        if case.get('full'):assert q['coverage']['full_scope_evaluated'],case['case']
        if case.get('path'):assert case['path'] in q['path'],(case['case'],q['path'])
        if case.get('support'):assert set(ids)&set(q['answer']['support_ids']),case['case']
        assert 'PRIVATE_ARCHIVE_SENTINEL' not in json.dumps(q)
        value={'case':case['case'],'cohort':case['cohort'],'expected_outcomes':case['expected'],'outcome':q['outcome'],'path':q['path'],'intent':q['intent'],'full_scope_evaluated':q['coverage']['full_scope_evaluated'],'sample':q['sample'],'usage':q['usage'],'passed':True}
        cases.append(value);print('PASS',case['case'],q['path'],q['outcome'],flush=True);return q
    try:
        hub.start();schema=request(hub.base,'/protocol/schema')[1]
        hub.call({'op':'send','recipient_id':'bob','text':'PRIVATE_ARCHIVE_SENTINEL'})
        fixtures=[
            {'case':'paraphrased-cause','cohort':'development','question':'How did the gateway recover?','records':[{'text':'Restarting the router restored the gateway connection.'}],'expected':['direct'],'support':True},
            {'case':'explicit-negation','cohort':'development','question':'Was module R approved?','records':[{'text':'Module R was not approved.'}],'expected':['direct'],'support':True},
            {'case':'contextual-answer','cohort':'development','question':'Was package T delivered?','records':[{'text':'Yes','context':{'question':'Did package T reach the laboratory?'}}],'expected':['direct'],'support':True},
            {'case':'all-reports','cohort':'development','question':'List all recorded sample results.','records':[{'text':'Sample Q passed.'},{'text':'Sample R failed.'}],'expected':['direct'],'full':True,'path':'scan','support':True},
            {'case':'irrelevant-corpus','cohort':'development','question':'Who repaired the observatory telescope?','records':[{'text':'The cafeteria served lentil soup.'}],'expected':['no_evidence','insufficient'],'full':True,'path':'scan'},
            {'case':'held-synonym','cohort':'previously-observed-held-out','question':'What restored the water supply?','records':[{'text':'Replacing the faulty pump brought running water back.'}],'expected':['direct'],'support':True},
            {'case':'held-context-negative','cohort':'previously-observed-held-out','question':'Was the expedition delayed?','records':[{'text':'No','context':{'question':'Was the expedition delayed?','subject':'expedition-Y'}}],'expected':['direct'],'support':True},
            {'case':'held-missing-detail','cohort':'previously-observed-held-out','question':'What color was the inspected vessel?','records':[{'text':'A vessel passed the inspection station.'}],'expected':['insufficient','no_evidence'],'full':True,'path':'scan'},
            {'case':'held-repeated-sighting-count','cohort':'previously-observed-held-out','question':'How many distinct drones were reported?','records':[{'text':'A drone hovered above the pier.'},{'text':'A drone was seen above the same pier.'}],'expected':['insufficient'],'full':True,'path':'scan'},
            {'case':'held-explicit-complete','cohort':'previously-observed-held-out','question':'Which parcel was damaged?','records':[{'text':'Parcel V was damaged during transport.'}],'options':{'complete':True},'expected':['direct'],'full':True,'path':'scan','support':True},
        ]
        for case in fixtures:run(case)
        # Disable only semantic retrieval. The primary scan must recover an
        # independently worded cause whose words do not occur in the query.
        update({'retrieval':{'recipe':{'semantic':False}}})
        recovered=run({'case':'lexical-miss-full-scan-recovery','cohort':'fallback-regression','question':'How was connectivity restored?','records':[{'text':'Replacing the broken switch brought network access back.'}],'expected':['direct'],'full':True,'path':'scan','support':True})
        assert 'no_candidates' in recovered['fallback_reasons']
        update({'retrieval':{'recipe':{'semantic':True}},'archive':{'audit_rate_ppm':1000000}})
        audited=run({'case':'real-successful-search-audited','cohort':'audit-regression','question':'Who approved shipment Z?','records':[{'text':'Mira approved shipment Z.'}],'expected':['direct'],'full':True,'path':'audit','support':True})
        assert audited['sample']['selected'] and audited['comparison']['completed_scope']
        # A later correction is a distinct immutable source and full coverage
        # preserves the contradiction instead of declaring either statement true.
        update({'archive':{'audit_rate_ppm':0}})
        run({'case':'later-correction-full-coverage','cohort':'context-regression','question':"Was team Amber or team Indigo reported as package G's owner?",'records':[{'text':'Package G belongs to team Amber.','context':{'subject':'package-G'}},{'text':'Correction: package G belongs to team Indigo, not team Amber.','context':{'subject':'package-G','links':[{'relation':'corrects','publication_id':'$0'}]}}],'options':{'complete':True},'expected':['conflicting'],'full':True,'path':'scan','support':True})
        fresh_held=[
            {'case':'fresh-held-power','cohort':'previously-observed-held-out','question':'What brought electrical power back?','records':[{'text':'Resetting the circuit breaker restored electricity.'}],'expected':['direct'],'support':True},
            {'case':'fresh-held-authorization','cohort':'previously-observed-held-out','question':'Was voyage C authorized?','records':[{'text':'Voyage C was not authorized.'}],'expected':['direct'],'support':True},
            {'case':'fresh-held-recorded-yes','cohort':'previously-observed-held-out','question':'Was capsule W recovered?','records':[{'text':'Yes','context':{'question':'Was capsule W recovered?'}}],'expected':['direct'],'support':True},
            {'case':'fresh-held-unreported-distance','cohort':'previously-observed-held-out','question':'What distance was measured?','records':[{'text':'Observers watched the test launch.'}],'expected':['insufficient','no_evidence'],'full':True,'path':'scan'},
            {'case':'fresh-held-nonindependent-boats','cohort':'previously-observed-held-out','question':'How many distinct boats passed?','records':[{'text':'A boat passed the buoy.'},{'text':'A boat was observed near the same buoy.'}],'expected':['insufficient'],'full':True,'path':'scan'},
            {'case':'fresh-held-missing-id','cohort':'previously-observed-held-out','question':'Who approved inspection ZZ-14?','records':[{'text':'Dana approved inspection ZZ-15.'}],'expected':['insufficient','no_evidence'],'full':True,'path':'scan'},
        ]
        for case in fresh_held:run(case)
        final_held=[
            {'case':'final-held-release-signature','cohort':'fresh-held-out-final-template','question':'Who signed release NF-26?','records':[{'text':'Rhea signed release NF-26.'}],'expected':['direct'],'support':True},
            {'case':'final-held-docking-negation','cohort':'fresh-held-out-final-template','question':'Was docking procedure V accepted?','records':[{'text':'Docking procedure V was not accepted.'}],'expected':['direct'],'support':True},
            {'case':'final-held-uplink-recovery','cohort':'fresh-held-out-final-template','question':'How did the uplink resume?','records':[{'text':'Replacing the antenna restored the uplink.'}],'expected':['direct'],'support':True},
            {'case':'final-held-unrecorded-pressure','cohort':'fresh-held-out-final-template','question':'What pressure reading was recorded?','records':[{'text':'An engineer inspected the valve.'}],'expected':['insufficient','no_evidence'],'full':True,'path':'scan'},
        ]
        for case in final_held:run(case)
        report={'schema':'adhd/archive-quality@1','passed':True,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest() if command else None,'image':args.image,'cases':cases,'scope':'Model decisions on authored fixtures; source statements and provisional comparisons are not certified facts.','workdir':str(root.relative_to(Path.cwd()))}
        Path(args.report).write_text(json.dumps(report,indent=2)+'\n')
    finally:hub.stop()

if __name__=='__main__':main()
