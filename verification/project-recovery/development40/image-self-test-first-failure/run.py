from pathlib import Path
import os,sys,json,hashlib,subprocess
work=Path(__file__).resolve().parent
plan=json.loads((work/'plan.json').read_text())
assert hashlib.sha256((work/'plan.json').read_bytes()).hexdigest()==sys.argv[1]
assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==plan['driver_sha256']
sys.dont_write_bytecode=True;sys.path.insert(0,str(work/'frozen/tests'))
from image_qualification_inputs import verify_frozen_inputs
from container_fixture import OwnedImage
verify_frozen_inputs(work/'frozen',plan['inputs'])
for name,digest in plan['bindings'].items():assert hashlib.sha256((work/name).read_bytes()).hexdigest()==digest
with (work/'execution.started').open('x') as marker:
 marker.write(sys.argv[1]);marker.flush();os.fsync(marker.fileno())
fd=os.open(work,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
report={'passed':False,'image_config_identity':plan['image'],'rows':[]}
probe=OwnedImage(plan['image'],work/'image-manifest.json',work)
try:
 probe.verify()
 output=probe.probe('elixir','/app/hub.exs','--litai-test')
 (work/'self-tests.stdout').write_bytes(output)
 result=json.loads(output);assert result['summary']=={'failed':0,'passed':18,'skipped':0,'total':18}
 (work/'self-tests.json').write_text(json.dumps(result,indent=2)+'\n')
 report['rows'].append({'name':'packaged-self-tests','passed':True,'checks':18,'runtime':probe.identity()})
 (work/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',ERL_FLAGS='+S 2:2')
 with (work/'ownership.log').open('wb') as log:
  result=subprocess.run(plan['ownership_argv'],cwd=work/'runtime',env=env,stdout=log,stderr=subprocess.STDOUT)
 assert result.returncode==0
 value=json.loads((work/'ownership.json').read_text());assert value['passed'] is True and len(value['checks'])==3
 runtime=value['runtime'];assert runtime['image_config_identity']==plan['image'] and runtime['payload_verified']
 for event in runtime['container_lifecycle']:
  target=event.get('container_id')
  if target:assert OwnedImage.probe_absence(subprocess.run(['docker','inspect',target],capture_output=True),target)
 for event in runtime['payload_probe_lifecycle']:
  for target in (event.get('name'),event.get('container_id')):
   if target:assert OwnedImage.probe_absence(subprocess.run(['docker','inspect',target],capture_output=True),target)
 verify_frozen_inputs(work/'frozen',plan['inputs'])
 report['rows'].append({'name':'ownership-fault-recovery','passed':True,'checks':3})
 report['passed']=True
finally:
 report['self_test_probe_lifecycle']=probe.probe_events
 (work/'result.json').write_text(json.dumps(report,indent=2)+'\n')
