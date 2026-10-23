#!/usr/bin/env python3
"""Check authored scope inventory covers every published operation/config field."""
import argparse
import json
from pathlib import Path


def check(schema, inventory):
    defs=schema['$defs']
    for surface,prefix in [('agent','agent_'),('admin','admin_')]:
        actual={key[len(prefix):] for key in defs if key.startswith(prefix)
                and not key.startswith('admin_result_')}
        assert actual==set(inventory[surface]),(surface,actual^set(inventory[surface]))
    properties=set(defs['PublicConfig']['properties'])|set(defs['MergePatch']['properties'])
    assert properties==set(inventory['configuration']),properties^set(inventory['configuration'])
    assert set(defs['ProjectSettings']['properties'])==set(inventory['project_settings'])
    assert {'whoami','list_projects'}=={op for op,scope in inventory['agent'].items() if scope=='server-identity'}
    assert inventory['admin']['resource_status']=='server'
    for op in ('repair_eventing','replay_events','eventing_replay','eventing_audit','update_subscription','subscriptions'):
        assert inventory['admin'][op]=='project'
    for op in inventory['peer']:assert 'PeerV2_'+op in defs


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--schema',type=Path,required=True)
    p.add_argument('--inventory',type=Path,default=Path('docs/protocol/scopes.json'))
    args=p.parse_args();check(json.loads(args.schema.read_text()),json.loads(args.inventory.read_text()))
    print('PASS complete operation/configuration scope inventory')


if __name__=='__main__':main()
