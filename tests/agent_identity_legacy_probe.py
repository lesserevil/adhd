#!/usr/bin/env python3
"""Trace exact legacy-config guard without claiming public legacy lifecycle.

Snapshots are authored by the actual public server. Separate unit VMs load exact
artifact modules and trace :dets.open_file, with a real isolated positive control.
Only the supplied owned fixture snapshots are removed/corrupted and restored.
"""
import asyncio,hashlib,json,subprocess
from pathlib import Path
from multi_support import Fixture,arguments,scoped

async def main(args):
 if not args.hub:raise ValueError('This native exact-artifact unit probe requires --hub')
 f=Fixture(args);f.config['eventing']={'enabled':False}
 d={'schema':'adhd/legacy-retired-agent-guard-unit@1','passed':False,'artifact_sha256':hashlib.sha256(args.hub.read_bytes()).hexdigest(),'checks':[],'limitations':['Loads actual artifact modules for targeted guard unit calls; not a public legacy lifecycle or Admin create_agent fallback qualification.','Actual snapshots come from public API writes; zero guard DETS calls are contrasted with an actual isolated opener positive control.']}
 snapshot=f.root/'hub.dets.snapshot';original=None
 helper=Path(__file__).with_suffix('.exs')
 def probe(agent):
  raw=subprocess.check_output(['elixir',str(helper),str(args.hub.resolve()),str(f.root/'hub.dets'),'project-red',str(f.root/'control.dets'),agent],text=True)
  value=json.loads(raw.strip().splitlines()[-1]);assert value['positive_control_dets_calls']>0 and value['guard_dets_calls']==0
  return value
 try:
  await f.start();a=await f.agent('red-a')
  await a.call(scoped('project-red','send',recipient_id='red-b',text='Retained private unit evidence'))
  original=snapshot.read_bytes()
  for name,agent,expected in [('healthy-unused','unused-unit-agent',False),('healthy-retained','red-a',True)]:
   value=await asyncio.to_thread(probe,agent);assert value['result']=={'value':expected};d['checks'].append({'name':name,'passed':True,**value})
  snapshot.unlink()
  value=await asyncio.to_thread(probe,'unused-unit-agent');assert 'error' in value['result'];d['checks'].append({'name':'missing-snapshot','passed':True,**value})
  snapshot.write_bytes(b'corrupt-owned-unit-snapshot')
  value=await asyncio.to_thread(probe,'unused-unit-agent');assert 'error' in value['result'];d['checks'].append({'name':'corrupt-snapshot','passed':True,**value})
  d['passed']=True
 finally:
  if original is not None:snapshot.write_bytes(original)
  await f.close()
  d['harness_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();d['probe_sha256']=hashlib.sha256(helper.read_bytes()).hexdigest();args.report.write_text(json.dumps(d,indent=2)+'\n')
if __name__=='__main__':asyncio.run(main(arguments(__doc__).parse_args()))
