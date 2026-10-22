#!/usr/bin/env python3
"""Qualify and export ADHD for the current Linux or macOS host through Literate AI."""
import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path


def identity(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform',choices=('linux','macos'))
    parser.add_argument('--regenerate',action='store_true',help='Generate from changed specifications instead of reusing committed source')
    parser.add_argument('--model',help='Optional model selector for intentional regeneration')
    parser.add_argument('--from-accepted-source',action='store_true',help='Fail unless a matching committed source entry exists')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    actual={'Linux':'linux','Darwin':'macos'}.get(platform.system());target=args.platform or actual
    if target is None or target!=actual:parser.error('Native verification requires a matching Linux or macOS host')
    defaults=json.loads((root/'literate.project.json').read_text())['default_flavor_selectors']
    flavors=[]
    if f'+flavor://literate-ai/os-{target}' not in defaults:
        other='macos' if target=='linux' else 'linux'
        flavors=[f'--flavor=-os-{other}',f'--flavor=+os-{target}']
    # Locks are current authority; cache bytes remain untrusted until qualification.
    subprocess.run(['litai','lock','components/hub',*flavors],cwd=root,check=True,capture_output=True)
    lock=json.loads((root/'components/hub/component.lock.json').read_text());lock_id=identity(lock)
    cache=root/'generated/committed-source-cache';matches=[]
    for path in sorted((cache/'entries/sha256').glob('*.json')):
        entry=json.loads(path.read_text())
        if entry['derivation']['component_lock_identity']['digest']==lock_id:
            if identity(entry)!=path.stem:raise SystemExit('Committed source entry hash differs')
            matches.append(entry)
    if matches and len({entry['derivation']['source_tree_identity']['digest'] for entry in matches}) == 1:
        matches = matches[:1]
    if args.regenerate:
        command=['litai','rebuild','components/hub',*flavors,'--allow-host-execution','--update-receipt','--keep-runtime']
        if args.model:command+=['--model',args.model]
        result=subprocess.run(command,cwd=root,text=True,capture_output=True)
    elif len(matches)==1:
        entry=matches[0];build=root/'_build';build.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='hub-source-',dir=build) as temporary:
            source=Path(temporary)
            for item in entry['source_files']:
                relative=Path(item['path'])
                if relative.is_absolute() or '..' in relative.parts or relative.parts[0]!='source':
                    raise SystemExit('Unsafe cached source path')
                blob=item['blob'];digest=blob['digest']
                content=(cache/'cas/blobs/sha256'/digest[:2]/digest).read_bytes()
                if len(content)!=blob['size'] or hashlib.sha256(content).hexdigest()!=digest:
                    raise SystemExit('Committed source blob hash differs')
                destination=source/relative;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(content)
            selector=entry['derivation']['cache_key']['model_binding']['model_selector']
            command=['litai','rebuild','components/hub',*flavors,'--retained-source',str(source/'source')]
            if selector:command+=['--model',selector]
            plan=subprocess.run(command+['--retained-source-plan'],cwd=root,text=True,capture_output=True)
            if plan.returncode:raise SystemExit(plan.stdout or plan.stderr)
            authorization=json.loads(plan.stdout)['result']['authorization_identity']
            result=subprocess.run(command+['--authorize-retained-source',authorization,'--allow-host-execution','--update-receipt','--keep-runtime'],cwd=root,text=True,capture_output=True)
    else:
        if matches:raise SystemExit('Multiple matching source entries; select and qualify a reviewed source explicitly with litai rebuild')
        if args.from_accepted_source:raise SystemExit('No committed source matches the selected host lock')
        raise SystemExit('No committed source matches this target. Use --regenerate on this host to generate and qualify it.')
    if result.returncode:raise SystemExit(result.stdout or result.stderr)
    document=json.loads(result.stdout);value=document['result']
    if document.get('ok') is not True or value.get('passed') is not True:raise SystemExit('Lifecycle did not accept the artifact')
    artifact=Path(value['artifact'])
    if not artifact.is_file() or artifact.is_symlink():raise SystemExit('Expected the accepted portable script artifact')
    output=root/'generated/artifacts/hub';output.mkdir(parents=True,exist_ok=True)
    exported=output/'hub.exs';shutil.copyfile(artifact,exported)
    digest=hashlib.sha256(exported.read_bytes()).hexdigest()
    record={'schema':'adhd/artifact-export@1','component':'components/hub','artifact':str(exported),
            'artifact_reference':{'identity':{'algorithm':'sha256','digest':digest}},
            'lifecycle_result_identity':value['lifecycle_result_identity'],'receipt_identity':value['receipt_identity'],
            'target':target}
    (output/'lifecycle.json').write_text(json.dumps(document,indent=2)+'\n')
    (output/'execution.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record))
    return 0


if __name__=='__main__':raise SystemExit(main())
