from pathlib import Path
import json
root=Path('/home/horde/src/adhd');work=root/'_build/acme/finaldocs01'
rows=[json.loads(s)for s in (work/'process-cases.jsonl').read_text().splitlines()]
last=next((r for r in reversed(rows)if r.get('authored_case_ids')),{});ids=last.get('authored_case_ids',[])
cases=json.loads((root/'verification/acceptance/hub.json').read_text())['cases']
events=[json.loads(s)for s in (work/'exit-monitor.stdout').read_text().splitlines()]
terminal=next((r for r in reversed(events)if r.get('terminal_observed')),None)
print(json.dumps({'latest_observed_case_ids':ids,'positions':[i+1 for i,c in enumerate(cases)if c['case_id']in ids],'configured_cases':len(cases),'terminal':terminal,'pass_count_inferred':False}))
