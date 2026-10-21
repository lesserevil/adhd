#!/usr/bin/env python3
"""Select a durable installation identity before unchanged Confluent startup.

Standard-library only, mounted read-only. Never formats storage or rewrites Kafka
metadata. This single-node deployment still requires one owner of the volume.
"""
import argparse
import fcntl
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

ID = re.compile(r'[A-Za-z0-9_-]{22}')
SEED = '.adhd-cluster-id'
LOCK = '.adhd-bootstrap.lock'


def fail(message):
    raise ValueError(message)


def regular(path, maximum=65536):
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(descriptor,'r',encoding='ascii') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>maximum:
            fail('Identity input must be a bounded regular file')
        return stream.read(maximum+1)


def checked_id(value):
    if not ID.fullmatch(value):
        fail('Invalid Kafka cluster identity')
    return value


def identity(root, environment):
    root=Path(root).absolute()
    if '..' in root.parts:fail('Traversal in broker data directory is not allowed')
    for part in [root,*root.parents]:
        if part.is_symlink():
            fail('Symlink broker data directory is not allowed')
    if not root.is_dir():
        fail('Broker data volume must already exist')
    lock=os.open(root/LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    if not stat.S_ISREG(os.fstat(lock).st_mode):
        os.close(lock);fail('Invalid bootstrap lock file')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        paths=[Path(value).absolute() for value in environment.get('KAFKA_LOG_DIRS',str(root/'logs')).split(',')]
        if environment.get('KAFKA_METADATA_LOG_DIR'):
            paths.append(Path(environment['KAFKA_METADATA_LOG_DIR']).absolute())
        found=[]
        for directory in set(paths):
            if '..' in directory.parts:fail('Traversal in broker log directory is not allowed')
            if root not in [directory,*directory.parents]:
                fail('Every broker log directory must be inside its durable data volume')
            for part in [directory,*directory.parents]:
                if part.is_symlink():
                    fail('Symlink broker log directory is not allowed')
            meta=directory/'meta.properties'
            if meta.exists() or meta.is_symlink():
                entries={}
                for line in regular(meta).splitlines():
                    line=line.strip()
                    if not line or line.startswith(('#','!')):
                        continue
                    key,sep,value=line.partition('=')
                    if sep and key.strip() in ('cluster.id','node.id','version'):
                        key=key.strip()
                        if key in entries:fail('Duplicate Kafka metadata identity field')
                        entries[key]=value.strip()
                found.append(checked_id(entries.get('cluster.id','')))
                if entries.get('version')!='1':fail('Only existing KRaft metadata version 1 is supported')
                if entries.get('node.id')!=environment.get('KAFKA_NODE_ID','1'):
                    fail('Kafka node identity differs from existing volume')
            elif directory.exists():
                children=list(directory.iterdir())
                if directory==root:
                    children=[path for path in children if path.name not in (LOCK,SEED,'lost+found') and not path.name.startswith(SEED+'.stage-')]
                if children:fail('Nonempty Kafka log directory lacks its identity metadata')
        seed=root/SEED
        if seed.exists() or seed.is_symlink():
            found.append(checked_id(regular(seed,128).strip()))
        elif not found:
            # Refuse arbitrary nonempty volumes rather than initializing on top
            # of unidentified older/moved data. Empty intended log dirs are fine.
            allowed=set(paths)|{root/LOCK,root/'lost+found'}
            if any(path not in allowed and not path.name.startswith(SEED+'.stage-') for path in root.iterdir()):
                fail('Unidentified nonempty broker data volume')
        explicit=environment.get('CLUSTER_ID')
        if explicit:
            found.append(checked_id(explicit))
        if len(set(found))>1:
            fail('Kafka cluster identity mismatch; refusing startup without changing storage')
        selected=found[0] if found else checked_id(subprocess.check_output(
            ['kafka-storage','random-uuid'],text=True,timeout=30).strip())
        if not seed.exists():
            descriptor,stage=tempfile.mkstemp(prefix=SEED+'.stage-',dir=root)
            try:
                with os.fdopen(descriptor,'w',encoding='ascii') as stream:
                    stream.write(selected+'\n');stream.flush();os.fsync(stream.fileno())
                os.link(stage,seed,follow_symlinks=False)
                directory_fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(directory_fd)
                finally:os.close(directory_fd)
            finally:
                os.unlink(stage)
        return selected,lock
    except BaseException:
        os.close(lock)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=Path('/var/lib/kafka/data'))
    parser.add_argument('--identity-only',action='store_true',help='Provision/check identity without starting or formatting Kafka')
    args=parser.parse_args()
    try:
        selected,lock=identity(args.data_dir,os.environ)
        if args.identity_only:
            print(selected);os.close(lock);return
        os.environ['CLUSTER_ID']=selected
        os.set_inheritable(lock,True)
        os.execv('/etc/confluent/docker/run',['/etc/confluent/docker/run'])
    except (ValueError,OSError,subprocess.SubprocessError,UnicodeError) as error:
        # Fixed domain errors avoid printing environment or credential values.
        print('Kafka bootstrap refused startup: '+(str(error) if isinstance(error,ValueError) else type(error).__name__),file=sys.stderr)
        raise SystemExit(1)


if __name__=='__main__':
    main()
