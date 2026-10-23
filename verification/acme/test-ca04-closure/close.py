from pathlib import Path
import json,hashlib,os,signal,time
w=Path(__file__).resolve().parent;ca=w.parent/'ca04';manifest=json.loads((ca/'manifest.json').read_bytes())
expected_owner=['/home/horde/src/adhd/.venv/bin/python','-B','tests/acme_test_ca.py','--tools',str(w.parent/'tools'),'--work',str(ca),'--lifetime-seconds','10800']
expected=[('owner',4165059,'28598085',expected_owner),*[(p['name'],p['pid'],p['start_ticks'],manifest['argv'][p['name']]) for p in manifest['processes']]]
def observe(name,pid,start,argv):
 path=Path('/proc',str(pid));actual_start=(path/'stat').read_text().rsplit(')',1)[1].split()[19];actual_argv=(path/'cmdline').read_bytes().decode().split(chr(0))[:-1];uids=(path/'status').read_text().split('Uid:',1)[1].splitlines()[0].split();assert actual_start==start and actual_argv==argv and uids==['1003']*4
 if name!='owner':assert hashlib.sha256(Path(argv[0]).read_bytes()).hexdigest()==manifest['binary_sha256'][name]
 return {'name':name,'pid':pid,'start_ticks':actual_start,'uid':1003,'argv':actual_argv,'argv_sha256':hashlib.sha256((path/'cmdline').read_bytes()).hexdigest()}
before=[observe(*row) for row in expected];record={'schema':'adhd/acme-owned-CA04-closure@1','manifest_sha256':hashlib.sha256((ca/'manifest.json').read_bytes()).hexdigest(),'before':before,'authorized_graceful_owner_signal':'pidfd SIGTERM','no_other_signals':True,'actual_signal_monotonic':time.monotonic()}
(w/'before.json').write_text(json.dumps(record,indent=2)+'\n')
fd=os.pidfd_open(4165059)
try:
 observe(*expected[0]);signal.pidfd_send_signal(fd,signal.SIGTERM)
finally:os.close(fd)
deadline=time.monotonic()+15
while any(Path('/proc',str(row[1])).exists() for row in expected):
 assert time.monotonic()<deadline,'Owned CA process remains';time.sleep(.1)
cleanup=json.loads((ca/'cleanup.json').read_bytes());assert cleanup['all_absent']
assert {v['pid'] for v in cleanup['closed']}=={4165393,4165410} and all(v['absent'] for v in cleanup['closed'])
ports={19100,19101,19102,19153};listeners=[]
for proto in ['tcp','tcp6','udp','udp6']:
 for line in Path('/proc/net',proto).read_text().splitlines()[1:]:
  fields=line.split();port=int(fields[1].rsplit(':',1)[1],16)
  if port in ports and (proto.startswith('udp') or fields[3]=='0A'):listeners.append({'protocol':proto,'port':port})
assert listeners==[]
record.update({'passed':True,'owner_and_exact_children_currently_absent':True,'existing_owner_reaped_both_children':cleanup,'owned_ports_no_current_listeners':True,'checked_TCP_ports':[19100,19101,19102,19153],'checked_UDP_ports':[19153],'CA_evidence_and_manifests_preserved':True,'fixture_cleanup_only_no_app_provider_or_protected_service_actions':True})
(w/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'passed':True,'exact3PIDs_absent':True,'ownedPortsFree':True,'owner_children_waitpid_cleanup':cleanup}))
