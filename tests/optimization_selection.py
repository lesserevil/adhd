#!/usr/bin/env python3
"""Independent live selection/reset journal, Admin ownership and hot settings checks."""
import argparse,hashlib,json,secrets,tempfile,time
from pathlib import Path
from foundation_acceptance import Runtime,Client,free_port
from archive_support import ArchiveFixture


def main():
    ap=argparse.ArgumentParser(description=__doc__);mode=ap.add_mutually_exclusive_group(required=True);mode.add_argument('--command');mode.add_argument('--image');ap.add_argument('--report',default='verification/optimization-selection.json');args=ap.parse_args()
    parent=Path('_build/roadmap/optimization-tests').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='selection-',dir=parent));h=Runtime(root/'hub',json.loads(args.command) if args.command else [],args.image);model=ArchiveFixture();cases=[]
    cfg={'project_id':'selection-fixture','store_path':str(h.root/'hub.dets'),'port':free_port(),'agents':{'alice':secrets.token_urlsafe(32)},'admin_token':secrets.token_urlsafe(32),'matcher':{'url':model.url,'model':'Nemotron-Deciffusion-8B-v2.1','timeout_ms':1000,'retry_ms':100},'archive':{'audit_rate_ppm':0}}
    h.file.write_text(json.dumps(cfg));h.file.chmod(0o600)
    def admin(v,mutation=False):return Client(h,h.config['admin_token']).api(v,mutation=mutation)
    def patch(v):return admin({'op':'config_update','patch':v},True)
    def selection():return admin({'op':'retrieval_index'})['index']['selection']
    def wait(fn,seconds=30):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if v:=fn():return v
            time.sleep(.05)
        raise AssertionError('Selection deadline; inspect '+str(root))
    def error(v,code,mutation=True):
        if mutation:v={**v,'confirm':True,'message_id':secrets.token_urlsafe(16),'expected_revision':h.config.get('config_revision',1)}
        status,result,_=Client(h,h.config['admin_token']).request('/admin/api',v);assert status>=400 and result['error']['code']==code,(status,result)
    def record(name):cases.append({'case':name,'passed':True});print('PASS',name,flush=True)
    try:
        h.start();pid=h.pid
        state=selection();assert state['revision']==0 and not state['applied'] and state['selected'] is None and state['previous'] is None
        status=admin({'op':'optimization_status'})['status'];assert status['enabled'] is False and status['mode']=='review' and status['proposals']==0
        assert admin({'op':'index_proposals'})=={'items':[],'next_offset':None}
        error({'op':'propose_index'},'UNAVAILABLE');error({'op':'rollback_index','expected_selection_revision':0},'NO_PREVIOUS_SELECTION')
        record('disabled-default-has-explicit-base-and-no-implied-qualification')
        patch({'optimization':{'enabled':True,'max_proposals':3,'max_active_proposals':1,'budget':{'calls':70}}})
        current=admin({'op':'config_get'});assert current['config']['optimization']['enabled'] and current['config']['optimization']['max_proposals']==3 and current['config']['optimization']['budget']['calls']==70
        assert h.pid==pid;error({'op':'propose_index'},'MIN_EVIDENCE')
        error({'op':'config_validate','expected_revision':h.config.get('config_revision',1),'patch':{'optimization':{'max_active_proposals':4}}},'INVALID_PARAMS',False)
        error({'op':'index_proposals','status':'forged'},'INVALID_PARAMS',False)
        error({'op':'propose_index','requester_kind':'optimization'},'INVALID_PARAMS')
        record('settings-are-hot-cross-field-validated-and-insufficient-evidence-never-spins')
        revision=selection()['revision'];recipe=selection()['base_recipe']
        patch({'retrieval':{'recipe':recipe}});assert selection()['revision']==revision+1
        patch({'retrieval':{'recipe':recipe}});assert selection()['revision']==revision+2
        patch({'retrieval':{'recipe':None}});assert selection()['revision']==revision+3
        patch({'retrieval':{'build_batch':3}});assert selection()['revision']==revision+3
        config_revision=h.config.get('config_revision',1);h.file.write_text(json.dumps(h.config,indent=2)+'\n');wait(lambda:h.config.get('config_revision',1)>config_revision)
        assert selection()['revision']==revision+3 and h.pid==pid
        record('identical-and-deleted-explicit-recipes-reset-but-unrelated-and-whitespace-edits-preserve-selection')
        error({'op':'reset_index_selection','expected_selection_revision':0},'CONFIG_CONFLICT')
        cmd={'op':'reset_index_selection','expected_selection_revision':selection()['revision'],'message_id':secrets.token_urlsafe(16),'confirm':True,'expected_revision':h.config.get('config_revision',1)}
        client=Client(h,h.config['admin_token']);first=client.api(cmd);assert client.api(cmd)==first;assert selection()['revision']==revision+4
        assert not Path(str(h.file)+'.transaction').exists()
        record('admin-reset-has-durable-selection-fence-and-actor-idempotency')
        # Simulate crashes after the existing durable config decision and after
        # the Store reset, using its exact journal format rather than a test hook.
        h.stop(hard=True);decision_id=secrets.token_urlsafe(24)
        decision={'config':h.config,'journal':json.loads(Path(str(h.file)+'.journal').read_text()),'index_reset':{'id':decision_id}}
        transaction=Path(str(h.file)+'.transaction');transaction.write_text(json.dumps(decision));transaction.chmod(0o600)
        h.start();assert selection()['revision']==revision+5 and not transaction.exists()
        h.stop(hard=True);transaction.write_text(json.dumps(decision));transaction.chmod(0o600)
        h.start();assert selection()['revision']==revision+5 and not transaction.exists()
        record('repeated-crash-recovery-applies-the-same-config-reset-decision-exactly-once')
        token=h.config['agents']['alice'];rpc=Client(h)
        pub=rpc.rpc({'op':'publish_record','text':'Original preserved after index selection reset.'},token)['record']['publication']['id']
        wait(lambda:admin({'op':'retrieval_index'})['index']['status']=='ready')
        assert rpc.rpc({'op':'get_record','publication_id':pub},token)['record']['publication']['text'].startswith('Original preserved')
        assert admin({'op':'query_jobs','kind':'optimization'})['items']==[]
        record('ordinary-agent-publication-index-and-admin-activity-remain-operational')
        report={'schema':'adhd-optimization-selection-report@1','passed':True,'cases':cases,'artifact_sha256':hashlib.sha256(Path(h.command[-1]).read_bytes()).hexdigest() if h.command else None,'image':args.image};Path(args.report).parent.mkdir(parents=True,exist_ok=True);Path(args.report).write_text(json.dumps(report,indent=2)+'\n')
    finally:h.stop();model.close()

if __name__=='__main__':main()
