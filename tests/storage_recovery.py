#!/usr/bin/env python3
"""Crash real snapshot/DETS writes and reject corrupt or conflicting recovery state."""
import argparse,hashlib,json,os,re,secrets,shutil,subprocess,tempfile,threading,time
from pathlib import Path
from foundation_acceptance import Runtime,Client,ModelFixture,free_port


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--command',required=True);p.add_argument('--integrity-only',action='store_true');p.add_argument('--report',default='verification/storage-recovery.json');args=p.parse_args();command=json.loads(args.command)
    assert shutil.which('strace'),'strace is required for actual filesystem-boundary crashes'
    parent=Path('_build/roadmap/storage-recovery').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));cases=[];model=ModelFixture();hubs=[]
    def runtime(name,argv):
        r=Runtime(root/name,argv);r.file.write_text(json.dumps({'project_id':'storage-fixture','port':free_port(),'store_path':str(r.root/'hub.dets'),
            'agents':{'alice':secrets.token_urlsafe(32),'bob':secrets.token_urlsafe(32)},'admin_token':secrets.token_urlsafe(32),
            'matcher':{'url':model.url,'model':'Nemotron-Deciffusion-8B-v2.1','timeout_ms':500,'retry_ms':100}}));r.file.chmod(0o600);hubs.append(r)
        if argv != command:
            # Provision and migrate through the real runtime before delaying
            # every filesystem call. These cases target subsequent publication
            # commits; startup/migration crashes have dedicated independent suites.
            r.command=command;r.start();r.stop();r.command=argv
        r.start();return r
    def rpc(r,cmd,mid=None,actor='alice'):return Client(r).rpc(cmd,r.config['agents'][actor],mid=mid)
    def record(name,**extra):cases.append({'case':name,'passed':True,**extra});print('PASS',name,extra,flush=True)
    def rejected(r):
        try:r.start()
        except AssertionError:assert r.process.poll() is not None and r.process.returncode!=0
        else:raise AssertionError('Invalid persistent state was accepted')
        finally:r.stop()
    try:
        dirty_witness=False
        for boundary in (() if args.integrity_only else ('snapshot-data-sync','snapshot-install','checkpoint-write','checkpoint-sync')):
            model.mode='match';trace=root/(boundary+'.trace')
            traced=['strace','-f','-yy','-s','1024','-e','trace=rename,pwrite64,fsync','-e','inject=rename:delay_exit=1s',
                '-e','inject=fsync:delay_exit=1s','-e','inject=pwrite64:delay_exit=100ms','-o',str(trace)]+command
            r=runtime(boundary,traced);data=Path(r.config['store_path']);snapshot=Path(str(data)+'.snapshot')
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
            model.mode='error';offset=trace.stat().st_size;errors=[]
            mutation={'op':'publish_record','text':'Transition interrupted at '+boundary,'context':{'links':[{'relation':'corrects','publication_id':oid}]},'source':{'kind':'email','id':'origin','item_id':'crash-event'}}
            def mutate():
                try:rpc(r,mutation,mid='crash-request')
                except Exception as error:errors.append(type(error).__name__)
            worker=threading.Thread(target=mutate,daemon=True);worker.start();deadline=time.monotonic()+30;hit=None
            while time.monotonic()<deadline:
                text=trace.read_text(errors='replace')[offset:]
                if boundary=='snapshot-data-sync':matches=[line for line in text.splitlines() if 'fsync(' in line and '.snapshot.tmp-' in line]
                elif boundary=='snapshot-install':matches=[line for line in text.splitlines() if 'rename(' in line and '\", \"'+str(snapshot)+'\"' in line]
                elif boundary=='checkpoint-write':matches=[line for line in text.splitlines() if 'pwrite64(' in line and '<'+str(data)+'>' in line]
                else:matches=[line for line in text.splitlines() if 'fsync(' in line and '<'+str(data)+'>' in line]
                if matches:hit=matches[0];break
                time.sleep(.005)
            assert hit is not None,'Actual filesystem boundary not observed: '+boundary
            r.stop(hard=True);worker.join(timeout=16);assert not worker.is_alive()
            committed=snapshot.read_bytes()!=before
            if boundary in ('checkpoint-write','checkpoint-sync'):assert committed and b'crash-request' in snapshot.read_bytes()
            check=subprocess.check_output(['elixir','-e',':dets.open_file(:inspect_fault,[file: String.to_charlist(hd(System.argv())),access: :read,repair: false]) |> IO.inspect()',str(data)],text=True,stderr=subprocess.STDOUT)
            needs_repair='needs_repair' in check;dirty_witness=dirty_witness or needs_repair
            r.command=command;r.start()
            assert rpc(r,baseline_command,mid='baseline-publication')['record']==original
            assert rpc(r,{'op':'get_record','publication_id':oid,'watermark':mark})==baseline
            queued=rpc(r,{'op':'poll'},actor='bob')['deliveries'];assert queued==[private]
            result=rpc(r,mutation,mid='crash-request');assert rpc(r,mutation,mid='crash-retry')==result
            found=rpc(r,{'op':'search','query':'Transition interrupted at '+boundary})['publications'];assert len(found)==1 and found[0]['id']==result['record']['publication']['id']
            assert snapshot.stat().st_mode&0o777==0o600 and data.stat().st_mode&0o777==0o600
            record('kill-at-'+boundary,snapshot_installed=committed,checkpoint_needed_repair=needs_repair)
            r.stop()
        assert dirty_witness or args.integrity_only,'Fault injection never produced the original DETS needs_repair condition'
        model.mode='match';r=runtime('integrity',command);data=Path(r.config['store_path']);snapshot=Path(str(data)+'.snapshot')
        expected=rpc(r,{'op':'publish_record','text':'Integrity original','context':{'subject':'integrity'}},mid='integrity-original');r.stop();good=snapshot.read_bytes()
        damaged=bytearray(good);damaged[-1]^=1;snapshot.write_bytes(damaged);rejected(r);assert snapshot.read_bytes()==damaged
        snapshot.write_bytes(good);r.start();assert rpc(r,{'op':'publish_record','text':'Integrity original','context':{'subject':'integrity'}},mid='integrity-original')==expected;r.stop()
        record('corrupt-checksum-fails-closed-without-reset-and-matched-restore-works')
        snapshot_before=snapshot.read_bytes();r.start();later=rpc(r,{'op':'publish','text':'Later acknowledged evidence'},mid='integrity-later');r.stop();latest=snapshot.read_bytes();snapshot.write_bytes(snapshot_before)
        rejected(r);snapshot.write_bytes(latest);r.start();assert rpc(r,{'op':'get','publication_id':later['publication']['id']})['publication']==later['publication'];r.stop()
        record('stale-snapshot-cannot-roll-back-a-newer-acknowledged-checkpoint')
        # Independent codec fixture changes identity while preserving a valid hash.
        source='''path=hd(System.argv()); <<"ADHDSTATE",1,_::binary-size(32),body::binary>>=File.read!(path); s=:erlang.binary_to_term(body); s=Map.put(s,:server_id,String.duplicate("0",32)); b=:erlang.term_to_binary(s,[:deterministic,{:minor_version,2}]); File.write!(path,<<"ADHDSTATE",1,(:crypto.hash(:sha256,b))::binary,b::binary>>)'''
        fixture=subprocess.run(['elixir','-e',source,str(snapshot)],capture_output=True,text=True);assert fixture.returncode==0,fixture.stderr;rejected(r);snapshot.write_bytes(latest)
        record('validly-checksummed-foreign-identity-snapshot-is-rejected')
        data.unlink();r.start();assert rpc(r,{'op':'get','publication_id':later['publication']['id']})['publication']==later['publication'];r.stop()
        record('missing-checkpoint-reconstructed-from-complete-valid-snapshot')
        checkpoint=data.read_bytes();data.write_bytes(b'not a DETS file');rejected(r);assert data.read_bytes()==b'not a DETS file';data.write_bytes(checkpoint)
        record('unrelated-checkpoint-corruption-is-not-silently-treated-as-an-interrupted-write')
        target=r.root/'operator-file';target.write_bytes(b'untouched operator data');snapshot.unlink();snapshot.symlink_to(target);rejected(r);assert target.read_bytes()==b'untouched operator data'
        record('snapshot-symlink-is-rejected-without-modifying-its-target')
        Path(args.report).write_text(json.dumps({'schema':'adhd/storage-recovery@1','scope':'integrity' if args.integrity_only else 'full','passed':True,'cases':cases,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest()},indent=2)+'\n')
    finally:
        for r in hubs:r.stop()
        model.close()


if __name__=='__main__':main()
