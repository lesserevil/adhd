import json,hashlib,os,subprocess,sys
from pathlib import Path
ROOT=Path('/home/horde/src/adhd');os.chdir(ROOT)
BASE=ROOT/'verification/acme/final-documentation-bridge';BASE.mkdir(exist_ok=False)
WORK=ROOT/'_build/acme/finaldocs01'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
template_path=ROOT/'.worktrees/contracts/_build/acme-final-image-bridge/template.json'
assert sha(template_path)=='8b7eee8690b59888715dde9792c6652fb6c58c26f8151c672e33e9b6bd395634'
template=json.loads(template_path.read_text())
for name,wanted in template['helper_sha256'].items():assert sha(name)==wanted,name
assert sha(ROOT/'.worktrees/contracts/_build/acme-final-image-bridge/prepare.py')=='a80b0fc30a41946c9484d0499af5210582ae80ed0995342a307f421c13d1dfc1'

v=json.loads((WORK/'rebuild.json').read_text());assert v['ok']is True and v['result']['passed']is True
assert sha(v['result']['artifact'])==template['original_lineage']['artifact_sha256']
assert json.loads((WORK/'receipt-update-execution.json').read_text())['actual_exit_code']==0
config=WORK/'bridge-docker-config';config.mkdir(mode=0o700);(config/'config.json').write_text('{}');(config/'config.json').chmod(0o600)
values={'<ACTUAL_FRESH_PLAN_SHA256>':sha(WORK/'retained-plan.json'),'<ACTUAL_FINALIZED_CANDIDATE_SHA256>':sha('/tmp/adhd-acme42-finaldocs01-receipt.json'),'<ACTUAL_SUCCESSFUL_REBUILD_ENVELOPE_SHA256>':sha(WORK/'rebuild.json')}
env=os.environ.copy();env['PATH']=str(ROOT/'_build/federation/native/erlang/bin')+':'+str(ROOT/'_build/federation/native/elixir/bin')+':'+env['PATH'];env['ERL_FLAGS']='+S 2:2';env['PYTHONDONTWRITEBYTECODE']='1'
for step in template['procedure']:
 if 'argv_template'not in step:continue
 if (BASE/'source-admission/manifest.json').exists():values['<ACTUAL_NEW_SOURCE_ADMISSION_SHA256>']=sha(BASE/'source-admission/manifest.json')
 argv=[values.get(x,x)for x in step['argv_template']];assert not any(x.startswith('<ACTUAL')for x in argv)
 name={'capture actual final source provenance':'source-capture','actual normal stage':'stage','strict whole context comparison':'context-compare','metadata-only compiled image capture':'compiled-capture'}[step['phase']]
 with (BASE/(name+'.stdout')).open('xb')as o,(BASE/(name+'.stderr')).open('xb')as e:r=subprocess.run(argv,cwd=ROOT,env=env,stdout=o,stderr=e)
 record={'argv':argv,'actual_exit_code':r.returncode,'stdout_sha256':sha(BASE/(name+'.stdout')),'stderr_sha256':sha(BASE/(name+'.stderr'))};(BASE/(name+'-execution.json')).write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'phase':name,'actual_exit_code':r.returncode}),flush=True)
 if r.returncode:sys.exit(r.returncode)
