#!/usr/bin/env python3
"""Run every original readiness case with default compiled-entrypoint custody.

No application source or original scenario is changed. Original health readiness
runs first, then read-only custody inspects that same actual VM.
"""
import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import container_fixture
import eventing_readiness_faults as scenario
from eventing_readiness_matrix import CASES
from eventing_retention_compiled import Custody


def install(custody):
    original=scenario.Fixture
    class Fixture(original):
        async def start(self):
            await super().start()
            custody.observe(self.image_runtime)
            custody.starts[-1]['case']=self.root.name
            custody.save()
    return patch.object(container_fixture,'OwnedImage',custody.image_class()),patch.object(scenario,'Fixture',Fixture)


def main():
    parser=scenario.arguments(__doc__)
    parser.add_argument('--cases',default=','.join(CASES))
    parser.add_argument('--recovery-schema',type=Path,required=True)
    parser.add_argument('--custody-plan',type=Path,required=True)
    parser.add_argument('--custody-ledger',type=Path,required=True)
    args=parser.parse_args()
    assert args.image and not(args.command or args.rest_url or args.with_model)
    assert args.cases==','.join(CASES),'All23 original cases required'
    plan=json.loads(args.custody_plan.read_text());assert plan['image']==args.image
    custody=Custody(plan,args.custody_ledger);patches=install(custody);primary=None
    try:
        with patches[0],patches[1]:asyncio.run(scenario.main(args))
        assert len(custody.starts)==len(CASES)
        assert [row['case']for row in custody.starts]==list(CASES)
    except BaseException as error:primary=error;raise
    finally:
        try:custody.close()
        except BaseException as error:
            if primary is None:raise
            primary.add_note('Compiled readiness custody cleanup failure: '+type(error).__name__)


if __name__=='__main__':main()
