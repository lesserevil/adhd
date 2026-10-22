"""Check actual callback-capsule status output against the closed ACME contract."""
import argparse
import hashlib
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

p=argparse.ArgumentParser()
p.add_argument('schema',type=Path)
p.add_argument('report',type=Path)
a=p.parse_args()
s=json.loads(a.schema.read_bytes());r=json.loads(a.report.read_bytes())
v=Draft202012Validator({'$schema':s['$schema'],'$defs':s['$defs'],'$ref':'#/$defs/TLSStatus'},format_checker=FormatChecker())
for row in r['status_projections']:v.validate(row)
assert {r['https_state'] for r in r['status_projections']}=={'disabled','waiting','ready','expired','error'}
assert {r['acme_state'] for r in r['status_projections']}=={'disabled','idle','ordering','backoff','error'}
for state, field in [('ordering','last_attempt_at'),('backoff','next_attempt_at')]:
    invalid=dict(next(row for row in r['status_projections'] if row['acme_state']==state))
    invalid[field]=None
    assert list(v.iter_errors(invalid)), (state,field)
print(json.dumps({'invalid_fixture_states_rejected':2,'passed':True,'projections':len(r['status_projections']),'schema_sha256':hashlib.sha256(a.schema.read_bytes()).hexdigest(),'report_sha256':hashlib.sha256(a.report.read_bytes()).hexdigest()}))
