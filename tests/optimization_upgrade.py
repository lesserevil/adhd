#!/usr/bin/env python3
"""Preserve a genuinely selected learned recipe across store moves and runtime changes."""
import argparse,hashlib,json,shutil,tempfile,time
from pathlib import Path
from foundation_acceptance import Runtime,Client,free_port


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--producer-report',required=True);p.add_argument('--producer-command',required=True);mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--command');mode.add_argument('--image');p.add_argument('--report',default='verification/optimization-upgrade.json');a=p.parse_args();producer_command=json.loads(a.producer_command);command=json.loads(a.command) if a.command else []
    report=json.loads(Path(a.producer_report).read_text());assert report['passed'];source=Path(report['workdir'])/'hub';cfg=json.loads((source/'hub.json').read_text());source_store=Path(cfg['store_path']);assert source_store.is_relative_to(source.resolve())
    parent=Path('_build/roadmap/optimization-upgrade').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));producer=Runtime(root/'producer',producer_command);shutil.copytree(source,producer.root,dirs_exist_ok=True)
    cfg.update(store_path=str(producer.root/source_store.name),port=free_port());cfg['public_url']='http://127.0.0.1:'+str(cfg['port']);producer.file.write_text(json.dumps(cfg));producer.file.chmod(0o600);target=Runtime(root/'target',command,a.image);cases=[]
    def wait(fn):
        end=time.monotonic()+60
        while time.monotonic()<end:
            if v:=fn():return v
            time.sleep(.05)
        raise AssertionError('Selected-state upgrade deadline '+str(root))
    def api(h,v,mutation=False):return Client(h,h.config['admin_token']).api(v,mutation=mutation)
    def record(name,**v):cases.append({'case':name,'passed':True,**v});print('PASS',name,flush=True)
    try:
        producer.start();before=api(producer,{'op':'retrieval_index'})['index'];assert before['selection']['rollback_available']
        operation=api(producer,{'op':'rollback_index','expected_selection_revision':before['selection']['revision']},True)['proposal'];id=operation['id'];settled=wait(lambda:q if (q:=api(producer,{'op':'index_proposal','proposal_id':id})['proposal'])['status']!='pending' else None);assert settled['status']=='promoted' and settled['usage']['calls']==0
        selected=api(producer,{'op':'retrieval_index'})['index'];assert selected['status']=='ready' and selected['selection']['applied'] and selected['selection']['qualification_current'];assert selected['selection']['effective_recipe']!=selected['selection']['base_recipe']
        original_selection=selected['selection'];count=api(producer,{'op':'overview'})['counts']['publications'];deliveries=api(producer,{'op':'deliveries'})['items'];server=selected['active']['server_id'];offline=Path(producer.config['store_path'])
        api(producer,{'op':'config_update','patch':{'store_path':str(producer.root/'moved.dets')}},True)
        after_move=api(producer,{'op':'retrieval_index'})['index'];assert after_move['selection']==original_selection and api(producer,{'op':'overview'})['counts']['publications']==count
        record('hot-store-move-preserves-selected-primitive-qualification-control-and-originals',selection=original_selection,publications=count)
        producer.stop()
        # Config.move leaves this source closed and offline before its ACK. Copy
        # only that exact store's files, not the now-moved live destination.
        copied=[]
        for f in producer.root.iterdir():
            if f.is_file() and f.name.startswith(offline.name):shutil.copy2(f,target.root/f.name);copied.append(f.name)
        assert offline.name in copied
        target_config=dict(producer.config);target_config.update(store_path=str(target.root/offline.name),port=free_port());target_config['public_url']='http://127.0.0.1:'+str(target_config['port']);target.file.write_text(json.dumps(target_config));target.file.chmod(0o600)
        target.start();ready=wait(lambda:v if (v:=api(target,{'op':'retrieval_index'})['index'])['status']=='ready' else None);selection=ready['selection']
        assert selection['applied'] and selection['revision']==original_selection['revision'] and selection['base_identity']==original_selection['base_identity']
        for field in ['base_recipe','effective_recipe','selected','previous']:assert selection[field]==original_selection[field],field
        assert ready['active']['recipe']==selection['effective_recipe'] and ready['active']['server_id']==server
        runtime_changed=selection['current_runtime']!=original_selection['current_runtime'];assert selection['qualification_current']==(not runtime_changed)
        assert api(target,{'op':'overview'})['counts']['publications']==count
        current_deliveries=api(target,{'op':'deliveries'})['items'];assert current_deliveries==deliveries
        record('selected-recipe-and-deliveries-survive-restart-and-derived-runtime-rebuild',runtime_changed=runtime_changed,qualification_current=selection['qualification_current'],current_runtime=selection['current_runtime'],qualification_runtime=selection['selected']['qualification_runtime'],offline_store_sha256=hashlib.sha256(offline.read_bytes()).hexdigest())
        # An explicit equal operator recipe still resets learned control after
        # migration. The previous native generation cannot re-enable it later.
        api(target,{'op':'config_update','patch':{'retrieval':{'recipe':selection['base_recipe']}}},True)
        reset=api(target,{'op':'retrieval_index'})['index']['selection'];assert reset['revision']==selection['revision']+1 and not reset['applied'] and reset['selected'] is None and reset['previous'] is None
        wait(lambda:api(target,{'op':'retrieval_index'})['index']['status']=='ready');assert api(target,{'op':'overview'})['counts']['publications']==count
        record('explicit-unchanged-base-reset-clears-a-real-learned-override-after-upgrade')
        output={'schema':'adhd-optimization-upgrade-report@1','passed':True,'cases':cases,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest() if command else None,'producer_artifact_sha256':hashlib.sha256(Path(producer_command[-1]).read_bytes()).hexdigest(),'image':a.image,'workdir':str(root.relative_to(Path.cwd()))};Path(a.report).parent.mkdir(parents=True,exist_ok=True);Path(a.report).write_text(json.dumps(output,indent=2)+'\n')
    finally:target.stop();producer.stop()

if __name__=='__main__':main()
