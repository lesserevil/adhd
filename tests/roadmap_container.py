#!/usr/bin/env python3
"""Run new roadmap suites against an isolated, hardened container image."""
import argparse,asyncio,json,subprocess
from pathlib import Path
from uuid import uuid4
from container_acceptance import ContainerHub
import roadmap_acceptance,oidc_acceptance,adaptation_acceptance

class Hub(ContainerHub):
    def __init__(self,*args):
        super().__init__(*args)
        self.command[2:2]=['--env','ADHD_TEST_OIDC_SECRET']

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--image',required=True);p.add_argument('--report',default='verification/roadmap-container.json')
    args=p.parse_args();Hub.image=args.image
    root=Path('_build/tests/roadmap-container').resolve()/str(uuid4());root.mkdir(parents=True)
    cases=[]
    def record(name):cases.append({'case':name,'passed':True});print('PASS',name,flush=True)
    async def run():
        for module in [roadmap_acceptance,oidc_acceptance,adaptation_acceptance]:
            module.Hub=Hub
            await module.checks([],root,record)
        await adaptation_acceptance.automatic_checks([],root,record)
    asyncio.run(run())
    iid=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',args.image],text=True).strip()
    Path(args.report).write_text(json.dumps({'schema':'adhd/roadmap-container@1','passed':True,'image_id':iid,'cases':cases},indent=2)+'\n')
if __name__=='__main__':main()
