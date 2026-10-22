#!/usr/bin/env python3
"""Exercise actual offline tar helper ownership/mode fidelity on synthetic files.

No application code runs, no live volume is mounted, and no image is built.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess


def main(args):
    root=args.work.resolve()
    if root.exists():raise ValueError('Use a fresh private probe directory')
    root.mkdir(parents=True,mode=0o700)
    directory=root/'synthetic';directory.mkdir();directory.chmod(0o2770)
    fact=directory/'fact';fact.write_bytes(b'Synthetic metadata fidelity fixture\n');fact.chmod(0o600)
    before=[(p.stat().st_uid,p.stat().st_gid,stat.S_IMODE(p.stat().st_mode)) for p in (directory,fact)]
    archive=root/'backup.tgz'
    helper=['docker','run','--rm','-i','--network','none','--read-only','--user','0:0',
        '--cap-drop','ALL','--cap-add','CHOWN','--cap-add','DAC_OVERRIDE','--cap-add','FOWNER','--cap-add','FSETID',
        '--memory','256m','--cpus','1','--pids-limit','64','--security-opt','no-new-privileges:true',
        '--mount','type=bind,source='+str(directory)+',target=/state','--entrypoint','sh',args.image,'-ec']
    with archive.open('xb') as stream:
        archive.chmod(0o600)
        subprocess.run(helper+['exec tar -czpf - -C /state .'],stdout=stream,check=True,timeout=60)
    directory.chmod(0o700);fact.write_bytes(b'intentionally newer data\n');fact.chmod(0o644)
    with archive.open('rb') as stream:
        subprocess.run(helper+['exec tar -xzpf - -C /state'],stdin=stream,check=True,timeout=60)
    after=[(p.stat().st_uid,p.stat().st_gid,stat.S_IMODE(p.stat().st_mode)) for p in (directory,fact)]
    assert before==after and fact.read_bytes()==b'Synthetic metadata fidelity fixture\n'
    image=json.loads(subprocess.check_output(['docker','image','inspect',args.image]))[0]['Id']
    source=Path(__file__).with_name('kafka_final_platform.py')
    report={'suite':'adhd/offline-backup-owner-mode-fidelity@1','passed':True,'lifecycle_qualified':False,
        'scope':'Synthetic utility/container filesystem probe only; no accepted application run or live volume access.',
        'image_config_digest':image,'restored_directory_mode':oct(after[0][2]),'restored_file_mode':oct(after[1][2]),
        'owner_and_group_preserved':True,'content_restored':True,'helper_caps':['CHOWN','DAC_OVERRIDE','FOWNER','FSETID'],
        'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'platform_harness_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS actual tar restored original owner/group, directory2770, file0600 and content')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image',required=True)
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    main(p.parse_args())
