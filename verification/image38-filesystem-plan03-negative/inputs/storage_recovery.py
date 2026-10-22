#!/usr/bin/env python3
"""Crash real snapshot/DETS writes and reject corrupt or conflicting recovery state."""
import argparse,hashlib,json,os,re,secrets,shutil,signal,subprocess,tempfile,threading,time
from pathlib import Path
from foundation_acceptance import Runtime,Client,ModelFixture,free_port
from image_filesystem_fault import fault_arguments
from image_filesystem_runtime import FilesystemRuntime


def main():
    p=argparse.ArgumentParser(description=__doc__)
    target=p.add_mutually_exclusive_group(required=True);target.add_argument('--command');target.add_argument('--image')
    p.add_argument('--image-manifest',type=Path);fault_arguments(p)
    p.add_argument('--integrity-only',action='store_true');p.add_argument('--report',default='verification/storage-recovery.json')
    args=p.parse_args();command=json.loads(args.command) if args.command else []
    parent=Path('_build/roadmap/storage-recovery').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));cases=[];model=ModelFixture();hubs=[]
    def runtime(name,argv,environment=None):
        r=(FilesystemRuntime(root/name,args,'storage_write_fault.c' if environment else None,environment,mount_root=root) if args.image else Runtime(root/name,argv))
        r.file.write_text(json.dumps({'project_id':'storage-fixture','port':free_port(),'store_path':str(r.root/'hub.dets'),
            'projects':[{'id':name,'name':name,'status':'active','settings':{}} for name in ('storage-fixture','healthy-blue')],
            'agents':{name:secrets.token_urlsafe(32) for name in ('alice','bob','blue')},
            'agent_projects':{'alice':['storage-fixture'],'bob':['storage-fixture'],'blue':['healthy-blue']},'admin_token':secrets.token_urlsafe(32),
            'matcher':{'url':model.url,'model':'Nemotron-Deciffusion-8B-v2.1','timeout_ms':500,'retry_ms':100}}));r.file.chmod(0o600);hubs.append(r)
        r.start()
        r.profile21=Client(r).get('/protocol/schema')[1].get('$id')=='urn:adhd:protocol:2.1'
        r.blue_witness=rpc(r,{'op':'publish_record','text':'Independent Blue survives Red failure'},mid='blue-safety-witness',actor='blue')
        return r
    def rpc(r,cmd,mid=None,actor='alice'):
        return Client(r).rpc({'project_id':'healthy-blue' if actor=='blue' else 'storage-fixture',**cmd},r.config['agents'][actor],mid=mid)
    def selected(r):
        if Path(str(r.file)+'.stores').exists():
            from project_recovery_state import route
            return route(r.file,'storage-fixture')[1]
        return Path(r.config['store_path'])
    def record(name,**extra):cases.append({'case':name,'passed':True,**extra});print('PASS',name,extra,flush=True)
    def rejected(r):
        # Profile2.1 quarantines one failed project while authenticated global
        # control and a separately accepted Blue witness remain operational.
        previous=r.initialize_projects
        r.initialize_projects=False
        try:
            r.start()
            profile=Client(r).get('/protocol/schema')[1].get('$id')
            assert profile=='urn:adhd:protocol:2.1','Earlier profiles must reject invalid state globally'
            client=Client(r,r.config['admin_token'])
            status=client.api({'op':'project_restore_status','project_id':'storage-fixture'})
            assert status['availability']=='recovery_required'
            assert client.api({'op':'config_get'})['config']['server_id']==r.config['server_id']
            result=rpc(r,{'op':'get_record','publication_id':r.blue_witness['record']['publication']['id']},actor='blue')
            assert result['record']==r.blue_witness['record']
            rejected=client.api({'op':'overview','project_id':'storage-fixture'},expected=503)
            assert rejected['error']['code']=='RECOVERY_REQUIRED'
        except AssertionError:
            assert not r.profile21, 'Profile2.1 target corruption killed global control or failed an isolation assertion'
            assert r.process.poll() is not None and r.process.returncode!=0
        finally:
            r.stop()
            r.initialize_projects=previous
    try:
        observer=root/'storage-write-fault.so'
        if not args.integrity_only and not args.image:
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC','-O2',str(Path(__file__).with_name('storage_write_fault.c')),'-o',str(observer),'-ldl'],check=True)
        dirty_witness=False
        for boundary in (() if args.integrity_only else ('snapshot-data-sync','snapshot-install','checkpoint-write','checkpoint-sync')):
            model.mode='match';sentinel=root/(boundary+'.observed.json');arm=root/(boundary+'.arm');target=root/(boundary+'.target')
            traced=['env','LD_PRELOAD='+str(observer),'ADHD_WRITE_STAGE='+boundary,'ADHD_WRITE_SENTINEL='+str(sentinel),'ADHD_WRITE_ARM='+str(arm),'ADHD_WRITE_TARGET='+str(target)]+command
            environment={'ADHD_WRITE_STAGE':boundary,'ADHD_WRITE_SENTINEL':str(sentinel),'ADHD_WRITE_ARM':str(arm),'ADHD_WRITE_TARGET':str(target)}
            r=runtime(boundary,traced,environment);data=selected(r);snapshot=Path(str(data)+'.snapshot')
            rpc(r,{'op':'subscribe','description':'Observe source records'},mid='baseline-subscription',actor='bob')
            baseline_command={'op':'publish_record','text':'Acknowledged original evidence','context':{'question':'What was observed?','subject':'original'},'source':{'kind':'email','id':'origin','item_id':'original-event'}}
            original=rpc(r,baseline_command,mid='baseline-publication')['record'];oid=original['publication']['id']
            deadline=time.monotonic()+20;deliveries=[]
            while time.monotonic()<deadline:
                deliveries=rpc(r,{'op':'poll'},actor='bob')['deliveries']
                if deliveries:break
                time.sleep(.1)
            assert len(deliveries)==1
            rpc(r,{'op':'ack','delivery_ids':[deliveries[0]['id']]},mid='baseline-ack',actor='bob')
            private=rpc(r,{'op':'send','recipient_id':'bob','text':'Private durable state'},mid='baseline-private')['delivery']
            baseline=rpc(r,{'op':'get_record','publication_id':oid});mark=baseline['snapshot']['watermark'];before=snapshot.read_bytes()
            model.mode='error';errors=[]
            for path,body in ((target,str(data).encode()),(arm,b'armed-after-accepted-baseline\n')):
                fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'wb') as output:output.write(body);output.flush();os.fsync(output.fileno())
            mutation={'op':'publish_record','text':'Transition interrupted at '+boundary,'context':{'links':[{'relation':'corrects','publication_id':oid}]},'source':{'kind':'email','id':'origin','item_id':'crash-event'}}
            def mutate():
                try:rpc(r,mutation,mid='crash-request')
                except Exception as error:errors.append(type(error).__name__)
            worker=threading.Thread(target=mutate,daemon=True);worker.start();deadline=time.monotonic()+30;hit=None
            while time.monotonic()<deadline:
                if sentinel.exists():
                    hit=json.loads(sentinel.read_text())
                    if args.image:
                        r.target.stop_at_observed_boundary(hit)
                        assert time.monotonic()<=deadline,'Actual image STOP exceeded original boundary deadline'
                        break
                    state=Path('/proc/'+str(r.process.pid)+'/status').read_text()
                    if re.search(r'^State:\s+T',state,re.M):break
                time.sleep(.005)
            assert hit is not None,'Actual filesystem boundary not observed: '+boundary
            assert hit['stage']==boundary and hit['pid']==(1 if args.image else r.process.pid)
            assert hit['syscall'] in ({'rename'} if boundary=='snapshot-install' else {'pwrite','pwrite64'} if boundary=='checkpoint-write' else {'fsync'})
            if not args.image:assert re.search(r'^State:\s+T',Path('/proc/'+str(r.process.pid)+'/status').read_text(),re.M),'Observer did not stop the actual hub'
            r.stop(hard=True)
            if args.image:assert r.process.returncode==137 and r.target.last_exit_code==137
            else:assert r.process.returncode==-signal.SIGKILL
            worker.join(timeout=16);assert not worker.is_alive()
            committed=snapshot.read_bytes()!=before
            if boundary in ('checkpoint-write','checkpoint-sync'):assert committed and b'crash-request' in snapshot.read_bytes()
            if args.image:
                inspected=r.offline_elixir(':dets.open_file(:inspect_fault,[file: String.to_charlist(hd(System.argv())),access: :read,repair: false]) |> IO.inspect()',data)
                assert inspected.returncode==0,inspected.stderr
                check=inspected.stdout+inspected.stderr
            else:
                check=subprocess.check_output(['elixir','-e',':dets.open_file(:inspect_fault,[file: String.to_charlist(hd(System.argv())),access: :read,repair: false]) |> IO.inspect()',str(data)],text=True,stderr=subprocess.STDOUT)
            needs_repair='needs_repair' in check;dirty_witness=dirty_witness or needs_repair
            r.command=command;r.start()
            assert rpc(r,baseline_command,mid='baseline-publication')['record']==original
            assert rpc(r,{'op':'get_record','publication_id':oid,'watermark':mark})==baseline
            queued=rpc(r,{'op':'poll'},actor='bob')['deliveries'];assert queued==[private]
            result=rpc(r,mutation,mid='crash-request');assert rpc(r,mutation,mid='crash-retry')==result
            found=rpc(r,{'op':'search','query':'Transition interrupted at '+boundary})['publications'];assert len(found)==1 and found[0]['id']==result['record']['publication']['id']
            assert snapshot.stat().st_mode&0o777==0o600 and data.stat().st_mode&0o777==0o600
            record('kill-at-'+boundary,snapshot_installed=committed,checkpoint_needed_repair=needs_repair,observer=hit,actual_sigkill=True)
            r.stop()
        assert dirty_witness or args.integrity_only,'Fault injection never produced the original DETS needs_repair condition'
        model.mode='match';r=runtime('integrity',command);data=selected(r);snapshot=Path(str(data)+'.snapshot')
        expected=rpc(r,{'op':'publish_record','text':'Integrity original','context':{'subject':'integrity'}},mid='integrity-original');r.stop();good=snapshot.read_bytes()
        damaged=bytearray(good);damaged[-1]^=1;snapshot.write_bytes(damaged);rejected(r);assert snapshot.read_bytes()==damaged
        snapshot.write_bytes(good);r.start();assert rpc(r,{'op':'publish_record','text':'Integrity original','context':{'subject':'integrity'}},mid='integrity-original')==expected;r.stop()
        record('corrupt-checksum-fails-closed-without-reset-and-matched-restore-works')
        snapshot_before=snapshot.read_bytes();r.start();later=rpc(r,{'op':'publish','text':'Later acknowledged evidence'},mid='integrity-later');r.stop();latest=snapshot.read_bytes();snapshot.write_bytes(snapshot_before)
        rejected(r);snapshot.write_bytes(latest);r.start();assert rpc(r,{'op':'get','publication_id':later['publication']['id']})['publication']==later['publication'];r.stop()
        record('stale-snapshot-cannot-roll-back-a-newer-acknowledged-checkpoint')
        # Independent codec fixture changes identity while preserving a valid hash.
        source='''path=hd(System.argv()); <<"ADHDSTATE",1,_::binary-size(32),body::binary>>=File.read!(path); s=:erlang.binary_to_term(body); s=Map.put(s,:server_id,String.duplicate("0",32)); b=:erlang.term_to_binary(s,[:deterministic,{:minor_version,2}]); File.write!(path,<<"ADHDSTATE",1,(:crypto.hash(:sha256,b))::binary,b::binary>>)'''
        fixture=r.offline_elixir(source,snapshot) if args.image else subprocess.run(['elixir','-e',source,str(snapshot)],capture_output=True,text=True);assert fixture.returncode==0,fixture.stderr;rejected(r);snapshot.write_bytes(latest)
        record('validly-checksummed-foreign-identity-snapshot-is-rejected')
        data.unlink();r.start();assert rpc(r,{'op':'get','publication_id':later['publication']['id']})['publication']==later['publication'];r.stop()
        record('missing-checkpoint-reconstructed-from-complete-valid-snapshot')
        checkpoint=data.read_bytes();data.write_bytes(b'not a DETS file');rejected(r);assert data.read_bytes()==b'not a DETS file';data.write_bytes(checkpoint)
        record('unrelated-checkpoint-corruption-is-not-silently-treated-as-an-interrupted-write')
        target=r.root/'operator-file';target.write_bytes(b'untouched operator data');snapshot.unlink();snapshot.symlink_to(target);rejected(r);assert target.read_bytes()==b'untouched operator data'
        record('snapshot-symlink-is-rejected-without-modifying-its-target')
        Path(args.report).write_text(json.dumps({'schema':'adhd/storage-recovery@1','scope':'integrity' if args.integrity_only else 'full','passed':True,'cases':cases,'artifact_sha256':r.target.manifest['files']['hub.exs'] if args.image else hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest(),'runtime':[{**h.target.identity(),'offline_helpers':h.offline_helpers} for h in hubs] if args.image else None},indent=2)+'\n')
    finally:
        for r in hubs:r.stop()
        model.close()


if __name__=='__main__':main()
